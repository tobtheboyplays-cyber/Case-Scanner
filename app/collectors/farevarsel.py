"""Meteorologisk institutts farevarsler for Stavanger-omraadet.

Eieren 26.07.2026: «mer kilde mer. Masse nyheter» og «redaktoeren sjekker
kvaliteten og analytikeren».

## Et aerlig forbehold, sagt én gang

Denne kilden gir **hurtighet, ikke eksklusivitet**. Et farevarsel fra MET er det
ene enhver redaksjon i landet allerede faar dyttet paa seg - Case-radar finner
det ikke foerst. Verdien ligger et annet sted: varselet kommer inn med *omraade*,
*varighet*, *konsekvenser* og *raad* ferdig formulert av meteorologene, saa
journalisten kan gaa rett paa de lokale foelgene i stedet for aa lete etter hva
varselet egentlig sier.

Det er redaktoeren som avgjor om det er verdt en plass. Kollektorens jobb er at
tallet og teksten er riktige naar den gjor det.

## Lovligheten, sjekket 26.07.2026

`api.met.no/robots.txt` har `User-agent: *` med tom `Disallow:` - alt er tillatt.
(Googlebot er stengt ute fra `/weatherapi/*`, men det gjelder bare Google.) MET
krever en identifiserbar `User-Agent` med kontaktadresse; den staar i
`config.py` og foelger med hvert kall.

## Hvorfor tre punkter og ikke ett

Varslene er MultiPolygon-omraader, og API-et filtrerer paa punkt. Et varsel som
dekker Jaeren treffer ikke noedvendigvis et punkt i Stavanger sentrum. Tre
punkter - Stavanger, Sandnes og Sola - fanger storbyomraadet uten aa dra inn hele
Rogaland. Samme varsel som treffer flere punkter, telles bare én gang (`id`).

## Terskelen

Ingen kunstig terskel er noedvendig: MET sender bare ut varsel naar det ER noe.
Men gule varsler om «lokalt kraftige regnbyger» kommer ofte, saa `MIN_NIVAA`
holder det paa oransje og roedt med mindre alvorlighetsgraden sier noe annet.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx

from app.models import Case

API = "https://api.met.no/weatherapi/metalerts/2.0/current.json"
SIDE = "https://www.yr.no/nb/farevarsler"

TEMAER_MINE = {"natur og miljø", "transport og reiseliv"}

# Storbyomraadet, som punkter. API-et filtrerer paa koordinat, ikke paa kommune.
PUNKTER = [
    ("Stavanger", 58.970, 5.731),
    ("Sandnes", 58.853, 5.735),
    ("Sola", 58.884, 5.617),
]

# MET bruker gult/oransje/roedt. Gult er hverdagslig i Rogaland om hoesten;
# oransje betyr at folk faktisk maa gjore noe annerledes.
NIVAA_RANG = {"green": 0, "yellow": 1, "orange": 2, "red": 3}
MIN_NIVAA = 2

# Alvorlighetsgrad fra CAP-standarden. Et «Severe»-varsel slipper gjennom selv om
# fargen er gul - de to skalaene maaler ikke helt det samme.
ALVOR_SLIPPER = {"Severe", "Extreme"}


# Farge -> ord folk bruker. `awareness_level` kommer som «3; orange; Severe»,
# og det er en intern kode, ikke noe som skal staa paa et saksforslag.
NIVAA_NAVN = {0: "grønt nivå", 1: "gult nivå", 2: "oransje nivå", 3: "rødt nivå"}


def _nivaa(p: dict) -> int:
    """«3; orange; Severe» -> 2. Feltet er en tekst med tre ledd, ikke et tall.

    Merk at MET-tallet foran (2 = gult, 3 = oransje) IKKE er det samme som
    rangen her; vi leser fargeordet, som er entydig.
    """
    raa = str(p.get("awareness_level") or "").lower()
    for navn, rang in NIVAA_RANG.items():
        if navn in raa:
            return rang
    return 0


def _hent(lat: float, lon: float) -> list[dict]:
    svar = httpx.get(
        API,
        params={"lat": lat, "lon": lon},
        timeout=20,
        # MET krever en identifiserbar klient med kontaktadresse. Uten den
        # svarer de 403, og det ser ut som om det ikke er varsler.
        headers={"User-Agent": "case-radar/0.1 (github.com/tobtheboyplays-cyber)"},
    )
    svar.raise_for_status()
    return svar.json().get("features") or []


def collect(temaer: list[str] | None = None) -> tuple[list[Case], list[str]]:
    """Ett lead per aktivt farevarsel over terskelen. Fail-soft."""
    if temaer and not (TEMAER_MINE & set(temaer)):
        return [], ["Farevarsel: hoppet over (utenfor temavalget)"]

    sett: dict[str, dict] = {}
    steder: dict[str, set[str]] = {}
    feil = 0
    for navn, lat, lon in PUNKTER:
        try:
            for f in _hent(lat, lon):
                p = f.get("properties") or {}
                vid = str(p.get("id") or p.get("title") or "")
                if not vid:
                    continue
                # Samme varsel treffer ofte flere av punktene. Vi vil ha det
                # ÉN gang, men huske hvilke byer det gjelder.
                sett.setdefault(vid, p)
                steder.setdefault(vid, set()).add(navn)
        except Exception:  # noqa: BLE001 - kilden er en bonus, aldri et krav
            feil += 1

    if feil == len(PUNKTER):
        return [], ["[FEIL] Farevarsel: MET svarte ikke"]

    status = [f"Farevarsel: {len(sett)} aktive varsler for storbyområdet"]
    if feil:
        status.append(f"Farevarsel: {feil} av {len(PUNKTER)} punkter svarte ikke")

    over = [
        (vid, p) for vid, p in sett.items()
        if _nivaa(p) >= MIN_NIVAA or str(p.get("severity")) in ALVOR_SLIPPER
    ]
    if not over:
        status.append("Farevarsel: ingen over gult nivå — ingen sak")
        return [], status

    # Det alvorligste foerst. Er to like, tar vi det med lengst varighet.
    vid, p = max(over, key=lambda x: (_nivaa(x[1]), str(x[1].get("eventEndingTime") or "")))
    byer = ", ".join(sorted(steder.get(vid, {"Stavanger"})))
    hendelse = p.get("eventAwarenessName") or p.get("event") or "Farevarsel"
    omraade = p.get("area") or byer

    # MET skriver tre felt vi kan bruke ordrett: hva som skjer, hva det foerer
    # til, og hva folk boer gjore. Vi limer dem sammen i stedet for aa skrive om
    # - meteorologene er presise med vilje, og en omskriving kan endre meningen.
    biter = [str(p.get("description") or "").strip()]
    if p.get("consequences"):
        biter.append("Konsekvenser: " + str(p["consequences"]).strip())
    if p.get("instruction"):
        biter.append("Råd fra MET: " + str(p["instruction"]).strip())
    funn = " ".join(b for b in biter if b)

    slutt = str(p.get("eventEndingTime") or "")[:16].replace("T", " kl. ")

    return [Case(
        # `id` fra MET er stabil per varsel, saa det samme varselet ikke
        # dukker opp som nytt ved hvert skann mens det staar.
        key=f"farevarsel:{vid}",
        title=f"Farevarsel {hendelse.lower()} for {omraade}",
        score=26 + _nivaa(p) * 6,
        geo="lokal",
        topics=["natur og miljø"],
        angle=(
            "Hvem rammes lokalt, og hva gjør kommunen? Ring beredskapsvakta i "
            "Stavanger kommune og Rogaland brann og redning, og sjekk om noe "
            "allerede er stengt eller innstilt."
        ),
        why="Meteorologisk institutt har sendt ut varsel som dekker storbyområdet.",
        signals=[],
        created_at=datetime.now(tz=UTC),
        kind="hendelse",
        finding=funn or f"MET har sendt ut farevarsel for {omraade}.",
        metric_value=NIVAA_NAVN.get(_nivaa(p), str(p.get("severity") or "")),
        metric_period=f"gjelder til {slutt}" if slutt else "",
        data_source="Meteorologisk institutt (MetAlerts)",
        data_url=SIDE,
        coverage_query=f"farevarsel {hendelse} {byer}",
    )], status
