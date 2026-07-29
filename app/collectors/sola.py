"""Sola lufthavn (SVG): kanselleringer og forsinkelser, time for time.

Eieren 26.07.2026: «Flere kilder til Stavanger som kan gi noe.»

Sola er Stavangers egen flyplass. Naar noe stopper opp der, rammer det folk som
staar i avgangshallen akkurat naa - og det er en sak journalisten kan ringe paa i
loepet av minutter, ikke dager. Avinors XML-feed er aapen, uten noekkel, og
oppdateres kontinuerlig.

Sjekket 26.07.2026: `avinor.no/robots.txt` inneholder bare en `Sitemap:`-linje -
ingen `Disallow`. Feeden svarte 200 med 15 avganger i et seks timers vindu.

## Hvorfor dette IKKE er et lead hver dag

En forsinket avgang er ikke en nyhet - det er en tirsdag. Terskelen er derfor
satt paa noe som faktisk er unormalt: minst én KANSELLERING, eller saa mange
forsinkelser samtidig at det er et moenster og ikke uflaks.

Statuskodene fra Avinor (XmlFeed v1.0):

    N = ny tid        E = forventet (forsinket)   D = avgaatt/landet
    C = kansellert    A = ankommet

`E` alene betyr bare at det er satt en forventet tid; vi teller den som
forsinkelse foerst naar den ligger mer enn `MIN_FORSINKELSE` minutter etter
rutetida. Uten det ville hver eneste avgang med et estimat blitt «forsinket».
"""

from __future__ import annotations

from datetime import UTC, datetime
from xml.etree import ElementTree

from app.collectors.base import http_get
from app.models import Case

FEED = "https://asrv.avinor.no/XmlFeed/v1.0"
SIDE = "https://avinor.no/flyplass/stavanger/"

# Vinduet vi ser paa. `TimeFrom` MAA vaere 0 eller stoerre: Avinor svarer 400 paa
# et negativt vindu (maalt 26.07.2026 - -1 ga 400, 0 ga 200). Foerste utkast
# proevde aa se én time bakover for aa fange ferske kanselleringer, og fikk en
# HTTPStatusError i stedet for data.
FRA_TIMER = 0
TIL_TIMER = 6

# Hvor mange minutter etter rutetid noe faktisk er «forsinket».
MIN_FORSINKELSE = 20

# Terskler for at det i det hele tatt er en sak.
MIN_KANSELLERINGER = 1
MIN_FORSINKELSER = 4

TEMAER_MINE = {"transport og reiseliv"}


def _tid(raa: str) -> datetime | None:
    try:
        return datetime.fromisoformat(raa.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _flyginger(retning: str) -> list[dict]:
    """Avganger (D) eller ankomster (A) i vinduet, som enkle dicts."""
    url = f"{FEED}?airport=SVG&direction={retning}&TimeFrom={FRA_TIMER}&TimeTo={TIL_TIMER}"
    rot = ElementTree.fromstring(http_get(url, timeout=20).content)
    ut = []
    for f in rot.iter("flight"):
        st = f.find("status")
        rute = _tid((f.findtext("schedule_time") or ""))
        ny = _tid(st.get("time", "")) if st is not None else None
        forsinket = 0
        if rute and ny:
            forsinket = int((ny - rute).total_seconds() // 60)
        ut.append({
            "nr": f.findtext("flight_id") or "",
            "selskap": f.findtext("airline") or "",
            "mot": f.findtext("airport") or "",
            "rutetid": rute,
            "kode": st.get("code", "") if st is not None else "",
            "forsinket": forsinket,
        })
    return ut


def collect(temaer: list[str] | None = None) -> tuple[list[Case], list[str]]:
    """Ett lead naar noe faktisk stopper opp paa Sola. Fail-soft."""
    if temaer and not (TEMAER_MINE & set(temaer)):
        return [], ["Sola: hoppet over (utenfor temavalget)"]

    try:
        fly = _flyginger("D") + _flyginger("A")
    except Exception as exc:  # noqa: BLE001 - kilden er en bonus, aldri et krav
        return [], [f"[FEIL] Sola lufthavn: {type(exc).__name__}"]

    if not fly:
        return [], ["Sola: ingen flyginger i vinduet"]

    kansellert = [f for f in fly if f["kode"] == "C"]
    forsinket = [
        f for f in fly
        if f["kode"] in ("E", "N") and f["forsinket"] >= MIN_FORSINKELSE
    ]
    status = [
        f"Sola: {len(fly)} flyginger i vinduet, {len(kansellert)} kansellert, "
        f"{len(forsinket)} forsinket over {MIN_FORSINKELSE} min"
    ]

    if len(kansellert) < MIN_KANSELLERINGER and len(forsinket) < MIN_FORSINKELSER:
        status.append("Sola: normal drift — ingen sak")
        return [], status

    if kansellert:
        eks = ", ".join(f"{f['selskap']}{f['nr'][2:]} til {f['mot']}"
                        for f in kansellert[:3])
        tittel = (
            f"{len(kansellert)} fly kansellert på Sola"
            if len(kansellert) > 1 else
            f"Fly kansellert på Sola: {kansellert[0]['selskap']}{kansellert[0]['nr'][2:]} "
            f"til {kansellert[0]['mot']}"
        )
        funn = (
            f"{len(kansellert)} flyginger er kansellert på Stavanger lufthavn Sola "
            f"i vinduet nå ({eks}). I tillegg er {len(forsinket)} forsinket mer enn "
            f"{MIN_FORSINKELSE} minutter."
        )
        score = 24 + min(len(kansellert) * 4, 16)
        vinkel = (
            "Ring Avinor og flyselskapet: hva er årsaken, hvor mange passasjerer "
            "er rammet, og hva har de krav på? Snakk med noen som står i hallen."
        )
    else:
        verst = max(forsinket, key=lambda f: f["forsinket"])
        funn = (
            f"{len(forsinket)} flyginger på Sola er forsinket mer enn "
            f"{MIN_FORSINKELSE} minutter akkurat nå. Verst er "
            f"{verst['selskap']}{verst['nr'][2:]} til {verst['mot']}, "
            f"{verst['forsinket']} minutter etter rutetid."
        )
        tittel = f"{len(forsinket)} fly forsinket på Sola akkurat nå"
        score = 20
        vinkel = (
            "Er det vær, bemanning eller noe hos flyselskapet? Avinor har "
            "tallene, og passasjerene i hallen har historien."
        )

    return [Case(
        key=f"sola:{datetime.now(tz=UTC).strftime('%Y-%m-%dT%H')}",
        title=tittel,
        score=score,
        geo="lokal",
        topics=["transport og reiseliv"],
        angle=vinkel,
        why="Hentet fra Avinors egen sanntidsfeed for Sola.",
        signals=[],
        created_at=datetime.now(tz=UTC),
        kind="hendelse",
        finding=funn,
        metric_value=f"{len(kansellert)} kansellert",
        metric_period=datetime.now(tz=UTC).strftime("%d.%m kl. %H:%M"),
        data_source="Avinor (sanntidsfeed, Stavanger lufthavn Sola)",
        data_url=SIDE,
        coverage_query="Sola lufthavn kansellert forsinket Stavanger",
    )], status
