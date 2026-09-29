import re
import csv
import os
import sys
import argparse
import hashlib
import math
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Set, Tuple, Optional

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services.designation import parse_designation
from app.services.embedding import build_embedding_text

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SEED_DIR = Path(__file__).resolve().parent.parent / "data" / "seed"

EXPECTED_FILES = {
    "standards": "standards.csv",
    "standard_editions": "standard_editions.csv",
    "standard_amendments": "standard_amendments.csv",
    "standard_relations": "standard_relations.csv",
}

OPTIONAL_FILES = {
    "certification_rules": "certification_rules.csv",
    "benchmark_rows": "benchmark_rows.csv",
    "benchmark_expected": "benchmark_expected.csv",
}

ENUMS = {
    "status": {"current", "superseded", "withdrawn"},
    "relation_type": {
        "normative_ref",
        "test_method",
        "terminology",
        "safety",
        "installation",
        "product",
    },
    "cert_status": {"mandatory", "voluntary", "needs_review"},
    "benchmark_kind": {"normal", "abstain"},
    "benchmark_role": {"primary", "allied"},
    "verification_status": {"entered", "reviewed", "verified"},
    "product_group": {"Cement", "Steel", "Cables", "Pipes", "Pumps"},
}

# ---------------------------------------------------------------------------
# Global Embedding Model Singleton & Helper
# ---------------------------------------------------------------------------
_EMBEDDING_MODEL: Optional[Any] = None
_EMBEDDING_MODEL_TYPE: Optional[str] = None
_EMBEDDING_INITIALIZED: bool = False


def init_embedding_model() -> None:
    """Initialize the embedding model singleton once before processing rows.
    Prints a loud warning if neither fastembed nor sentence_transformers is available.
    """
    global _EMBEDDING_MODEL, _EMBEDDING_MODEL_TYPE, _EMBEDDING_INITIALIZED
    if _EMBEDDING_INITIALIZED:
        return

    _EMBEDDING_INITIALIZED = True

    try:
        from fastembed import TextEmbedding
        _EMBEDDING_MODEL = TextEmbedding()
        _EMBEDDING_MODEL_TYPE = "fastembed"
        return
    except Exception:
        pass

    try:
        from sentence_transformers import SentenceTransformer
        _EMBEDDING_MODEL = SentenceTransformer("all-MiniLM-L6-v2")
        _EMBEDDING_MODEL_TYPE = "sentence_transformers"
        return
    except Exception:
        pass

    print(
        "[WARNING] No real embedding model available - falling back to a non-semantic placeholder vector. "
        "Retrieval quality will be meaningless until this is fixed."
    )
    _EMBEDDING_MODEL = None
    _EMBEDDING_MODEL_TYPE = "fallback"


def compute_embedding(text: str, dim: int, model: Optional[Any] = None) -> List[float]:
    """Compute unit-normalized embedding of dimension dim for given text using the cached model.
    Falls back deterministically to SHA-256 seed if no neural model is available.
    """
    if not text:
        return [0.0] * dim

    actual_model = model if model is not None else _EMBEDDING_MODEL

    if actual_model is not None and _EMBEDDING_MODEL_TYPE == "fastembed":
        try:
            embeddings = list(actual_model.embed([text]))
            vec = list(embeddings[0])
            if len(vec) == dim:
                return vec
        except Exception:
            pass

    if actual_model is not None and _EMBEDDING_MODEL_TYPE == "sentence_transformers":
        try:
            vec = actual_model.encode(text).tolist()
            if len(vec) == dim:
                return vec
        except Exception:
            pass

    # Deterministic fallback: Generate dim floats seeded by SHA-256 of text
    vec: List[float] = []
    chunk_index = 0
    while len(vec) < dim:
        seed_bytes = f"{text}:{chunk_index}".encode("utf-8")
        h = hashlib.sha256(seed_bytes).digest()
        for i in range(0, len(h), 4):
            if len(vec) >= dim:
                break
            val = int.from_bytes(h[i:i+4], byteorder="big", signed=True) / 2147483648.0
            vec.append(val)
        chunk_index += 1

    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [round(x / norm, 6) for x in vec]

