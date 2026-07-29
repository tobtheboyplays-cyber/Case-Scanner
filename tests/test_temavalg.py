"""Menyen skal styre HELE skannet — ikke bare søkesystemet.

Eieren 26.07.2026: «Og den gir ikke det jeg velger i menyen. Ta stor sjekk her nå.»

Han hadde rett, og feilen var lett å overse: `collect_all` sendte `temaer` videre
til ÉN av tre SSB-kilder. De fem faste befolkningsprobene og kvartalstallene for
flytting kjørte uansett hva han huket av. Fordi de scorer høyt, la de seg øverst,
og fordi KI-en bare rekker tre saker per skann, tok de plassene fra det han
faktisk hadde bedt om. Menyen var altså ikke ødelagt — den var pynt.

Testene her måler koblingen (valget når fram til kollektoren) og virkningen
(feil tema ⇒ prober kjøres ikke). Ingen av dem rører nettet.
"""

from __future__ import annotations

from app.collectors import ssb, ssb_flytting
from app.config import SSB_PROBES, demografi_for

# ── Oversetteren: tema → demografi-merkelapper ─────────────────────────────


def test_tema_oversettes_til_demografi():
    assert "bolig og leie" in demografi_for(["bolig og bygg"]) or \
        demografi_for(["bolig og bygg"]) != set()


def test_tomt_valg_betyr_alt():
    """Ingen avhuking = «let bredt». Ville dette gitt tom mengde med SAMME
    betydning som «ingen treff», hadde et umerket skann returnert null saker."""
    assert demografi_for([]) == set()
    assert demografi_for(None) == set()


def test_ukjent_tema_ignoreres_stille():
    """Et gammelt bokmerke med et tema som er døpt om skal ikke velte skannet."""
    assert demografi_for(["Et tema som ikke finnes"]) == set()


# ── De faste probene ───────────────────────────────────────────────────────


def _probe_ider(temaer, monkeypatch) -> list[str]:
    """Kjør ssb.collect() uten nett og registrer HVILKE prober den forsøkte."""
    provd: list[str] = []

    def falsk_fetch(table, query):
        provd.append(table)
        raise RuntimeError("ingen nett i testen — vi måler bare hvem som ble spurt")

    monkeypatch.setattr(ssb, "_fetch", falsk_fetch)
    ssb.collect(temaer)
    return provd


def test_uten_valg_kjorer_alle_probene(monkeypatch):
    assert len(_probe_ider([], monkeypatch)) == len(SSB_PROBES)


def test_valgt_tema_snevrer_inn_probene(monkeypatch):
    """Selve feilen eieren meldte. Velger han klima, skal ikke fem
    befolkningsprober om bolig og jobb legge seg øverst i lista hans."""
    klima = _probe_ider(["natur og miljø"], monkeypatch)
    assert klima == [], f"klimavalg kjørte befolkningsprober: {klima}"


def test_relevant_tema_slipper_probene_gjennom(monkeypatch):
    """Filteret må ikke være så stramt at det slukker kilden. Velger han bolig,
    SKAL boligprobene kjøre."""
    bolig = _probe_ider(["bolig og bygg"], monkeypatch)
    assert bolig, "boligvalg ga ingen prober i det hele tatt"


# ── Flyttetallene ──────────────────────────────────────────────────────────


def test_flyttetall_hoppes_over_utenfor_temaet(monkeypatch):
    """Ingen nettkall skal skje i det hele tatt — hoppet ligger FØR `_hent()`."""
    def eksploder():
        raise AssertionError("flyttetallene ble hentet selv om temaet ikke passet")

    monkeypatch.setattr(ssb_flytting, "_hent", eksploder)
    cases, notater = ssb_flytting.collect(["natur og miljø"])
    assert cases == []
    assert any("temavalget" in n for n in notater), notater


def test_flyttetall_kjorer_naar_temaet_passer(monkeypatch):
    kalt: list[bool] = []

    def falsk_hent():
        kalt.append(True)
        raise RuntimeError("stopp her — vi måler bare at den ble forsøkt")

    monkeypatch.setattr(ssb_flytting, "_hent", falsk_hent)
    ssb_flytting.collect(["bolig og bygg"])
    assert kalt, "flyttetallene ble hoppet over på et tema de dekker"


