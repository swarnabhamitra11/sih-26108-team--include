"""Retrieval service for Standards Navigator.

Implements:
- Vector search (top 20 by cosine similarity)
- Full-text search (top 20 by tsvector)
- Real cosine similarity calculation for all candidate hits (including FTS-only hits)
- Pure Reciprocal Rank Fusion (RRF)
- Cosine-weighted rank fusion ensuring high-cosine results are not demoted by FTS noise
- Pure status reranking (favouring current over superseded/withdrawn within 10%)
- Pure abstain logic with multi-hit FTS guard
- Enriched standard metadata assembly
"""

import re
from typing import List, Dict, Tuple, Any, Optional, Union
from app import config
from app.services.embedding import embed_query


def compute_rrf(
    vector_ids: List[int],
    fts_ids: List[int],
    k: int = 60,
) -> List[Tuple[int, float]]:
    """Compute Reciprocal Rank Fusion score for items from vector and FTS ranks.

    Args:
        vector_ids: Ranked standard IDs from vector search (index 0 = rank 1).
        fts_ids: Ranked standard IDs from full-text search (index 0 = rank 1).
        k: RRF constant (default 60).

    Returns:
        List of (standard_id, rrf_score) sorted descending by rrf_score.
    """
    scores: Dict[int, float] = {}

    for rank, sid in enumerate(vector_ids, start=1):
        scores[sid] = scores.get(sid, 0.0) + (1.0 / (k + rank))

    for rank, sid in enumerate(fts_ids, start=1):
        scores[sid] = scores.get(sid, 0.0) + (1.0 / (k + rank))

    sorted_results = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return sorted_results


def rerank_by_status(
    scored_items: List[Tuple[int, float]],
    statuses: Dict[int, str],
) -> List[Tuple[int, float]]:
    """Rerank items so current standards rank above superseded/withdrawn ones when within 10%.

    If standard is not current, its effective score for ordering is multiplied by 0.90.
    """
    def sort_key(item: Tuple[int, float]) -> float:
        sid, score = item
        status = statuses.get(sid, "current").lower()
        if status != "current":
            return score * 0.90
        return score

    return sorted(scored_items, key=sort_key, reverse=True)


def rerank_candidates(
    rrf_scored: List[Tuple[int, float]],
    statuses: Dict[int, str],
    cosine_map: Dict[int, float],
) -> List[Tuple[int, float]]:
    """Final ordering: RRF combined with cosine similarity and status tiebreak.

    Ensures a result with much higher cosine is not ranked below a low-cosine one
    purely by FTS noise, while maintaining the status tiebreak rule.
    """
    def final_score(item: Tuple[int, float]) -> float:
        sid, rrf = item
        cos = max(0.0, min(1.0, cosine_map.get(sid, 0.0)))
        # Weight RRF with quadratic cosine boost so high semantic similarity dominates FTS noise
        weighted = rrf * (1.0 + 3.0 * (cos ** 2))
        status = statuses.get(sid, "current").lower()
        if status != "current":
            weighted *= 0.90
        return weighted

    return sorted(rrf_scored, key=final_score, reverse=True)


def should_abstain(
    best_cosine: float,
    fts_count: Optional[Union[int, bool]] = None,
    threshold: float = 0.55,
    has_fts_hit: Optional[bool] = None,
) -> bool:
    """Pure abstain rule:

    Abstain if best_cosine is below threshold AND the query has fewer than 2 full-text matching results.
    A full-text hit alone does NOT prevent abstaining when best cosine is below threshold.
    """
    if fts_count is not None:
        if isinstance(fts_count, bool):
            num_fts = 2 if fts_count else 0
        else:
            num_fts = int(fts_count)
    elif has_fts_hit is not None:
        num_fts = 2 if has_fts_hit else 0
    else:
        num_fts = 0

    return (best_cosine < threshold) and (num_fts < 2)