# ---------------------------------------------------------------------------
# Helper functions for CSV handling & boolean parsing
# ---------------------------------------------------------------------------

def _load_csv(file_path: Path) -> List[Dict[str, str]]:
    """Read a CSV file with utf-8-sig and return a list of rows as dictionaries."""
    with file_path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        return list(reader)


def load_seeds(seed_dir: Path = SEED_DIR) -> Dict[str, List[Dict[str, str]]]:
    """Load all expected (and any present optional) seed CSVs from seed_dir."""
    seeds: Dict[str, List[Dict[str, str]]] = {}
    for table, filename in EXPECTED_FILES.items():
        path = seed_dir / filename
        if not path.is_file():
            raise FileNotFoundError(
                f"Expected seed file '{filename}' for table '{table}' not found in {seed_dir}"
            )
        seeds[table] = _load_csv(path)

    for table, filename in OPTIONAL_FILES.items():
        path = seed_dir / filename
        if path.is_file():
            seeds[table] = _load_csv(path)

    return seeds


def _parse_bool(val: str) -> Optional[bool]:
    """Parse boolean values accepting TRUE/true/1 and FALSE/false/0.
    Returns None if invalid or empty.
    """
    val_clean = val.strip().upper()
    if val_clean in {"TRUE", "1"}:
        return True
    if val_clean in {"FALSE", "0"}:
        return False
    return None

# ---------------------------------------------------------------------------
# Validation logic
# ---------------------------------------------------------------------------

def _validate_standards(rows: List[Dict[str, str]]) -> Tuple[List[str], Set[Tuple[str, str]], Dict[Tuple[str, str], str]]:
    errors: List[str] = []
    seen: Set[Tuple[str, str]] = set()
    verif_status_map: Dict[Tuple[str, str], str] = {}

    for i, row in enumerate(rows, start=2):  # spreadsheet row numbers (header=row 1)
        is_number = row.get("is_number", "").strip()
        part = row.get("part", "").strip()
        title = row.get("title", "").strip()
        product_group = row.get("product_group", "").strip()
        scope = row.get("scope_text", "").strip()
        keywords = row.get("keywords", "").strip()
        status = row.get("status", "").strip()
        verif_status = row.get("verification_status", "").strip() or "entered"
        source_url = row.get("source_url", "").strip()

        # Required fields
        if not is_number:
            errors.append(f"standards.csv row {i}: missing required field 'is_number'.")
        if not title:
            errors.append(f"standards.csv row {i}: missing required field 'title'.")
        if not scope:
            errors.append(f"standards.csv row {i}: missing required field 'scope_text'.")
        if not source_url:
            errors.append(f"standards.csv row {i}: missing required field 'source_url'.")

        # Validate product_group
        if product_group and product_group not in ENUMS["product_group"]:
            errors.append(
                f"standards.csv row {i}: invalid product_group '{product_group}'. Allowed: {sorted(ENUMS['product_group'])}."
            )

        # Validate is_number format using parse_designation
        if is_number:
            desig = parse_designation(is_number)
            if desig.year is not None:
                errors.append(f"standards.csv row {i}: 'is_number' '{is_number}' contains a year ({desig.year}).")
            if desig.part is not None or re.search(r"\bpart\b", is_number, re.IGNORECASE):
                errors.append(f"standards.csv row {i}: 'is_number' '{is_number}' contains 'Part'.")

        # Validate part format (must be bare label like '1' or '2')
        if part and not part.isalnum():
            errors.append(f"standards.csv row {i}: 'part' '{part}' must be a bare label (e.g. '1').")

        # Enum checks
        if status and status not in ENUMS["status"]:
            errors.append(
                f"standards.csv row {i}: invalid status '{status}'. Allowed: {sorted(ENUMS['status'])}."
            )
        if verif_status and verif_status not in ENUMS["verification_status"]:
            errors.append(
                f"standards.csv row {i}: invalid verification_status '{verif_status}'. Allowed: {sorted(ENUMS['verification_status'])}."
            )

        # Duplicate (is_number, part)
        std_key = (is_number, part)
        if std_key in seen:
            errors.append(
                f"standards.csv row {i}: duplicate standard with is_number='{is_number}' and part='{part}'."
            )
        else:
            seen.add(std_key)
            verif_status_map[std_key] = verif_status

        # Warnings
        if scope and len(scope) > 600:
            print(f"[WARNING] standards.csv row {i}: scope_text exceeds 600 characters ({len(scope)} chars).")
        if keywords:
            kw_list = [k.strip() for k in keywords.split(",") if k.strip()]
            if len(kw_list) < 5:
                print(f"[WARNING] standards.csv row {i}: fewer than 5 keywords ({len(kw_list)} found).")

    # Second pass for superseded logic cross-validation
    for i, row in enumerate(rows, start=2):
        status = row.get("status", "").strip()
        superseded_by_is = row.get("superseded_by_is_number", "").strip()
        superseded_by_part = row.get("superseded_by_part", "").strip()

        if status == "superseded":
            if not superseded_by_is:
                errors.append(
                    f"standards.csv row {i}: status is 'superseded' but 'superseded_by_is_number' is empty."
                )
            else:
                target_key = (superseded_by_is, superseded_by_part)
                if target_key not in seen:
                    errors.append(
                        f"standards.csv row {i}: superseded_by target '{superseded_by_is}' (part '{superseded_by_part}') does not exist in standards.csv."
                    )
        else:
            if superseded_by_is or superseded_by_part:
                errors.append(
                    f"standards.csv row {i}: 'superseded_by_is_number' or 'superseded_by_part' is set, but status is not 'superseded' (status='{status}')."
                )

    return errors, seen, verif_status_map


