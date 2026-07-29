"""Planlegger: gjor caser + kalender om til konkrete "gjor dette"-forslag.

Prototypen fungerer HELT uten Google-kalender. Hvis kalender er koblet til,
beriker vi planen med kommende avtaler; hvis ikke, foreslaar vi ut fra casene.
"""

from __future__ import annotations

from app.calendar_google import get_calendar_status, list_upcoming_events
from app.models import Case


def build_plan(cases: list[Case]) -> dict:
    """Lag en enkel ukeplan-liste + kalenderstatus."""
    suggestions: list[dict] = []

    # Topp lokale caser -> feltarbeid-forslag.
    local_cases = [c for c in cases if c.geo == "lokal"][:5]
    for c in local_cases:
        suggestions.append(
            {
                "type": "case",
                "title": f"Følg opp: {c.title}",
                "action": c.angle,
                "priority": "høy" if c.score >= 12 else "medium",
            }
        )

    # Fyll paa med sterke nasjonale caser hvis faa lokale.
    if len(suggestions) < 4:
        for c in [c for c in cases if c.geo == "nasjonal"][: 4 - len(suggestions)]:
            suggestions.append(
                {
                    "type": "case",
                    "title": f"Vurder lokal vinkel: {c.title}",
                    "action": c.angle,
                    "priority": "medium",
                }
            )

    events, cal_note = list_upcoming_events()
    return {
        "suggestions": suggestions,
        "calendar_events": events,
        "calendar_status": get_calendar_status(),
        "calendar_note": cal_note,
    }
