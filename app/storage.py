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
            "SELECT payload, created_at FROM approved ORDER BY created_at DESC"
        ).fetchall()
        out = []
        for payload, created in rows:
            lead = json.loads(payload)
            lead["_approved_at"] = created
            out.append(lead)
        return out
    finally:
        conn.close()


def decisions_map() -> dict[str, str]:
    if not os.path.exists(DB_PATH):
        return {}
    conn = _connect()
    try:
        rows = conn.execute("SELECT key, status FROM decisions").fetchall()
        return {k: s for k, s in rows}
    finally:
        conn.close()
