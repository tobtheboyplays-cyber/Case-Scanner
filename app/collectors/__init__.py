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
    farevarsel,
    google_trends,
    kolumbus,
    reddit,
    ssb,
    ssb_flytting,
    ssb_kalender,
    sola,
    ssb_sok,
    stortinget,
    strompris,
    vegtrafikk,
)
from app.config import ENABLE_REDDIT
from app.models import Case, SignalItem


def collect_all(
    si: Callable[[str], None] | None = None, temaer: list[str] | None = None
) -> tuple[list[SignalItem], list[Case], list[str]]:
    """Returnerer (grasrot-signaler, ssb-leads, statuslinjer).

    `temaer` er journalistens valg, og det styrer ALLE SSB-kildene: hvilke faste
    befolkningsprober som kjores (ssb), om flyttetallene er relevante
    (ssb_flytting), og hva soekesystemet leter etter (ssb_sok). Tomt valg = alle.

    Fram til 26.07.2026 leste bare soekesystemet valget. De faste probene kjorte
    uansett, scoret hoyt, og la seg oeverst - saa menyen saa ut som pynt.

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
        cases, notes = ssb.collect(temaer)
        ssb_cases.extend(cases)
        status.extend(notes)
    except Exception as exc:  # noqa: BLE001
        status.append(f"[FEIL] SSB: {exc}")

    # 1a) Kvartalsvise flyttetall - ferskere enn aarsstatistikken og en annen
    # type sak (bevegelsene bak befolkningstallet).
    meld("SSB: kvartalsvise flyttetall")
    try:
        cases, notes = ssb_flytting.collect(temaer)
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

    # 1c) Stortinget - hva Rogalands egne representanter holder paa med. Eneste
    # av kandidatkildene 26.07.2026 som baade hadde «Allow: /» i robots.txt og
    # faktisk svarte; se docs/KILDER.md for hvem som falt fra og hvorfor.
    # Verdien er ikke det nasjonale stoffet, men at en sak med en
    # Rogaland-representant paa seg gir journalisten en NAVNGITT kilde med
    # svarplikt - i motsetning til et tall han maa finne noen som merker.
    meld("Stortinget: saker med Rogaland-representanter")
    try:
        cases, notes = stortinget.collect(temaer)
        ssb_cases.extend(cases)
        status.extend(notes)
    except Exception as exc:  # noqa: BLE001
        status.append(f"[FEIL] Stortinget: {exc}")

    # 1d) Stroemprisen i NO2 - Stavangers eget prisomraade. Prisen for i morgen
    # settes klokka 13 i dag, saa fra ettermiddagen har vi et tall ingen har
    # skrevet om enda, og som treffer hver husstand i byen.
    meld("Strømpris: NO2 (Stavanger)")
    try:
        cases, notes = strompris.collect(temaer)
        ssb_cases.extend(cases)
        status.extend(notes)
    except Exception as exc:  # noqa: BLE001
        status.append(f"[FEIL] Strømpris: {exc}")

    # 1e) Sola lufthavn. Naar noe stopper opp der, staar folk i avgangshallen
    # akkurat naa - det er en sak man kan ringe paa i loepet av minutter.
    meld("Sola lufthavn: kanselleringer og forsinkelser")
    try:
        cases, notes = sola.collect(temaer)
        ssb_cases.extend(cases)
        status.extend(notes)
    except Exception as exc:  # noqa: BLE001
        status.append(f"[FEIL] Sola: {exc}")

    # 1f) Vegvesenets tellepunkter. Sykkeltallene foerst: 21 punkter i
    # storbyomraadet teller sykler doegn for doegn - blant dem fire paa
    # Sykkelstamvegen - og ingen henter dem ut, fordi de ligger bak et
    # GraphQL-API i stedet for i en pressemelding.
    meld("Vegvesenet: sykkel- og biltellinger")
    try:
        cases, notes = vegtrafikk.collect(temaer)
        ssb_cases.extend(cases)
        status.extend(notes)
    except Exception as exc:  # noqa: BLE001
        status.append(f"[FEIL] Vegtrafikk: {exc}")

    # 1g) Kolumbus i sanntid. Sola svarer paa «staar flyene?»; denne paa det
    # som treffer langt flere hver morgen: staar bussen?
    meld("Kolumbus: innstilte og forsinkede avganger")
    try:
        cases, notes = kolumbus.collect(temaer)
        ssb_cases.extend(cases)
        status.extend(notes)
    except Exception as exc:  # noqa: BLE001
        status.append(f"[FEIL] Kolumbus: {exc}")

    # 1h) MET-farevarsel. Gir hurtighet, ikke eksklusivitet - hele landets
    # redaksjoner faar det samme varselet. Verdien er at konsekvenser og raad
    # foelger med ferdig formulert, saa vinkelen kan gaa rett paa lokale foelger.
    meld("Farevarsel: MET for storbyområdet")
    try:
        cases, notes = farevarsel.collect(temaer)
        ssb_cases.extend(cases)
        status.extend(notes)
    except Exception as exc:  # noqa: BLE001
        status.append(f"[FEIL] Farevarsel: {exc}")

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
