"""Rekkefølgen på forsiden: primærkilder først.

Eieren meldte det to ganger. Først 26.07.2026: «Nå bruker den plutselig
Aftenposten og Bergens Tidende som kilder.» Da demoterte jeg dem bare. Så, samme
dag: «Alt slikt dropper vi. Den skal bruke kilder som kan LAGE artikler, ikke
artikler for å lage artikler. De skal være først.»

Den andre meldingen er den som gjelder: avis-RSS er slettet som lead-kilde, ikke
skrudd av. Det som er igjen er råstoff ingen har skrevet ut ennå — SSB-tall og
Brønnøysund-hendelser — og de rangerer likt på toppen. Google Trends er et
signal om hva folk søker på, og ligger under.

Avisartikler brukes fortsatt ett sted: dekningssjekken, som svarer «har noen
allerede skrevet dette?». Det er å bruke dem som fasit, ikke som råstoff.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from app import storage
from app.models import Case


def sak(key: str, kind: str, score: float, verdi: str = "") -> Case:
    return Case(
        key=key, title=key, kind=kind, geo="lokal", score=score,
        topics=[], angle="", why="", signals=[], created_at=datetime.now(UTC),
        coverage_status="green", metric_value=verdi or key,
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
        monkeypatch.setattr(m.brreg, "collect", lambda *a, **k: ([], []))
        return [c["key"] for c in m.run_scan()["cases"]]

    return kjor


def test_primaerkilder_ligger_foran_grasrot(scan):
    """Kjernen. Et SSB-tall og et konkursvedtak er råstoff ingen har skrevet ut;
    et Google Trends-søk er et signal om hva folk lurer på. Råstoffet først —
    også når signalet scorer høyere."""
    rekkefolge = scan([
        sak("trend:noe-folk-soker-paa", "grasrot", 99.0),
        sak("brreg:konkurs:921456875", "hendelse", 20.0),
        sak("ssb:12345", "data", 18.0),
    ])
    assert rekkefolge[0] in ("brreg:konkurs:921456875", "ssb:12345"), rekkefolge
    assert rekkefolge[-1] == "trend:noe-folk-soker-paa", rekkefolge


# Selve kilderegelen - at avis-RSS ikke finnes som lead-kilde i det hele tatt -
# voktes i tests/test_kilder.py. Her handler det bare om rekkefølgen.


def test_uendret_tall_kommer_ikke_tilbake(scan):
    """Eieren 26.07.2026: «når man trykker søk igjen skal nye tall dukke opp,
    aldri den samme».

    De faste SSB-probene spør de SAMME tabellene hver gang. Uten dette kom de
    samme fem funnene tilbake ved hvert skann, med identiske tall, og druknet
    det som faktisk var nytt."""
    scan([sak("ssb:fast", "data", 10.0, verdi="+3 %")])
    andre = scan([sak("ssb:fast", "data", 10.0, verdi="+3 %")])
    assert andre == [], f"samme sak med samme tall kom tilbake: {andre}"


def test_samme_sak_med_nytt_tall_er_en_ny_sak(scan):
    """Grensen som gjør filteret trygt: det er TALLET som må være uendret, ikke
    saken. Publiserer SSB nye tall for samme tabell, skal den fram igjen."""
    scan([sak("ssb:fast", "data", 10.0, verdi="+3 %")])
    andre = scan([sak("ssb:fast", "data", 10.0, verdi="+31 %")])
    assert andre == ["ssb:fast"], f"nytt tall ble skjult: {andre}"


def test_nytt_ssb_funn_slaar_et_gammelt(scan):
    """Ny-løftet skal fortsatt virke der det betyr noe: mellom egne datafunn."""
    scan([sak("ssb:gammel", "data", 50.0)])
    rekkefolge = scan([
        sak("ssb:gammel", "data", 50.0),
        sak("ssb:fersk", "data", 10.0),
    ])
    assert rekkefolge[0] == "ssb:fersk", f"det nye funnet kom ikke først: {rekkefolge}"