def _validate_standard_editions(
    rows: List[Dict[str, str]], valid_standards: Set[Tuple[str, str]]
) -> Tuple[List[str], Set[Tuple[str, str, str]]]:
    errors: List[str] = []
    seen_editions: Set[Tuple[str, str, str]] = set()
    editions_by_standard: Dict[Tuple[str, str], List[Tuple[int, Optional[bool]]]] = {}
    max_year = datetime.now().year + 1

    for i, row in enumerate(rows, start=2):
        is_number = row.get("is_number", "").strip()
        part = row.get("part", "").strip()
        edition_year = row.get("edition_year", "").strip()
        is_latest_raw = row.get("is_latest", "").strip()

        if not is_number:
            errors.append(f"standard_editions.csv row {i}: missing required field 'is_number'.")
        if not edition_year:
            errors.append(f"standard_editions.csv row {i}: missing required field 'edition_year'.")

        std_key = (is_number, part)
        if is_number and std_key not in valid_standards:
            errors.append(
                f"standard_editions.csv row {i}: standard (is_number='{is_number}', part='{part}') does not exist in standards.csv."
            )

        # Validate year (1900 to next year)
        if edition_year:
            if not edition_year.isdigit() or not (1900 <= int(edition_year) <= max_year):
                errors.append(
                    f"standard_editions.csv row {i}: 'edition_year' must be between 1900 and {max_year}, got '{edition_year}'."
                )

        # Validate boolean is_latest
        parsed_latest = _parse_bool(is_latest_raw)
        if parsed_latest is None:
            errors.append(
                f"standard_editions.csv row {i}: invalid boolean for 'is_latest': '{is_latest_raw}'. Must be TRUE/true/1 or FALSE/false/0."
            )

        # Check duplicate edition
        ed_key = (is_number, part, edition_year)
        if ed_key in seen_editions:
            errors.append(
                f"standard_editions.csv row {i}: duplicate edition for is_number='{is_number}', part='{part}', edition_year='{edition_year}'."
            )
        else:
            seen_editions.add(ed_key)

        editions_by_standard.setdefault(std_key, []).append((i, parsed_latest))

    # Verify is_latest rules per standard: at most one TRUE; warning if none TRUE
    for std_key, ed_list in editions_by_standard.items():
        true_rows = [row_idx for row_idx, latest in ed_list if latest is True]
        if len(true_rows) > 1:
            errors.append(
                f"standard_editions.csv: multiple editions marked is_latest=TRUE for standard {std_key} on rows {true_rows}."
            )
        elif len(true_rows) == 0:
            print(
                f"[WARNING] standard_editions.csv: standard {std_key} has {len(ed_list)} edition(s) but none marked is_latest=TRUE."
            )

    return errors, seen_editions


