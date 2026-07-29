"""Kvartalsvise befolkningsendringer per kommune - SSB tabell 01222.

Hvorfor denne i tillegg til befolkningstabellen vi hadde fra foer: den gamle
(07459) er AARLIG og deler bare befolkningen i aldersgrupper. Denne er KVARTALSVIS
og viser bevegelsene bak tallet - hvem som flytter inn, ut, foedes og doer. Det gir
bade ferskere data (nye tall fire ganger i aaret, ikke én) og en helt annen type
sak: «flere flytter fra Stavanger enn til».

Kilde: https://data.ssb.no/api/pxwebapi/v2/tables/01222 - aapent API, ingen noekkel,
CC BY 4.0. Verifisert live 25.07.2026.

Driftshensyn (fra SSBs egen brukerveiledning): 30 spoerringer per minutt per IP,
800 000 celler per uttrekk. Vi gjor ÉN spoerring per skann og henter 8 kvartaler for
en haandfull kommuner - godt innenfor.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.collectors.base import http_get
from app.config import demografi_for
from app.models import Case

TABELL = "01222"
BASE = f"https://data.ssb.no/api/pxwebapi/v2/tables/{TABELL}/data"
KILDE_URL = f"https://www.ssb.no/statbank/table/{TABELL}"

# Stavanger + nabokommunene det er naturlig aa sammenligne med, og hele landet.
KOMMUNER: dict[str, str] = {
    "1103": "Stavanger",
    "1108": "Sandnes",
    "1124": "Sola",
    "1127": "Randaberg",
    "1130": "Strand",
}
LANDET = "0"

# Statistikkvariablene vi bruker, med klarspraak.
VARIABLER: dict[str, str] = {
    "Tilflytting7": "innflytting",
    "Fraflytting8": "utflytting",
    "Fodte2": "fodte",
    "Dode3": "dode",
    "Innvandring5": "innvandring",
}

# Hvor mange kvartaler tilbake vi ser. 8 gir fjoraaret samme kvartal som
# sammenligning, som er den eneste aerlige maaten aa haandtere sesong paa uten
# aa sesongjustere selv.
KVARTALER = 8


def _hent() -> dict:
    regioner = ",".join([*KOMMUNER, LANDET])
    variabler = ",".join(VARIABLER)
    url = (
        f"{BASE}?lang=no&format=json-stat2"
        f"&valueCodes%5BRegion%5D={regioner}"
        f"&valueCodes%5BContentsCode%5D={variabler}"
        f"&valueCodes%5BTid%5D=top({KVARTALER})"
    )
    return http_get(url, timeout=25).json()


def _oppslag(data: dict):
    """Returnerer (hent, kvartaler, region-etiketter) for json-stat2-kuben."""
    order = data["id"]
    size = data["size"]
    dim = data["dimension"]
    idx = {k: list(dim[k]["category"]["index"]) for k in order}
    verdier = data["value"]

    def hent(region: str, variabel: str, tid: str):
        pos = 0
        for k, n in zip(order, size):
            valg = {"Region": region, "ContentsCode": variabel, "Tid": tid}[k]
            pos = pos * n + idx[k].index(valg)
        return verdier[pos]

    return hent, idx["Tid"], dim["Region"]["category"]["label"]


# Flyttetall handler om hvem som kommer og hvem som drar - det treffer bolig og
# arbeidsmarked. Velger journalisten bare «klima» eller «kriminalitet», er dette
# ikke det han spurte om, og da skal det ikke ta plassen hans.
DEMOGRAFI = {"bolig og leie", "jobb og okonomi"}


def collect(temaer: list[str] | None = None) -> tuple[list[Case], list[str]]:
    """Leads fra kvartalsvise flyttetall. Fail-soft som alle kollektorer.

    `temaer` er journalistens valg; treffer det ikke bolig/jobb, hopper vi over."""
    onsket = demografi_for(temaer)
    if onsket and not (onsket & DEMOGRAFI):
        return [], ["SSB flytting: hoppet over (utenfor temavalget)"]

    try:
        data = _hent()
        hent, kvartaler, navn = _oppslag(data)
    except Exception as exc:  # noqa: BLE001
        return [], [f"[FEIL] SSB flytting ({TABELL}): {exc}"]

    if len(kvartaler) < 5:
        return [], [f"SSB flytting: for kort tidsserie ({len(kvartaler)} kvartaler)"]

    naa = kvartaler[-1]
    i_fjor = kvartaler[-5]  # samme kvartal i fjor - hindrer sesong-feiltolkning
    cases: list[Case] = []
    notater: list[str] = [f"SSB flytting ({TABELL}): {naa} mot {i_fjor}"]

    for kode, kommune in KOMMUNER.items():
        try:
            inn = hent(kode, "Tilflytting7", naa) or 0
            ut = hent(kode, "Fraflytting8", naa) or 0
            inn_f = hent(kode, "Tilflytting7", i_fjor) or 0
            ut_f = hent(kode, "Fraflytting8", i_fjor) or 0
        except (ValueError, KeyError, IndexError):
            continue

        netto = inn - ut
        netto_f = inn_f - ut_f
        endring = netto - netto_f

        # En sak krever at bevegelsen er stor nok til aa ikke vaere stoy. 40
        # personer er lavt nok til aa fange smaa kommuner, hoyt nok til aa
        # ignorere normal svingning.
        if abs(netto) < 40 and abs(endring) < 40:
            continue

        retning = "ut av" if netto < 0 else "til"
        funn = (
            f"{kommune}: netto {abs(netto)} personer flyttet {retning} kommunen "
            f"i {naa} (innenlands). Samme kvartal i fjor: "
            f"{'−' if netto_f < 0 else '+'}{abs(netto_f)}."
        )
        tittel = (
            f"Flere flytter fra {kommune} enn til"
            if netto < 0
            else f"{kommune} vokser på tilflytting"
        )

        cases.append(
            Case(
                key=f"ssb:{TABELL}:{kode}:{naa}",
                title=tittel,
                score=min(abs(netto) / 10 + abs(endring) / 20, 40),
                geo="lokal",
                topics=["bolig og leie", "jobb og okonomi"],
                angle=(
                    f"Hvem er de som flytter, og hvorfor? Sammenlign med "
                    f"nabokommunene - Sandnes og Sola har egne tall samme kvartal."
                ),
                why=f"Netto innenlands flytting endret seg med {endring:+d} fra i fjor.",
                signals=[],
                created_at=datetime.now(tz=timezone.utc),
                kind="data",
                finding=funn,
                metric_value=f"{netto:+d}",
                metric_period=f"{naa} (mot {netto_f:+d} i {i_fjor})",
                data_source=f"SSB tabell {TABELL} (kvartalsvise befolkningsendringer)",
                data_url=KILDE_URL,
                coverage_query=f"{kommune} flytting tilflytting utflytting befolkning",
            )
        )

    notater.append(f"SSB flytting: {len(cases)} leads over terskel")
    return cases, notater
