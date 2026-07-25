"""Tester for bakgrunnsjobber og «Lag utkast»-flyten.

Bakgrunn: journalisten trykket «Be om utkast» og ingenting skjedde. To feil laa
bak - POST-en blokkerte i 10-30 sekunder uten et eneste tegn paa skjermen, og
naar den endelig kom tilbake var vinkelen slaatt sammen igjen saa teksten var
usynlig. Testene her holder begge lukket.
"""

from __future__ import annotations

import re
import time
from datetime import UTC

import pytest
from app import jobs, storage
from app.main import app
from fastapi.testclient import TestClient

KEY = "ssb-sok:05889:1103:2026K2"


def _skann() -> dict:
    return {
        "cases": [
            {
                "key": KEY,
                "title": "Godkjente boliger opp 770 % i Stavanger",
                "score": 40,
                "geo": "lokal",
                "topics": ["bolig og leie"],
                "angle": "a",
                "why": "w",
                "kind": "data",
                "finding": "Godkjente boliger i Stavanger: 261 i 2026K2, mot 30 i 2025K2.",
                "metric_value": "+770 %",
                "metric_period": "2026K2 mot 2025K2",
                "data_source": "SSB tabell 05889",
                "data_url": "https://www.ssb.no/statbank/table/05889",
                "coverage_status": "green",
                "coverage_examples": [],
                "editor": {"angle": "Sjekk hvorfor"},
                "angles": [
                    {"vinkel": "konsekvens", "title": "V1", "kort": "k1"},
                    {"vinkel": "menneske", "title": "V2", "kort": "k2"},
                ],
            }
        ],
        "plan": {},
        "status": [],
        "summary": {},
        "ai_mode": "mal",
    }


