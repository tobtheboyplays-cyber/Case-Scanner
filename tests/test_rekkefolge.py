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

    tomt_regnskap = {"mode": "mal", "forsokt": 0, "lyktes": 0, "feilet": 0,
                     "gjenbrukt": 0, "i_ko": 0, "feil": ""}

    def kjor(cases: list[Case], workflow=None) -> list[str]:
        monkeypatch.setattr(m, "collect_all", lambda si=None, temaer=None: ([], list(cases), []))
        monkeypatch.setattr(m, "build_cases", lambda s: [])
        monkeypatch.setattr(m.coverage, "check", lambda q: {"status": "green", "examples": []})
        monkeypatch.setattr(m, "finalize_scores", lambda c: None)
        monkeypatch.setattr(
            m, "run_workflow",
            workflow or (lambda c, si=None: dict(tomt_regnskap)))
        monkeypatch.setattr(m.ssb_kalender, "collect", lambda **k: ([], []))
        monkeypatch.setattr(m.brreg, "collect", lambda *a, **k: ([], []))
        kjor.siste = m.run_scan()
        return [c["key"] for c in kjor.siste["cases"]]

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


def test_uendret_tall_viker_for_det_som_er_nytt(scan):
    """Eieren 26.07.2026: «når man trykker søk igjen skal nye tall dukke opp,
    aldri den samme».

    De faste SSB-probene spør de SAMME tabellene hver gang. Uten dette kom de
    samme fem funnene tilbake ved hvert skann, med identiske tall, og druknet
    det som faktisk var nytt."""
    scan([sak("ssb:fast", "data", 10.0, verdi="+3 %")])
    andre = scan([
        sak("ssb:fast", "data", 90.0, verdi="+3 %"),   # høyest score, men uendret
        sak("ssb:fersk", "data", 10.0, verdi="+41 %"),
    ])
    assert andre == ["ssb:fersk"], f"gjengangeren tok plassen fra det nye: {andre}"


def test_et_skann_blir_aldri_tomt(scan):
    """Eieren 26.07.2026: «når jeg scanner så kommer det ingenting».

    Har ingenting endret seg, er det et ærlig svar — men et blankt dashboard ser
    ut som at verktøyet er i stykker, og journalisten kan ikke se forskjell. Da
    viser vi gjengangerne på nytt, MERKET, i stedet for ingenting."""
    scan([sak("ssb:fast", "data", 10.0, verdi="+3 %")])
    andre = scan([sak("ssb:fast", "data", 10.0, verdi="+3 %")])

    assert andre == ["ssb:fast"], f"skjermen ble tom: {andre}"
    sak_dict = scan.siste["cases"][0]
    assert sak_dict["uendret"] is True, "gjengangeren ble ikke merket som uendret"
    assert any("endret seg" in s for s in scan.siste["status"]), scan.siste["status"]


def test_gjengangeren_merkes_ikke_naar_den_faktisk_er_fersk(scan):
    """Merket må bety noe. Står «UENDRET» på et ferskt funn, slutter man å tro
    på det."""
    scan([sak("ssb:x", "data", 10.0, verdi="+41 %")])
    assert not scan.siste["cases"][0]["uendret"]


def test_ki_en_kjorer_paa_det_som_faktisk_vises(scan):
    """Selve feilen bak «det kommer ingenting».

    KI-flyten sto FØR uendret-filteret: den brukte hele budsjettet (tre saker per
    skann) på de høyest scorede funnene — de faste SSB-probene — og rett etterpå
    fjernet filteret nettopp dem fordi tallene sto stille. Kvota var brukt opp på
    noe som aldri ble vist. Denne testen måler HVA KI-en fikk se."""
    sett: list[list[str]] = []

    def spion(cases, si=None):
        sett.append([c.key for c in cases])
        return {"mode": "mal", "forsokt": 0, "lyktes": 0, "feilet": 0,
                "gjenbrukt": 0, "i_ko": 0, "feil": ""}

    scan([sak("ssb:fast", "data", 90.0, verdi="+3 %")])
    scan([
        sak("ssb:fast", "data", 90.0, verdi="+3 %"),
        sak("ssb:fersk", "data", 10.0, verdi="+41 %"),
    ], workflow=spion)
    assert sett == [["ssb:fersk"]], f"KI-en brukte kvota på en skjult sak: {sett}"


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


def test_tom_skjerm_forklarer_seg_i_stedet_for_aa_vaere_blank(tmp_path, monkeypatch):
    """Eieren 26.07.2026: «når jeg scanner så kommer det ingenting».

    Malen hoppet BOKSTAVELIG TALT over hele hoveddelen når `data.cases` var tom:
    ingen overskrift, ingen forklaring, ingen kildestatus. Journalisten kunne
    ikke skille «kildene hadde ingenting nytt» fra «appen er ødelagt».

    Den ærlige varianten sier hva som skjedde, hva han gjør nå, og viser
    statuslinjene fra skannet så han kan sjekke det selv.
    """
    from app import storage as s
    from app.main import app
    from fastapi.testclient import TestClient

    monkeypatch.setattr(s, "DB_PATH", str(tmp_path / "t.sqlite3"))
    s.save_scan({"cases": [], "plan": {}, "summary": {}, "ai_mode": "mal",
                 "status": ["SSB: 0 av 5 befolkningsprober passer temavalget"]})

    html = TestClient(app).get("/").text
    assert "Skannet fant ingen nye saker" in html
    assert "Temavalget er for smalt" in html
    assert "Velg flere temaer" in html
    # Kildestatusen er det som gjør svaret etterrettelig.
    assert "0 av 5 befolkningsprober" in html