def run_fts_query(cur, query_text: str, limit: int = 20) -> List[int]:
    """Execute full-text search using websearch_to_tsquery with OR-fallback."""
    clean_q = query_text.strip()
    if not clean_q:
        return []

    # 1. websearch_to_tsquery
    cur.execute(
        """
        SELECT id
        FROM standards
        WHERE tsv @@ websearch_to_tsquery('english', %s)
        ORDER BY ts_rank_cd(tsv, websearch_to_tsquery('english', %s)) DESC
        LIMIT %s
        """,
        (clean_q, clean_q, limit),
    )
    rows = cur.fetchall()
    if rows:
        return [r[0] for r in rows]

    # 2. Fallback: words OR-ed together
    words = re.findall(r"[A-Za-z0-9]+", clean_q)
    if not words:
        return []

    or_query = " | ".join(words)
    try:
        cur.execute(
            """
            SELECT id
            FROM standards
            WHERE tsv @@ to_tsquery('english', %s)
            ORDER BY ts_rank_cd(tsv, to_tsquery('english', %s)) DESC
            LIMIT %s
            """,
            (or_query, or_query, limit),
        )
        rows = cur.fetchall()
        return [r[0] for r in rows]
    except Exception:
        return []


def run_vector_query(cur, query_vector: List[float], limit: int = 20) -> List[Tuple[int, float]]:
    """Execute vector cosine similarity search."""
    cur.execute(
        """
        SELECT id, 1 - (embedding <=> %s::vector) AS cosine_sim
        FROM standards
        WHERE embedding IS NOT NULL
        ORDER BY embedding <=> %s::vector ASC
        LIMIT %s
        """,
        (query_vector, query_vector, limit),
    )
    rows = cur.fetchall()
    return [(r[0], max(0.0, min(1.0, float(r[1])))) for r in rows]


def fetch_enriched_standard(cur, standard_id: int, confidence: float) -> Dict[str, Any]:
    """Fetch complete metadata for a standard to render rich result card."""
    cur.execute(
        """
        SELECT s.id, s.is_number, s.part, s.title, s.scope_text,
               pg.name AS product_group, s.category, s.status,
               s.source_url, s.verification_status, s.superseded_by_id
        FROM standards s
        LEFT JOIN product_group pg ON s.product_group = pg.id
        WHERE s.id = %s
        """,
        (standard_id,),
    )
    s_row = cur.fetchone()
    if not s_row:
        return {}

    (
        sid, is_num, part, title, scope_text, pg_name,
        category, status, source_url, ver_status, sup_id
    ) = s_row

    # Latest edition and amendment count
    cur.execute(
        """
        SELECT id, edition_year
        FROM standard_editions
        WHERE standard_id = %s
        ORDER BY is_latest DESC, edition_year DESC
        LIMIT 1
        """,
        (standard_id,),
    )
    ed_row = cur.fetchone()
    latest_edition_year = ed_row[1] if ed_row else None
    amendment_count = 0
    if ed_row:
        cur.execute(
            "SELECT COUNT(*) FROM standard_amendments WHERE edition_id = %s",
            (ed_row[0],),
        )
        amendment_count = cur.fetchone()[0]

    # Superseded by info
    superseded_by = None
    if sup_id:
        cur.execute(
            "SELECT is_number, part, title FROM standards WHERE id = %s",
            (sup_id,),
        )
        sup_row = cur.fetchone()
        if sup_row:
            superseded_by = {
                "is_number": sup_row[0],
                "part": sup_row[1],
                "title": sup_row[2],
            }

    # Allied standards (both directions from standard_relations)
    cur.execute(
        """
        SELECT sr.relation_type, s.is_number, s.part, s.title
        FROM standard_relations sr
        JOIN standards s ON sr.to_standard_id = s.id
        WHERE sr.from_standard_id = %s
        UNION
        SELECT sr.relation_type, s.is_number, s.part, s.title
        FROM standard_relations sr
        JOIN standards s ON sr.from_standard_id = s.id
        WHERE sr.to_standard_id = %s
        """,
        (standard_id, standard_id),
    )
    allied_rows = cur.fetchall()
    allied_standards = [
        {
            "relation_type": r[0] or "allied",
            "is_number": r[1],
            "part": r[2],
            "title": r[3],
        }
        for r in allied_rows
    ]

    # Certification rules
    cur.execute(
        """
        SELECT status, order_reference, source_note
        FROM certification_rules
        WHERE standard_id = %s
        LIMIT 1
        """,
        (standard_id,),
    )
    cert_row = cur.fetchone()
    if cert_row:
        certification = {
            "status": str(cert_row[0]),
            "order_reference": cert_row[1],
            "source_note": cert_row[2],
        }
    else:
        certification = {
            "status": "needs_review",
            "note": "No QCO data loaded",
        }

    return {
        "id": sid,
        "is_number": is_num,
        "part": part,
        "title": title,
        "scope_summary": scope_text,
        "product_group": pg_name or "General",
        "category": category,
        "status": status,
        "latest_edition_year": latest_edition_year,
        "amendment_count": amendment_count,
        "superseded_by": superseded_by,
        "allied_standards": allied_standards,
        "certification": certification,
        "source_url": source_url,
        "verification_status": ver_status,
        "confidence": round(confidence, 4),
    }


