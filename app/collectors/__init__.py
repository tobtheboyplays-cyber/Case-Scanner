"""Kollektorer henter raadata og produserer leads.

v2-pipeline:
- SSB (ssb.py) gir ferdige DATADREVNE leads (Case-objekter) - primaerkilden.
- SSB-kalenderen (ssb_kalender.py) varsler om tall som IKKE er publisert enda -
  det eneste ekte forspranget i verktoyet.
- Reddit + Google Trends gir raa SignalItems (grasrot) som klynges i scoring.
- Nyhets-RSS genererer IKKE lenger caser; dekning sjekkes via coverage.py
  (Google News) per lead.

Alle kollektorer er "fail-soft": en kilde som er nede stopper ikke resten.
"""

from __future__ import annotations

from app.collectors import (
    google_trends,
    reddit,
    schibsted,
    ssb,
    ssb_flytting,
    ssb_kalender,
)
from app.models import Case, SignalItem


def collect_all() -> tuple[list[SignalItem], list[Case], list[str]]:
    """Returnerer (grasrot-signaler, ssb-leads, statuslinjer)."""
    signals: list[SignalItem] = []
    ssb_cases: list[Case] = []
    status: list[str] = []

    # 1) SSB - datadrevne leads (Case-objekter)
    try:
        cases, notes = ssb.collect()
        ssb_cases.extend(cases)
        status.extend(notes)
    except Exception as exc:  # noqa: BLE001
        status.append(f"[FEIL] SSB: {exc}")

    # 1a) Kvartalsvise flyttetall - ferskere enn aarsstatistikken og en annen
    # type sak (bevegelsene bak befolkningstallet).
    try:
        cases, notes = ssb_flytting.collect()
        ssb_cases.extend(cases)
        status.extend(notes)
    except Exception as exc:  # noqa: BLE001
        status.append(f"[FEIL] SSB flytting: {exc}")

    # 1b) Schibsted-soesteraviser - gjenbruks-leads (Case-objekter)
    try:
        cases, notes = schibsted.collect()
        ssb_cases.extend(cases)
        status.extend(notes)
    except Exception as exc:  # noqa: BLE001
        status.append(f"[FEIL] Schibsted: {exc}")

    # 2) Grasrot-signaler (klynges i scoring)
    for name, fn in (("Reddit", reddit.collect), ("Google Trends", google_trends.collect)):
        try:
            items, notes = fn()
            signals.extend(items)
            status.extend(notes)
        except Exception as exc:  # noqa: BLE001
            status.append(f"[FEIL] {name}: {exc}")

    return signals, ssb_cases, status
