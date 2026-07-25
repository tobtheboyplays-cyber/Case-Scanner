"""Schibsted-soesteraviser: finn saker Aftenbladet KAN gjenbruke lokalt.

Aftenbladet er en Schibsted-avis. Denne kollektoren henter saker fra andre
Schibsted-aviser (Aftenposten, BT, E24 - ikke Stavanger), beholder de som er
relevante for 20-39, og lager gjenbruks-leads. Dekningssjekken (coverage.py)
avgjor etterpaa om Aftenbladet/andre allerede har skrevet det siste ~3 mnd.

Fail-soft: en feed som er nede stopper ikke resten.
"""

from __future__ import annotations

from datetime import datetime, timezone

import feedparser

from app.collectors.base import http_get, now_utc, to_utc
from app.config import ENABLE_SCHIBSTED, SCHIBSTED_FEEDS
from app.models import Case
from app.scoring import detect_topics


def _published(entry) -> datetime:
    for attr in ("published_parsed", "updated_parsed"):
        val = getattr(entry, attr, None)
        if val:
            try:
                return datetime(*val[:6], tzinfo=timezone.utc)
            except (TypeError, ValueError):
                continue
    return now_utc()


def collect() -> tuple[list[Case], list[str]]:
    if not ENABLE_SCHIBSTED:
        return [], ["Schibsted: avslaatt"]

    cases: list[Case] = []
    status: list[str] = []
    seen: set[str] = set()

    for feed in SCHIBSTED_FEEDS:
        try:
            resp = http_get(feed["url"])
            parsed = feedparser.parse(resp.content)
            kept = 0
            for entry in parsed.entries[:40]:
                title = getattr(entry, "title", "").strip()
                if not title or title.lower() in seen:
                    continue
                summary = getattr(entry, "summary", "")
                topics = detect_topics(f"{title} {summary}")
                if not topics:  # bare saker som treffer 20-39-tema
                    continue
                seen.add(title.lower())
                cases.append(
                    Case(
                        key=f"schibsted:{feed['name']}:{title[:40]}",
                        title=title[:140],
                        score=0.0,
                        geo="nasjonal",
                        topics=topics,
                        angle=(
                            f"{feed['name']} har en sak om dette. Vurder en lokal "
                            f"Stavanger/Rogaland-vinkel for unge (20-39) - hvis Aftenbladet "
                            f"ikke har skrevet det ennaa."
                        ),
                        why=f"Plukket opp fra søsteravis {feed['name']}.",
                        signals=[],
                        created_at=now_utc(),
                        kind="schibsted",
                        target_relevance="middels",
                        finding=f"{feed['name']}: «{title[:110]}»",
                        data_source=f"{feed['name']} (Schibsted)",
                        data_url=getattr(entry, "link", ""),
                        coverage_query=title[:80],
                    )
                )
                kept += 1
                if kept >= 6:  # begrens per avis
                    break
            status.append(f"Schibsted {feed['name']}: {kept} gjenbruks-ideer")
        except Exception as exc:  # noqa: BLE001 - fail-soft per feed
            status.append(f"[FEIL] Schibsted {feed['name']}: {type(exc).__name__}")

    return cases, status
