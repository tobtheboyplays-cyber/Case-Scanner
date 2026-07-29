"""Tester for SSB json-stat2-parsing og originalitets-scoring (uten nettverk)."""

from __future__ import annotations

from app.collectors import ssb
from app.collectors.base import now_utc
from app.models import Case
from app.scoring import finalize_scores


def _fake_jsonstat():
    # dims: Region(1) x Alder(2) x ContentsCode(1) x Tid(2)
    return {
        "id": ["Region", "Alder", "ContentsCode", "Tid"],
        "size": [1, 2, 1, 2],
        "value": [100, 110, 200, 180],  # row-major
        "dimension": {
            "Region": {"category": {"index": {"1103": 0}, "label": {"1103": "Stavanger"}}},
            "Alder": {"category": {"index": {"020": 0, "021": 1},
                                   "label": {"020": "20 år", "021": "21 år"}}},
            "ContentsCode": {"category": {"index": {"Personer1": 0},
                                          "label": {"Personer1": "Personer"}}},
            "Tid": {"category": {"index": {"2025": 0, "2026": 1},
                                 "label": {"2025": "2025", "2026": "2026"}}},
        },
    }


def test_series_by_region_sums_over_age():
    series, tids = ssb._series_by_region(_fake_jsonstat())
    assert tids == ["2025", "2026"]
    # 2025: 100+200=300, 2026: 110+180=290
    assert series["1103"] == [("2025", 300.0), ("2026", 290.0)]


def test_make_case_produces_finding_and_local_geo():
    probe = {"id": "t", "table": "07459", "label": "Test 20–21",
             "topics": ["studentliv"], "coverage_query": "x"}
    series, tids = ssb._series_by_region(_fake_jsonstat())
    case = ssb._make_case(probe, series, tids)
    assert case is not None
    assert case.geo == "lokal"
    assert case.kind == "data"
    assert "290" in case.finding          # siste verdi
    assert "3.3%" in case.finding or "3.4%" in case.finding  # -10/300
    assert case.data_url.endswith("07459")


def test_finalize_scores_rewards_originality():
    def mk(status, base=10.0):
        return Case(key="k", title="t", score=base, geo="lokal", topics=[],
                    angle="", why="", signals=[], created_at=now_utc(),
                    coverage_status=status)
    green, red = mk("green"), mk("red")
    finalize_scores([green, red])
    assert green.score > red.score  # uskrevet skal ranke over allerede dekket
