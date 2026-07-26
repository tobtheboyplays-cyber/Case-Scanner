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
    ssb,
    ssb_flytting,
    ssb_kalender,
    ssb_sok,
)
from app.config import ENABLE_REDDIT
from app.models import Case, SignalItem


def collect_all(
    si: Callable[[str], None] | None = None, temaer: list[str] | None = None
) -> tuple[list[SignalItem], list[Case], list[str]]:
    """Returnerer (grasrot-signaler, ssb-leads, statuslinjer).

    `temaer` er journalistens valg; det styrer hvilke SSB-tabeller soekesystemet
    leter etter. Tomt valg = alle temaer.

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
        cases, notes = ssb_sok.collect(temaer)
        ssb_cases.extend(cases)
        status.extend(notes)
    except Exception as exc:  # noqa: BLE001
        status.append(f"[FEIL] SSB-soek: {exc}")

    # Her laa det EN GANG en kollektor som hentet saker fra Aftenposten, Bergens
    # Tidende og E24 og gjorde dem til leads. Den er slettet, ikke skrudd av.
    #
    # Eieren 26.07.2026: «Den skal bruke kilder som kan LAGE artikler, ikke
    # artikler for aa lage artikler.» En avissak er noen andres ferdige jobb; en
    # SSB-tabell og et konkursvedtak er raastoff ingen har skrevet ut enda.
    #
    # Det kostet ogsaa mer enn plass: redaktoer og journalist rekker fire saker
    # per skann, og hver gjenbrukte avissak stjal en av de fire plassene fra et
    # ekte funn.
    #
    # Avisartikler brukes fortsatt ETT sted - i dekningssjekken (coverage.py),
    # som svarer «har noen allerede skrevet dette?». Det er aa bruke dem som
    # fasit, ikke som raastoff, og det er riktig bruk.

    # 2) Grasrot-signaler (klynges i scoring). Reddit er av som standard - se
    # config.ENABLE_REDDIT for hvorfor.
    kilder = [("Google Trends", google_trends.collect)]
    if ENABLE_REDDIT:
        kilder.insert(0, ("Reddit", reddit.collect))
    else:
        status.append(
            "Reddit: av (anonymt API stengt av Reddit) - "
            "skru paa med CASE_RADAR_ENABLE_REDDIT=true"
        )
    for name, fn in kilder:
        meld(name)
        try:
            items, notes = fn()
            signals.extend(items)
            status.extend(notes)
        except Exception as exc:  # noqa: BLE001
            status.append(f"[FEIL] {name}: {exc}")

    return signals, ssb_cases, status