@pytest.fixture()
def klient(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", str(tmp_path / "t.sqlite3"))
    monkeypatch.setattr("app.main.DB_PATH", str(tmp_path / "t.sqlite3"), raising=False)
    storage.save_scan(_skann())
    return TestClient(app)


def _vent(klient: TestClient, jobb_id: str, frist: float = 30.0) -> dict:
    slutt = time.monotonic() + frist
    while time.monotonic() < slutt:
        s = klient.get(f"/jobb/{jobb_id}").json()
        if s["status"] != "kjorer":
            return s
        time.sleep(0.1)
    raise AssertionError("jobben ble aldri ferdig")


# ── Jobbmotoren ──────────────────────────────────────────────────────────────


def test_prosenten_naar_aldri_100_for_jobben_er_ferdig():
    """En bar som staar paa 100 % mens den fortsatt jobber er en loegn."""
    port = {"slipp": False}

    def arbeid(jobb):
        while not port["slipp"]:
            time.sleep(0.01)
        return "ok"

    jobb = jobs.start([(0, "Steg ett", 0.05), (50, "Steg to", 0.05)], arbeid)
    time.sleep(0.4)                       # langt forbi antatt varighet
    assert jobb.tilstand()["pct"] < 100
    port["slipp"] = True
    for _ in range(100):
        if jobb.status != "kjorer":
            break
        time.sleep(0.05)
    assert jobb.tilstand()["pct"] == 100


def test_teksten_folger_fasen_arbeideren_faktisk_er_i():
    naadd = {"to": False}

    def arbeid(jobb):
        jobb.fase(1)
        naadd["to"] = True
        time.sleep(0.3)
        return "ok"

    jobb = jobs.start([(0, "Henter", 5.0), (40, "Skriver", 5.0)], arbeid)
    for _ in range(50):
        if naadd["to"]:
            break
        time.sleep(0.02)
    assert jobb.tilstand()["tekst"] == "Skriver"


def test_feil_i_jobben_velter_ikke_appen_og_sier_hva_som_gikk_galt():
    def arbeid(jobb):
        raise RuntimeError("modellen svarte ikke")

    jobb = jobs.start([(0, "Prover", 1.0)], arbeid)
    for _ in range(100):
        if jobb.status != "kjorer":
            break
        time.sleep(0.02)
    t = jobb.tilstand()
    assert t["status"] == "feilet"
    assert "modellen svarte ikke" in t["feil"]


def test_fasen_gaar_aldri_bakover():
    def arbeid(jobb):
        jobb.fase(2)
        jobb.fase(1)          # skal ignoreres
        time.sleep(0.2)
        return

    jobb = jobs.start([(0, "A", 9.0), (30, "B", 9.0), (60, "C", 9.0)], arbeid)
    time.sleep(0.1)
    assert jobb.tilstand()["tekst"] == "C"


# ── «Lag utkast» ende-til-ende ───────────────────────────────────────────────


def test_utkast_med_js_svarer_med_en_gang_og_gir_framdrift(klient):
    r = klient.post(f"/leads/{KEY}/utkast", data={"vinkel": "1", "js": "1"})
    assert r.status_code == 200
    jobb_id = r.json()["jobb"]
    assert _vent(klient, jobb_id)["status"] == "ferdig"


def test_utkastet_blir_faktisk_lagret(klient):
    jobb_id = klient.post(
        f"/leads/{KEY}/utkast", data={"vinkel": "0", "js": "1"}
    ).json()["jobb"]
    _vent(klient, jobb_id)
    lagret = storage.load_latest()["cases"][0]["angles"][0]
    assert lagret.get("body"), "utkastet skal ligge i skannet etterpaa"


def test_vinkelen_apnes_automatisk_etterpa(klient):
    """Regresjonstest for «jeg ba om utkast, ingenting skjedde».

    Teksten var skrevet, men <details> var slaatt sammen ved sidelast."""
    jobb_id = klient.post(
        f"/leads/{KEY}/utkast", data={"vinkel": "1", "js": "1"}
    ).json()["jobb"]
    _vent(klient, jobb_id)

    html = klient.get("/", params={"apen": f"{KEY}|1"}).text
    tagger = re.findall(r'<details class="angle"[^>]*>', html, re.S)
    assert len(tagger) == 2
    assert "open" not in tagger[0]      # den vi ikke ba om forblir lukket
    assert "open" in tagger[1]          # den vi ba om er aapen


def test_uten_js_faller_vi_tilbake_til_omdirigering(klient):
    """Nettlesere uten JavaScript skal fortsatt fungere - bare uten framdrift."""
    r = klient.post(f"/leads/{KEY}/utkast", data={"vinkel": "0"}, follow_redirects=False)
    assert r.status_code == 303
    assert "apen=" in r.headers["location"]


def test_ukjent_sak_gir_aerlig_feil_ikke_stillhet(klient):
    jobb_id = klient.post(
        "/leads/finnes-ikke/utkast", data={"vinkel": "0", "js": "1"}
    ).json()["jobb"]
    s = _vent(klient, jobb_id)
    assert s["status"] == "feilet"
    assert "Fant ikke saken" in s["feil"]


def test_ukjent_jobb_gir_404_med_forklaring(klient):
    r = klient.get("/jobb/finnesikke")
    assert r.status_code == 404
    assert r.json()["feil"]


def test_banner_varsler_nar_ki_er_av(klient):
    """Uten KI er vinklene faste maler. Det skal staa, ikke gjemmes."""
    html = klient.get("/").text
    assert "KI-en er av" in html
    assert "faste maler" in html


# ── Sveipearkiv paa lagrede utkast ───────────────────────────────────────────


def test_sveip_venstre_arkiverer_men_sletter_ikke(klient):
    storage.approve_lead(KEY, {"title": "Sak", "key": KEY})
    storage.set_plan(KEY, start_date="2026-08-01", deadline="2026-08-05")

    assert storage.arkiver(KEY) is True
    assert [x["key"] for x in storage.list_approved()] == []
    arkiv = storage.list_approved(arkiverte=True)
    assert [x["key"] for x in arkiv] == [KEY]
    # Datoene skal overleve - de er journalistens planlegging, ikke KI-ens.
    assert arkiv[0]["_start"] == "2026-08-01"
    assert arkiv[0]["_deadline"] == "2026-08-05"


def test_angre_henter_saken_tilbake_med_datoer_i_behold(klient):
    storage.approve_lead(KEY, {"title": "Sak", "key": KEY})
    storage.set_plan(KEY, start_date="2026-08-01", deadline="2026-08-05")
    storage.arkiver(KEY)

    assert storage.gjenopprett(KEY) is True
    tilbake = storage.list_approved()
    assert [x["key"] for x in tilbake] == [KEY]
    assert tilbake[0]["_deadline"] == "2026-08-05"


def test_dobbel_arkivering_er_ufarlig(klient):
    storage.approve_lead(KEY, {"title": "Sak", "key": KEY})
    assert storage.arkiver(KEY) is True
    assert storage.arkiver(KEY) is False      # allerede borte - ikke en ny hendelse


def test_arkiverte_saker_forsvinner_fra_kalenderen(klient):
    storage.approve_lead(KEY, {"title": "Sak", "key": KEY})
    storage.set_plan(KEY, start_date="2026-08-03", deadline="2026-08-04")
    assert len(storage.calendar_month(2026, 8)) == 2
    storage.arkiver(KEY)
    assert storage.calendar_month(2026, 8) == {}


def test_arkiv_ruter_svarer(klient):
    storage.approve_lead(KEY, {"title": "Sak", "key": KEY})
    assert klient.post(f"/godkjente/{KEY}/arkiver", data={"js": "1"}).json()["ok"] is True
    assert "arkiv=1" in klient.get("/godkjente").text
    assert KEY in klient.get("/godkjente", params={"arkiv": 1}).text
    assert klient.post(f"/godkjente/{KEY}/gjenopprett", data={"js": "1"}).json()["ok"] is True


def test_uten_js_omdirigerer_arkivering(klient):
    storage.approve_lead(KEY, {"title": "Sak", "key": KEY})
    r = klient.post(f"/godkjente/{KEY}/arkiver", follow_redirects=False)
    assert r.status_code == 303


# ── Vinkler: tre ULIKE forslag til tittel ────────────────────────────────────


def test_vinkler_med_samme_faktum_regnes_som_én():
    """To titler paa samme tall er ikke to vinkler - da er valget falskt."""
    from app.agents import _uten_gjengangere

    ut = _uten_gjengangere([
        {"title": "Boligbygging skyter i været", "headline_fact": "261 mot 30 i 2025K2"},
        {"title": "Rekordmange boliger godkjent", "headline_fact": "261 mot 30 i 2025K2"},
        {"title": "Sandnes henger etter", "headline_fact": "Sandnes: 13 821 kvm"},
    ])
    assert len(ut) == 2
    assert ut[1]["title"] == "Sandnes henger etter"


def test_identiske_titler_kastes_ogsaa_uten_faktum():
    from app.agents import _uten_gjengangere

    ut = _uten_gjengangere([
        {"title": "Samme tittel", "headline_fact": ""},
        {"title": "samme  TITTEL ", "headline_fact": ""},
    ])
    assert len(ut) == 1


def test_malvinklene_peker_paa_hvert_sitt_faktum():
    """Ogsaa uten KI skal de tre ikke vaere tre varianter av samme setning."""
    from datetime import datetime

    from app.agents import _fallback_angles
    from app.models import Case

    case = Case(
        key="k", title="T", score=1, geo="lokal", topics=[], angle="", why="",
        signals=[], created_at=datetime.now(tz=UTC), kind="data",
        finding="Godkjente boliger: 261 i 2026K2, mot 30 i 2025K2.",
        metric_value="+770 %", metric_period="2026K2 mot 2025K2",
        data_source="SSB tabell 05889",
    )
    a = _fallback_angles(case, {})
    assert len({x["title"] for x in a}) == 3
    assert len({x["headline_fact"] for x in a}) == 3
    assert all("Hva betyr tallet i praksis" not in x["title"] for x in a)