def _validate_standard_amendments(
    rows: List[Dict[str, str]], valid_editions: Set[Tuple[str, str, str]]
) -> List[str]:
    errors: List[str] = []
    seen: Set[Tuple[str, str, str, str]] = set()
    max_year = datetime.now().year + 1

    for i, row in enumerate(rows, start=2):
        is_number = row.get("is_number", "").strip()
        part = row.get("part", "").strip()
        edition_year = row.get("edition_year", "").strip()
        amendment_no = row.get("amendment_no", "").strip()
        year = row.get("year", "").strip()

        if not is_number:
            errors.append(f"standard_amendments.csv row {i}: missing required field 'is_number'.")
        if not edition_year:
            errors.append(f"standard_amendments.csv row {i}: missing required field 'edition_year'.")
        if not amendment_no:
            errors.append(f"standard_amendments.csv row {i}: missing required field 'amendment_no'.")

        ed_key = (is_number, part, edition_year)
        if is_number and edition_year and ed_key not in valid_editions:
            errors.append(
                f"standard_amendments.csv row {i}: edition (is_number='{is_number}', part='{part}', edition_year='{edition_year}') does not exist in standard_editions.csv."
            )

        if amendment_no and not amendment_no.isdigit():
            errors.append(
                f"standard_amendments.csv row {i}: 'amendment_no' must be an integer, got '{amendment_no}'."
            )

        if year:
            if not year.isdigit() or not (1900 <= int(year) <= max_year):
                errors.append(
                    f"standard_amendments.csv row {i}: 'year' must be between 1900 and {max_year}, got '{year}'."
                )

        key = (is_number, part, edition_year, amendment_no)
        if key in seen:
            errors.append(
                f"standard_amendments.csv row {i}: duplicate amendment {amendment_no} for standard {is_number} part '{part}' edition {edition_year}."
            )
        else:
            seen.add(key)

    return errors


def _validate_standard_relations(
    rows: List[Dict[str, str]], valid_standards: Set[Tuple[str, str]]
) -> List[str]:
    errors: List[str] = []
    seen: Set[Tuple[str, str, str, str, str]] = set()

    for i, row in enumerate(rows, start=2):
        from_is = row.get("from_is_number", "").strip()
        from_part = row.get("from_part", "").strip()
        to_is = row.get("to_is_number", "").strip()
        to_part = row.get("to_part", "").strip()
        rel_type = row.get("relation_type", "").strip()

        if not from_is:
            errors.append(f"standard_relations.csv row {i}: missing required field 'from_is_number'.")
        if not to_is:
            errors.append(f"standard_relations.csv row {i}: missing required field 'to_is_number'.")

        from_key = (from_is, from_part)
        to_key = (to_is, to_part)

        # Relation cannot be to itself
        if from_is and to_is and from_key == to_key:
            errors.append(
                f"standard_relations.csv row {i}: self-relation error: 'from' and 'to' point to the same standard {from_key}."
            )

        if from_is and from_key not in valid_standards:
            errors.append(
                f"standard_relations.csv row {i}: 'from' standard {from_key} does not exist in standards.csv."
            )
        if to_is and to_key not in valid_standards:
            errors.append(
                f"standard_relations.csv row {i}: 'to' standard {to_key} does not exist in standards.csv."
            )

        if rel_type and rel_type not in ENUMS["relation_type"]:
            errors.append(
                f"standard_relations.csv row {i}: invalid relation_type '{rel_type}'. Allowed: {sorted(ENUMS['relation_type'])}."
            )

        rel_key = (from_is, from_part, to_is, to_part, rel_type)
        if rel_key in seen:
            errors.append(
                f"standard_relations.csv row {i}: duplicate relation between {from_key} and {to_key} with type '{rel_type}'."
            )
        else:
            seen.add(rel_key)

    return errors


