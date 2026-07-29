"""Statens vegvesens tellepunkter — hvor mange som faktisk kjorer og sykler.

Eieren 26.07.2026: «Flere Stavanger kilder du kan legge til. Fortsettelse fra
Aftenposten.» Altsaa: flere kilder som kan LAGE artikler (se `KILDEREGELEN.md`),
ikke flere ferdige artikler.

Dette er raastoff i reneste form. Vegvesenet teller hver eneste bil og sykkel som
passerer 245 punkter i Rogaland, doegn for doegn, og legger tallene aapent ut i et
GraphQL-API. Ingen skriver om dem, fordi de ligger bak et sporrespraak og ikke i
en pressemelding.

## Hvorfor SYKKEL foerst

21 av punktene i Stavanger-omraadet teller sykler - blant dem fire paa
**Sykkelstamvegen**, som har kostet noermere en milliard og som det har staatt
strid om i ti aar. «Hvor mange sykler faktisk der?» er et spoersmaal med et
konkret tall bak, og tallet er offentlig.

For et publikum paa 20-39 aar i en by med evig bompenge- og sykkeldebatt er dette
naermere hverdagen enn de fleste SSB-tabeller.

## Lovligheten, sjekket 26.07.2026

`trafikkdata-api.atlas.vegvesen.no/robots.txt` svarer `404` - det finnes ingen
robots.txt, altsaa ingen direktiver aa bryte. API-et er Vegvesenets egen aapne
trafikkdata-tjeneste, dokumentert paa <https://trafikkdata.no>, uten noekkel.

## Hva vi lager en sak av, og hva vi lar vaere

Trafikk svinger med vaer, ferie og veiarbeid. En sak hver dag er ikke en sak.
Terskelen er derfor en ENDRING mot samme periode i fjor: minst
`MIN_ENDRING`, maalt over to uker, paa et punkt som teller nok til at tallet
betyr noe (`MIN_SNITT`).

To feller som kostet et forsoek hver, maalt 26.07.2026:

- **Doede punkter svarer med `null`, ikke med feil.** «Kannik (sykkel)» sto som
  `isOperational: true` og ga 14 doegn paa rad uten tall. Uten filteret ville
  kollektoren regnet paa en tom liste.
- **Tallene henger etter.** De siste doegnene er ikke ferdig kvalitetssikret, saa
  vinduet slutter `ETTERSLEP` dager tilbake. Foerste utkast spurte om i gaar og
  fikk et halvt doegn som saa ut som et krasj i trafikken.

Og den tredje, som er den farligste fordi den ser riktig ut:

- **Et doegn kan vaere DELVIS maalt.** Hvert doegn har en `coverage.percentage`.
  Foerste ekte kjoring ga «Sykkelstamvegen 62 % opp mot i fjor» - men flere av
  fjoraarsdoegnene var maalt med 67 % dekning, saa fjoraarssnittet var kunstig
  lavt og hele endringen blaast opp. Et tall som det hadde staatt paa trykk.
  Naa teller bare doegn med minst `MIN_DEKNING` prosent, og perioden regnes av
  de doegnene som faktisk ble talt.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx

from app.models import Case

# Merk: denne kollektoren bruker `httpx.post` direkte og ikke `base.http_get`,
# fordi API-et er GraphQL over POST. Det er samme moenster som `ssb.py`, og det
# er ogsaa der testene setter inn det falske nettet (se `tests/nett.py`).

API = "https://trafikkdata-api.atlas.vegvesen.no/"
SIDE = "https://www.vegvesen.no/trafikkdata/start/kart"

TEMAER_MINE = {"transport og reiseliv", "natur og miljø"}

# Storbyomraadet. Rogaland har 245 punkter; de fleste ligger i kommuner
# Aftenbladets lesere ikke kjenner igjen navnet paa.
KOMMUNER = {"Stavanger", "Sandnes", "Sola", "Randaberg"}

# Vinduet vi sammenligner. To uker jevner ut enkeltdoegn (regnvaer, 17. mai)
# uten aa bli saa langt at en endring drukner.
VINDU_DAGER = 14
ETTERSLEP = 4

# Terskler.
MIN_ENDRING = 0.15        # 15 % mot samme periode i fjor
MIN_SNITT = 80            # passeringer per doegn - under dette er tallet stoey
MIN_DAGER_MED_TALL = 10   # av VINDU_DAGER, i BEGGE aarene
# Et doegn maa vaere naer komplett maalt for aa telle. 95 og ikke 100 fordi en
# kort utkobling ikke skal kaste et ellers godt doegn - men 67 % skal aldri
# vaere med, for da mangler en tredjedel av syklistene.
MIN_DEKNING = 95.0

# Hvor mange punkter vi spor om. Hvert punkt er en aliasert delsporring i den
# samme HTTP-forespoerselen, saa dette er en grense mot svarstoerrelse, ikke
# mot antall kall.
MAKS_PUNKTER = 24


def _sporring(sporsmaal: str) -> dict:
    """Ett POST-kall mot GraphQL-API-et. Kaster ved feil - kalleren fanger."""
    svar = httpx.post(
        API,
        json={"query": sporsmaal},
        timeout=30,
        headers={"content-type": "application/json"},
    )
    svar.raise_for_status()
    kropp = svar.json()
    if kropp.get("errors"):
        raise ValueError(str(kropp["errors"])[:200])
    return kropp["data"]


def _punkter(slag: str) -> list[dict]:
    """Tellepunkter i storbyomraadet, av typen BICYCLE eller VEHICLE."""
    data = _sporring(
        "{trafficRegistrationPoints(searchQuery:{countyNumbers:[11],"
        f"isOperational:true,trafficType:{slag}}})"
        "{id name location{municipality{name}}}}"
    )
    return [
        {"id": p["id"], "navn": p["name"], "kommune": p["location"]["municipality"]["name"]}
        for p in data["trafficRegistrationPoints"]
        if p["location"]["municipality"]["name"] in KOMMUNER
    ][:MAKS_PUNKTER]


def _volum(punkter: list[dict], fra: datetime, til: datetime) -> dict[str, list[int]]:
    """Doegntall per punkt i vinduet. Ett HTTP-kall for HELE lista.

    GraphQL lar oss aliasere: `p0: trafficData(...) p1: trafficData(...)`. Uten
    det ville 24 punkter x 2 aar blitt 48 forespoersler per skann - paa en kilde
    som skal vaere en bonus, ikke en belastning.
    """
    if not punkter:
        return {}
    biter = []
    for i, p in enumerate(punkter):
        biter.append(
            f'p{i}: trafficData(trafficRegistrationPointId:"{p["id"]}")'
            "{volume{byDay(from:\"" + fra.strftime("%Y-%m-%dT00:00:00+02:00") + "\","
            "to:\"" + til.strftime("%Y-%m-%dT00:00:00+02:00") + "\")"
            "{edges{node{total{volumeNumbers{volume} coverage{percentage}}}}}}}"
        )
    data = _sporring("{" + " ".join(biter) + "}")
    ut: dict[str, list[int]] = {}
    for i, p in enumerate(punkter):
        node = (data.get(f"p{i}") or {}).get("volume") or {}
        kanter = (node.get("byDay") or {}).get("edges") or []
        tall = []
        for k in kanter:
            total = ((k.get("node") or {}).get("total") or {})
            v = total.get("volumeNumbers")
            dekning = (total.get("coverage") or {}).get("percentage")
            # `null` betyr «punktet leverte ikke dette doegnet», ikke «null biler».
            if not v or v.get("volume") is None:
                continue
            # Og et delvis maalt doegn er ikke et lavt doegn - det er et
            # ufullstendig ett. Tas det med, blir sammenligningen loegn.
            if dekning is None or dekning < MIN_DEKNING:
                continue
            tall.append(int(v["volume"]))
        ut[p["id"]] = tall
    return ut


def _prosent(x: float) -> str:
    return f"{abs(x) * 100:.0f}"


def _funn(slag: str, punkter: list[dict]) -> tuple[dict, float] | None:
    """Punktet med stoerst endring mot i fjor, eller None om ingen naar terskelen."""
    i_dag = datetime.now(tz=UTC).date()
    til = i_dag - timedelta(days=ETTERSLEP)
    fra = til - timedelta(days=VINDU_DAGER)

    naa = _volum(punkter, datetime.combine(fra, datetime.min.time()),
                 datetime.combine(til, datetime.min.time()))
    i_fjor = _volum(punkter,
                    datetime.combine(fra.replace(year=fra.year - 1), datetime.min.time()),
                    datetime.combine(til.replace(year=til.year - 1), datetime.min.time()))

    beste: tuple[dict, float] | None = None
    for p in punkter:
        a, b = naa.get(p["id"], []), i_fjor.get(p["id"], [])
        if len(a) < MIN_DAGER_MED_TALL or len(b) < MIN_DAGER_MED_TALL:
            continue
        snitt_na, snitt_fjor = sum(a) / len(a), sum(b) / len(b)
        if snitt_na < MIN_SNITT or snitt_fjor < MIN_SNITT:
            continue
        endring = (snitt_na - snitt_fjor) / snitt_fjor
        if abs(endring) < MIN_ENDRING:
            continue
        if beste is None or abs(endring) > abs(beste[1]):
            beste = ({**p, "slag": slag, "snitt": snitt_na,
                      "fjor": snitt_fjor, "dager": len(a), "dager_fjor": len(b),
                      "fra": fra, "til": til}, endring)
    return beste


def collect(temaer: list[str] | None = None) -> tuple[list[Case], list[str]]:
    """Ett lead naar trafikken har endret seg maalbart. Fail-soft."""
    if temaer and not (TEMAER_MINE & set(temaer)):
        return [], ["Vegtrafikk: hoppet over (utenfor temavalget)"]

    status: list[str] = []
    beste: tuple[dict, float] | None = None
    # Sykkel foerst og med vilje: bilrekorder blir skrevet om uansett, mens
    # sykkeltallene er de faa ingen henter ut.
    for slag in ("BICYCLE", "VEHICLE"):
        try:
            punkter = _punkter(slag)
        except Exception as exc:  # noqa: BLE001 - kilden er en bonus, aldri et krav
            status.append(f"[FEIL] Vegtrafikk ({slag}): {type(exc).__name__}")
            continue
        if not punkter:
            status.append(f"Vegtrafikk: ingen {slag.lower()}-punkter i storbyomraadet")
            continue
        try:
            funn = _funn(slag, punkter)
        except Exception as exc:  # noqa: BLE001
            status.append(f"[FEIL] Vegtrafikk ({slag}): {type(exc).__name__}")
            continue
        status.append(f"Vegtrafikk: {len(punkter)} {slag.lower()}-punkter sjekket")
        if funn and (beste is None or abs(funn[1]) > abs(beste[1])):
            beste = funn
        # Har sykkelen en sak, trenger vi ikke bilene i tillegg.
        if slag == "BICYCLE" and funn:
            break

    if beste is None:
        status.append("Vegtrafikk: ingen punkter over terskelen — ingen sak")
        return [], status

    p, endring = beste
    opp = endring > 0
    sykkel = p["slag"] == "BICYCLE"
    hva = "Sykkeltrafikken" if sykkel else "Biltrafikken"
    # Navnene i registeret har varierende store bokstaver («Siddishallen Sykkel»,
    # «Bybrua øst»). Vi rydder bare bort ordet «sykkel», som ellers ville staatt
    # to ganger i samme setning.
    sted = p["navn"].replace(" (sykkel)", "").replace(" Sykkel", "").replace(" sykkel", "")
    periode = f"{p['fra'].strftime('%d.%m')}–{p['til'].strftime('%d.%m')}"

    return [Case(
        key=f"vegtrafikk:{p['id']}:{p['til'].isoformat()}",
        title=(
            f"{hva} ved {sted} er {_prosent(endring)} % "
            f"{'opp' if opp else 'ned'} mot i fjor"
        ),
        score=24 + min(abs(endring) * 30, 14) + (4 if sykkel else 0),
        geo="lokal",
        topics=["transport og reiseliv"],
        angle=(
            "Hva har endret seg her — ny sykkelvei, veiarbeid, en bomring, "
            "eller bare været? Vegvesenet har tallene, kommunen har planene, "
            "og de som passerer hver dag har svaret."
            if sykkel else
            "Er dette en varig endring eller et anleggsarbeid? Sjekk mot "
            "nabopunktene, og spør kommunen hva de venter seg framover."
        ),
        why=f"Vegvesenet teller hver passering ved {sted} døgn for døgn.",
        signals=[],
        created_at=datetime.now(tz=UTC),
        kind="data",
        finding=(
            f"Tellepunktet «{p['navn']}» i {p['kommune']} registrerte i snitt "
            f"{p['snitt']:.0f} {'sykler' if sykkel else 'kjøretøy'} i døgnet "
            f"{periode}, mot {p['fjor']:.0f} i samme periode i fjor — "
            f"{_prosent(endring)} prosent {'opp' if opp else 'ned'}. "
            # Antall doegn oppgis for BEGGE aarene. Foerste utkast skrev bare
            # aarets tall, og lot det se ut som fjoraaret var like godt maalt -
            # det var det ikke, og det er nettopp der en slik sammenligning
            # kan bomme.
            f"Snittene er regnet over {p['dager']} komplett målte døgn i år og "
            f"{p['dager_fjor']} i fjor; delvis målte døgn er holdt utenfor."
        ),
        metric_value=f"{p['snitt']:.0f}/døgn",
        metric_period=periode,
        data_source="Statens vegvesen (trafikkdata.no, tellepunkt)",
        data_url=SIDE,
        coverage_query=f"{'sykkeltrafikk' if sykkel else 'biltrafikk'} {p['kommune']} {sted}",
    )], status
