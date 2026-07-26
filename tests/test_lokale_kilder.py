"""Strømpris og Sola — to kilder som er ekte Stavanger-stoff.

Eieren 26.07.2026: «Flere kilder til Stavanger som kan gi noe.»

  · Strømprisen i NO2 er Stavangers eget prisområde. Prisen for i morgen settes
    klokka 13 i dag, så fra ettermiddagen har vi et tall ingen har skrevet om —
    og som treffer hver husstand i byen.
  · Sola er byens flyplass. Stopper noe opp der, står folk i avgangshallen akkurat
    nå, og saken kan ringes på i løpet av minutter.

Begge har samme innebygde fare: de gir tall HVER DAG. En sak hver dag er ikke en
sak, det er støy. Testene under vokter terskelen like hardt som de vokter at
kilden virker.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from app.collectors import sola, strompris


# ── Strømpris ──────────────────────────────────────────────────────────────


def timer(priser: list[float], dag: str = "2026-07-27") -> list[dict]:
    return [
        {"NOK_per_kWh": p, "EUR_per_kWh": p / 11, "EXR": 11.0,
         "time_start": f"{dag}T{i:02d}:00:00+02:00",
         "time_end": f"{dag}T{i + 1:02d}:00:00+02:00"}
        for i, p in enumerate(priser)
    ]


@pytest.fixture()
def strom(monkeypatch):
    boks: dict = {"i_dag": [], "i_morgen": []}

    def falsk(dag):
        i_dag = datetime.now(tz=UTC).date()
        if dag == i_dag:
            return boks["i_dag"]
        if dag == i_dag + timedelta(days=1):
            if not boks["i_morgen"]:
                raise ValueError("404 — ikke sluppet ennå")
            return boks["i_morgen"]
        raise ValueError("uventet dag")

    monkeypatch.setattr(strompris, "_hent", falsk)
    return boks


def test_stort_hopp_i_morgen_blir_en_sak(strom):
    strom["i_dag"] = timer([1.0] * 24)
    strom["i_morgen"] = timer([1.6] * 24)
    cases, _ = strompris.collect()

    assert len(cases) == 1
    c = cases[0]
    assert "dyrere" in c.title and "60 %" in c.title
    assert "160,0 øre" in c.finding
    # Forbeholdet er ikke pynt: prisen folk faktisk betaler inkluderer nettleie,
    # avgifter og strømstøtte, og en overskrift uten det er misvisende.
    assert "uten nettleie" in c.finding.lower()


def test_prisfall_er_ogsaa_en_sak(strom):
    strom["i_dag"] = timer([2.0] * 24)
    strom["i_morgen"] = timer([1.0] * 24)
    cases, _ = strompris.collect()
    assert "billigere" in cases[0].title


def test_vanlig_dag_gir_ingen_sak(strom):
    """En sak hver dag er ikke en sak. Uten terskelen ville strømprisen tatt en
    plass i lista hver eneste morgen, uansett hva den gjorde."""
    strom["i_dag"] = timer([1.0] * 24)
    strom["i_morgen"] = timer([1.05] * 24)
    cases, notat = strompris.collect()
    assert cases == []
    assert any("ingen uvanlige utslag" in n for n in notat), notat


def test_stort_sprik_i_doegnet_blir_en_sak(strom):
    """«Vent med vaskemaskinen» er et konkret råd — men bare når forskjellen er
    stor nok til å merkes på regningen."""
    strom["i_dag"] = timer([0.2] * 12 + [1.4] * 12)
    strom["i_morgen"] = timer([0.2] * 12 + [1.4] * 12)
    cases, _ = strompris.collect()
    assert len(cases) == 1
    assert "ganger mer" in cases[0].title


def test_samme_tall_i_tittel_og_tekst(strom):
    """Første utkast sa «5 ganger» i tittelen og «4.8 ganger» i teksten under —
    to tall for samme sak, og det ene med engelsk desimalpunktum."""
    strom["i_dag"] = timer([0.2] * 12 + [0.96] * 12)
    strom["i_morgen"] = timer([0.2] * 12 + [0.96] * 12)
    c = strompris.collect()[0][0]
    assert "4,8" in c.title and "4,8" in c.finding
    assert "4.8" not in c.title and "4.8" not in c.finding


def test_morgendagen_mangler_er_ikke_en_feil(strom):
    """Prisen slippes rundt klokka 13. Før det er 404 det normale svaret."""
    strom["i_dag"] = timer([0.2] * 12 + [1.4] * 12)
    strom["i_morgen"] = []
    cases, notat = strompris.collect()
    assert len(cases) == 1
    assert "i dag" in cases[0].finding
    assert not any("[FEIL]" in n for n in notat), notat


def test_doed_kilde_gir_en_feillinje_ikke_et_krasj(monkeypatch):
    def nede(dag):
        raise ConnectionError("nede")

    monkeypatch.setattr(strompris, "_hent", nede)
    cases, notat = strompris.collect()
    assert cases == [] and any("[FEIL]" in n for n in notat)


def test_utenfor_temavalget_kjorer_den_ikke(strom):
    strom["i_dag"] = timer([1.0] * 24)
    strom["i_morgen"] = timer([2.0] * 24)
    cases, notat = strompris.collect(["bolig og bygg"])
    assert cases == [] and any("temavalget" in n for n in notat)


def test_riktig_tema_slipper_den_gjennom(strom):
    strom["i_dag"] = timer([1.0] * 24)
    strom["i_morgen"] = timer([2.0] * 24)
    assert len(strompris.collect(["energi"])[0]) == 1


# ── Sola lufthavn ──────────────────────────────────────────────────────────


def fly_xml(fly: list[tuple[str, str, str, int]]) -> bytes:
    """(flightnr, mot, statuskode, minutter forsinket) -> Avinors XML."""
    naa = datetime.now(tz=UTC).replace(microsecond=0)
    biter = []
    for nr, mot, kode, forsinket in fly:
        rute = naa + timedelta(hours=2)
        ny = rute + timedelta(minutes=forsinket)
        biter.append(
            f"<flight uniqueID='1'><airline>{nr[:2]}</airline>"
            f"<flight_id>{nr}</flight_id><dom_int>D</dom_int>"
            f"<schedule_time>{rute.isoformat().replace('+00:00', 'Z')}</schedule_time>"
            f"<arr_dep>D</arr_dep><airport>{mot}</airport>"
            f"<status code='{kode}' time='{ny.isoformat().replace('+00:00', 'Z')}'/>"
            "</flight>"
        )
    return (f"<airport name='SVG'><flights>{''.join(biter)}</flights></airport>").encode()


@pytest.fixture()
def sola_nett(monkeypatch):
    boks: dict = {"fly": []}

    class Svar:
        @property
        def content(self):
            return fly_xml(boks["fly"])

    monkeypatch.setattr(sola, "http_get", lambda *a, **k: Svar())
    return boks


def test_kansellering_blir_en_sak(sola_nett):
    sola_nett["fly"] = [("DY547", "OSL", "C", 0)]
    cases, _ = sola.collect()
    assert len(cases) == 1
    assert "kansellert" in cases[0].title
    # Begge retninger hentes, saa den ene kanselleringen telles to ganger.
    assert "OSL" in cases[0].finding


def test_normal_drift_gir_ingen_sak(sola_nett):
    """En forsinket avgang er ikke en nyhet — det er en tirsdag."""
    sola_nett["fly"] = [("DY547", "OSL", "E", 5), ("SK4109", "CPH", "D", 0)]
    cases, notat = sola.collect()
    assert cases == []
    assert any("normal drift" in n for n in notat), notat


def test_mange_forsinkelser_samtidig_er_et_moenster(sola_nett):
    sola_nett["fly"] = [(f"DY{500 + i}", "OSL", "E", 30) for i in range(3)]
    cases, _ = sola.collect()
    # Tre avganger x to retninger = seks over terskelen paa fire.
    assert len(cases) == 1
    assert "forsinket" in cases[0].title


def test_et_estimat_er_ikke_en_forsinkelse(sola_nett):
    """Statuskoden `E` betyr bare at det er satt en forventet tid. Uten
    minuttgrensen ville hver eneste avgang med et estimat blitt «forsinket»."""
    sola_nett["fly"] = [(f"DY{500 + i}", "OSL", "E", 2) for i in range(6)]
    assert sola.collect()[0] == []


def test_doed_feed_gir_en_feillinje(monkeypatch):
    def nede(*a, **k):
        raise ConnectionError("Avinor er nede")

    monkeypatch.setattr(sola, "http_get", nede)
    cases, notat = sola.collect()
    assert cases == [] and any("[FEIL]" in n for n in notat)


def test_tidsvinduet_er_aldri_negativt():
    """Avinor svarer 400 på et negativt vindu — målt 26.07.2026. Første utkast
    prøvde å se én time bakover og fikk en HTTPStatusError i stedet for data."""
    assert sola.FRA_TIMER >= 0


def test_begge_kildene_er_koblet_inn_i_skannet():
    from pathlib import Path

    kode = (Path(__file__).resolve().parents[1] / "app" / "collectors"
            / "__init__.py").read_text()
    assert "strompris.collect(temaer)" in kode
    assert "sola.collect(temaer)" in kode
