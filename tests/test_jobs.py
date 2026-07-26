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
    assert "KI-en er AV" in html
    assert "maler, ikke journalistens" in html


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


def test_kortkilde_beholder_tabellnummeret():
    """Det lange tabellnavnet sto tre steder i samme kort og tok to linjer hver
    gang. Vi korter det ned - men nummeret er det eneste presise, så det blir."""
    from app.main import kortkilde

    assert kortkilde(
        "SSB tabell 05887 (Byggeareal. Bruksareal til annet enn bolig, "
        "etter bygningstype (m²) (K))"
    ) == "SSB tabell 05887"
    # Eldre format har nummeret INNE i parentesen - da må det hentes ut.
    assert kortkilde("SSB (befolkning, 07459)") == "SSB tabell 07459"
    assert kortkilde("Stavanger Aftenblad") == "Stavanger Aftenblad"
    assert kortkilde("") == ""


# ── Skanneskjermen ───────────────────────────────────────────────────────────


def test_skann_med_js_svarer_med_en_gang(klient, monkeypatch):
    """Skannet tar 40-60 sekunder. POST-en skal ikke holde på brukeren så lenge."""
    import app.main as m

    monkeypatch.setattr(m, "run_scan", lambda jobb=None: {"cases": []})
    r = klient.post("/scan", data={"js": "1"})
    assert r.status_code == 200
    assert _vent(klient, r.json()["jobb"])["status"] == "ferdig"


