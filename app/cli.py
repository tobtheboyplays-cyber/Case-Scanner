"""Kommandolinje-skann: kjor et skann uten webserver.

Nyttig for testing og for a sette opp cron/planlagt kjoring.

    uv run python -m app.cli
"""

from __future__ import annotations

from app.main import run_scan


def main() -> None:
    print("Skanner kilder ...")
    payload = run_scan()
    print(f"\n{payload['signal_count']} signaler hentet.\n")

    print("Kildestatus:")
    for line in payload["status"]:
        print(f"  - {line}")

    badge = {"green": "🟢 USKREVET", "yellow": "🟡 delvis", "red": "🔴 dekket",
             "unknown": "· ukjent"}
    print(f"\nTopp leads ({len(payload['cases'])}):")
    for i, case in enumerate(payload["cases"][:12], 1):
        geo = "LOKAL" if case["geo"] == "lokal" else "Norge"
        kind = "DATA" if case.get("kind") == "data" else "grasrot"
        cov = badge.get(case.get("coverage_status", "unknown"), "")
        print(f"\n  #{i} [{geo}/{kind}] {cov}  score {case['score']}")
        print(f"     {case['title']}")
        if case.get("finding"):
            print(f"     Funn:     {case['finding']}")
        print(f"     Vinkling: {case['angle'][:150]}")
        if case.get("coverage_examples"):
            ex = case["coverage_examples"][0]
            print(f"     Dekning:  {ex['source']} {ex['date']} - {ex['title'][:50]}")


if __name__ == "__main__":
    main()
