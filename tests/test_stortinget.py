"""Stortinget som kilde: hva Rogalands egne representanter holder på med.

Eieren 26.07.2026: «Finn flere kilder vi kan søke igjennom som er gratis og kan
gi noe.»

Poenget er ikke det nasjonale stoffet — det er at en sak med en
Rogaland-representant på seg gir journalisten en NAVNGITT kilde med svarplikt.
«Margret Hagerup (H) er saksordfører for X» kan han ringe på i dag; et SSB-tall
må han først finne noen som merker.

Testene bytter bare `http_get`, så alt fra .NET-datoparsingen til
scoreberegningen er ekte kode.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from app.collectors import stortinget


def naa_minus(dager: int) -> str:
    """Stortingets eget format: /Date(millisekunder+0200)/"""
    t = datetime.now(tz=UTC) - timedelta(days=dager)
    return f"/Date({int(t.timestamp() * 1000)}+0200)/"


REPRESENTANTER = {"dagensrepresentanter_liste": [
    {"id": "MHA", "fornavn": "Margret", "etternavn": "Hagerup",
     "fylke": {"navn": "Rogaland"}, "parti": {"navn": "Høyre"}},
    {"id": "GPO", "fornavn": "Geir", "etternavn": "Pollestad",
     "fylke": {"navn": "Rogaland"}, "parti": {"navn": "Senterpartiet"}},
    {"id": "OSL", "fornavn": "Ola", "etternavn": "Oslomann",
     "fylke": {"navn": "Oslo"}, "parti": {"navn": "Arbeiderpartiet"}},
]}


def sak(**kw) -> dict:
    base = {
        "id": 200149, "korttittel": "Trygghet for mødre i barselomsorgen",
        "tittel": "Representantforslag om trygghet for mødre",
        "henvisning": "Innst. 300 S (2025–2026)",
        "sist_oppdatert_dato": naa_minus(40),
        "emne_liste": [{"navn": "Helsetjenester"}],
        "saksordfoerer_liste": [], "forslagstiller_liste": [],
    }
    return {**base, **kw}


@pytest.fixture()
def nett(monkeypatch):
    """Bytt ut HTTP-laget. `saker` settes per test."""
    boks: dict = {"saker": []}

    class Svar:
        def __init__(self, data): self._d = data
        def json(self): return self._d
        text = ""

    def falsk(url, **kw):
        if "dagensrepresentanter" in url:
            return Svar(REPRESENTANTER)
        if "saker" in url:
            return Svar({"saker_liste": boks["saker"]})
        raise AssertionError(f"uventet kall: {url}")

    monkeypatch.setattr(stortinget, "http_get", falsk)
    return boks


# ── Kjernen: den lokale kroken ─────────────────────────────────────────────


def test_sak_med_rogalandsrepresentant_blir_et_lead(nett):
    nett["saker"] = [sak(saksordfoerer_liste=[{"id": "MHA"}])]
    cases, _ = stortinget.collect()

    assert len(cases) == 1
    c = cases[0]
    assert "Margret Hagerup" in c.title and "Høyre" in c.title
    assert "saksordfører" in c.title
    assert c.data_url.endswith("p=200149")
    assert "Ring Margret Hagerup" in c.angle, c.angle


def test_sak_uten_lokal_krok_droppes(nett):
    """Uten filteret ville dette vært 650 nasjonale saker i en Stavanger-radar."""
    nett["saker"] = [sak(saksordfoerer_liste=[{"id": "OSL"}])]
    assert stortinget.collect()[0] == []


def test_lokalt_stedsnavn_i_tittelen_holder_alene(nett):
    """En sak om Rogaland er lokal selv om ingen herfra er saksordfører."""
    nett["saker"] = [sak(korttittel="Ny E39 gjennom Rogaland")]
    cases, _ = stortinget.collect()
    assert len(cases) == 1
    assert "Stortinget behandler" in cases[0].title


def test_saksordforer_veier_tyngre_enn_forslagsstiller(nett):
    """Saksordføreren skal svare på hvorfor innstillingen ble som den ble. Det er
    en mer presis kilde enn én av ti som skrev under på et forslag."""
    nett["saker"] = [
        sak(id=1, saksordfoerer_liste=[{"id": "MHA"}]),
        sak(id=2, forslagstiller_liste=[{"id": "GPO"}]),
    ]
    cases, _ = stortinget.collect()
    assert cases[0].key == "stortinget:1", [c.key for c in cases]
    assert cases[0].score > cases[1].score


# ── Datoene, som er der de fleste feilene sitter ───────────────────────────


def test_dot_net_datoformatet_leses(nett):
    """Stortinget svarer `/Date(1782338400000+0200)/`, ikke ISO. Uten parsing
    ville hver sak sett like fersk ut."""
    t = stortinget._dato("/Date(1782338400000+0200)/")
    assert t is not None and t.year == 2026


def test_soppel_i_datofeltet_velter_ingenting(nett):
    assert stortinget._dato("") is None
    assert stortinget._dato("i går") is None
    nett["saker"] = [sak(sist_oppdatert_dato="tull", saksordfoerer_liste=[{"id": "MHA"}])]
    assert stortinget.collect()[0] == []


def test_sommerferien_toemmer_ikke_kilden(nett):
    """Målt 26.07.2026: nyeste oppdaterte sak var 31 dager gammel, medianen 89 —
    Stortinget har ferie fra juni til oktober. Et vindu på 30 dager ga NULL treff
    hele sommeren, altså nettopp når journalisten har minst annet å skrive om."""
    nett["saker"] = [sak(sist_oppdatert_dato=naa_minus(80),
                         saksordfoerer_liste=[{"id": "MHA"}])]
    assert len(stortinget.collect()[0]) == 1


def test_for_gammelt_er_fortsatt_for_gammelt(nett):
    nett["saker"] = [sak(sist_oppdatert_dato=naa_minus(400),
                         saksordfoerer_liste=[{"id": "MHA"}])]
    assert stortinget.collect()[0] == []


def test_fersk_sak_slaar_gammel(nett):
    nett["saker"] = [
        sak(id=1, sist_oppdatert_dato=naa_minus(110), saksordfoerer_liste=[{"id": "MHA"}]),
        sak(id=2, sist_oppdatert_dato=naa_minus(5), saksordfoerer_liste=[{"id": "GPO"}]),
    ]
    cases, _ = stortinget.collect()
    assert cases[0].key == "stortinget:2", [(c.key, c.score) for c in cases]


# ── Temavalget gjelder her også ────────────────────────────────────────────


def test_utenfor_temavalget_kjorer_den_ikke(nett):
    """Samme regel som SSB og Brønnøysund: har han huket av «bolig og bygg»,
    skal ikke Stortinget ta plassen hans."""
    nett["saker"] = [sak(saksordfoerer_liste=[{"id": "MHA"}])]
    cases, notat = stortinget.collect(["bolig og bygg"])
    assert cases == []
    assert any("temavalget" in n for n in notat)


def test_riktig_tema_slipper_den_gjennom(nett):
    nett["saker"] = [sak(saksordfoerer_liste=[{"id": "MHA"}])]
    assert len(stortinget.collect(["valg og politikk"])[0]) == 1


def test_tomt_temavalg_betyr_alt(nett):
    nett["saker"] = [sak(saksordfoerer_liste=[{"id": "MHA"}])]
    assert len(stortinget.collect([])[0]) == 1


# ── Fail-soft ──────────────────────────────────────────────────────────────


def test_doed_kilde_gir_en_feillinje_ikke_et_krasj(monkeypatch):
    def nede(url, **kw):
        raise ConnectionError("stortinget er nede")

    monkeypatch.setattr(stortinget, "http_get", nede)
    cases, notat = stortinget.collect()
    assert cases == []
    assert any("[FEIL]" in n for n in notat), notat


def test_taket_hindrer_at_stortinget_druknr_de_lokale_tallene(nett):
    """650 saker i en sesjon. Slipper vi inn alle med en Rogaland-representant,
    har vi byttet ut en lokalradar med et stortingsreferat."""
    nett["saker"] = [sak(id=i, saksordfoerer_liste=[{"id": "MHA"}]) for i in range(40)]
    assert len(stortinget.collect()[0]) == stortinget.MAKS


def test_kollektoren_er_koblet_inn_i_skannet():
    """En kilde som ikke kalles er ingen kilde."""
    from pathlib import Path

    kode = (Path(__file__).resolve().parents[1] / "app" / "collectors" / "__init__.py").read_text()
    assert "stortinget.collect(temaer)" in kode