def _validate_benchmarks(
    rows: List[Dict[str, str]],
    expected_rows: List[Dict[str, str]],
    valid_standards: Set[Tuple[str, str]],
    standards_verif_status: Dict[Tuple[str, str], str],
) -> List[str]:
    """Validate benchmark_rows and benchmark_expected rules:
    - Abstain rule: kind='abstain' must have zero expected rows; kind='normal' must have >= 1 'primary' row.
    - Verification rule: benchmark row can only be 'verified' if every standard in its expected rows is 'verified'.
    """
    errors: List[str] = []
    queries_map: Dict[str, Tuple[int, str, str]] = {}  # query -> (row_num, kind, verif_status)

    for i, row in enumerate(rows, start=2):
        query = row.get("query", "").strip()
        kind = row.get("kind", "").strip() or "normal"
        verif_status = row.get("verification_status", "").strip() or "entered"

        if not query:
            errors.append(f"benchmark_rows.csv row {i}: missing required field 'query'.")
            continue

        if query in queries_map:
            errors.append(f"benchmark_rows.csv row {i}: duplicate query '{query}'.")
        else:
            queries_map[query] = (i, kind, verif_status)

        if kind not in ENUMS["benchmark_kind"]:
            errors.append(
                f"benchmark_rows.csv row {i}: invalid kind '{kind}'. Allowed: {sorted(ENUMS['benchmark_kind'])}."
            )
        if verif_status not in ENUMS["verification_status"]:
            errors.append(
                f"benchmark_rows.csv row {i}: invalid verification_status '{verif_status}'. Allowed: {sorted(ENUMS['verification_status'])}."
            )

    # Group expected rows by query
    expected_by_query: Dict[str, List[Tuple[int, Tuple[str, str], str]]] = {}
    for i, exp in enumerate(expected_rows, start=2):
        q = exp.get("query", "").strip()
        is_num = exp.get("is_number", "").strip()
        part = exp.get("part", "").strip()
        role = exp.get("role", "").strip()

        if not q:
            errors.append(f"benchmark_expected.csv row {i}: missing required field 'query'.")
            continue
        if q not in queries_map:
            errors.append(
                f"benchmark_expected.csv row {i}: query '{q}' does not exist in benchmark_rows.csv."
            )

        std_key = (is_num, part)
        if not is_num:
            errors.append(f"benchmark_expected.csv row {i}: missing required field 'is_number'.")
        elif std_key not in valid_standards:
            errors.append(
                f"benchmark_expected.csv row {i}: standard {std_key} does not exist in standards.csv."
            )

        if role not in ENUMS["benchmark_role"]:
            errors.append(
                f"benchmark_expected.csv row {i}: invalid role '{role}'. Allowed: {sorted(ENUMS['benchmark_role'])}."
            )

        expected_by_query.setdefault(q, []).append((i, std_key, role))

    # Enforce Abstain Rule & Verification Cascade Rule
    for q, (row_idx, kind, verif_status) in queries_map.items():
        exps = expected_by_query.get(q, [])
        if kind == "abstain":
            if len(exps) > 0:
                errors.append(
                    f"benchmark_rows.csv row {row_idx}: abstain rule violation: kind='abstain' query '{q}' has {len(exps)} benchmark_expected row(s). Must have 0."
                )
        elif kind == "normal":
            primary_count = sum(1 for _, _, role in exps if role == "primary")
            if primary_count == 0:
                errors.append(
                    f"benchmark_rows.csv row {row_idx}: abstain rule violation: kind='normal' query '{q}' has no 'primary' expected standard. Must have at least 1."
                )

        if verif_status == "verified":
            for exp_row, std_key, _ in exps:
                std_status = standards_verif_status.get(std_key, "entered")
                if std_status != "verified":
                    errors.append(
                        f"benchmark_rows.csv row {row_idx}: verification rule violation: query '{q}' is marked 'verified', but referenced standard {std_key} is '{std_status}' (not 'verified')."
                    )

    return errors


