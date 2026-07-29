"""Stortinget: hva Rogalands egne representanter holder paa med.

Eieren 26.07.2026: «Finn flere kilder vi kan soeke igjennom som er gratis og kan
gi noe.»

Dette er den kilden som faktisk besto proeven. Kandidatene og hvorfor de falt fra
staar i docs/KILDER.md - kort: de fleste er enten stengt for roboter, avviklet
eller flyttet uten aa etterlate en fungerende adresse.

`data.stortinget.no` har `Allow: /` i robots.txt, krever ingen noekkel, ingen
kvote, og svarer JSON. Verifisert 26.07.2026:

    /eksport/saker?sesjonid=2025-2026     -> alle saker i sesjonen
    /eksport/dagensrepresentanter          -> 169 representanter, med fylke

DEN JOURNALISTISKE VINKELEN, og grunnen til at dette ikke bare er «nasjonalt
stoff»: fjorten av representantene er valgt fra Rogaland. Er én av dem
saksordfoerer eller forslagsstiller, er en riksdekkende sak ogsaa en LOKAL sak -
med en navngitt kilde som har telefonnummer og plikt til aa svare. «Margret
Hagerup (H) fra Rogaland er saksordfoerer for X» er en sak man kan ringe paa i
dag, ikke et tall man maa lete etter noen som merker.

Vi lager BARE leads av saker som enten har en Rogaland-representant paa seg
eller nevner noe lokalt i tittelen. Uten det filteret ville dette vaert 1 200
nasjonale saker i en radar for Stavanger.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

from app.collectors.base import http_get
from app.models import Case

API = "https://data.stortinget.no/eksport"
FYLKE = "Rogaland"

# Hvor gammelt et lead faar vaere. Maalt 26.07.2026: nyeste oppdaterte sak var
# 31 dager gammel og medianen 89 - Stortinget har sommerferie fra juni til
# oktober. Et vindu paa 30 dager ga derfor NULL treff hele sommeren, altsaa
# nettopp naar journalisten har minst annet aa skrive om.
#
# 120 dager dekker feriegapet. Scoren faller med alderen (se `_case`), saa en
# fersk sak slaar en gammel - men en gammel forsvinner ikke helt, for «hva ble
# det av forslaget representanten din fremmet i mai?» er ogsaa en sak.
DAGER = 120

# Ord som gjor en nasjonal sak lokal ogsaa naar ingen Rogaland-representant staar
# paa den. Holdt kort med vilje - «olje» og «energi» treffer halve Stortinget, og
# da er filteret ikke et filter lenger.
LOKALE_ORD = (
    "rogaland", "stavanger", "sandnes", "jæren", "jaeren", "haugesund",
    "nord-jæren", "ryfylke", "dalane", "sola", "randaberg", "eigersund",
)

# Temaet i menyen som denne kilden hoerer under. Har journalisten huket av noe
# helt annet, skal ikke Stortinget ta plassen hans - samme regel som for SSB og
# Broennoeysund.
TEMA = "valg og politikk"

MAKS = 8


def _dato(raa: str) -> datetime | None:
    """«/Date(1782338400000+0200)/» -> datetime. Stortinget bruker det gamle
    .NET-formatet, ikke ISO."""
    m = re.search(r"/Date\((-?\d+)", raa or "")
    if not m:
        return None
    try:
        return datetime.fromtimestamp(int(m.group(1)) / 1000, tz=UTC)
    except (ValueError, OSError, OverflowError):
        return None


def _navn(person: dict) -> str:
    return f"{person.get('fornavn', '')} {person.get('etternavn', '')}".strip()


def rogalandsbenken() -> dict[str, dict]:
    """{representant-id: {navn, parti}} for dem som er valgt fra Rogaland."""
    svar = http_get(f"{API}/dagensrepresentanter?format=json", timeout=25).json()
    ut = {}
    for r in svar.get("dagensrepresentanter_liste") or []:
        if (r.get("fylke") or {}).get("navn") != FYLKE:
            continue
        ut[r.get("id", "")] = {
            "navn": _navn(r),
            "parti": (r.get("parti") or {}).get("navn", ""),
        }
    return ut


def _lokal(tittel: str) -> bool:
    t = (tittel or "").lower()
    return any(o in t for o in LOKALE_ORD)


def _rolle(sak: dict, benk: dict[str, dict]) -> tuple[str, dict] | None:
    """Hvilken Rogaland-representant er paa saken, og i hvilken rolle.

    Saksordfoerer foerst: det er den som faktisk skal svare paa hvorfor
    innstillingen ble som den ble, og den mest presise kilden vi kan gi."""
    for felt, rolle in (("saksordfoerer_liste", "saksordfører"),
                        ("forslagstiller_liste", "forslagsstiller")):
        for p in sak.get(felt) or []:
            traff = benk.get(p.get("id", ""))
            if traff:
                return rolle, traff
    return None


def _case(sak: dict, benk: dict[str, dict], oppdatert: datetime) -> Case | None:
    tittel = (sak.get("korttittel") or sak.get("tittel") or "").strip()
    if not tittel:
        return None

    treff = _rolle(sak, benk)
    if treff is None and not _lokal(tittel):
        return None

    dager = (datetime.now(tz=UTC) - oppdatert).days
    emner = [e.get("navn", "") for e in (sak.get("emne_liste") or []) if e.get("navn")]
    sak_id = sak.get("id")

    if treff:
        rolle, rep = treff
        overskrift = f"{rep['navn']} ({rep['parti']}) er {rolle} for saken om {tittel.lower()}"
        funn = (
            f"{rep['navn']} fra Rogaland ({rep['parti']}) staar som {rolle} for "
            f"«{tittel}». Saken ble sist oppdatert paa Stortinget for {dager} dager siden"
            f"{' - ' + sak.get('henvisning', '') if sak.get('henvisning') else ''}."
        )
        # En navngitt lokal kilde med svarplikt er det som gjor dette til et
        # lead og ikke et referat.
        # Fersk sak slaar gammel, men ingen faller under halv verdi: en
        # navngitt kilde med svarplikt er verdt noe uansett alder.
        forfall = max(0.5, 1.0 - dager / 240)
        score = (30 if rolle == "saksordfører" else 24) * forfall
        vinkel = (
            f"Ring {rep['navn']} og spoer hva saken betyr for Rogaland - "
            f"han/hun er {rolle} og skal kunne svare."
        )
    else:
        overskrift = f"Stortinget behandler en sak om {tittel.lower()}"
        funn = (
            f"«{tittel}» ligger til behandling paa Stortinget. Sist oppdatert for "
            f"{dager} dager siden. Tittelen nevner Rogaland eller en kommune her."
        )
        score = 18 * max(0.5, 1.0 - dager / 240)
        vinkel = "Sjekk hva saken konkret betyr for kommunen, og hvem her som blir beroert."

    return Case(
        key=f"stortinget:{sak_id}",
        title=overskrift[:150],
        score=score,
        geo="lokal",
        topics=[TEMA] + emners_tema(emner),
        angle=vinkel,
        why=f"Sist oppdatert paa Stortinget for {dager} dager siden.",
        signals=[],
        created_at=datetime.now(tz=UTC),
        kind="hendelse",
        finding=funn,
        # `metric_value` er STORE TALL i malen (30-40 px). En henvisning som
        # «Dokument 12:9 (2023-2024)» hoerer ikke hjemme der - den er en
        # referanse, ikke et maal, og den brakk mobilvisningen (se
        # static/style.css, .metric-v). Henvisningen staar i `metric_period`,
        # som er den lille graa linja ved siden av.
        metric_value="",
        metric_period=(sak.get("henvisning") or "").strip()
        or oppdatert.date().isoformat(),
        data_source="Stortinget (data.stortinget.no)",
        data_url=f"https://www.stortinget.no/no/Saker-og-publikasjoner/Saker/Sak/?p={sak_id}",
        coverage_query=f"Stortinget {tittel}",
    )


def emners_tema(emner: list[str]) -> list[str]:
    """Stortingets egne emneord, som de er. De er allerede lesbare paa norsk, og
    aa mappe dem til vaare egne temaer ville lagt til en oversettelse ingen har
    bedt om - og en feilkilde."""
    return [e.lower() for e in emner[:2]]


def collect(temaer: list[str] | None = None) -> tuple[list[Case], list[str]]:
    """Saker fra Stortinget med en lokal krok. Fail-soft som alle kollektorer."""
    if temaer and TEMA not in temaer:
        return [], ["Stortinget: hoppet over (utenfor temavalget)"]

    status: list[str] = []
    try:
        benk = rogalandsbenken()
    except Exception as exc:  # noqa: BLE001 - kilden er en bonus, aldri et krav
        return [], [f"[FEIL] Stortinget (representanter): {type(exc).__name__}"]

    # Sesjonen loeper fra oktober til oktober, saa den «gjeldende» skifter navn
    # midt i aaret. Vi regner den ut i stedet for aa hardkode - ellers slutter
    # kilden aa virke en tilfeldig dag i oktober, uten at noen skjonner hvorfor.
    naa = datetime.now(tz=UTC)
    start = naa.year if naa.month >= 10 else naa.year - 1
    sesjon = f"{start}-{start + 1}"

    try:
        svar = http_get(f"{API}/saker?sesjonid={sesjon}&format=json", timeout=25).json()
    except Exception as exc:  # noqa: BLE001
        return [], [f"[FEIL] Stortinget (saker): {type(exc).__name__}"]

    saker = svar.get("saker_liste") or []
    grense = naa - timedelta(days=DAGER)
    cases: list[Case] = []
    for sak in saker:
        oppdatert = _dato(sak.get("sist_oppdatert_dato", ""))
        if oppdatert is None or oppdatert < grense:
            continue
        c = _case(sak, benk, oppdatert)
        if c:
            cases.append(c)

    cases.sort(key=lambda c: -c.score)
    status.append(
        f"Stortinget: {len(benk)} representanter fra {FYLKE}, "
        f"{len(saker)} saker i sesjon {sesjon}, {len(cases)} med lokal krok"
    )
    return cases[:MAKS], status
