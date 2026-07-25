"""Tester for temavalget: hva journalisten huker av skal styre HVA som letes etter.

Kravet fra eieren var eksplisitt: temaene skal styre selve søket, ikke bare
filtrere resultatet. Forskjellen er at han faktisk får NY statistikk han ikke
fikk før — ikke bare færre av de samme leadsene.
"""

from __future__ import annotations

import pytest
from app import storage
from app.config import TEMAER, sokeord_for, ssb_emner_for
from app.main import app
from fastapi.testclient import TestClient


@pytest.fixture()
def klient(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", str(tmp_path / "t.sqlite3"))
    return TestClient(app)


# ── De åtte temaene ─────────────────────────────────────────────────────────


def test_alle_atte_temaene_finnes():
    assert set(TEMAER) == {
        "helse", "lønn", "fattigdom", "barn og unge",
        "alderdom", "idrett", "kriminalitet", "næringsliv",
    }


def test_hvert_tema_har_sokeord_og_ssb_emner():
    for navn, t in TEMAER.items():
        assert t["sok"], f"{navn} mangler søkeord — da styrer den ingenting"
        assert t["ssb_emner"], f"{navn} mangler SSB-emner"
        assert t["ikon"], f"{navn} mangler ikon"


# ── Tomt valg = alt, aldri ingenting ────────────────────────────────────────


def test_tomt_valg_gir_alle_sokeord():
    """En tom meny skal aldri gi et tomt skann."""
    alle = sokeord_for([])
    assert len(alle) > 20
    assert sokeord_for(None) == alle


def test_valgte_temaer_gir_bare_sine_egne_sokeord():
    kun_helse = sokeord_for(["helse"])
    assert "sykefravaer" in kun_helse
    assert "konkurs" not in kun_helse, "næringsliv var ikke valgt"
    assert len(kun_helse) < len(sokeord_for([]))


def test_to_temaer_gir_summen_uten_duplikater():
    to = sokeord_for(["helse", "kriminalitet"])
    assert "lovbrudd" in to and "fastlege" in to
    assert len(to) == len(set(to))


def test_ukjent_tema_ignoreres_i_stedet_for_aa_kaste():
    assert sokeord_for(["finnes ikke"]) == sokeord_for([])


def test_ssb_emner_folger_valget():
    assert "sosiale-forhold-og-kriminalitet" in ssb_emner_for(["kriminalitet"])
    assert "helse" not in ssb_emner_for(["kriminalitet"])


# ── Lagring ─────────────────────────────────────────────────────────────────


def test_valget_lagres_og_overlever(klient):
    assert storage.valgte_temaer() == []          # tomt = alle
    storage.sett_temaer(["helse", "kriminalitet"])
    assert storage.valgte_temaer() == ["helse", "kriminalitet"]


def test_alle_valgt_lagres_som_tomt(klient):
    """Alle valgt og ingen valgt betyr det samme. Lagre det enkleste."""
    storage.sett_temaer(list(TEMAER))
    assert storage.valgte_temaer() == []


def test_soppel_i_valget_kastes(klient):
    storage.sett_temaer(["helse", "tullball", "helse"])
    assert storage.valgte_temaer() == ["helse"]


# ── Ruten ───────────────────────────────────────────────────────────────────


def test_menyen_lagrer_flere_avkryssinger(klient):
    """Avkryssingsbokser sender samme feltnavn flere ganger — hele poenget med
    å lese skjemaet rått i stedet for å bruke Form()."""
    r = klient.post(
        "/temaer",
        data={"tema": ["helse", "idrett"], "tilbake": "/"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert storage.valgte_temaer() == ["helse", "idrett"]


def test_menyen_vises_med_valget_avhuket(klient):
    storage.sett_temaer(["helse"])
    html = klient.get("/").text
    assert 'name="tema" value="helse"' in html
    assert "Hva skal skannet lete etter?" in html


def test_ingen_valgte_viser_alle_avhuket(klient):
    """Tomt valg betyr «alle» — da skal alle boksene stå på, ikke ingen."""
    html = klient.get("/").text
    assert html.count("checked") >= len(TEMAER)


# ── Der temaene faktisk biter ───────────────────────────────────────────────


def test_sokesystemet_bruker_de_valgte_ordene(klient, monkeypatch):
    """Selve kravet: valget skal endre HVILKE SSB-tabeller som letes opp."""
    from app.collectors import ssb_sok

    sokte_etter = []

    def falsk_katalog(params):
        if "query" in params:
            sokte_etter.append(params["query"])
        return [], 1

    monkeypatch.setattr(ssb_sok, "_hent_katalog", falsk_katalog)
    ssb_sok._kandidater([], ["kriminalitet"])

    assert sokte_etter, "søket spurte ikke katalogen i det hele tatt"
    lovlige = set(sokeord_for(["kriminalitet"]))
    assert all(o in lovlige for o in sokte_etter), sokte_etter


def test_uten_valg_leter_soket_bredt_som_for(klient, monkeypatch):
    from app.collectors import ssb_sok

    sokte_etter = []
    monkeypatch.setattr(
        ssb_sok, "_hent_katalog",
        lambda p: (sokte_etter.append(p["query"]) if "query" in p else None) or ([], 1),
    )
    ssb_sok._kandidater([], [])
    assert all(o in set(sokeord_for([])) for o in sokte_etter)


def test_kalenderen_loefter_valgte_emner_men_skjuler_ingenting(klient):
    """Kalenderen er det eneste forspranget verktøyet har. Et emne han ikke
    valgte skal rangeres lavere — ikke forsvinne."""
    from datetime import date

    from app.collectors import ssb_kalender

    feed = """<?xml version="1.0" encoding="UTF-8"?>
    <rss xmlns:ssbrss="http://www.ssb.no/ns/ssbrss"><channel>
      <item><title>01.08.2026: Lovbrudd</title><link>#</link>
        <ssbrss:date>2026-08-01</ssbrss:date>
        <ssbrss:subject>sosiale-forhold-og-kriminalitet</ssbrss:subject></item>
      <item><title>01.08.2026: Byggeareal</title><link>#</link>
        <ssbrss:date>2026-08-01</ssbrss:date>
        <ssbrss:subject>bygg-bolig-og-eiendom</ssbrss:subject></item>
    </channel></rss>"""

    class Svar:
        content = feed.encode()

    import app.collectors.ssb_kalender as mod

    mod.http_get = lambda *a, **k: Svar()
    varsler, _ = ssb_kalender.collect(i_dag=date(2026, 7, 26), temaer=["kriminalitet"])

    assert len(varsler) == 2, "ingenting skal filtreres bort"
    assert varsler[0]["emne"] == "sosiale-forhold-og-kriminalitet", "valgt emne skal ligge først"


def test_skannet_forteller_hvilke_temaer_som_ble_brukt(klient, monkeypatch):
    import app.main as m

    storage.sett_temaer(["helse"])
    monkeypatch.setattr(m, "collect_all", lambda si=None, temaer=None: ([], [], []))
    monkeypatch.setattr(m, "run_workflow", lambda c, si=None: {
        "mode": "mal", "forsokt": 0, "lyktes": 0, "feilet": 0, "feil": ""})
    monkeypatch.setattr(m.ssb_kalender, "collect", lambda **k: ([], []))

    res = m.run_scan()
    assert any("Temaer: helse" in s for s in res["status"]), res["status"]


def test_temasporet_prioriteres_naar_journalisten_har_valgt(klient, monkeypatch):
    """Målt 26.07.2026: uten dette ga «helse+kriminalitet» og «næringsliv»
    nøyaktig samme åtte tabeller. Søkeordene endret seg, men ferskhets- og
    katalogsporet fylte kvoten uansett — og da var menyen bare pynt."""
    from app.collectors import ssb_sok

    def falsk_katalog(params):
        if "query" in params:
            return [{"id": "TEMA1", "label": "Fra temaet (K)",
                     "variableNames": ["region"], "updated": "2020-01-01"}], 1
        # Ferskhets- og katalogsporet: nyere, så de ville vunnet på dato alene.
        return [{"id": "FERSK1", "label": "Nylig oppdatert (K)",
                 "variableNames": ["region"], "updated": "2026-07-26"}], 1

    monkeypatch.setattr(ssb_sok, "_hent_katalog", falsk_katalog)

    med_valg = [r["id"] for r in ssb_sok._kandidater([], ["helse"])]
    assert med_valg[0] == "TEMA1", f"temaet skal ligge først, fikk {med_valg}"

    uten_valg = [r["id"] for r in ssb_sok._kandidater([], [])]
    assert uten_valg[0] == "FERSK1", "uten valg vinner ferskhet, som før"