def validate_seeds(seeds: Dict[str, List[Dict[str, str]]]) -> List[str]:
    """Validate all seed CSVs using natural keys and return human-readable error strings."""
    errors: List[str] = []

    standards = seeds.get("standards", [])
    std_errors, valid_standards, standards_verif_map = _validate_standards(standards)
    errors.extend(std_errors)

    editions = seeds.get("standard_editions", [])
    ed_errors, valid_editions = _validate_standard_editions(editions, valid_standards)
    errors.extend(ed_errors)

    amendments = seeds.get("standard_amendments", [])
    am_errors = _validate_standard_amendments(amendments, valid_editions)
    errors.extend(am_errors)

    relations = seeds.get("standard_relations", [])
    rel_errors = _validate_standard_relations(relations, valid_standards)
    errors.extend(rel_errors)

    # Optional benchmark validation
    if "benchmark_rows" in seeds or "benchmark_expected" in seeds:
        bench_rows = seeds.get("benchmark_rows", [])
        bench_exp = seeds.get("benchmark_expected", [])
        bench_errors = _validate_benchmarks(bench_rows, bench_exp, valid_standards, standards_verif_map)
        errors.extend(bench_errors)

    return errors

# ---------------------------------------------------------------------------
# Insert logic (real DB logic)
# ---------------------------------------------------------------------------

