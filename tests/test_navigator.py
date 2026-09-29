"""Unit tests for Standards Navigator core logic (pure, no live DB required).

Covers:
- Hallucination guard (stripping fake IS designations, preserving known keys)
- Reciprocal Rank Fusion (known input ordering)
- Citation evaluation logic (ok, outdated_edition, superseded, part_required, not_in_database, invalid_format)
- Retrieval abstain rule with stubbed scores
"""

import pytest
from app.services.guard import guard_text
from app.services.retrieval import compute_rrf, rerank_by_status, should_abstain
from app.services.citation import evaluate_citation
from app.services.designation import parse_designation, Designation


def test_guard_strips_fake_designation():
    """Fake standard like IS 0000:2001 must be stripped, while known standards are preserved."""
    known_keys = {("IS 269", None), ("IS 1489", "1")}
    text_with_fake = "You should use IS 0000:2001 for foundations, but IS 269 is also good."

    clean_text, removed = guard_text(text_with_fake, known_keys)

    assert "IS 0000" not in clean_text
    assert "IS 269" in clean_text
    assert len(removed) >= 1
    assert any("0000" in r for r in removed)


def test_guard_preserves_clean_text():
    """Text with only valid known designations is unchanged."""
    known_keys = {("IS 269", None), ("IS 456", None)}
    text = "Refer to IS 269 and IS 456 for concrete mix specifications."

    clean_text, removed = guard_text(text, known_keys)

    assert "IS 269" in clean_text
    assert "IS 456" in clean_text
    assert removed == []


def test_rrf_ordering():
    """RRF ranks items that appear high in both result lists at the top."""
    # Item 1 is rank 1 in vec and rank 1 in FTS -> top
    # Item 2 is rank 2 in vec only
    # Item 3 is rank 2 in FTS only
    # Item 4 is rank 3 in both
    vec_ids = [1, 2, 4]
    fts_ids = [1, 3, 4]

    ranked = compute_rrf(vec_ids, fts_ids, k=60)

    top_id = ranked[0][0]
    assert top_id == 1

    # Verify score calculation: 1/(60+1) + 1/(60+1) = 2/61 ~= 0.032787
    expected_top_score = (1.0 / 61) + (1.0 / 61)
    assert pytest.approx(ranked[0][1], 0.0001) == expected_top_score

    # Item 4 appears in both (rank 3 in both: 2/63 ~= 0.03174)
    # Item 2 appears in one (rank 2: 1/62 ~= 0.0161)
    # So item 4 should rank above item 2 and item 3
    assert ranked[1][0] == 4


def test_rerank_by_status():
    """Current standards rank above superseded ones when scores are within 10%."""
    # Item 10 (superseded) score 0.020
    # Item 20 (current) score 0.019 (within 10% of 0.020)
    items = [(10, 0.020), (20, 0.019)]
    statuses = {10: "superseded", 20: "current"}

    reranked = rerank_by_status(items, statuses)

    # 10 penalty: 0.020 * 0.90 = 0.018 < 0.019
    # So 20 should come first!
    assert reranked[0][0] == 20
    assert reranked[1][0] == 10


def test_citation_invalid_format():
    """Non-IS citations yield invalid_format."""
    parsed = parse_designation("ISO 9001:2015")
    res = evaluate_citation(parsed, [])

    assert res["valid_format"] is False
    assert res["found"] is False
    assert res["verdict"] == "invalid_format"


def test_citation_not_in_database():
    """Valid IS format but missing from DB yields not_in_database."""
    parsed = parse_designation("IS 9999:2020")
    res = evaluate_citation(parsed, [])

    assert res["valid_format"] is True
    assert res["found"] is False
    assert res["verdict"] == "not_in_database"
    assert "not in our database" in res["messages"][0]


def test_citation_part_required():
    """No part cited when only parted records exist yields part_required."""
    parsed = parse_designation("IS 1489")
    db_records = [
        {"id": 1, "is_number": "IS 1489", "part": "1", "title": "PPC Fly Ash", "status": "current", "latest_edition_year": 2015, "amendment_count": 1},
        {"id": 2, "is_number": "IS 1489", "part": "2", "title": "PPC Clay", "status": "current", "latest_edition_year": 2015, "amendment_count": 0},
    ]

    res = evaluate_citation(parsed, db_records)

    assert res["valid_format"] is True
    assert res["found"] is True
    assert res["verdict"] == "part_required"
    assert res["available_parts"] == ["1", "2"]


def test_citation_ok():
    """Current standard with matching latest year yields ok."""
    parsed = parse_designation("IS 269:2015")
    db_records = [
        {
            "id": 1,
            "is_number": "IS 269",
            "part": None,
            "title": "Ordinary Portland Cement",
            "status": "current",
            "latest_edition_year": 2015,
            "amendment_count": 2,
        }
    ]

    res = evaluate_citation(parsed, db_records)

    assert res["valid_format"] is True
    assert res["found"] is True
    assert res["verdict"] == "ok"
    assert any("amendment" in m for m in res["messages"])


def test_citation_outdated_edition():
    """Cited year older than latest year yields outdated_edition."""
    parsed = parse_designation("IS 269:1989")
    db_records = [
        {
            "id": 1,
            "is_number": "IS 269",
            "part": None,
            "title": "Ordinary Portland Cement",
            "status": "current",
            "latest_edition_year": 2015,
            "amendment_count": 0,
        }
    ]

    res = evaluate_citation(parsed, db_records)

    assert res["verdict"] == "outdated_edition"
    assert any("outdated" in m for m in res["messages"])
    assert any("2015" in m for m in res["messages"])


def test_citation_superseded():
    """Superseded standard reports superseded verdict with replacement details."""
    parsed = parse_designation("IS 1139:1966")
    db_records = [
        {
            "id": 10,
            "is_number": "IS 1139",
            "part": None,
            "title": "Hot rolled mild steel and medium tensile steel deformed bars",
            "status": "superseded",
            "latest_edition_year": 1966,
            "amendment_count": 0,
            "superseded_by": {
                "is_number": "IS 1786",
                "part": None,
                "title": "High strength deformed steel bars",
            },
        }
    ]

    res = evaluate_citation(parsed, db_records)

    assert res["verdict"] == "superseded"
    assert any("superseded" in m for m in res["messages"])
    assert any("IS 1786" in m for m in res["messages"])


def test_retrieval_abstain_rule():
    """Abstain triggers if best cosine < threshold AND no FTS hit."""
    threshold = 0.55

    # Low cosine, no FTS -> ABSTAIN
    assert should_abstain(best_cosine=0.30, has_fts_hit=False, threshold=threshold) is True

    # Low cosine, BUT has FTS -> DO NOT ABSTAIN
    assert should_abstain(best_cosine=0.30, has_fts_hit=True, threshold=threshold) is False

    # High cosine, no FTS -> DO NOT ABSTAIN
    assert should_abstain(best_cosine=0.70, has_fts_hit=False, threshold=threshold) is False

    # High cosine, has FTS -> DO NOT ABSTAIN
    assert should_abstain(best_cosine=0.70, has_fts_hit=True, threshold=threshold) is False

    # Fewer than 2 FTS matching results does NOT prevent abstaining when best cosine < threshold
    assert should_abstain(best_cosine=0.40, fts_count=1, threshold=threshold) is True
    assert should_abstain(best_cosine=0.40, fts_count=0, threshold=threshold) is True
    # 2 or more FTS matching results prevents abstaining
    assert should_abstain(best_cosine=0.40, fts_count=2, threshold=threshold) is False
