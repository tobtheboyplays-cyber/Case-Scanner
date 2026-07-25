"""Felles hjelpere for kollektorer: HTTP-klient og tid."""

from __future__ import annotations

from datetime import datetime, timezone

import httpx

from app.config import USER_AGENT


def http_get(url: str, *, timeout: float = 12.0, headers: dict | None = None) -> httpx.Response:
    """GET med realistisk User-Agent. Kaster ved feil (kaller fanger opp)."""
    hdrs = {"User-Agent": USER_AGENT, "Accept-Language": "nb-NO,nb;q=0.9,en;q=0.6"}
    if headers:
        hdrs.update(headers)
    resp = httpx.get(url, headers=hdrs, timeout=timeout, follow_redirects=True)
    resp.raise_for_status()
    return resp


def now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def to_utc(dt: datetime | None) -> datetime:
    """Gjor en datetime tz-aware i UTC. None -> naa."""
    if dt is None:
        return now_utc()
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
