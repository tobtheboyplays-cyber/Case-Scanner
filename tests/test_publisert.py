"""Publiserte saker: fasiten på hva radaren faktisk ga.

Eieren 26.07.2026: «Jeg vil at han skal kunne lagre det han legger ut. Så en helt
ny side ... der det er en tom side, står legg til, så kommer opp Legg inn URL. Så
kan han legge inn artiklene han legger ut, slik at det blir lagret og han vet hvem
som kom ut herfra.»

Alt annet i appen handler om saker som KAN bli noe. Denne lista er den eneste
måten å se om verktøyet er verdt tiden — og derfor er det verste den kan gjøre å
miste en lenke, eller å føre den samme saken opp to ganger.
"""

from __future__ import annotations

import pytest
from app import storage
from app.main import app
from fastapi.testclient import TestClient


@pytest.fixture()
def klient(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", str(tmp_path / "t.sqlite3"))
    monkeypatch.setattr("app.main.DB_PATH", str(tmp_path / "t.sqlite3"), raising=False)
    return TestClient(app)


def legg_inn(klient, url, **kw):
    return klient.post("/publisert", data={"url": url, **kw}, follow_redirects=False)


# ── Selve flyten eieren beskrev ─────────────────────────────────────────────


def test_tom_side_viser_legg_til(klient):
    """«Der det er en tom side, står legg til.» Skjemaet skal stå åpent når det
    ikke er noe annet å gjøre på sida — ellers møter man en knapp og ingenting."""
    html = klient.get("/publisert").text
    assert "Legg til" in html
    assert "Lim inn URL" in html
    assert "Ingen publiserte saker ennå" in html


def test_lagret_lenke_staar_paa_sida_etterpaa(klient):
    r = legg_inn(klient, "https://www.aftenbladet.no/i/abc123",
                 tittel="370 flere stavangerfolk står uten jobb")
    assert r.status_code == 303

    html = klient.get("/publisert").text
    assert "370 flere stavangerfolk står uten jobb" in html
    assert "https://www.aftenbladet.no/i/abc123" in html
    assert "aftenbladet.no" in html
    assert "Ingen publiserte saker ennå" not in html


def test_uten_tittel_staar_lenka_selv(klient):
    """Han skal kunne lime inn og gå videre. Tittel er valgfritt, og en rad uten
    tittel må fortsatt være klikkbar."""
    legg_inn(klient, "https://www.nrk.no/rogaland/sak-1")
    html = klient.get("/publisert").text
    assert "https://www.nrk.no/rogaland/sak-1" in html


def test_notatet_vises(klient):
    legg_inn(klient, "https://x.no/a", notat="Kom av SSB-funnet om fastsatt skatt")
    assert "Kom av SSB-funnet om fastsatt skatt" in klient.get("/publisert").text


def test_saken_kan_fjernes_igjen(klient):
    legg_inn(klient, "https://x.no/feil-lenke")
    rad = storage.publisert_liste()[0]
    klient.post(f"/publisert/{rad['id']}/slett", follow_redirects=False)
    assert storage.publisert_liste() == []


# ── Det som ville gjort lista ubrukelig ─────────────────────────────────────


def test_samme_sak_to_ganger_blir_én_rad(klient):
    """En fasit som fører opp den samme saken to ganger er ikke en fasit.

    «aftenbladet.no/i/x», «https://www.aftenbladet.no/i/x» og den samme med
    skråstrek på slutten er nøyaktig samme artikkel — og det er akkurat slike
    varianter man limer inn når man kopierer fra ulike steder."""
    legg_inn(klient, "aftenbladet.no/i/abc")
    legg_inn(klient, "https://www.aftenbladet.no/i/abc")
    legg_inn(klient, "https://aftenbladet.no/i/abc/")
    assert len(storage.publisert_liste()) == 1


def test_duplikat_sier_ifra_i_stedet_for_aa_forsvinne(klient):
    """En lenke som stille ikke ble lagret er verre enn ingen lagring: han tror
    den ligger der, og oppdager det først når lista er feil."""
    legg_inn(klient, "https://x.no/a")
    r = legg_inn(klient, "https://x.no/a")
    assert "feil=" in r.headers["location"]

    html = klient.get(r.headers["location"]).text
    assert "ligger allerede inne" in html


def test_soppel_lagres_ikke_og_forklares(klient):
    r = legg_inn(klient, "ikke en lenke i det hele tatt")
    assert storage.publisert_liste() == []
    html = klient.get(r.headers["location"]).text
    assert "nettadresse" in html


def test_javascript_lenke_avvises(klient):
    """Sida har ingen innlogging, og radene rendres som ekte <a href>. En
    «javascript:»-lenke lagret her ville vært et hull vi ikke trenger å ha."""
    legg_inn(klient, "javascript:alert(1)")
    legg_inn(klient, "data:text/html,<script>alert(1)</script>")
    assert storage.publisert_liste() == []


def test_halv_lenke_faar_https(klient):
    """Folk limer inn «aftenbladet.no/i/x» hele tiden. Uten skjema blir det en
    relativ lenke som peker inn i Case-radar selv."""
    legg_inn(klient, "aftenbladet.no/i/xyz")
    assert storage.publisert_liste()[0]["url"].startswith("https://")


def test_lange_felt_kappes(klient):
    legg_inn(klient, "https://x.no/" + "a" * 900, tittel="t" * 900)
    rad = storage.publisert_liste()[0]
    assert len(rad["url"]) <= storage.MAKS_PUBLISERT_FELT
    assert len(rad["tittel"]) <= storage.MAKS_PUBLISERT_FELT


def test_nyeste_staar_oeverst(klient):
    for i in range(3):
        legg_inn(klient, f"https://x.no/{i}", tittel=f"Sak {i}")
    assert [r["tittel"] for r in storage.publisert_liste()][0] == "Sak 2"


# ── Sida skal finnes fra de andre sidene ────────────────────────────────────


def test_lenka_staar_i_menyen_paa_alle_sidene(klient):
    """Blir sida ikke lenket til, finnes den ikke. Han skal aldri måtte huske
    en URL."""
    storage.save_scan({"cases": [], "plan": {}, "status": [], "summary": {},
                       "ai_mode": "mal"})
    for sti in ("/", "/godkjente", "/kalender"):
        assert 'href="/publisert"' in klient.get(sti).text, sti


def test_telleren_i_menyen_stemmer(klient):
    storage.save_scan({"cases": [], "plan": {}, "status": [], "summary": {},
                       "ai_mode": "mal"})
    assert "Publisert (" not in klient.get("/").text
    legg_inn(klient, "https://x.no/a")
    legg_inn(klient, "https://x.no/b")
    assert "Publisert (2)" in klient.get("/").text


def test_tabellen_lages_paa_en_gammel_database(tmp_path, monkeypatch):
    """Eieren har en kjørende database med skann i. Oppgraderingen skal legge til
    tabellen uten å røre det som ligger der."""
    monkeypatch.setattr(storage, "DB_PATH", str(tmp_path / "gammel.sqlite3"))
    storage.save_scan({"cases": [{"key": "k", "title": "T"}], "plan": {},
                       "status": [], "summary": {}, "ai_mode": "mal"})
    assert storage.publisert_liste() == []
    assert storage.publisert_legg_til("https://x.no/a") == (True, "")
    assert storage.load_latest()["cases"][0]["key"] == "k"
