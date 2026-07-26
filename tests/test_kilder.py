"""Kilder som kan LAGE artikler — ikke artikler for å lage artikler.

Eieren 26.07.2026, andre gang han måtte si det: «Alt slikt dropper vi. Den skal
bruke kilder som kan lage artikler, ikke artikler for å lage artikler. De skal
være først.»

Første gang demoterte jeg avis-RSS-en bare. Den lå fortsatt der og laget leads,
og — verre — den slapp inn til redaktøren, som bare rekker fire saker per skann.
Hver gjenbrukte avissak stjal én av de fire plassene fra et ekte funn.

Nå er kollektoren slettet, og Brønnøysund-hendelsene er blitt ekte leads i
stedet. Testene her vokter begge halvdeler av beslutningen, fordi begge er lette
å reversere ved et uhell.
"""

from __future__ import annotations

from pathlib import Path

import app.main as m

APP = Path(__file__).resolve().parents[1] / "app"


# ── Halvdel 1: artikler er ikke råstoff ─────────────────────────────────────


def test_avis_kollektoren_er_slettet_ikke_avslaatt():
    """Et flagg satt til «false» blir slått på igjen av en framtidig økt som ikke
    kjenner grunnen. En slettet fil gjør det ikke."""
    assert not (APP / "collectors" / "schibsted.py").exists()
    for fil in APP.rglob("*.py"):
        assert "SCHIBSTED" not in fil.read_text(), fil


def test_ingen_avis_feed_ligger_igjen_i_konfigurasjonen():
    konf = (APP / "config.py").read_text()
    for vert in ("aftenposten.no/rss", "bt.no/rss"):
        assert vert not in konf, vert


def test_dekningssjekken_bruker_fortsatt_aviser():
    """Den ene lovlige bruken: «har noen allerede skrevet dette?». Det er å bruke
    artikler som FASIT, ikke som råstoff — og den skal stå."""
    assert (APP / "collectors" / "coverage.py").exists()
    assert 'AFTENBLADET_NAME = "Stavanger Aftenblad"' in (APP / "config.py").read_text()


def test_bare_primaerkilder_naar_redaktoeren():
    kode = (APP / "agents.py").read_text()
    assert 'c.kind in ("data", "hendelse")' in kode


# ── Halvdel 2: Brønnøysund er blitt et ekte lead ────────────────────────────


def hendelse(**kw) -> dict:
    base = {
        "type": "konkurs", "navn": "Ekte Kafe As", "kommune": "Stavanger",
        "dato": "2026-07-17", "dager_siden": 9, "bransje": "Drift av restauranter",
        "publikum": "restaurant og servering", "ansatte": 7,
        "orgnr": "921456875",
        "lenke": "https://virksomhet.brreg.no/nb/oppslag/enheter/921456875",
        "vekt": 9,
    }
    return {**base, **kw}


def test_konkurs_blir_en_sak_med_lenke_til_oppslaget():
    """Kjernen i den andre halvdelen. En konkurs er råstoff ingen har skrevet ut
    — den skal få vinkler på lik linje med et SSB-tall."""
    sak = m._hendelse_cases([hendelse()])[0]
    assert sak.kind == "hendelse"
    assert "Ekte Kafe As" in sak.title and "konkurs" in sak.title
    assert sak.data_url.endswith("/921456875")
    assert sak.data_source == "Brønnøysundregistrene"
    assert sak.key == "brreg:konkurs:921456875"


def test_regnskapstallene_staar_i_grunnlaget():
    """«Firma X gikk konkurs» er en notis. «Firma X omsatte for 4,1 millioner og
    gikk med underskudd» er noe man kan ringe på — og det er dette KI-agentene
    får som eneste grunnlag."""
    sak = m._hendelse_cases([hendelse(
        regnskap={"aar": "2024", "omsetning": 4125952.0, "resultat": -78790.0})])[0]
    assert "4 125 952" in sak.finding
    assert "-78 790" in sak.finding
    assert "4 125 952 kr" == sak.metric_value


