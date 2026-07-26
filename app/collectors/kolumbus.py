"""Kolumbus i sanntid, via Enturs aapne reiseplanlegger.

Eieren 26.07.2026: «mer kilde mer. Masse nyheter.»

Sola-kollektoren svarer paa «staar flyene?». Denne svarer paa det som treffer
langt flere hver morgen: **staar bussen?** For et publikum paa 20-39 aar i
Stavanger er kollektivtrafikken naermere hverdagen enn nesten alt annet vi
henter.

## Lovligheten, sjekket 26.07.2026

`api.entur.io/robots.txt` er tom - ingen direktiver. Entur krever en
`ET-Client-Name`-header som identifiserer klienten; den foelger med hvert kall.
Dataene er Kolumbus' egne ruteopplysninger, publisert som nasjonale aapne data.

## Hva vi lager en sak av, og hva vi lar vaere

Nøyaktig samme resonnement som paa Sola: **en forsinket buss er ikke en nyhet -
det er en tirsdag.** Terskelen maa vaere noe som er unormalt:

  · minst `MIN_KANSELLERINGER` innstilte avganger i vinduet, ELLER
  · saa mange samtidige forsinkelser at det er et moenster (`MIN_FORSINKELSER`)

## Fella som er lett aa gaa i

`realtime: false` betyr at avgangen **ikke har sanntidsdata** - ikke at den gaar
presis. For slike avganger er `expectedDepartureTime` bare en kopi av rutetida,
og aa regne forsinkelse paa dem gir alltid null. De maa holdes utenfor BEGGE
tellingene, ellers ser en morgen der halve flaaten mangler sanntid ut som en
morgen uten problemer.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx

from app.models import Case

API = "https://api.entur.io/journey-planner/v3/graphql"
SIDE = "https://www.kolumbus.no/ruter/sanntid/"
KLIENT = "case-radar-stavanger"

TEMAER_MINE = {"transport og reiseliv"}

# Knutepunktene i storbyomraadet. Holdt kort med vilje: dette er stedene der en
# innstilt avgang faktisk rammer mange, og der en journalist kan gaa ut og
# snakke med noen med én gang.
HOLDEPLASSER = [
    ("Stavanger bussterminal", "NSR:StopPlace:59853"),
    ("Stavanger stasjon", "NSR:StopPlace:61291"),
    ("Stavanger lufthavn", "NSR:StopPlace:59284"),
]

# Hvor langt fram vi ser, og hvor mange avganger per holdeplass.
VINDU_SEKUNDER = 4 * 3600
MAKS_AVGANGER = 50

# Naar en avgang faktisk er «forsinket».
MIN_FORSINKELSE = 10

# Terskler for at det i det hele tatt er en sak.
MIN_KANSELLERINGER = 3
MIN_FORSINKELSER = 8


def _sporring(sporsmaal: str) -> dict:
    svar = httpx.post(
        API,
        json={"query": sporsmaal},
        timeout=25,
        headers={"content-type": "application/json", "ET-Client-Name": KLIENT},
    )
    svar.raise_for_status()
    kropp = svar.json()
    if kropp.get("errors"):
        raise ValueError(str(kropp["errors"])[:200])
    return kropp["data"]


def _avganger() -> list[dict]:
    """Alle avganger fra knutepunktene i vinduet. Ett HTTP-kall for hele lista."""
    biter = []
    for i, (_navn, sid) in enumerate(HOLDEPLASSER):
        biter.append(
            f'h{i}: stopPlace(id:"{sid}")'
            "{name estimatedCalls("
            f"numberOfDepartures:{MAKS_AVGANGER},timeRange:{VINDU_SEKUNDER})"
            "{aimedDepartureTime expectedDepartureTime cancellation realtime "
            "destinationDisplay{frontText} serviceJourney{line{publicCode}}}}"
        )
    data = _sporring("{" + " ".join(biter) + "}")

    ut = []
    for i, (navn, _sid) in enumerate(HOLDEPLASSER):
        sted = data.get(f"h{i}") or {}
        for k in sted.get("estimatedCalls") or []:
            try:
                rute = datetime.fromisoformat(k["aimedDepartureTime"])
                ventet = datetime.fromisoformat(k["expectedDepartureTime"])
            except (KeyError, TypeError, ValueError):
                continue
            linje = ((k.get("serviceJourney") or {}).get("line") or {}).get("publicCode") or "?"
            ut.append({
                "sted": sted.get("name") or navn,
                "linje": linje,
                "mot": (k.get("destinationDisplay") or {}).get("frontText") or "",
                "innstilt": bool(k.get("cancellation")),
                # `realtime: false` = ingen sanntidsdata, IKKE «gaar presis».
                "sanntid": bool(k.get("realtime")),
                "forsinket": int((ventet - rute).total_seconds() // 60),
            })
    return ut


def collect(temaer: list[str] | None = None) -> tuple[list[Case], list[str]]:
    """Ett lead naar kollektivtrafikken faktisk stopper opp. Fail-soft."""
    if temaer and not (TEMAER_MINE & set(temaer)):
        return [], ["Kolumbus: hoppet over (utenfor temavalget)"]

    try:
        avg = _avganger()
    except Exception as exc:  # noqa: BLE001 - kilden er en bonus, aldri et krav
        return [], [f"[FEIL] Kolumbus: {type(exc).__name__}"]

    if not avg:
        return [], ["Kolumbus: ingen avganger i vinduet"]

    innstilt = [a for a in avg if a["innstilt"]]
    # Bare avganger med sanntid kan si noe om forsinkelse i det hele tatt.
    med_sanntid = [a for a in avg if a["sanntid"] and not a["innstilt"]]
    forsinket = [a for a in med_sanntid if a["forsinket"] >= MIN_FORSINKELSE]

    status = [
        f"Kolumbus: {len(avg)} avganger i vinduet, {len(innstilt)} innstilt, "
        f"{len(forsinket)} forsinket over {MIN_FORSINKELSE} min "
        f"(av {len(med_sanntid)} med sanntid)"
    ]

    if len(innstilt) < MIN_KANSELLERINGER and len(forsinket) < MIN_FORSINKELSER:
        status.append("Kolumbus: normal drift — ingen sak")
        return [], status

    naa = datetime.now(tz=UTC)
    if len(innstilt) >= MIN_KANSELLERINGER:
        linjer = sorted({a["linje"] for a in innstilt})
        eks = ", ".join(f"linje {a['linje']} mot {a['mot']}" for a in innstilt[:3])
        tittel = f"{len(innstilt)} bussavganger innstilt i Stavanger nå"
        funn = (
            f"{len(innstilt)} avganger fra knutepunktene i Stavanger er innstilt "
            f"i løpet av de neste {VINDU_SEKUNDER // 3600} timene ({eks}). "
            f"Det rammer {len(linjer)} linjer. I tillegg er {len(forsinket)} "
            f"avganger forsinket mer enn {MIN_FORSINKELSE} minutter."
        )
        score = 24 + min(len(innstilt) * 2, 14)
        vinkel = (
            "Ring Kolumbus: hva er årsaken, hvor mange er rammet, og hva gjør "
            "de med det? Gå på bussterminalen og snakk med noen som står der."
        )
        maal = f"{len(innstilt)} innstilt"
    else:
        verst = max(forsinket, key=lambda a: a["forsinket"])
        tittel = f"{len(forsinket)} bussavganger forsinket i Stavanger nå"
        funn = (
            f"{len(forsinket)} av {len(med_sanntid)} avganger med sanntidsdata "
            f"fra knutepunktene i Stavanger er forsinket mer enn "
            f"{MIN_FORSINKELSE} minutter. Verst er linje {verst['linje']} mot "
            f"{verst['mot']} fra {verst['sted']}, {verst['forsinket']} minutter "
            "etter rutetid."
        )
        score = 20
        vinkel = (
            "Er det veiarbeid, bemanning eller noe annet? Kolumbus har "
            "årsaken, og de som står og venter har historien."
        )
        maal = f"{len(forsinket)} forsinket"

    return [Case(
        key=f"kolumbus:{naa.strftime('%Y-%m-%dT%H')}",
        title=tittel,
        score=score,
        geo="lokal",
        topics=["transport og reiseliv"],
        angle=vinkel,
        why="Hentet fra Kolumbus' egne sanntidsdata via Entur.",
        signals=[],
        created_at=naa,
        kind="hendelse",
        finding=funn,
        metric_value=maal,
        metric_period=naa.strftime("%d.%m kl. %H:%M"),
        data_source="Kolumbus via Entur (sanntid)",
        data_url=SIDE,
        coverage_query="Kolumbus buss innstilt forsinket Stavanger",
    )], status
