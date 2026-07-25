"""Google Trends-kollektor via pytrends (uofisielt).

Valgfritt og fail-soft: pytrends kan mangle eller bli rate-limitet (429).
Da returnerer vi bare en statuslinje og tom liste - resten av appen gaar fint.
"""

from __future__ import annotations

from app.collectors.base import now_utc
from app.config import ENABLE_TRENDS
from app.models import SignalItem


def collect() -> tuple[list[SignalItem], list[str]]:
    if not ENABLE_TRENDS:
        return [], ["Google Trends: avslaatt (CASE_RADAR_ENABLE_TRENDS=false)"]

    try:
        from pytrends.request import TrendReq
    except Exception:  # noqa: BLE001 - pakke ikke installert
        return [], ["Google Trends: pytrends ikke installert (pip install '.[trends]')"]

    signals: list[SignalItem] = []
    status: list[str] = []
    try:
        pytrends = TrendReq(hl="nb-NO", tz=-60)
        df = pytrends.trending_searches(pn="norway")
        terms = [str(t) for t in df[0].tolist()][:20]
        for term in terms:
            signals.append(
                SignalItem(
                    source="Google Trends (Norge)",
                    source_type="trends",
                    title=term,
                    url=f"https://trends.google.com/trends/explore?geo=NO&q={term}",
                    published=now_utc(),
                    summary="Stigende søk i Norge akkurat naa.",
                    geo="nasjonal",
                )
            )
        status.append(f"Google Trends: {len(signals)} stigende søk")
    except Exception as exc:  # noqa: BLE001 - fail-soft (ofte 429 fra Google)
        status.append(f"Google Trends: utilgjengelig ({type(exc).__name__})")

    return signals, status
