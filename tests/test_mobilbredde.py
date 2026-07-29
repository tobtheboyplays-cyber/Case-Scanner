"""Kortene skal ikke kunne dra sida bredere enn telefonen.

Eieren 26.07.2026, med skjermbilde: «Nye sakene kommer i feil format og linjene
går utenfor. Tror i pc format.»

Årsaken var presis: `.metric-v` hadde `white-space: nowrap` på 30–40 px skrift,
og Stortinget la «Dokument 12:9 (2023-2024)» i det feltet. 364 px uknekkelig
tekst satte en min-bredde på kortet, og HELE sida ble 500 px bred på en 390 px
skjerm — overskrifter, filterrad og knapper var kuttet på høyre side.

Disse testene måler ikke pikselbredde; det gjør nettlesertesten
(`bredde_test.py`, kjørt manuelt mot Chromium på 320/390/1280). Her voktes de to
tingene som faktisk gikk galt, og som en fremtidig økt kan gjeninnføre uten å
merke det:

  1. at ingen kollektor legger en lang tekst i tall-feltet
  2. at CSS-en ikke får `nowrap` tilbake på det feltet
"""

from __future__ import annotations

import re
from pathlib import Path

ROT = Path(__file__).resolve().parent.parent
CSS = (ROT / "static" / "style.css").read_text(encoding="utf-8")


# ── CSS-en ──────────────────────────────────────────────────────────────────


def test_tallfeltet_har_ikke_nowrap():
    """`nowrap` på .metric-v er det som brakk mobilvisningen."""
    for blokk in re.findall(r"\.metric-v\s*\{([^}]*)\}", CSS):
        assert "nowrap" not in blokk, f".metric-v har nowrap igjen: {blokk.strip()}"


def test_tallfeltet_kan_krympe():
    """I en flex-boks nekter et barn å krympe under innholdet uten min-width: 0."""
    blokker = " ".join(re.findall(r"\.metric-v\s*\{([^}]*)\}", CSS))
    assert "min-width: 0" in blokker
    assert "overflow-wrap" in blokker


def test_filterraden_brekker():
    """Tre chips på én linje stakk ut over kanten på 320 px."""
    blokk = re.search(r"\.filters\s*\{([^}]*)\}", CSS).group(1)
    assert "flex-wrap: wrap" in blokk, blokk.strip()


def test_lead_kortet_kan_krympe():
    """`1fr` nekter å krympe under innholdets min-bredde; minmax(0, 1fr) gjør det."""
    blokk = re.search(r"\.lead\s*\{([^}]*)\}", CSS).group(1)
    assert "minmax(0, 1fr)" in blokk, blokk.strip()


# ── Dataene ─────────────────────────────────────────────────────────────────


def test_stortinget_legger_ikke_henvisningen_i_tallfeltet():
    """En dokumenthenvisning er en referanse, ikke et mål. Den hører hjemme i
    den lille grå linja, ikke i 30 px skrift."""
    kilde = (ROT / "app" / "collectors" / "stortinget.py").read_text(encoding="utf-8")
    m = re.search(r"metric_value=(.+)", kilde)
    assert m, "fant ingen metric_value i stortinget.py"
    assert m.group(1).strip().startswith('""'), m.group(1).strip()


def test_alle_kollektorer_holder_tallfeltet_kort():
    """Tall-feltet tegnes på 30–40 px. Et langt uttrykk der drar sida med seg.

    Testen ser på LITERALENE i kildekoden, ikke på kjøretid: en f-streng med
    faste ord («{len(x)} innstilt») kan ikke bli lang, mens en hel setning kan.
    """
    for fil in (ROT / "app" / "collectors").glob("*.py"):
        for treff in re.findall(r'metric_value=f?"([^"]*)"', fil.read_text(encoding="utf-8")):
            # Fjern feltnavnene; det er de faste ordene som teller.
            fast = re.sub(r"\{[^}]*\}", "", treff)
            assert len(fast) <= 20, f"{fil.name}: metric_value «{treff}» er for lang"


# ── Beskjeden ved et skann som ikke ga noe ─────────────────────────────────
#
# Eieren 26.07.2026: «Må også legge til tydelig når en scan kommer tom ... du
# kan legge til en 'trykk ok' på den popuppen» og «og popuppen fungerer når det
# ikke kommer noe på scannen».
#
# Målt på tre ekte skann etter hverandre samme kveld:
#   runde 1: 16 saker, 16 nye  -> ingen beskjed  (skjermen er full)
#   runde 2:  5 saker,  0 nye  -> «ingenting nytt»
#   runde 3:  1 sak,    1 ny   -> ingen beskjed
#
# Runde 2 er poenget: skjermen er IKKE tom, men journalisten fikk ingenting
# nytt. Forskjellen mellom «0 kort» og «5 gamle kort» er usynlig for han.

from datetime import UTC, datetime  # noqa: E402

from app.main import _varsel  # noqa: E402
from app.models import Case  # noqa: E402


def _sak(uendret: bool = False) -> Case:
    c = Case(key="k", title="t", score=1.0, geo="lokal", topics=[], angle="",
             why="", signals=[], created_at=datetime.now(tz=UTC), kind="data",
             finding="f")
    c.uendret = uendret
    return c


def test_tomt_skann_er_viktig():
    v = _varsel([], ["helse"], 0)
    assert v["viktig"] is True
    assert v["handling"] == "temaer"
    assert "bytte tema" in v["tekst"].lower()


def test_ingenting_nytt_er_ogsaa_viktig():
    """5 gamle kort er like mye en blindvei som 0 kort."""
    v = _varsel([_sak(uendret=True)] * 5, ["helse"], 0)
    assert v["viktig"] is True
    assert "Bytt tema" in v["tekst"]


def test_ingen_nye_saker_er_ogsaa_viktig():
    v = _varsel([_sak()], ["helse"], 0)
    assert v["viktig"] is True


def test_et_vellykket_skann_gir_ingen_beskjed():
    """Sier den fra om alt, blir den støy — og da er vi tilbake til statuslinja
    ingen leste."""
    assert _varsel([_sak()], ["helse"], 3) == {}


def test_ett_funn_skrives_i_entall():
    """«Viser de 1 sterkeste funnene» er ikke norsk, og ett funn er vanligere
    enn man tror når temavalget er smalt."""
    t = _varsel([_sak(uendret=True)], ["helse"], 0)["tekst"]
    assert "det sterkeste funnet" in t
    assert "de 1 " not in t
