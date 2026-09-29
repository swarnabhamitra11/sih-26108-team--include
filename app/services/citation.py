"""Citation check service for Standards Navigator.

Provides pure decision logic in evaluate_citation() and helper to parse and evaluate.
"""

from typing import Dict, Any, List, Optional
from app.services.designation import parse_designation, Designation


def _norm_part(p: Optional[Any]) -> Optional[str]:
    if p is None or p == "":
        return None
    return str(p).strip()


def evaluate_citation(parsed: Designation, db_records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Pure evaluation of a parsed designation against DB records for that base IS number.

    Args:
        parsed: Designation NamedTuple (base_is_number, part, year).
        db_records: List of dicts representing standards matching the base_is_number.
                    Each dict must contain:
                    - 'id': int
                    - 'is_number': str
                    - 'part': Optional[str]
                    - 'title': str
                    - 'status': str ('current', 'superseded', 'withdrawn')
                    - 'latest_edition_year': Optional[int]
                    - 'amendment_count': int
                    - 'superseded_by': Optional[dict] with 'is_number', 'part', 'title'

    Returns:
        Dict with keys:
        - valid_format: bool
        - found: bool
        - cited: dict(is_number, part, year)
        - standard: Optional[dict(title, status, latest_edition_year)]
        - verdict: str ('ok', 'outdated_edition', 'superseded', 'part_required', 'not_in_database', 'invalid_format')
        - messages: list[str]
    """
    if not parsed.base_is_number:
        return {
            "valid_format": False,
            "found": False,
            "cited": {"is_number": "", "part": None, "year": None},
            "standard": None,
            "verdict": "invalid_format",
            "messages": ["Unrecognized or non-IS designation format. Expecting format like 'IS 269:2015'."],
        }

    cited = {
        "is_number": parsed.base_is_number,
        "part": parsed.part,
        "year": parsed.year,
    }

    if not db_records:
        return {
            "valid_format": True,
            "found": False,
            "cited": cited,
            "standard": None,
            "verdict": "not_in_database",
            "messages": [f"Standard '{parsed.base_is_number}' is not in our database."],
        }

    # Case: No part cited, but the standard in DB only exists with parts (e.g. IS 1489 Part 1 & Part 2)
    target_part = _norm_part(parsed.part)
    has_exact_part_match = any(_norm_part(r.get("part")) == target_part for r in db_records)

    if target_part is None and not has_exact_part_match:
        parts_available = sorted([
            str(r["part"]) for r in db_records if _norm_part(r.get("part")) is not None
        ])
        return {
            "valid_format": True,
            "found": True,
            "cited": cited,
            "standard": None,
            "verdict": "part_required",
            "messages": [
                f"{parsed.base_is_number} requires a part designation. "
                f"Available parts in our database: Part {', Part '.join(parts_available)}."
            ],
            "available_parts": parts_available,
        }

    # Find the specific record matching this part
    match = None
    for r in db_records:
        if _norm_part(r.get("part")) == target_part:
            match = r
            break

    if not match:
        available_parts = sorted([
            str(r["part"]) for r in db_records if _norm_part(r.get("part")) is not None
        ])
        return {
            "valid_format": True,
            "found": False,
            "cited": cited,
            "standard": None,
            "verdict": "not_in_database",
            "messages": [
                f"{parsed.base_is_number}"
                + (f" Part {parsed.part}" if parsed.part else "")
                + " is not in our database."
                + (f" Available parts: Part {', Part '.join(available_parts)}." if available_parts else "")
            ],
        }

    standard_info = {
        "title": match.get("title", ""),
        "status": match.get("status", "current"),
        "latest_edition_year": match.get("latest_edition_year"),
        "amendment_count": match.get("amendment_count", 0),
    }

    verdict = "ok"
    messages: List[str] = []

    # Check status: superseded or withdrawn
    st = match.get("status", "current").lower()
    if st in ("superseded", "withdrawn"):
        verdict = "superseded"
        rep = match.get("superseded_by")
        if rep:
            rep_text = f"{rep.get('is_number')}"
            if rep.get("part"):
                rep_text += f" (Part {rep.get('part')})"
            if rep.get("title"):
                rep_text += f" - {rep.get('title')}"
            messages.append(
                f"Standard is {st}. Replacement: {rep_text}."
            )
        else:
            messages.append(f"Standard is {st} with no recorded replacement.")

    # Check edition year
    latest_year = match.get("latest_edition_year")
    if parsed.year and latest_year and parsed.year < latest_year:
        if verdict == "ok":
            verdict = "outdated_edition"
        messages.append(
            f"Cited edition ({parsed.year}) is outdated. Latest edition is {latest_year}."
        )

    # Check amendments
    amend_cnt = match.get("amendment_count", 0)
    if amend_cnt > 0:
        messages.append(
            f"Latest edition has {amend_cnt} amendment{'s' if amend_cnt > 1 else ''} issued."
        )

    if verdict == "ok":
        messages.append(f"Citation is valid and current: {match.get('title')}.")

    return {
        "valid_format": True,
        "found": True,
        "cited": cited,
        "standard": standard_info,
        "verdict": verdict,
        "messages": messages,
    }


def check_citation_with_db(citation: str, conn) -> Dict[str, Any]:
    """Parse citation, query DB for matching standards, and evaluate."""
    parsed = parse_designation(citation)
    if not parsed.base_is_number:
        return evaluate_citation(parsed, [])

    with conn.cursor() as cur:
        # Fetch all standards matching the base_is_number
        cur.execute(
            """
            SELECT s.id, s.is_number, s.part, s.title, s.status, s.superseded_by_id,
                   (SELECT se.edition_year FROM standard_editions se WHERE se.standard_id = s.id ORDER BY se.is_latest DESC, se.edition_year DESC LIMIT 1) AS latest_year,
                   (SELECT se.id FROM standard_editions se WHERE se.standard_id = s.id ORDER BY se.is_latest DESC, se.edition_year DESC LIMIT 1) AS latest_edition_id
            FROM standards s
            WHERE UPPER(TRIM(s.is_number)) = UPPER(TRIM(%s))
            """,
            (parsed.base_is_number,),
        )
        rows = cur.fetchall()
        db_records: List[Dict[str, Any]] = []

        for row in rows:
            sid, is_num, part, title, status, sup_id, latest_year, latest_ed_id = row
            amend_count = 0
            if latest_ed_id:
                cur.execute(
                    "SELECT COUNT(*) FROM standard_amendments WHERE edition_id = %s",
                    (latest_ed_id,),
                )
                amend_count = cur.fetchone()[0]

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

            db_records.append({
                "id": sid,
                "is_number": is_num,
                "part": part,
                "title": title,
                "status": status,
                "latest_edition_year": latest_year,
                "amendment_count": amend_count,
                "superseded_by": superseded_by,
            })

    return evaluate_citation(parsed, db_records)