def test_skann_uten_js_omdirigerer_som_for(klient, monkeypatch):
    import app.main as m

    monkeypatch.setattr(m, "run_scan", lambda jobb=None: {"cases": []})
    r = klient.post("/scan", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/"


def test_skannet_melder_hvilken_kilde_som_jobber(klient, monkeypatch):
    """Prosenten er et anslag. Kildenavnet er det ikke - det er sant."""
    import app.main as m

    def falskt_skann(jobb=None):
        jobb.fase(1, "Sjekker dekning 3 av 15: Boligprisene i Stavanger")
        time.sleep(0.25)
        return {"cases": []}

    monkeypatch.setattr(m, "run_scan", falskt_skann)
    jobb_id = klient.post("/scan", data={"js": "1"}).json()["jobb"]
    for _ in range(40):
        s = klient.get(f"/jobb/{jobb_id}").json()
        if s.get("siste"):
            assert "Boligprisene i Stavanger" in s["siste"]
            assert s["tekst"] == "Sjekker om noen allerede har skrevet om det"
            return
        time.sleep(0.05)
    raise AssertionError("statuslinja kom aldri fram")


def test_feilet_skann_sier_hva_som_gikk_galt(klient, monkeypatch):
    import app.main as m

    def kraesj(jobb=None):
        raise RuntimeError("SSB svarte ikke")

    monkeypatch.setattr(m, "run_scan", kraesj)
    s = _vent(klient, klient.post("/scan", data={"js": "1"}).json()["jobb"])
    assert s["status"] == "feilet"
    assert "SSB svarte ikke" in s["feil"]


def test_collect_all_melder_uten_aa_kreve_det(monkeypatch):
    """`si` er valgfri - uten den skal alt oppføre seg nøyaktig som før."""
    import inspect

    from app.collectors import collect_all

    sig = inspect.signature(collect_all)
    assert sig.parameters["si"].default is None


# ── Kalenderens timebudsjett ─────────────────────────────────────────────────


def test_timer_legges_sammen_per_dag(klient):
    """Tre saker à tre timer på samme dag er ni timer - det skal synes."""
    for i in range(3):
        k = f"sak-{i}"
        storage.approve_lead(k, {"title": f"Sak {i}", "key": k})
        storage.set_plan(k, start_date="2026-08-03", deadline="2026-08-03", timer="3")

    dager = storage.calendar_month(2026, 8)
    assert storage.timer_per_dag(dager)["2026-08-03"] == 9.0


def test_timer_fordeles_over_hele_spennet(klient):
    storage.approve_lead(KEY, {"title": "Sak", "key": KEY})
    storage.set_plan(KEY, start_date="2026-08-03", deadline="2026-08-05", timer="2.5")
    timer = storage.timer_per_dag(storage.calendar_month(2026, 8))
    assert timer == {"2026-08-03": 2.5, "2026-08-04": 2.5, "2026-08-05": 2.5}


def test_ugyldige_timer_ignoreres_i_stedet_for_aa_kaste(klient):
    """UI-et skal aldri låse seg på en skrivefeil - samme regel som datoene."""
    storage.approve_lead(KEY, {"title": "Sak", "key": KEY})
    storage.set_plan(KEY, start_date="2026-08-03", timer="3")
    storage.set_plan(KEY, timer="tre timer")          # tull
    assert storage.list_approved()[0]["_timer"] == 3.0
    storage.set_plan(KEY, timer="2,5")                 # norsk komma
    assert storage.list_approved()[0]["_timer"] == 2.5
    storage.set_plan(KEY, timer="900")                 # over taket
    assert storage.list_approved()[0]["_timer"] == storage.MAKS_TIMER


def test_dagskapasitet_kan_justeres_og_taaler_soppel(klient):
    assert storage.dagskapasitet() == storage.DAGSKAPASITET_STANDARD
    assert storage.sett_dagskapasitet(6) == 6.0
    assert storage.dagskapasitet() == 6.0
    storage.meta_set("dagskapasitet", "ikke et tall")
    assert storage.dagskapasitet() == storage.DAGSKAPASITET_STANDARD


def test_kalenderen_merker_overbookede_dager(klient):
    storage.sett_dagskapasitet(7.5)
    for i in range(4):
        k = f"full-{i}"
        storage.approve_lead(k, {"title": f"Sak {i}", "key": k})
        storage.set_plan(k, start_date="2026-08-10", deadline="2026-08-10", timer="3")

    html = klient.get("/kalender", params={"ym": "2026-08"}).text
    assert "er-full" in html            # ruta er merket i månedsrutenettet
    assert "12" in html                 # 4 × 3 timer
    assert "dag over" in html or "dager over" in html


def test_kapasitet_endres_fra_kalenderen(klient):
    r = klient.post("/kalender/kapasitet", data={"timer": "5"}, follow_redirects=False)
    assert r.status_code == 303
    assert storage.dagskapasitet() == 5.0


# ── Oppgavefanen ─────────────────────────────────────────────────────────────


def _oppgave(key: str, tittel: str, start: str, frist: str, timer: str = "2") -> None:
    storage.approve_lead(key, {"title": tittel, "key": key, "finding": "f"})
    storage.set_plan(key, start_date=start, deadline=frist, timer=timer)


def test_oppgavene_kommer_i_rekkefolge_etter_deadline(klient):
    _oppgave("c", "Sist frist", "2026-08-01", "2026-08-20")
    _oppgave("a", "Naermest frist", "2026-08-01", "2026-08-03")
    _oppgave("b", "Midt imellom", "2026-08-01", "2026-08-10")

    assert [x["title"] for x in storage.oppgaver()] == [
        "Naermest frist", "Midt imellom", "Sist frist"
    ]


def test_sak_uten_dato_er_ikke_en_oppgave(klient):
    """Uten dato er den ikke lagt i kalenderen - da hører den ikke hjemme her."""
    storage.approve_lead("udatert", {"title": "Ingen dato", "key": "udatert"})
    _oppgave("datert", "Har dato", "2026-08-01", "2026-08-05")
    assert [x["key"] for x in storage.oppgaver()] == ["datert"]


def test_ferdig_fjerner_oppgaven_fra_bade_liste_og_kalender(klient):
    _oppgave("x", "Artikkel om gutter som blir aggressive", "2026-08-03", "2026-08-05")
    assert len(storage.calendar_month(2026, 8)) == 3      # 3., 4. og 5.

    assert storage.fullfor("x") is True
    assert storage.oppgaver() == []
    assert storage.calendar_month(2026, 8) == {}
    # ... men den er ikke slettet.
    assert [y["key"] for y in storage.list_approved(fullforte=True)] == ["x"]


def test_angre_setter_oppgaven_tilbake_med_datoer_og_timer(klient):
    _oppgave("x", "Sak", "2026-08-03", "2026-08-05", timer="3.5")
    storage.fullfor("x")

    assert storage.gjenapne("x") is True
    tilbake = storage.oppgaver()
    assert len(tilbake) == 1
    assert tilbake[0]["_start"] == "2026-08-03"
    assert tilbake[0]["_deadline"] == "2026-08-05"
    assert tilbake[0]["_timer"] == 3.5


def test_dobbel_ferdig_er_ufarlig(klient):
    _oppgave("x", "Sak", "2026-08-03", "2026-08-05")
    assert storage.fullfor("x") is True
    assert storage.fullfor("x") is False      # allerede ferdig - ikke en ny hendelse


def test_ferdig_og_arkivert_er_ikke_det_samme(klient):
    """«Denne ville jeg ikke ha» og «denne er gjort» skal ikke blandes."""
    _oppgave("ferdig", "Gjort", "2026-08-01", "2026-08-02")
    _oppgave("bortlagt", "Ville ikke ha", "2026-08-01", "2026-08-02")
    storage.fullfor("ferdig")
    storage.arkiver("bortlagt")

    assert [x["key"] for x in storage.list_approved(fullforte=True)] == ["ferdig"]
    assert [x["key"] for x in storage.list_approved(arkiverte=True)] == ["bortlagt"]
    # Ingen av dem er i arbeid lenger ...
    assert storage.list_approved(fullforte=False) == []
    # ... men den ferdige ligger fortsatt under Lagrede utkast. «Ferdig» tar den
    # ut av KALENDEREN, ikke ut av arkivet der journalisten finner igjen teksten.
    assert [x["key"] for x in storage.list_approved()] == ["ferdig"]


def test_ferdig_sak_blir_staaende_under_lagrede_utkast(klient):
    _oppgave("x", "Artikkel om gutter som blir aggressive", "2026-08-03", "2026-08-05")
    storage.fullfor("x")
    html = klient.get("/godkjente").text
    assert "Artikkel om gutter som blir aggressive" in html
    assert "Ferdig" in html                 # merket som ferdig, ikke borte


def test_oppgavefanen_viser_saken_og_ferdigknappen(klient):
    _oppgave("x", "Artikkel om gutter som blir aggressive", "2026-08-03", "2026-08-05")
    html = klient.get("/kalender", params={"ym": "2026-08", "fane": "oppgaver"}).text
    assert "Artikkel om gutter som blir aggressive" in html
    assert "Ferdig" in html
    assert "/oppgaver/x/ferdig" in html


def test_ferdigknappen_virker_fra_fanen(klient):
    _oppgave("x", "Sak", "2026-08-03", "2026-08-05")
    r = klient.post("/oppgaver/x/ferdig", follow_redirects=False)
    assert r.status_code == 303
    assert storage.oppgaver() == []

    r = klient.post("/oppgaver/x/angre", follow_redirects=False)
    assert r.status_code == 303
    assert len(storage.oppgaver()) == 1


def test_kalenderfanen_er_standard(klient):
    html = klient.get("/kalender").text
    assert 'class="fane er-valgt"' in html
    assert "cal-grid" in html          # rutenettet, ikke oppgavelista


# ── At KI-veien faktisk gir ekte vinkler når nøkkelen er på plass ────────────


def _sak():
    from datetime import datetime

    from app.models import Case

    return Case(
        key="k", title="Vold blant gutter opp 1,3 %", score=30, geo="lokal",
        topics=["trygghet og kriminalitet"], angle="", why="", signals=[],
        created_at=datetime.now(tz=UTC), kind="data",
        finding="Anmeldte voldslovbrudd med gutteregistrert gjerningsperson i "
                "Stavanger: 1,3 % opp fra i fjor. Hele landet: 0,2 % ned.",
        metric_value="+1,3 %", metric_period="2025–2026",
        data_source="SSB tabell 08487", data_url="https://www.ssb.no/statbank/table/08487",
    )


def test_journalisten_gir_tre_ulike_vinkler_nar_ki_svarer(monkeypatch):
    """Med nøkkel skal vinklene komme fra modellen - tre ulike spor, ikke tre
    omskrivninger av tallet."""
    from app import agents

    svar = {"angles": [
        {"vinkel": "uventet", "title": "Skjermtid og gaming: hva sier hjelpetjenesten?",
         "headline_fact": "+1,3 % i Stavanger", "kort": "k", "styrke": 70},
        {"vinkel": "handling", "title": "Fritidsklubbene mistet støtte i fjor",
         "headline_fact": "Hele landet gikk 0,2 % ned", "kort": "k", "styrke": 65},
        {"vinkel": "motsetning", "title": "Endret politiet registreringspraksis?",
         "headline_fact": "SSB tabell 08487", "kort": "k", "styrke": 60},
    ]}
    monkeypatch.setattr(agents.llm, "complete_json", lambda *a, **k: svar)

    vinkler = agents.journalist_angles(_sak(), {})
    assert len(vinkler) == 3
    assert all(v["mode"] == "llm" for v in vinkler), "skal være merket som ekte KI"
    assert len({v["title"] for v in vinkler}) == 3
    assert len({v["headline_fact"] for v in vinkler}) == 3


def test_ki_som_leverer_samme_faktum_to_ganger_gir_to_vinkler(monkeypatch):
    """Beskjed er ingen garanti. To titler på samme tall er ett falskt valg."""
    from app import agents

    svar = {"angles": [
        {"vinkel": "uventet", "title": "A", "headline_fact": "+1,3 % i Stavanger"},
        {"vinkel": "konsekvens", "title": "B", "headline_fact": "+1,3 % i Stavanger"},
        {"vinkel": "motsetning", "title": "C", "headline_fact": "Landet 0,2 % ned"},
    ]}
    monkeypatch.setattr(agents.llm, "complete_json", lambda *a, **k: svar)
    assert len(agents.journalist_angles(_sak(), {})) == 2


def test_uten_ki_leverer_vi_ingen_vinkler(monkeypatch):
    """Feiler KI-en, skal lista være TOM - ikke fylt med maler.

    Regresjonsvakt på eierens beslutning: en mal kan ikke foreslå en vinkel, og
    tre svake forslag ser ut som et valg uten å være det."""
    from app import agents

    monkeypatch.setattr(agents.llm, "complete_json", lambda *a, **k: None)
    assert agents.journalist_angles(_sak(), {}) == []


def test_prompten_krever_tre_ulike_spor():
    from app import prompts

    p = prompts.JOURNALIST_ANGLES_SYSTEM
    assert "SITT EGET faktum" in p
    assert "hypotese" in p.lower()
    assert "FORSLAG TIL TITTEL" in p


def test_journalisten_maa_selge_inn_vinkelen():
    """Eieren 26.07.2026: «journalistene trenger mer prompting og faktisk selge
    inn de titlene de lager». Promptene var korrekte, men flate - de ba aldri
    om et argument for hvorfor saken er verdt en dag."""
    from app import prompts

    p = prompts.JOURNALIST_ANGLES_SYSTEM
    assert "pitch" in p, "ingen salgspitch etterspurt"
    assert "IDEMOETE" in p, "journalisten vet ikke at han skal selge inn"
    assert "aktive verb" in p, "ingen konkrete regler for skarpe titler"
    # Vernet mot klikkagn må overleve at vi ber om skarpere titler.
    assert "Ingen klikkagn" in p and "Aldri dikt opp" in p

    e = prompts.EDITOR_SYSTEM
    assert "leserverdi" in e, "redaktøren svarer ikke på hvem som bryr seg"
    # «Unngå tomme abstraksjoner» var et råd modellen kunne tolke som den ville,
    # og den leverte flate arbeidstitler likevel. Etter 26.07.2026 er det en
    # navngitt forbudsliste — «Fokus på ...», «Setter søkelys på ...» — pluss tre
    # harde krav hver tittel må oppfylle.
    assert "FORBUDTE AAPNINGER" in e
    assert "Setter soekelys paa" in e
    assert "TRE KRAV TIL EN TITTEL" in e


# ── Ting som vokser uten tak, og sider som blir for tunge ────────────────────


def test_skann_tabellen_har_tak(klient):
    """Hvert skann OG hvert utkast skriver en full kopi. Uten tak ble det rundt
    90 MB på et år - på en liten VPS er det ren sløsing, og bare det nyeste
    skannet leses noen gang."""
    import sqlite3

    for _ in range(storage.MAKS_SKANN + 15):
        storage.save_scan(_skann())

    conn = sqlite3.connect(storage.DB_PATH)
    try:
        antall = conn.execute("SELECT COUNT(*) FROM scans").fetchone()[0]
    finally:
        conn.close()
    assert antall == storage.MAKS_SKANN
    # Det nyeste skal fortsatt være der - taket kutter de eldste, ikke de nye.
    assert storage.load_latest()["cases"][0]["key"] == KEY


def test_kalenderdagen_har_tak_paa_antall_kort(klient):
    """En dag med 40 saker rendret 40 fulle kort med hvert sitt skjema.
    Kalendersida ble 1,8 MB HTML i stresstest."""
    for i in range(40):
        k = f"m{i}"
        storage.approve_lead(k, {"title": f"Sak {i}", "key": k})
        storage.set_plan(k, start_date="2026-08-10", deadline="2026-08-10", timer="0.5")

    html = klient.get("/kalender", params={"ym": "2026-08"}).text
    assert "Viser 12 av 40 saker" in html
    assert html.count('name="timer"') <= 14      # 12 dagskort + kapasitetsfeltet
    assert len(html) < 400_000                    # ikke en megabyte


def test_reddit_er_av_og_sier_hvorfor(klient, monkeypatch):
    """Reddit ga 0 signaler og 3 røde feillinjer ved hvert skann. Av som
    standard - men koden står igjen, og statuslinja sier hvordan man slår på."""
    from app import collectors

    kalt = []
    monkeypatch.setattr(collectors.reddit, "collect", lambda: kalt.append(1) or ([], []))
    monkeypatch.setattr(collectors.google_trends, "collect", lambda: ([], []))
    for navn in ("ssb", "ssb_flytting", "ssb_sok", "schibsted"):
        monkeypatch.setattr(getattr(collectors, navn), "collect", lambda: ([], []))

    _, _, status = collectors.collect_all()
    assert not kalt, "Reddit skal ikke kalles når den er av"
    assert any("CASE_RADAR_ENABLE_REDDIT" in s for s in status)
