"""Smoke test script for Standards Navigator retrieval.

Runs retrieval directly (no HTTP) for standard test queries and prints
the top 3 results, confidence scores, and abstain decisions.
"""

import sys
import os

# Add root directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import config
from app.main import get_db_conn
from app.services.retrieval import search_standards

QUERIES = [
    "cement for house foundation",
    "ordinary portland cement",
    "fly ash based cement",
    "TMT bars for building construction",
    "rebar tensile strength test",
    "PVC insulated cable for house wiring",
    "XLPE cable 33 kV",
    "conductor resistance test for cables",
    "asdfgh qwerty zxcv",  # must abstain
]


def run_smoke_tests():
    print("=" * 70)
    print(f"RUNNING STANDARDS NAVIGATOR RETRIEVAL SMOKE TESTS")
    print(f"CONFIDENCE_THRESHOLD = {config.CONFIDENCE_THRESHOLD}")
    print("=" * 70)

    with get_db_conn() as conn:
        for q in QUERIES:
            res = search_standards(conn, q, top_k=3)
            abstain = res["abstain"]
            results = res["results"]
            best_conf = res.get("best_confidence", 0.0)

            print(f"\nQuery: '{q}'")
            print(f"Abstained: {abstain} (Best confidence: {best_conf})")
            if abstain:
                print("  [ABSTAINED - No confident match]")
            else:
                for idx, r in enumerate(results, start=1):
                    part_str = f" Part {r['part']}" if r.get("part") else ""
                    print(
                        f"  {idx}. {r['is_number']}{part_str}: {r['title']} "
                        f"(Conf: {r['confidence']}, Status: {r['status']})"
                    )

    print("\n" + "=" * 70)
    print("SMOKE TESTS COMPLETED")
    print("=" * 70)


if __name__ == "__main__":
    run_smoke_tests()
