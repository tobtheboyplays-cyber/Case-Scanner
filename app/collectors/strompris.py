"""Stroemprisen i Stavanger — NO2, time for time, i dag og i morgen.

Eieren 26.07.2026: «Flere kilder til Stavanger som kan gi noe.»

Stavanger ligger i prisomraade **NO2**. Prisen settes klokka 13 dagen foer og
gjelder hele neste doegn, saa fra ettermiddagen har vi et tall INGEN har skrevet
om enda - og som treffer hver eneste husstand i byen. For et publikum paa 20-39
aar er det den mest personlige oekonomiske nyheten som finnes.

## Lovligheten, sjekket 26.07.2026

`hvakosterstrommen.no/robots.txt` inneholder BARE den forklarende
Cloudflare-blokka om content signals - ingen `User-agent`, ingen `Disallow`,
ingen signalverdier. Ingenting er altsaa forbudt.

Og API-sida sier det rett ut:

    «Bruk vaart helt aapne og gratis API for aa hente dagens og morgendagens
     norske stroempriser. Fritt tilgjengelig for hvem som helst, til hva som
     helst. Fordi vi mener stroemprisen tilhoerer folket.»

Det er en eksplisitt tillatelse, ikke en tolkning.

## Hva vi lager en sak av, og hva vi lar vaere

Prisen svinger hver dag. En sak hver dag er ikke en sak - det er stoey. Derfor
kreves et AVVIK: morgendagen maa ligge minst en fjerdedel over eller under
dagens, eller doegnet maa ha et sprik mellom billigste og dyreste time som er
stort nok til at «vent med vaskemaskinen» faktisk er et raad.

Kilden krediteres i `data_source`, og lenka gaar til deres egen side for NO2 -
det er dem som gjor jobben med aa hente fra Nord Pool.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from app.collectors.base import http_get
from app.models import Case

API = "https://www.hvakosterstrommen.no/api/v1/prices"
SONE = "NO2"                       # Stavanger, Kristiansand, Soer-Norge
SIDE = "https://www.hvakosterstrommen.no/strompris/no2-kristiansand"

# Temaene i menyen denne kilden hoerer under.
TEMAER_MINE = {"energi", "priser"}

# Hvor mye morgendagen maa avvike fra i dag foer det er en sak. 25 % er valgt
# fordi mindre enn det er hverdagslig stoey - prisen beveger seg hele tiden.
MIN_ENDRING = 0.25
# Sprik innad i doegnet: er dyreste time mer enn tre ganger den billigste, er
# «naar paa doegnet» i seg selv raadet.
MIN_SPRIK = 3.0


def _hent(dag: date) -> list[dict]:
    """Timepriser for ett doegn. Morgendagen finnes foerst etter ca. kl. 13."""
    url = f"{API}/{dag.year}/{dag.month:02d}-{dag.day:02d}_{SONE}.json"
    return http_get(url, timeout=20).json()


def _snitt(timer: list[dict]) -> float:
    tall = [t["NOK_per_kWh"] for t in timer if t.get("NOK_per_kWh") is not None]
    return sum(tall) / len(tall) if tall else 0.0


def _ore(kr: float) -> str:
    """Kroner per kWh -> «142,3 oere». Folk snakker i oere, ikke i desimaler."""
    return f"{kr * 100:.1f}".replace(".", ",") + " øre"


def _time(t: dict) -> str:
    return t["time_start"][11:16]


def collect(temaer: list[str] | None = None) -> tuple[list[Case], list[str]]:
    """Ett lead naar stroemprisen faktisk gjor noe. Fail-soft."""
    if temaer and not (TEMAER_MINE & set(temaer)):
        return [], ["Strømpris: hoppet over (utenfor temavalget)"]

    i_dag = datetime.now(tz=UTC).date()
    try:
        dagens = _hent(i_dag)
    except Exception as exc:  # noqa: BLE001 - kilden er en bonus, aldri et krav
        return [], [f"[FEIL] Strømpris: {type(exc).__name__}"]
    if not dagens:
        return [], ["Strømpris: ingen timepriser for i dag"]

    # Morgendagen slippes rundt klokka 13. Foer det er 404 det normale svaret,
    # ikke en feil - derfor egen try, og ingen feillinje.
    i_morgen: list[dict] = []
    try:
        i_morgen = _hent(i_dag + timedelta(days=1))
    except Exception:  # noqa: BLE001
        i_morgen = []

    snitt_i_dag = _snitt(dagens)
    if snitt_i_dag <= 0:
        return [], ["Strømpris: tallene ga ingen mening"]

    status = [
        f"Strømpris NO2: {len(dagens)} timer i dag"
        + (f", {len(i_morgen)} i morgen" if i_morgen else " (morgendagen ikke sluppet)")
    ]

    # --- Sak 1: i morgen skiller seg fra i dag -------------------------------
    if i_morgen:
        snitt_i_morgen = _snitt(i_morgen)
        endring = (snitt_i_morgen - snitt_i_dag) / snitt_i_dag
        if abs(endring) >= MIN_ENDRING:
            opp = endring > 0
            dyrest = max(i_morgen, key=lambda t: t["NOK_per_kWh"])
            billigst = min(i_morgen, key=lambda t: t["NOK_per_kWh"])
            return [Case(
                key=f"strom:{SONE}:{(i_dag + timedelta(days=1)).isoformat()}",
                title=(
                    f"Strømmen blir {'dyrere' if opp else 'billigere'} i morgen: "
                    f"{abs(endring) * 100:.0f} % {'opp' if opp else 'ned'} i Stavanger"
                ),
                score=26 + min(abs(endring) * 20, 14),
                geo="lokal",
                topics=["energi", "priser"],
                angle=(
                    "Hvem merker dette mest? Ring en barnefamilie og en som bor "
                    "alene, og be Lyse forklare hva som ligger bak hoppet."
                ),
                why="Prisen for i morgen er satt og gjelder hele døgnet.",
                signals=[],
                created_at=datetime.now(tz=UTC),
                kind="data",
                finding=(
                    f"Snittprisen i NO2 (Stavanger) blir {_ore(snitt_i_morgen)} per kWh "
                    f"i morgen, mot {_ore(snitt_i_dag)} i dag — "
                    f"{abs(endring) * 100:.0f} prosent {'opp' if opp else 'ned'}. "
                    f"Dyrest kl. {_time(dyrest)} ({_ore(dyrest['NOK_per_kWh'])}), "
                    f"billigst kl. {_time(billigst)} ({_ore(billigst['NOK_per_kWh'])}). "
                    "Prisene er uten nettleie, avgifter og strømstøtte."
                ),
                metric_value=_ore(snitt_i_morgen),
                metric_period=(i_dag + timedelta(days=1)).isoformat(),
                data_source="hvakosterstrommen.no (Nord Pool, NO2)",
                data_url=SIDE,
                coverage_query="strømpris Stavanger Sør-Norge NO2",
            )], status

    # --- Sak 2: spriket innad i doegnet -------------------------------------
    timer = i_morgen or dagens
    naar = "i morgen" if i_morgen else "i dag"
    dyrest = max(timer, key=lambda t: t["NOK_per_kWh"])
    billigst = min(timer, key=lambda t: t["NOK_per_kWh"])
    lav = billigst["NOK_per_kWh"]
    if lav > 0 and dyrest["NOK_per_kWh"] / lav >= MIN_SPRIK:
        ganger = dyrest["NOK_per_kWh"] / lav
        # Samme tall i tittel og funn, og norsk desimalkomma. Foerste utkast sa
        # «5 ganger» i tittelen og «4.8 ganger» i teksten under - to tall for
        # samme sak, og det ene med engelsk punktum.
        ganger_tekst = f"{ganger:.1f}".replace(".", ",")
        # Og ikke «rushtimen»: den dyreste timen var kl. 22 i den foerste ekte
        # kjoringen. Vi skriver klokkeslettet i stedet for aa paastaa naar paa
        # doegnet det er - det er kilden som vet, ikke vi.
        return [Case(
            key=f"strom-sprik:{SONE}:{timer[0]['time_start'][:10]}",
            title=(
                f"Strømmen koster {ganger_tekst} ganger mer kl. {_time(dyrest)} "
                f"enn kl. {_time(billigst)} i Stavanger {naar}"
            ),
            score=22,
            geo="lokal",
            topics=["energi", "priser"],
            angle=(
                "Hva sparer en vanlig husstand på å flytte vask og lading? "
                "Regn på det med Lyse, og sjekk hvor mange som faktisk kan styre "
                "forbruket sitt."
            ),
            why="Spriket mellom billigste og dyreste time er stort nok til å merkes.",
            signals=[],
            created_at=datetime.now(tz=UTC),
            kind="data",
            finding=(
                f"I NO2 (Stavanger) koster strømmen {_ore(dyrest['NOK_per_kWh'])} per kWh "
                f"kl. {_time(dyrest)} og {_ore(lav)} kl. {_time(billigst)} {naar} — "
                f"{ganger_tekst} ganger forskjell. "
                "Uten nettleie, avgifter og strømstøtte."
            ),
            metric_value=f"{ganger_tekst}×",
            metric_period=timer[0]["time_start"][:10],
            data_source="hvakosterstrommen.no (Nord Pool, NO2)",
            data_url=SIDE,
            coverage_query="strømpris time for time Stavanger",
        )], status

    status.append("Strømpris: ingen uvanlige utslag — ingen sak i dag")
    return [], status