def search_standards(
    conn,
    query_text: str,
    top_k: int = 5,
    threshold: Optional[float] = None,
) -> Dict[str, Any]:
    """Execute hybrid search pipeline with real cosine similarity and abstain logic."""
    if threshold is None:
        threshold = config.CONFIDENCE_THRESHOLD

    q_clean = query_text.strip()
    if not q_clean:
        return {"results": [], "abstain": True, "best_confidence": 0.0}

    with conn.cursor() as cur:
        # 1. Full-text search
        fts_ids = run_fts_query(cur, q_clean, limit=20)

        # 2. Vector search
        q_vec = embed_query(q_clean)
        vec_matches = run_vector_query(cur, q_vec, limit=20)
        vec_ids = [m[0] for m in vec_matches]
        sim_map = {m[0]: m[1] for m in vec_matches}

        # Compute real cosine similarity for FTS-only hits with a single SELECT
        missing_fts_ids = [fid for fid in fts_ids if fid not in sim_map]
        if missing_fts_ids:
            cur.execute(
                """
                SELECT id, 1 - (embedding <=> %s::vector) AS cosine_sim
                FROM standards
                WHERE id = ANY(%s) AND embedding IS NOT NULL
                """,
                (q_vec, missing_fts_ids),
            )
            for fid, sim in cur.fetchall():
                sim_map[fid] = max(0.0, min(1.0, float(sim)))

        # 3. Reciprocal Rank Fusion
        rrf_ranked = compute_rrf(vec_ids, fts_ids, k=config.RRF_K)

        # 4. Fetch statuses for status-based reranking
        if rrf_ranked:
            cur.execute(
                "SELECT id, status FROM standards WHERE id = ANY(%s)",
                ([item[0] for item in rrf_ranked],),
            )
            status_map = {r[0]: r[1] for r in cur.fetchall()}
        else:
            status_map = {}

        # 5. Final order: RRF with status tiebreak and cosine noise protection
        reranked = rerank_candidates(rrf_ranked, status_map, sim_map)
        selected_ids = [item[0] for item in reranked[:top_k]]

        # 6. Fetch enriched standard details with real clipped cosine confidence
        results: List[Dict[str, Any]] = []
        for sid in selected_ids:
            conf = max(0.0, min(1.0, float(sim_map.get(sid, 0.0))))
            enriched = fetch_enriched_standard(cur, sid, conf)
            if enriched:
                results.append(enriched)

        # 7. Best confidence is the max cosine over displayed results
        best_cosine = max([r["confidence"] for r in results]) if results else (max(sim_map.values()) if sim_map else 0.0)

        # 8. Check Abstain Rule:
        # A full-text hit alone does NOT prevent abstaining when best cosine is below threshold
        # AND the query has fewer than 2 full-text matching results.
        if should_abstain(best_cosine, len(fts_ids), threshold):
            return {
                "results": [],
                "abstain": True,
                "best_confidence": round(best_cosine, 4),
            }

        return {
            "results": results,
            "abstain": False,
            "best_confidence": round(best_cosine, 4),
        }
