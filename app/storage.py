"""Enkel SQLite-lagring av siste skann (stdlib, ingen ORM-avhengighet).

Vi lagrer hvert skann som en JSON-blob slik at dashboardet kan vise siste
resultat uten a hente kilder paa nytt ved hver sidelast.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
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
            "SELECT payload, created_at, planned_for, stage FROM approved "
            "ORDER BY created_at DESC"
        ).fetchall()
        out = []
        for payload, created, planned, stage in rows:
            lead = json.loads(payload)
            lead["_approved_at"] = created
            lead["_planned_for"] = planned or ""
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


def set_plan(key: str, *, planned_for: str | None = None, stage: str | None = None) -> None:
    """Sett planlagt dato (YYYY-MM-DD) og/eller stadium for en godkjent sak.

    Tom streng for planned_for fjerner datoen (saken blir uplanlagt igjen).
    Ugyldig stadium ignoreres i stedet for aa kaste - UI skal aldri kunne
    laase seg paa en skrivefeil."""
    conn = _connect()
    try:
        if planned_for is not None:
            value = planned_for.strip() or None
            if value is not None:
                # Fail-safe: bare ekte ISO-datoer lagres.
                try:
                    date.fromisoformat(value)
                except ValueError:
                    value = None
            conn.execute("UPDATE approved SET planned_for = ? WHERE key = ?", (value, key))
        if stage is not None and stage in STAGES:
            conn.execute("UPDATE approved SET stage = ? WHERE key = ?", (stage, key))
        conn.commit()
    finally:
        conn.close()


def calendar_month(year: int, month: int) -> dict[str, list[dict]]:
    """Godkjente saker gruppert paa planlagt dato for én maaned.

    Returnerer {"YYYY-MM-DD": [sak, ...]}. Saker uten planlagt dato er ikke med
    her - de vises som "uplanlagt" i UI slik at de ikke blir borte."""
    prefix = f"{year:04d}-{month:02d}-"
    out: dict[str, list[dict]] = {}
    for lead in list_approved():
        day = lead.get("_planned_for") or ""
        if day.startswith(prefix):
            out.setdefault(day, []).append(lead)
    return out


def decisions_map() -> dict[str, str]:
    if not os.path.exists(DB_PATH):
        return {}
    conn = _connect()
    try:
        rows = conn.execute("SELECT key, status FROM decisions").fetchall()
        return {k: s for k, s in rows}
    finally:
        conn.close()
