"""Et falskt internett for ende-til-ende-testene.

Eieren 26.07.2026: «Synes testene dine ikke er gode nok siden vi alltid må
dobbeltsjekke.»

Han har rett, og grunnen er presis: de gamle testene byttet ut `collect_all`,
`run_workflow` og `coverage.check` med attrapper. Da MÅLTE de aldri koblingen
mellom menyvalget og kollektorene — som var nettopp der feilen lå. Testene var
grønne mens appen ga tomme skjermer og ignorerte menyen.

Løsningen er å flytte grensen helt ut til nettverket. Her byttes bare `httpx.get`
og `httpx.post`; ALT mellom knappetrykket og kortet på skjermen er ekte kode:
temavalget, probefiltrene, dekningssjekken, scoringen, uendret-filteret,
rangeringen, lagringen og malen.

`Nett` husker også hver eneste URL som ble spurt, slik at en test kan påstå
«dette valget førte til at SSB IKKE ble spurt om befolkning» — påstanden som
ville ha avslørt menyfeilen med en gang.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

import httpx

# ── Byggeklosser for SSB-svar ──────────────────────────────────────────────


def jsonstat(regioner: dict[str, list[float]], tider: list[str]) -> dict:
    """Minimal, men EKTE json-stat2-kube: dimensjonene Region, Alder, Tid.

    Alder har to koder slik at summeringen i `_series_by_region` faktisk blir
    utøvd — en kube med én alderskode ville latt en summeringsfeil passere.
    """
    reg = list(regioner)
    alder = ["020", "021"]
    value: list[float] = []
    for r in reg:                       # row-major: Region, Alder, Tid
        for _ in alder:
            for i in range(len(tider)):
                value.append(regioner[r][i] / 2)
    return {
        "id": ["Region", "Alder", "Tid"],
        "size": [len(reg), len(alder), len(tider)],
        "dimension": {
            "Region": {"category": {
                "index": {k: i for i, k in enumerate(reg)},
                "label": {k: f"Region {k}" for k in reg}}},
            "Alder": {"category": {
                "index": {k: i for i, k in enumerate(alder)},
                "label": {k: k for k in alder}}},
            "Tid": {"category": {
                "index": {k: i for i, k in enumerate(tider)},
                "label": {k: k for k in tider}}},
        },
        "value": value,
    }


BEFOLKNING = jsonstat(
    {"1103": [1000, 1000, 1000, 1000, 1420],     # Stavanger: +42 % siste år
     "11": [5000, 5000, 5000, 5000, 5100],       # Rogaland
     "0": [50000, 50000, 50000, 50000, 50500]},  # Hele landet
    ["2022", "2023", "2024", "2025", "2026"],
)

# Kvartalsvise flyttetall. Formen følger ssb_flytting._oppslag:
# dimensjonene Region, ContentsCode, Tid, og fem kvartaler.
_FLYTT_REG = ["1103", "1108"]
_FLYTT_CC = ["Tilflytting7", "Fraflytting8"]
_FLYTT_TID = ["2025K1", "2025K2", "2025K3", "2025K4", "2026K1"]
_FLYTT_TALL = {
    ("1103", "Tilflytting7"): [900, 900, 900, 900, 1200],
    ("1103", "Fraflytting8"): [900, 900, 900, 900, 900],
    ("1108", "Tilflytting7"): [400, 400, 400, 400, 400],
    ("1108", "Fraflytting8"): [400, 400, 400, 400, 700],
}
FLYTTING = {
    "id": ["Region", "ContentsCode", "Tid"],
    "size": [len(_FLYTT_REG), len(_FLYTT_CC), len(_FLYTT_TID)],
    "dimension": {
        "Region": {"category": {
            "index": {k: i for i, k in enumerate(_FLYTT_REG)},
            "label": {"1103": "Stavanger", "1108": "Sandnes"}}},
        "ContentsCode": {"category": {
            "index": {k: i for i, k in enumerate(_FLYTT_CC)},
            "label": {k: k for k in _FLYTT_CC}}},
        "Tid": {"category": {
            "index": {k: i for i, k in enumerate(_FLYTT_TID)},
            "label": {k: k for k in _FLYTT_TID}}},
    },
    "value": [v for r in _FLYTT_REG for c in _FLYTT_CC for v in _FLYTT_TALL[(r, c)]],
}

# Konkursdatoen maa ligge innenfor brreg.DAGER regnet fra I DAG, ellers filtrerer
# kollektoren den bort - `run_scan` kaller `brreg.collect()` uten dato, saa den
# bruker dagens. Tre dager tilbake er godt innenfor vinduet uansett naar testen
# kjores.
KONKURSDATO = (date.today() - timedelta(days=3)).isoformat()

KONKURS = {
    "_embedded": {"enheter": [{
        "organisasjonsnummer": "921456875",
        "navn": "TESTKAFEEN AS",
        "konkurs": True,
        "konkursdato": KONKURSDATO,
        "underAvvikling": False,
        "registreringsdatoEnhetsregisteret": KONKURSDATO,
        "organisasjonsform": {"kode": "AS"},
        "naeringskode1": {"kode": "56.101", "beskrivelse": "Drift av restauranter"},
        "antallAnsatte": 7,
        "forretningsadresse": {"kommune": "STAVANGER", "kommunenummer": "1103"},
    }]},
    "page": {"totalElements": 1},
}

TOM_RSS = ('<?xml version="1.0"?><rss version="2.0"><channel>'
           "<title>tom</title></channel></rss>")


# ── Selve det falske nettet ────────────────────────────────────────────────


class FalsktSvar:
    """Nok av httpx.Response til at kollektorene ikke merker forskjell."""

    def __init__(self, status: int, kropp: Any) -> None:
        self.status_code = status
        if isinstance(kropp, (dict, list)):
            self.text = json.dumps(kropp)
            self._json = kropp
        else:
            self.text = kropp
            self._json = None
        self.content = self.text.encode()

    def json(self) -> Any:
        if self._json is None:
            raise ValueError("ikke JSON")
        return self._json

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"{self.status_code}", request=None, response=None)  # type: ignore[arg-type]


class Nett:
    """Ruter forespørsler til faste svar, og husker hva som ble spurt om."""

    def __init__(self, *, brreg: bool = True) -> None:
        self.spurt: list[str] = []
        self.brreg = brreg

    # -- oppslag testene bruker --

    def spurte_om(self, bit: str) -> bool:
        return any(bit in u for u in self.spurt)

    def antall(self, bit: str) -> int:
        return sum(1 for u in self.spurt if bit in u)

    # -- ruting --

    def get(self, url: str, **_kw) -> FalsktSvar:
        self.spurt.append(url)
        if "01222" in url:
            return FalsktSvar(200, FLYTTING)
        if "data.stortinget.no" in url:
            # Stortinget kom til som kilde 26.07.2026. Uten en rute her ville
            # conftest-stubben slaatt inn - og den kaster `Failed`, som arver fra
            # BaseException og dreper hele skanntraaden. Skannet hang i 240 s.
            if "dagensrepresentanter" in url:
                return FalsktSvar(200, {"dagensrepresentanter_liste": []})
            return FalsktSvar(200, {"saker_liste": []})
        if "hvakosterstrommen.no" in url:
            return FalsktSvar(404, {})       # ingen stroemsak i testene
        if "asrv.avinor.no" in url:
            return FalsktSvar(200, "<airport name='SVG'><flights/></airport>")
        if "data.brreg.no" in url:
            return FalsktSvar(200, KONKURS if self.brreg else {"page": {}})
        if "regnskapsregisteret" in url:
            return FalsktSvar(404, {})
        if "news.google.com" in url or url.endswith(".rss") or "rss" in url:
            return FalsktSvar(200, TOM_RSS)
        if "data.ssb.no" in url:
            # Søkesystemet: ingen nye tabeller. Testene her handler om de faste
            # probene og om koblingen — søket har egne tester.
            return FalsktSvar(200, {"tables": [], "page": {"totalPages": 1}})
        return FalsktSvar(404, {})

    def post(self, url: str, **_kw) -> FalsktSvar:
        self.spurt.append(url)
        if "07459" in url:
            return FalsktSvar(200, BEFOLKNING)
        if "groq" in url or "chat/completions" in url:
            raise AssertionError(
                "KI-en ble kalt i en test som ikke har nøkkel — det ville brukt "
                "ekte kvote. Sett CASE_RADAR_ENABLE_AI=false i testen.")
        return FalsktSvar(404, {})