def test_uten_regnskap_staar_ferskheten_som_tallet():
    """Små og ferske foretak mangler ofte regnskap. Kortet skal fortsatt ha noe
    konkret øverst — ikke et tomt felt."""
    sak = m._hendelse_cases([hendelse()])[0]
    assert sak.metric_value == "2026-07-17"
    assert "9 dager siden" in sak.metric_period


def test_hendelse_uten_orgnr_droppes():
    """Uten orgnr finnes verken en stabil nøkkel eller en lenke å slå opp. Da er
    det ikke en sak, det er et navn."""
    assert m._hendelse_cases([hendelse(orgnr="")]) == []


def test_vekten_fra_brreg_gjenbrukes_som_score():
    """Vektingen i brreg._hendelse() er allerede journalistisk: publikumsnære
    bransjer og ferske konkurser veier tyngst. Å finne på en ny skala her ville
    vært to sannheter om samme sak."""
    tung = m._hendelse_cases([hendelse(vekt=9, orgnr="1")])[0]
    lett = m._hendelse_cases([hendelse(vekt=1, orgnr="2")])[0]
    assert tung.score > lett.score


def test_taket_hindrer_at_konkurser_drukner_SSB_funnene():
    """Fire saker per skann når KI-en. Slipper vi inn 40 konkurser, har vi byttet
    ett problem mot et annet."""
    mange = [hendelse(orgnr=str(900000000 + i)) for i in range(40)]
    assert len(m._hendelse_cases(mange)) == m.HENDELSER_SOM_SAKER


def test_hendelsene_hentes_for_KI_flyten():
    """Rekkefølgen i run_scan er selve poenget: sto brreg-kallet etter
    run_workflow, rakk hendelsene verken dekningssjekk, scoring eller vinkler —
    og da var de fortsatt bare en liste i en fane."""
    kode = (APP / "main.py").read_text()
    assert kode.index("brreg.collect()") < kode.index("run_workflow(cases")


# ── Cache-busting: CSS-en skal aldri kunne bli stående gammel ───────────────


def test_css_lenka_har_versjon(tmp_path, monkeypatch):
    from app import storage
    from fastapi.testclient import TestClient

    monkeypatch.setattr(storage, "DB_PATH", str(tmp_path / "t.sqlite3"))
    storage.save_scan({"cases": [], "plan": {}, "status": [], "summary": {},
                       "ai_mode": "mal"})
    klient = TestClient(m.app)
    for sti in ("/", "/godkjente", "/kalender", "/publisert"):
        html = klient.get(sti).text
        assert f"/static/style.css?v={m.CSS_V}" in html, sti
    assert len(m.CSS_V) == 8 and m.CSS_V != "0"


def test_hashen_endrer_seg_naar_css_endres(tmp_path, monkeypatch):
    """Uten dette er cache-bustingen ren dekorasjon. Det var nettopp en fiks som
    LÅ i CSS-en som aldri nådde eieren."""
    forst = m._css_versjon()

    falsk = tmp_path / "static"
    falsk.mkdir()
    (falsk / "style.css").write_text("/* noe helt annet */")
    monkeypatch.setattr(m, "BASE_DIR", tmp_path)
    assert m._css_versjon() != forst


def test_manglende_css_velter_ikke_appen(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "BASE_DIR", tmp_path)
    assert m._css_versjon() == "0"


# ── Gesten: kortet må kunne plukkes opp ─────────────────────────────────────


def test_langt_trykk_loefter_kortet():
    """Uten løftet er flyttingen umulig å utføre: låsen krever sidelengs
    bevegelse først, og på telefon gir `touch-action: pan-y` den loddrette
    bevegelsen til nettleseren."""
    js = (APP.parent / "templates" / "dashboard.html").read_text()
    assert "LOFT_MS" in js and "loftOpp" in js
    assert "'loftet'" in js
    # preventDefault på touchmove er det som faktisk holder på bevegelsen i iOS
    # Safari når klassen settes midt i en berøring.
    assert "holdFast" in js and "{ passive: false }" in js

    css = (APP.parent / "static" / "style.css").read_text()
    assert ".lead.swipe-kort.loftet" in css
    assert "touch-action: none" in css
