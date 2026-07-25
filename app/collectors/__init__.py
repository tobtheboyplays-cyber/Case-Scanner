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

from collections.abc import Callable

from app.collectors import (
    google_trends,
    reddit,
    schibsted,
    ssb,
    ssb_flytting,
    ssb_kalender,
    ssb_sok,
)
from app.models import Case, SignalItem


def collect_all(si: Callable[[str], None] | None = None) -> tuple[
    list[SignalItem], list[Case], list[str]
]:
    """Returnerer (grasrot-signaler, ssb-leads, statuslinjer).

    `si` er en valgfri tilbakekalling som faar én linje per kilde mens den
    jobber. Uten den oppfoerer alt seg som foer; med den kan UI-et vise hvilken
    kilde som holder paa akkurat naa i stedet for en tom skjerm."""
    signals: list[SignalItem] = []
    ssb_cases: list[Case] = []
    status: list[str] = []

    def meld(tekst: str) -> None:
        if si is not None:
            si(tekst)

    # 1) SSB - datadrevne leads (Case-objekter)
    meld("SSB: befolkningstall")
    try:
        cases, notes = ssb.collect()
        ssb_cases.extend(cases)
        status.extend(notes)
    except Exception as exc:  # noqa: BLE001
        status.append(f"[FEIL] SSB: {exc}")

    # 1a) Kvartalsvise flyttetall - ferskere enn aarsstatistikken og en annen
    # type sak (bevegelsene bak befolkningstallet).
    meld("SSB: kvartalsvise flyttetall")
    try:
        cases, notes = ssb_flytting.collect()
        ssb_cases.extend(cases)
        status.extend(notes)
    except Exception as exc:  # noqa: BLE001
        status.append(f"[FEIL] SSB flytting: {exc}")

    # 1b) Soekesystemet - leter i hele SSB-katalogen etter tabeller vi ikke har
    # provd for. Dette er kilden som gjor at et NYTT soek gir NY statistikk.
    meld("SSB-søk: leter i katalogen etter ny statistikk")
    try:
        cases, notes = ssb_sok.collect()
        ssb_cases.extend(cases)
        status.extend(notes)
    except Exception as exc:  # noqa: BLE001
        status.append(f"[FEIL] SSB-soek: {exc}")

    # 1c) Schibsted-soesteraviser - gjenbruks-leads (Case-objekter)
    meld("Schibsted-søsteraviser")
    try:
        cases, notes = schibsted.collect()
        ssb_cases.extend(cases)
        status.extend(notes)
    except Exception as exc:  # noqa: BLE001
        status.append(f"[FEIL] Schibsted: {exc}")

    # 2) Grasrot-signaler (klynges i scoring)
    for name, fn in (("Reddit", reddit.collect), ("Google Trends", google_trends.collect)):
        meld(name)
        try:
            items, notes = fn()
            signals.extend(items)
            status.extend(notes)
        except Exception as exc:  # noqa: BLE001
            status.append(f"[FEIL] {name}: {exc}")

    return signals, ssb_cases, status