def insert_seeds(
    seeds: Dict[str, List[Dict[str, str]]],
    skip_embeddings: bool = False,
    db_conn: Optional[Any] = None,
) -> None:
    """Insert or upsert seed data into PostgreSQL resolving natural keys to database ids.
    If db_conn is provided, it is used; otherwise loads configuration from .env.
    """
    import psycopg2
    from pgvector.psycopg2 import register_vector
    from dotenv import load_dotenv

    close_conn = False
    if db_conn is None:
        load_dotenv(Path(__file__).resolve().parent.parent / ".env")
        conn = psycopg2.connect(
            dbname=os.getenv("POSTGRES_DB", "standards"),
            user=os.getenv("POSTGRES_USER", "user"),
            password=os.getenv("POSTGRES_PASSWORD", "password"),
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=os.getenv("POSTGRES_PORT", "5433"),
        )
        close_conn = True
    else:
        conn = db_conn

    # Register pgvector adapter right after connecting
    register_vector(conn)

    # Register numpy float adapter so psycopg2 can handle numpy.float32
    import numpy as np
    from psycopg2.extensions import register_adapter, AsIs
    register_adapter(np.float32, lambda val: AsIs(float(val)))
    register_adapter(np.float64, lambda val: AsIs(float(val)))

    embedding_dim = int(os.getenv("EMBEDDING_DIM", "384"))

    # Initialize embedding model once before row loops
    if not skip_embeddings:
        init_embedding_model()

    try:
        with conn:
            with conn.cursor() as cur:
                # 1. Product groups cache
                cur.execute("SELECT id, name FROM product_group;")
                pg_map = {name.lower(): pg_id for pg_id, name in cur.fetchall()}

                # 2. Family creation and map
                standards = seeds.get("standards", [])
                base_numbers = {row["is_number"].strip() for row in standards if row.get("is_number")}
                family_map: Dict[str, int] = {}
                for base_is in sorted(base_numbers):
                    cur.execute(
                        "INSERT INTO family (base_is_number) VALUES (%s) ON CONFLICT (base_is_number) DO UPDATE SET base_is_number=EXCLUDED.base_is_number RETURNING id;",
                        (base_is,),
                    )
                    family_map[base_is] = cur.fetchone()[0]

                # 3. Standards pass 1 (insert all standards without superseded_by_id)
                standards_map: Dict[Tuple[str, Optional[str]], int] = {}
                for row in standards:
                    is_number = row["is_number"].strip()
                    part = row.get("part", "").strip() or None
                    title = row.get("title", "").strip()
                    pg_name = row.get("product_group", "").strip().lower()
                    pg_id = pg_map.get(pg_name)
                    category = row.get("category", "").strip() or None
                    scope_text = row.get("scope_text", "").strip()
                    raw_keywords = row.get("keywords", "").strip()
                    keywords = [k.strip() for k in raw_keywords.split(",") if k.strip()] if raw_keywords else None
                    status = row.get("status", "").strip() or "current"
                    verif_status = row.get("verification_status", "").strip() or "entered"
                    source_url = row.get("source_url", "").strip() or None
                    source_note = row.get("source_note", "").strip() or None
                    fam_id = family_map[is_number]

                    emb = None
                    if not skip_embeddings:
                        embed_text = build_embedding_text(title, scope_text, keywords)
                        emb = compute_embedding(embed_text, embedding_dim)

                    cur.execute(
                        """
                        INSERT INTO standards (
                            is_number, title, part, family_id, product_group,
                            embedding, verification_status, scope_text, keywords, status,
                            source_url, source_note, category
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (is_number, part) DO UPDATE SET
                            title = EXCLUDED.title,
                            family_id = EXCLUDED.family_id,
                            product_group = EXCLUDED.product_group,
                            embedding = COALESCE(EXCLUDED.embedding, standards.embedding),
                            scope_text = EXCLUDED.scope_text,
                            keywords = EXCLUDED.keywords,
                            status = EXCLUDED.status,
                            source_url = EXCLUDED.source_url,
                            source_note = EXCLUDED.source_note,
                            category = EXCLUDED.category
                        RETURNING id;
                        """,
                        (is_number, title, part, fam_id, pg_id, emb, verif_status, scope_text, keywords, status, source_url, source_note, category),
                    )
                    std_id = cur.fetchone()[0]
                    standards_map[(is_number, part)] = std_id

                # 4. Standards pass 2 (update superseded_by_id)
                for row in standards:
                    status = row.get("status", "").strip()
                    if status == "superseded":
                        is_number = row["is_number"].strip()
                        part = row.get("part", "").strip() or None
                        sup_is = row.get("superseded_by_is_number", "").strip()
                        sup_part = row.get("superseded_by_part", "").strip() or None
                        target_id = standards_map.get((sup_is, sup_part))
                        if target_id:
                            cur.execute(
                                "UPDATE standards SET superseded_by_id = %s WHERE id = %s;",
                                (target_id, standards_map[(is_number, part)]),
                            )
                        else:
                            print(f"[ERROR] standards: skipped setting superseded_by_id referencing ({sup_is}, {sup_part}) - not found")

                # 5. Standard editions
                editions_map: Dict[Tuple[str, Optional[str], int], int] = {}
                for row in seeds.get("standard_editions", []):
                    is_number = row["is_number"].strip()
                    part = row.get("part", "").strip() or None
                    std_id = standards_map.get((is_number, part))
                    if not std_id:
                        print(f"[ERROR] standard_editions: skipped row referencing standard ({is_number}, {part}) - not found")
                        continue
                    edition_year = int(row["edition_year"].strip())
                    is_latest = _parse_bool(row.get("is_latest", "")) or False
                    notes = row.get("notes", "").strip() or None

                    cur.execute(
                        """
                        INSERT INTO standard_editions (standard_id, edition_year, is_latest, notes)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (standard_id, edition_year) DO UPDATE SET
                            is_latest = EXCLUDED.is_latest,
                            notes = EXCLUDED.notes
                        RETURNING id;
                        """,
                        (std_id, edition_year, is_latest, notes),
                    )
                    ed_id = cur.fetchone()[0]
                    editions_map[(is_number, part, edition_year)] = ed_id

                # 6. Standard amendments
                for row in seeds.get("standard_amendments", []):
                    is_number = row["is_number"].strip()
                    part = row.get("part", "").strip() or None
                    edition_year = int(row["edition_year"].strip())
                    ed_id = editions_map.get((is_number, part, edition_year))
                    if not ed_id:
                        print(f"[ERROR] standard_amendments: skipped row referencing edition ({is_number}, {part}, {edition_year}) - not found")
                        continue
                    amendment_no = int(row["amendment_no"].strip())
                    year = int(row["year"].strip()) if row.get("year", "").strip().isdigit() else None
                    notes = row.get("notes", "").strip() or None

                    cur.execute(
                        """
                        INSERT INTO standard_amendments (edition_id, amendment_no, year, notes)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (edition_id, amendment_no) DO UPDATE SET
                            year = EXCLUDED.year,
                            notes = EXCLUDED.notes;
                        """,
                        (ed_id, amendment_no, year, notes),
                    )

                # 7. Standard relations
                for row in seeds.get("standard_relations", []):
                    from_is = row["from_is_number"].strip()
                    from_part = row.get("from_part", "").strip() or None
                    to_is = row["to_is_number"].strip()
                    to_part = row.get("to_part", "").strip() or None
                    from_id = standards_map.get((from_is, from_part))
                    to_id = standards_map.get((to_is, to_part))
                    if not from_id:
                        print(f"[ERROR] standard_relations: skipped row referencing from_standard ({from_is}, {from_part}) - not found")
                        continue
                    if not to_id:
                        print(f"[ERROR] standard_relations: skipped row referencing to_standard ({to_is}, {to_part}) - not found")
                        continue
                    rel_type = row.get("relation_type", "").strip() or None
                    notes = row.get("notes", "").strip() or None

                    cur.execute(
                        """
                        INSERT INTO standard_relations (from_standard_id, to_standard_id, relation_type, notes)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (from_standard_id, to_standard_id, relation_type) DO UPDATE SET
                            notes = EXCLUDED.notes;
                        """,
                        (from_id, to_id, rel_type, notes),
                    )

                # 8. Benchmark rows & benchmark expected
                bench_rows_map: Dict[str, int] = {}
                for row in seeds.get("benchmark_rows", []):
                    query = row["query"].strip()
                    lang = row.get("language", "").strip() or None
                    kind = row.get("kind", "").strip() or "normal"
                    verif_status = row.get("verification_status", "").strip() or "entered"

                    cur.execute(
                        """
                        INSERT INTO benchmark_rows (query, language, kind, verification_status)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (query) DO UPDATE SET
                            language = EXCLUDED.language,
                            kind = EXCLUDED.kind
                        RETURNING id;
                        """,
                        (query, lang, kind, verif_status),
                    )
                    b_id = cur.fetchone()[0]
                    bench_rows_map[query] = b_id

                for row in seeds.get("benchmark_expected", []):
                    query = row["query"].strip()
                    b_id = bench_rows_map.get(query)
                    if not b_id:
                        print(f"[ERROR] benchmark_expected: skipped row referencing benchmark query '{query}' - not found")
                        continue
                    is_num = row["is_number"].strip()
                    part = row.get("part", "").strip() or None
                    std_id = standards_map.get((is_num, part))
                    if not std_id:
                        print(f"[ERROR] benchmark_expected: skipped row referencing standard ({is_num}, {part}) - not found")
                        continue
                    role = row.get("role", "").strip() or "primary"

                    cur.execute(
                        """
                        INSERT INTO benchmark_expected (benchmark_row_id, standard_id, role)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (benchmark_row_id, standard_id) DO UPDATE SET
                            role = EXCLUDED.role;
                        """,
                        (b_id, std_id, role),
                    )

        print("[INFO] Seed data successfully imported.")
    finally:
        if close_conn:
            conn.close()

