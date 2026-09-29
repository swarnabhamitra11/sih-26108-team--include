"""Main FastAPI application for Standards Navigator.

Exposes:
- GET  /api/health
- GET  /api/stats
- POST /api/recommend
- POST /api/check-citation
- POST /api/reviews
- GET  /api/reviews
"""

import logging
from typing import Optional, List, Dict, Any, Tuple
from contextlib import asynccontextmanager, contextmanager

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import psycopg2
from psycopg2.pool import ThreadedConnectionPool
from pgvector.psycopg2 import register_vector
import httpx

from app import config
from app.services.retrieval import search_standards
from app.services.citation import check_citation_with_db
from app.services.guard import guard_text
from app.services.designation import parse_designation

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("standards_navigator")

# Connection pool singleton
_pool: Optional[ThreadedConnectionPool] = None


def get_pool() -> ThreadedConnectionPool:
    global _pool
    if _pool is None:
        _pool = ThreadedConnectionPool(
            minconn=1,
            maxconn=10,
            host=config.DB_HOST,
            port=config.DB_PORT,
            dbname=config.DB_NAME,
            user=config.DB_USER,
            password=config.DB_PASSWORD,
        )
    return _pool


@contextmanager
def get_db_conn():
    pool = get_pool()
    conn = pool.getconn()
    register_vector(conn)
    try:
        yield conn
    finally:
        pool.putconn(conn)


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_pool()
    logger.info("Database connection pool initialized.")
    yield
    global _pool
    if _pool:
        _pool.closeall()
        _pool = None
        logger.info("Database connection pool closed.")


app = FastAPI(title="Standards Navigator API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def detect_language(text: str) -> str:
    """Detect language by Unicode block."""
    for ch in text:
        cp = ord(ch)
        if 0x0900 <= cp <= 0x097F:
            return "hi"
        if 0x0980 <= cp <= 0x09FF:
            return "bn"
    return "en"


def translate_query_if_needed(query_text: str, lang: str) -> Tuple[str, List[str]]:
    """Translate non-English query using OpenAI-compatible LLM if API key exists."""
    warnings: List[str] = []
    if lang == "en":
        return query_text, warnings

    if not config.LLM_API_KEY:
        warnings.append("Non-English query: translation unavailable, results may be poor.")
        return query_text, warnings

    try:
        headers = {
            "Authorization": f"Bearer {config.LLM_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": config.LLM_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a translator. Translate the user's standard/engineering query into English. Return ONLY the English translation without quotes or explanations.",
                },
                {"role": "user", "content": query_text},
            ],
            "temperature": 0.0,
        }
        with httpx.Client(timeout=5.0) as client:
            resp = client.post(
                f"{config.LLM_BASE_URL.rstrip('/')}/chat/completions",
                headers=headers,
                json=payload,
            )
            if resp.status_code == 200:
                data = resp.json()
                translated = data["choices"][0]["message"]["content"].strip()
                return translated, warnings
    except Exception as exc:
        logger.warning("LLM translation failed: %s", exc)

    warnings.append("Non-English query: translation unavailable, results may be poor.")
    return query_text, warnings


def generate_why_it_applies(query: str, standard: Dict[str, Any]) -> Optional[str]:
    """Generate optional 1-sentence explanation strictly from title and scope."""
    if not config.LLM_API_KEY:
        return None

    try:
        headers = {
            "Authorization": f"Bearer {config.LLM_API_KEY}",
            "Content-Type": "application/json",
        }
        prompt = (
            f"Query: {query}\n"
            f"Standard Title: {standard.get('title')}\n"
            f"Standard Scope: {standard.get('scope_summary')}\n"
            "In one short factual sentence, explain why this standard applies to the query using ONLY the provided title and scope. Never invent facts or standards numbers."
        )
        payload = {
            "model": config.LLM_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
            "max_tokens": 60,
        }
        with httpx.Client(timeout=5.0) as client:
            resp = client.post(
                f"{config.LLM_BASE_URL.rstrip('/')}/chat/completions",
                headers=headers,
                json=payload,
            )
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        logger.warning("LLM why_it_applies generation failed: %s", exc)

    return None


# Request / Response Schemas
class RecommendRequest(BaseModel):
    query: str = Field(..., description="Natural language search query")
    top_k: int = Field(5, ge=1, le=20)


class CitationRequest(BaseModel):
    citation: str = Field(..., description="IS standard citation e.g. 'IS 269:2015'")


class ReviewRequest(BaseModel):
    query_id: int
    standard_id: int
    decision: str
    notes: Optional[str] = None
    confidence: Optional[float] = 0.0


@app.get("/api/health")
def health():
    """Health check verifying database connection."""
    try:
        with get_db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database check failed: {e}",
        )