# ── Koblingen i collect_all ────────────────────────────────────────────────


def test_alle_ssb_kildene_far_temavalget(monkeypatch):
    """Regresjonsvakten. Det var nettopp her feilen lå: to av tre kall sto uten
    argument, og ingen test merket det fordi begge kollektorene fungerte fint."""
    from app import collectors

    fikk: dict[str, object] = {}

    monkeypatch.setattr(collectors.ssb, "collect",
                        lambda t=None: (fikk.__setitem__("ssb", t), ([], []))[1])
    monkeypatch.setattr(collectors.ssb_flytting, "collect",
                        lambda t=None: (fikk.__setitem__("flytting", t), ([], []))[1])
    monkeypatch.setattr(collectors.ssb_sok, "collect",
                        lambda t=None: (fikk.__setitem__("sok", t), ([], []))[1])
    monkeypatch.setattr(collectors.google_trends, "collect", lambda: ([], []))

    collectors.collect_all(None, ["bolig og bygg"])
    assert fikk == {
        "ssb": ["bolig og bygg"],
        "flytting": ["bolig og bygg"],
        "sok": ["bolig og bygg"],
    }, fikk


# ── Brønnøysund følger samme regel ─────────────────────────────────────────


def _skann_med_hendelse(temaer, tmp_path, monkeypatch) -> list[dict]:
    """Kjør run_scan med én konkurs og ingen SSB-treff, og se hva som når lista."""
    from app import main as m
    from app import storage

    monkeypatch.setattr(storage, "DB_PATH", str(tmp_path / "t.sqlite3"))
    storage.sett_temaer(temaer)
    monkeypatch.setattr(m, "collect_all", lambda si=None, temaer=None: ([], [], []))
    monkeypatch.setattr(m, "build_cases", lambda s: [])
    monkeypatch.setattr(m.coverage, "check", lambda q: {"status": "green", "examples": []})
    monkeypatch.setattr(m, "finalize_scores", lambda c: None)
    monkeypatch.setattr(m, "run_workflow", lambda c, si=None: {
        "mode": "mal", "forsokt": 0, "lyktes": 0, "feilet": 0,
        "gjenbrukt": 0, "i_ko": 0, "feil": ""})
    monkeypatch.setattr(m.ssb_kalender, "collect", lambda **k: ([], []))
    monkeypatch.setattr(m.brreg, "collect", lambda *a, **k: ([{
        "type": "konkurs", "navn": "Ekte Kafe As", "kommune": "Stavanger",
        "dato": "2026-07-17", "dager_siden": 9, "bransje": "Drift av restauranter",
        "publikum": "restaurant og servering", "ansatte": 7, "orgnr": "921456875",
        "lenke": "https://virksomhet.brreg.no/nb/oppslag/enheter/921456875",
        "vekt": 9,
    }], []))
    return m.run_scan()["cases"]


def test_konkurser_naar_ikke_lista_paa_et_klimasoek(tmp_path, monkeypatch):
    """Et konkursvedtak er næringsliv. Ba journalisten om klima, er seks
    konkurser ikke svaret — og de tar plassene fra det han faktisk ba om."""
    assert _skann_med_hendelse(["natur og miljø"], tmp_path, monkeypatch) == []


def test_konkurser_naar_lista_paa_et_naeringssoek(tmp_path, monkeypatch):
    """Motprøven. Filteret må ikke slukke kilden på temaene den dekker."""
    saker = _skann_med_hendelse(["næringsliv"], tmp_path, monkeypatch)
    assert [c["key"] for c in saker] == ["brreg:konkurs:921456875"], saker


def test_konkurser_kommer_med_naar_ingenting_er_valgt(tmp_path, monkeypatch):
    """Tomt valg = «let bredt». Da skal alt med."""
    assert _skann_med_hendelse([], tmp_path, monkeypatch), "bredt søk mistet hendelsene"