# ---------------------------------------------------------------------------
# Command-line interface
# ---------------------------------------------------------------------------

def main(argv: List[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Load seed CSVs into the database.")
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Only validate CSV files and report errors; do not touch the DB.",
    )
    parser.add_argument(
        "--force-unvalidated",
        action="store_true",
        help="Skip pre-validation and force insertion into database.",
    )
    parser.add_argument(
        "--seed-dir",
        type=Path,
        default=SEED_DIR,
        help="Directory containing the seed CSV files (default: data/seed).",
    )
    parser.add_argument(
        "--skip-embeddings",
        action="store_true",
        help="Skip generating or updating vector embeddings during import.",
    )
    args = parser.parse_args(argv)

    try:
        seeds = load_seeds(args.seed_dir)
    except FileNotFoundError as exc:
        print(f"[ERROR] {exc}")
        sys.exit(1)

    # If --validate-only, validate and exit without DB operations
    if args.validate_only:
        errors = validate_seeds(seeds)
        if not errors:
            print("Validation finished – 0 errors found.")
        else:
            print(f"Validation finished – {len(errors)} error(s) found:")
            for idx, err in enumerate(errors, start=1):
                print(f"  {idx}. {err}")
        sys.exit(0 if not errors else 1)

    # Unless explicitly forced, always run validate_seeds before inserting
    if not args.force_unvalidated:
        errors = validate_seeds(seeds)
        if errors:
            print(f"Validation failed – {len(errors)} error(s) found. Aborting import:")
            for idx, err in enumerate(errors, start=1):
                print(f"  {idx}. {err}")
            sys.exit(1)

    insert_seeds(seeds, skip_embeddings=args.skip_embeddings)

if __name__ == "__main__":
    main()
