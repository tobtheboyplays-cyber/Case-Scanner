"""Reddit-kollektor via offentlig JSON (gratis, ingen API-nokkel).

Krever en realistisk User-Agent, ellers svarer Reddit 429/403.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.collectors.base import http_get
from app.config import SUBREDDITS
from app.models import SignalItem


def collect() -> tuple[list[SignalItem], list[str]]:
    signals: list[SignalItem] = []
    status: list[str] = []

    for sr in SUBREDDITS:
        url = f"https://www.reddit.com/r/{sr['sub']}/hot.json?limit=25"
        try:
            resp = http_get(url, headers={"Accept": "application/json"})
            data = resp.json()
            count = 0
            for child in data.get("data", {}).get("children", []):
                post = child.get("data", {})
                if post.get("stickied"):
                    continue
                title = (post.get("title") or "").strip()
                if not title:
                    continue
                created = post.get("created_utc", 0)
                signals.append(
                    SignalItem(
                        source=sr["name"],
                        source_type="reddit",
                        title=title,
                        url="https://www.reddit.com" + post.get("permalink", ""),
                        published=datetime.fromtimestamp(created, tz=timezone.utc),
                        summary=(post.get("selftext") or "")[:400],
                        geo="nasjonal",  # avgjores av innhold i scoring
                        outlet_local=sr["geo"] == "lokal",
                        score=int(post.get("score", 0)),
                    )
                )
                count += 1
            status.append(f"{sr['name']}: {count} poster")
        except Exception as exc:  # noqa: BLE001 - fail-soft per subreddit
            status.append(f"[FEIL] {sr['name']}: {type(exc).__name__}")

    return signals, status
