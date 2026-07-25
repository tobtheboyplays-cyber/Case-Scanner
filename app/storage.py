"""Enkel SQLite-lagring av siste skann (stdlib, ingen ORM-avhengighet).

Vi lagrer hvert skann som en JSON-blob slik at dashboardet kan vise siste
resultat uten a hente kilder paa nytt ved hver sidelast.
"""

from __future__ import annotations

import json
import os
import sqlite3
from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from app.config import DB_PATH


def _connect() -> sqlite3.Connection:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS scans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            payload TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS approved (
            key TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            payload TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS decisions (
            key TEXT PRIMARY KEY,
            status TEXT NOT NULL
        )
        """
    )
    # Redaksjonell kalender: planlagt publiseringsdato + status per godkjent sak.
    # Lagt til med ALTER slik at eksisterende databaser oppgraderes uten tap.
    cols = {row[1] for row in conn.execute("PRAGMA table_info(approved)")}
    if "planned_for" not in cols:
        conn.execute("ALTER TABLE approved ADD COLUMN planned_for TEXT")
    if "start_date" not in cols:
        conn.execute("ALTER TABLE approved ADD COLUMN start_date TEXT")
    if "deadline" not in cols:
        conn.execute("ALTER TABLE approved ADD COLUMN deadline TEXT")
    # Eldre rader hadde bare planned_for - la den bli startdato.
    conn.execute(
        "UPDATE approved SET start_date = planned_for "
        "WHERE start_date IS NULL AND planned_for IS NOT NULL"
    )
    if "stage" not in cols:
        conn.execute("ALTER TABLE approved ADD COLUMN stage TEXT NOT NULL DEFAULT 'ide'")
    conn.commit()
    return conn


def save_scan(payload: dict) -> None:
    payload = {**payload, "created_at": datetime.now(tz=timezone.utc).isoformat()}
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO scans (created_at, payload) VALUES (?, ?)",
            (payload["created_at"], json.dumps(payload, ensure_ascii=False)),
        )
        conn.commit()
    finally:
        conn.close()


def load_latest() -> dict | None:
    if not os.path.exists(DB_PATH):
        return None
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT payload FROM scans ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return json.loads(row[0]) if row else None
    finally:
        conn.close()


def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def approve_lead(key: str, lead: dict) -> None:
    conn = _connect()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO approved (key, created_at, payload) VALUES (?, ?, ?)",
            (key, _now(), json.dumps(lead, ensure_ascii=False)),
        )
        conn.execute(
            "INSERT OR REPLACE INTO decisions (key, status) VALUES (?, 'approved')", (key,)
        )
        conn.commit()
    finally:
        conn.close()


def reject_lead(key: str) -> None:
    conn = _connect()
    try:
        conn.execute("DELETE FROM approved WHERE key = ?", (key,))
        conn.execute(
            "INSERT OR REPLACE INTO decisions (key, status) VALUES (?, 'rejected')", (key,)
        )
        conn.commit()
    finally:
        conn.close()


def list_approved() -> list[dict]:
    if not os.path.exists(DB_PATH):
        return []
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT payload, created_at, start_date, deadline, stage FROM approved "
            "ORDER BY COALESCE(deadline, start_date, created_at) ASC"
        ).fetchall()
        out = []
        for payload, created, start, deadline, stage in rows:
            lead = json.loads(payload)
            lead["_approved_at"] = created
            lead["_start"] = start or ""
            lead["_deadline"] = deadline or ""
            lead["_stage"] = stage or "ide"
            out.append(lead)
        return out
    finally:
        conn.close()


# ── Redaksjonell kalender ────────────────────────────────────────────────────
# Stadier en sak gaar gjennom. Rekkefolgen er bevisst: den speiler arbeidsflyten
# i en redaksjon, og UI-et bruker samme rekkefolge.
STAGES: tuple[str, ...] = ("ide", "research", "skriving", "publisert")
STAGE_LABELS: dict[str, str] = {
    "ide": "Idé",
    "research": "Research",
    "skriving": "Skriving",
    "publisert": "Publisert",
}


def set_plan(
    key: str,
    *,
    start_date: str | None = None,
    deadline: str | None = None,
    stage: str | None = None,
) -> None:
    """Sett startdato, deadline og/eller stadium for en godkjent sak.

    Tom streng fjerner datoen. Ugyldige datoer ignoreres i stedet for aa kaste -
    UI skal aldri kunne laase seg paa en skrivefeil. Er deadline foer start,
    byttes de om: det er aapenbart hva brukeren mente."""
    def _clean(v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if not v:
            return ""
        try:
            date.fromisoformat(v)
        except ValueError:
            return None
        return v

    s, d = _clean(start_date), _clean(deadline)
    if s and d and d < s:
        s, d = d, s

    conn = _connect()
    try:
        if s is not None:
            conn.execute(
                "UPDATE approved SET start_date = ?, planned_for = ? WHERE key = ?",
                (s or None, s or None, key),
            )
        if d is not None:
            conn.execute("UPDATE approved SET deadline = ? WHERE key = ?", (d or None, key))
        if stage is not None and stage in STAGES:
            conn.execute("UPDATE approved SET stage = ? WHERE key = ?", (stage, key))
        conn.commit()
    finally:
        conn.close()


def calendar_month(year: int, month: int) -> dict[str, list[dict]]:
    """Godkjente saker plassert paa hver dag de er i arbeid.

    En sak med start 3. og deadline 6. vises paa 3, 4, 5 OG 6 - slik at kalenderen
    faktisk viser arbeidsbelastning, ikke bare to prikker. Hver oppfoering merkes
    med om dagen er start, deadline, begge, eller midt i loepet."""
    out: dict[str, list[dict]] = {}
    last_day = monthrange(year, month)[1]
    month_start = date(year, month, 1)
    month_end = date(year, month, last_day)

    for lead in list_approved():
        s_raw, d_raw = lead.get("_start") or "", lead.get("_deadline") or ""
        if not s_raw and not d_raw:
            continue
        try:
            start = date.fromisoformat(s_raw) if s_raw else date.fromisoformat(d_raw)
            end = date.fromisoformat(d_raw) if d_raw else start
        except ValueError:
            continue
        if end < start:
            start, end = end, start
        # Klipp til maaneden vi viser.
        span_start = max(start, month_start)
        span_end = min(end, month_end)
        if span_start > span_end:
            continue
        day = span_start
        while day <= span_end:
            iso = day.isoformat()
            out.setdefault(iso, []).append(
                {
                    **lead,
                    "_is_start": day == start,
                    "_is_deadline": day == end,
                }
            )
            day += timedelta(days=1)
    return out


def decisions_map() -> dict[str, str]:
    """{key: "approved"|"rejected"} for aa vise status paa radaren."""
    if not os.path.exists(DB_PATH):
        return {}
    conn = _connect()
    try:
        rows = conn.execute("SELECT key, status FROM decisions").fetchall()
        return {k: s for k, s in rows}
    finally:
        conn.close()
