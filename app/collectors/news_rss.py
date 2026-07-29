"""Nyhets-RSS-kollektor. Henter og normaliserer RSS til SignalItem."""

from __future__ import annotations

from datetime import datetime, timezone

import feedparser

from app.collectors.base import http_get, now_utc, to_utc
from app.config import NEWS_FEEDS
from app.models import SignalItem


def _parse_published(entry) -> datetime:
    for attr in ("published_parsed", "updated_parsed"):
        val = getattr(entry, attr, None)
        if val:
            try:
                return datetime(*val[:6], tzinfo=timezone.utc)
            except (TypeError, ValueError):
                continue
    return now_utc()


def collect() -> tuple[list[SignalItem], list[str]]:
    signals: list[SignalItem] = []
    status: list[str] = []

    for feed in NEWS_FEEDS:
        try:
            resp = http_get(feed["url"])
            parsed = feedparser.parse(resp.content)
            count = 0
            for entry in parsed.entries[:40]:
                title = getattr(entry, "title", "").strip()
                if not title:
                    continue
                summary = getattr(entry, "summary", "")
                signals.append(
                    SignalItem(
                        source=feed["name"],
                        source_type="news",
                        title=title,
                        url=getattr(entry, "link", ""),
                        published=to_utc(_parse_published(entry)),
                        summary=_strip_html(summary),
                        geo="nasjonal",  # avgjores av innhold i scoring
                        outlet_local=feed["geo"] == "lokal",
                    )
                )
                count += 1
            status.append(f"{feed['name']}: {count} saker")
        except Exception as exc:  # noqa: BLE001 - fail-soft per feed
            status.append(f"[FEIL] {feed['name']}: {type(exc).__name__}")

    return signals, status


def _strip_html(text: str) -> str:
    """Enkel HTML-stripping uten avhengigheter."""
    out = []
    depth = 0
    for ch in text:
        if ch == "<":
            depth += 1
        elif ch == ">":
            depth = max(0, depth - 1)
        elif depth == 0:
            out.append(ch)
    return "".join(out).strip()
