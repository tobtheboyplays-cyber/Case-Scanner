"""Google Calendar-integrasjon (valgfri, read-only i prototypen).

Uten credentials.json kjorer appen helt fint - da returnerer vi bare en
statusmelding om at kalender ikke er koblet til. Skriving til kalender er
bevisst holdt UTENFOR prototypen (fail-safe).
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from app.config import GOOGLE_CREDENTIALS_FILE, GOOGLE_TOKEN_FILE

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]


def get_calendar_status() -> str:
    if not os.path.exists(GOOGLE_CREDENTIALS_FILE):
        return "ikke_konfigurert"
    if not os.path.exists(GOOGLE_TOKEN_FILE):
        return "trenger_innlogging"
    return "koblet_til"


def list_upcoming_events(max_results: int = 10) -> tuple[list[dict], str]:
    """Returner (events, note). Fail-soft: aldri kast oppover."""
    status = get_calendar_status()
    if status == "ikke_konfigurert":
        return [], (
            "Google Calendar ikke konfigurert. Legg credentials.json i mappen "
            "for a aktivere (se README). Prototypen fungerer uten."
        )

    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except Exception:  # noqa: BLE001
        return [], "Google-bibliotek ikke installert (pip install '.[calendar]')."

    try:
        creds = None
        if os.path.exists(GOOGLE_TOKEN_FILE):
            creds = Credentials.from_authorized_user_file(GOOGLE_TOKEN_FILE, SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    GOOGLE_CREDENTIALS_FILE, SCOPES
                )
                creds = flow.run_local_server(port=0)
            with open(GOOGLE_TOKEN_FILE, "w", encoding="utf-8") as fh:
                fh.write(creds.to_json())

        service = build("calendar", "v3", credentials=creds)
        now = datetime.now(tz=timezone.utc).isoformat()
        result = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=now,
                maxResults=max_results,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        events = []
        for ev in result.get("items", []):
            start = ev.get("start", {})
            events.append(
                {
                    "summary": ev.get("summary", "(uten tittel)"),
                    "start": start.get("dateTime", start.get("date", "")),
                    "location": ev.get("location", ""),
                }
            )
        return events, f"{len(events)} kommende avtaler hentet."
    except Exception as exc:  # noqa: BLE001 - fail-soft
        return [], f"Kunne ikke hente kalender: {type(exc).__name__}."
