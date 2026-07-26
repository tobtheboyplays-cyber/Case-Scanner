"""Dekningssjekk - "har noen allerede skrevet om dette?"

Bruker Google News RSS-sok (gratis) til aa telle ferske medieoppslag for et tema.
Poenget i v2: loft fram det som er USKREVET (gronn), nedprioriter det som alt er
dekket (rod). Fail-soft: hvis sjekken feiler, setter vi status "unknown".
"""

from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import quote_plus

import feedparser

from app.collectors.base import http_get
from app.config import (
    AFTENBLADET_NAME,
    COVERAGE_LOOKBACK_DAYS,
    COVERAGE_RED_MIN,
    COVERAGE_YELLOW_MIN,
    ENABLE_COVERAGE,
    GOOGLE_NEWS_RSS,
)


def _parse_dt(entry) -> datetime | None:
    val = getattr(entry, "published_parsed", None)
    if val:
        try:
            return datetime(*val[:6], tzinfo=timezone.utc)
        except (TypeError, ValueError):
            return None
    return None


def check(query: str) -> dict:
    """Returner {status, count, examples}. status: green/yellow/red/unknown."""
    if not ENABLE_COVERAGE or not query:
        return {"status": "unknown", "count": 0, "examples": [], "aftenbladet": []}

    url = f"{GOOGLE_NEWS_RSS}?q={quote_plus(query)}&hl=no&gl=NO&ceid=NO:no"
    try:
        resp = http_get(url, headers={"Accept": "application/rss+xml"})
        parsed = feedparser.parse(resp.content)
    except Exception:  # noqa: BLE001 - fail-soft
        return {"status": "unknown", "count": 0, "examples": [], "aftenbladet": []}

    now = datetime.now(tz=timezone.utc)
    fresh = []
    egne = []
    for entry in parsed.entries:
        dt = _parse_dt(entry)
        if dt is None:
            continue
        age_days = (now - dt).total_seconds() / 86400.0
        src = ""
        if getattr(entry, "source", None) and getattr(entry.source, "title", None):
            src = entry.source.title
        post = {
            "title": getattr(entry, "title", "")[:120],
            "source": src,
            "date": dt.strftime("%d.%m.%Y"),
            "url": getattr(entry, "link", ""),
            "dager": int(age_days),
        }
        if age_days <= COVERAGE_LOOKBACK_DAYS:
            fresh.append(post)
        # AFTENBLADETS EGNE, uansett alder. Dette er raastoffet til
        # oppfoelgersaker - de letteste publiserte artiklene som finnes: «vi
        # skrev X i januar, her er hva som har skjedd siden». Avisa eier
        # premisset, bildene og kildene fra forrige gang.
        #
        # Dette koster IKKE ett eneste ekstra HTTP-kall. Google News returnerer
        # hele treffslista i samme svar; vi kastet bare alt eldre enn 90 dager.
        # Det gamle var det verdifulle.
        if src and AFTENBLADET_NAME.lower() in src.lower():
            egne.append(post)

    egne.sort(key=lambda p: p["dager"])
    count = len(fresh)
    if count >= COVERAGE_RED_MIN:
        status = "red"
    elif count >= COVERAGE_YELLOW_MIN:
        status = "yellow"
    else:
        status = "green"
    return {
        "status": status,
        "count": count,
        "examples": fresh[:3],
        "aftenbladet": egne[:2],
    }
