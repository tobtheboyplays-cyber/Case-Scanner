"""Sveip venstre for å rydde bort en sak — og at den faktisk BLIR borte.

Eieren 26.07.2026: «Blir veldig rotete med scannen nå. Legg til en Tinder swipe
på alle sakene, så han kan rydde bort det han ikke vil ha.»

To feil ble funnet med en ekte nettlesertest (Chromium 26.07.2026), og begge er
av den typen ingen ser i en enhetstest:

1. **Sveipen virket bare med finger.** Håndteringen lyttet på `touchstart` og
   `touchmove`. Med mus skjedde ingenting i det hele tatt — verktøyet så ødelagt
   ut på laptop. Nå brukes pointer-events, som dekker mus, finger og penn.
2. **Sveipede saker kom tilbake ved refresh.** Kortet forsvant fra skjermen og
   POST-en gikk fint, men forsiden viste det lagrede skannet rått og filtrerte
   aldri bort det som var forkastet. Det er den farligste varianten: den ser ut
   som at appen mistet det han nettopp gjorde.

Testene her holder begge lukket uten å kreve en nettleser.
"""

from __future__ import annotations

import pytest
from app import storage
from app.main import app
from fastapi.testclient import TestClient

BLIR = "ssb-sok:blir:1103:2026K2"
BORT = "ssb-sok:bort:1103:2026K2"


def _sak(key: str, tittel: str) -> dict:
    return {
        "key": key, "title": tittel, "score": 40, "geo": "lokal",
        "topics": ["bolig og leie"], "angle": "a", "why": "w", "kind": "data",
        "finding": "Godkjente boliger i Stavanger: 261 i 2026K2, mot 30 i 2025K2.",
        "metric_value": "+770 %", "metric_period": "2026K2 mot 2025K2",
        "data_source": "SSB tabell 05889",
        "data_url": "https://www.ssb.no/statbank/table/05889",
        "coverage_status": "green", "coverage_examples": [],
        "editor": {}, "angles": [],
    }


@pytest.fixture()
def klient(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", str(tmp_path / "t.sqlite3"))
    monkeypatch.setattr("app.main.DB_PATH", str(tmp_path / "t.sqlite3"), raising=False)
    storage.save_scan({
        "cases": [_sak(BLIR, "Denne skal stå"), _sak(BORT, "Denne sveipes bort")],
        "plan": {}, "status": [], "summary": {}, "ai_mode": "mal",
    })
    return TestClient(app)


def test_forkastet_sak_er_borte_ogsaa_etter_refresh(klient):
    """Kjernen. Uten dette må journalisten sveipe bort de samme sakene på nytt
    hver gang han laster siden — og da er ryddefunksjonen verdiløs."""
    assert "Denne sveipes bort" in klient.get("/").text

    klient.post(f"/leads/{BORT}/reject", follow_redirects=False)

    html = klient.get("/").text
    assert "Denne sveipes bort" not in html, "saken kom tilbake ved refresh"
    assert "Denne skal stå" in html, "feil sak forsvant"


def test_skannet_i_databasen_roeres_ikke(klient):
    """Forsiden filtrerer en KOPI. Muteres det lagrede skannet, mister vi
    historikken over hva et skann faktisk fant — og «Forkastet»-arkivet under
    Lagret ville pekt på saker som ikke finnes lenger."""
    klient.post(f"/leads/{BORT}/reject", follow_redirects=False)
    klient.get("/")

    lagret = storage.load_latest()
    assert {c["key"] for c in lagret["cases"]} == {BLIR, BORT}


def test_sveipen_bruker_pointer_events_ikke_bare_touch():
    """Med bare touch-lyttere gjorde sveipen ingenting med mus. Det er lett å
    skrive tilbake til `touchstart` fordi det ser riktigere ut på en telefon."""
    from pathlib import Path

    js = Path(__file__).resolve().parents[1].joinpath("templates/dashboard.html").read_text()
    assert "'pointerdown'" in js, "sveipen starter ikke på pointer-events"
    assert "'pointermove'" in js and "'pointerup'" in js
    # touch-action: pan-y er det som gjør at nettleseren fortsatt eier den
    # loddrette scrollingen mens vi tar den vannrette.
    css = Path(__file__).resolve().parents[1].joinpath("static/style.css").read_text()
    assert "touch-action: pan-y" in css


# ── Rekkefølgen han drar sakene i ───────────────────────────────────────────


def test_egen_rekkefolge_overlever_refresh(klient):
    """Eieren 26.07.2026: «Skal krympe og følge hånden smooth, så kan du bytte
    rekkefølgen.» En rekkefølge som bare lever i DOM-en er den samme stille
    løgnen som sveipede saker som kom tilbake."""
    r = klient.post("/rekkefolge", json={"keys": [BORT, BLIR]})
    assert r.json() == {"ok": True}

    html = klient.get("/").text
    assert html.index("Denne sveipes bort") < html.index("Denne skal stå")

    klient.post("/rekkefolge", json={"keys": [BLIR, BORT]})
    html = klient.get("/").text
    assert html.index("Denne skal stå") < html.index("Denne sveipes bort")


def test_nye_saker_velter_ikke_sorteringen_hans(klient):
    """En sak som dukker opp etter at han sorterte har ingen plass. Sprettet den
    øverst, ville hvert nytt skann ødelagt jobben han nettopp gjorde."""
    klient.post("/rekkefolge", json={"keys": [BORT, BLIR]})
    storage.save_scan({
        "cases": [_sak(BLIR, "Denne skal stå"), _sak(BORT, "Denne sveipes bort"),
                  _sak("ny", "Helt fersk sak")],
        "plan": {}, "status": [], "summary": {}, "ai_mode": "mal",
    })
    html = klient.get("/").text
    assert html.index("Denne sveipes bort") < html.index("Helt fersk sak")
    assert html.index("Denne skal stå") < html.index("Helt fersk sak")


def test_soppel_i_rekkefolgen_avvises(klient):
    assert klient.post("/rekkefolge", json={"keys": "ikke en liste"}).status_code == 400
    assert storage.rekkefolge_map() == {}


def test_sveipen_slipper_kortet_naar_det_flyttes_i_lista():
    """setPointerCapture var det opplagte valget, men en DOM-flytting slipper
    fangsten — og da nådde verken flere pointermove eller pointerup kortet.
    Målt i Chromium: kortet byttet plass én gang og ble så liggende, og
    rekkefølgen ble aldri lagret fordi slipp() aldri kjørte."""
    from pathlib import Path

    js = Path(__file__).resolve().parents[1].joinpath("templates/dashboard.html").read_text()
    # Ordet står i kommentaren som forklarer hvorfor — det er selve KALLET som
    # ikke skal tilbake.
    assert ".setPointerCapture(" not in js, "fangsten er tilbake — den bryter flyttingen"
    assert "document.addEventListener('pointermove'" in js
    assert "document.addEventListener('pointerup'" in js


def test_innfadingen_laaser_ikke_transformen():
    """`animation: ... both` beholder sluttilstanden `transform: none` for alltid,
    og en fylt CSS-animasjon slår inline style. Med `both` flyttet kortet seg
    ALDRI, uansett hvor langt man dro — verifisert i Chromium 26.07.2026."""
    from pathlib import Path

    css = Path(__file__).resolve().parents[1].joinpath("static/style.css").read_text()
    for linje in css.splitlines():
        if "animation:" in linje and ("rise" in linje or "flyt-opp" in linje):
            assert "both" not in linje, f"«both» låser transformen: {linje.strip()}"
            assert "backwards" in linje, linje.strip()