@app.get("/api/stats")
def stats():
    """Return database counts: total standards, verified count, breakdown by product group."""
    try:
        with get_db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM standards")
                total = cur.fetchone()[0]

                cur.execute("SELECT COUNT(*) FROM standards WHERE verification_status = 'verified'")
                verified = cur.fetchone()[0]

                cur.execute("""
                    SELECT COALESCE(pg.name, 'Uncategorized'), COUNT(*)
                    FROM standards s
                    LEFT JOIN product_group pg ON s.product_group = pg.id
                    GROUP BY pg.name
                    ORDER BY pg.name
                """)
                by_pg = {r[0]: r[1] for r in cur.fetchall()}

        return {
            "total_standards": total,
            "verified_count": verified,
            "by_product_group": by_pg,
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database query failed: {e}",
        )


@app.post("/api/recommend")
def recommend(req: RecommendRequest):
    """Recommend standards for a natural language user query."""
    clean_q = req.query.strip()
    if not clean_q:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Query cannot be empty or whitespace.",
        )

    lang = detect_language(clean_q)
    search_q, warnings = translate_query_if_needed(clean_q, lang)

    try:
        with get_db_conn() as conn:
            search_res = search_standards(conn, search_q, top_k=req.top_k)
            results = search_res["results"]
            is_abstain = search_res["abstain"]

            msg = ""
            if is_abstain:
                msg = "No confident match in the current database. Try describing the product, material or standard type."

            # Fetch all known (is_number, part) keys from DB for hallucination guard
            with conn.cursor() as cur:
                cur.execute("SELECT is_number, part FROM standards")
                known_keys = set((r[0], r[1]) for r in cur.fetchall())

            # Guard message
            if msg:
                clean_msg, _ = guard_text(msg, known_keys)
                msg = clean_msg

            # Enrich with optional why_it_applies
            for r in results:
                why = generate_why_it_applies(clean_q, r)
                if why:
                    clean_why, _ = guard_text(why, known_keys)
                    r["why_it_applies"] = clean_why

            # Log query to DB
            result_ids = [r["id"] for r in results]
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO queries (query_text, language, result_ids)
                    VALUES (%s, %s, %s)
                    RETURNING id
                    """,
                    (clean_q, lang, result_ids),
                )
                query_id = cur.fetchone()[0]
            conn.commit()

        return {
            "query_id": query_id,
            "language": lang,
            "results": results,
            "abstain": is_abstain,
            "message": msg,
            "warnings": warnings,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Recommend error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {e}",
        )


@app.post("/api/check-citation")
def check_citation(req: CitationRequest):
    """Check an IS designation against the database."""
    citation_text = req.citation.strip()
    if not citation_text:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Citation cannot be empty or whitespace.",
        )

    try:
        with get_db_conn() as conn:
            return check_citation_with_db(citation_text, conn)
    except Exception as e:
        logger.error("Check citation error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Citation check failed: {e}",
        )


@app.post("/api/reviews")
def create_review(req: ReviewRequest):
    """Submit a human review for a search result."""
    dec = req.decision.strip().lower()
    if dec not in ("accept", "reject", "flag"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Decision must be one of: 'accept', 'reject', 'flag'.",
        )

    try:
        with get_db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM queries WHERE id = %s", (req.query_id,))
                if not cur.fetchone():
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Query {req.query_id} does not exist.",
                    )

                cur.execute("SELECT 1 FROM standards WHERE id = %s", (req.standard_id,))
                if not cur.fetchone():
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Standard {req.standard_id} does not exist.",
                    )

                cur.execute(
                    """
                    INSERT INTO reviews (query_id, selected_standard_id, confidence, decision, notes)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id, created_at
                    """,
                    (
                        req.query_id,
                        req.standard_id,
                        req.confidence or 0.0,
                        dec,
                        req.notes,
                    ),
                )
                review_id, created_at = cur.fetchone()
            conn.commit()

        return {
            "id": review_id,
            "query_id": req.query_id,
            "standard_id": req.standard_id,
            "decision": dec,
            "notes": req.notes,
            "confidence": req.confidence,
            "created_at": created_at.isoformat() if created_at else None,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Review creation error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Creating review failed: {e}",
        )


@app.get("/api/reviews")
def list_reviews():
    """List the 50 most recent reviews."""
    try:
        with get_db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT r.id, r.query_id, q.query_text, r.selected_standard_id,
                           s.is_number, s.part, s.title, r.confidence, r.decision,
                           r.notes, r.created_at
                    FROM reviews r
                    JOIN standards s ON r.selected_standard_id = s.id
                    JOIN queries q ON r.query_id = q.id
                    ORDER BY r.created_at DESC
                    LIMIT 50
                    """
                )
                rows = cur.fetchall()

        reviews_list = [
            {
                "id": r[0],
                "query_id": r[1],
                "query_text": r[2],
                "standard_id": r[3],
                "is_number": r[4],
                "part": r[5],
                "standard_title": r[6],
                "confidence": round(float(r[7]), 4) if r[7] is not None else 0.0,
                "decision": r[8],
                "notes": r[9],
                "created_at": r[10].isoformat() if r[10] else None,
            }
            for r in rows
        ]

        return {"reviews": reviews_list}
    except Exception as e:
        logger.error("List reviews error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Fetching reviews failed: {e}",
        )
