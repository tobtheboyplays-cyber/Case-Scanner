"""Rekkefolgen på forsiden: egne funn før gjenbruk.

Bakgrunn, meldt av eieren 26.07.2026: «Nå bruker den plutselig Aftenposten og
Bergens Tidende som kilder, og den ga fram like mange saker som før.»

Han hadde rett, og årsaken var mekanisk. `schibsted.py` lager nøkkelen av
artikkeloverskriften, og RSS-feeder bytter overskrifter hele tiden — så hver
gjenbrukssak var teknisk «aldri sett før» ved hvert eneste skann. Med `er_ny`
som primær sorteringsnøkkel la de seg dermed øverst hver gang, og SSB-funnene
sank så snart de var sett én gang.

Det er verktøyets forsprang som forsvant: originale tall ingen har skrevet om,
byttet ut med nasjonale overskrifter som allerede er publisert.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from app import storage
from app.models import Case


def sak(key: str, kind: str, score: float) -> Case:
    return Case(
        key=key, title=key, kind=kind, geo="lokal", score=score,
        topics=[], angle="", why="", signals=[], created_at=datetime.now(UTC),
        coverage_status="green",
    )


@pytest.fixture()
def scan(tmp_path, monkeypatch):
    """Kjør run_scan med stubbede kilder, og få tilbake rekkefølgen."""
    import app.main as m

    monkeypatch.setattr(storage, "DB_PATH", str(tmp_path / "t.sqlite3"))

    def kjor(cases: list[Case]) -> list[str]:
        monkeypatch.setattr(m, "collect_all", lambda si=None, temaer=None: ([], list(cases), []))
        monkeypatch.setattr(m, "build_cases", lambda s: [])
        monkeypatch.setattr(m.coverage, "check", lambda q: {"status": "green", "examples": []})
        monkeypatch.setattr(m, "finalize_scores", lambda c: None)
        monkeypatch.setattr(m, "run_workflow", lambda c, si=None: {
            "mode": "mal", "forsokt": 0, "lyktes": 0, "feilet": 0,
            "gjenbrukt": 0, "i_ko": 0, "feil": ""})
        monkeypatch.setattr(m.ssb_kalender, "collect", lambda **k: ([], []))
        return [c["key"] for c in m.run_scan()["cases"]]

    return kjor


def test_ssb_funn_ligger_foran_gjenbruk_fra_soesteraviser(scan):
    """Kjernen. Et SSB-funn slår en Aftenposten-sak selv om avissaken scorer
    høyere — den er allerede publisert, og da er den ikke journalistens sak."""
    rekkefolge = scan([
        sak("schibsted:Aftenposten:Noe stort", "schibsted", 99.0),
        sak("schibsted:Bergens Tidende:Noe annet", "schibsted", 98.0),
        sak("ssb:12345", "data", 20.0),
    ])
    assert rekkefolge[0] == "ssb:12345", f"gjenbruk kom først: {rekkefolge}"


def test_gjenbrukssaker_regnes_aldri_som_nye(scan, tmp_path, monkeypatch):
    """Selve feilen. Nøkkelen deres er laget av overskriften, så de er «aldri
    sett før» ved hvert skann. Hadde de fått ny-løftet, ville de ligget øverst
    for alltid — uansett hvor mange ganger han trykket søk."""
    import app.main as m

    forste = scan([sak("ssb:1", "data", 10.0)])
    assert forste  # ssb-saken er ny i første skann

    # Andre skann: SSB-saken er sett før, Schibsted-saken har fersk overskrift.
    data = m.load_latest()
    andre_kjoring = scan([
        sak("ssb:1", "data", 10.0),
        sak("schibsted:Aftenposten:Helt fersk overskrift", "schibsted", 90.0),
    ])
    lagret = {c["key"]: c for c in m.load_latest()["cases"]}
    assert lagret["schibsted:Aftenposten:Helt fersk overskrift"]["er_ny"] is False, \
        "gjenbrukssaken ble merket NY — da tar RSS-churn over forsiden"
    assert andre_kjoring[0] == "ssb:1", f"SSB-funnet mistet førsteplassen: {andre_kjoring}"
    assert data is not None


def test_nytt_ssb_funn_slaar_et_gammelt(scan):
    """Ny-løftet skal fortsatt virke der det betyr noe: mellom egne datafunn."""
    scan([sak("ssb:gammel", "data", 50.0)])
    rekkefolge = scan([
        sak("ssb:gammel", "data", 50.0),
        sak("ssb:fersk", "data", 10.0),
    ])
    assert rekkefolge[0] == "ssb:fersk", f"det nye funnet kom ikke først: {rekkefolge}"
