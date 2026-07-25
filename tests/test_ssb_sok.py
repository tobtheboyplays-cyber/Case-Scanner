"""Tester for soekesystemet - kjorer uten nettverk (syntetiske SSB-svar).

Den viktigste testen her er `test_avviser_tabell_med_maanedsdimensjon`. Den
festes til en ekte feil: tabell 12983 («Døde i kommuner per måned») har aar
utenpaa og maaned inni, og da vi summerte bort maanedene sammenlignet vi et
halvferdig 2026 med hele 2025. Verktoyet meldte «Døde ned 50 % i Sandnes».
Det var ikke sant. Testen finnes for at det aldri skal skje igjen.
"""

from __future__ import annotations

import pytest
from app import storage
from app.collectors import ssb_sok

# ── Byggeklosser for syntetiske SSB-svar ─────────────────────────────────────


def _dim(etikett: str, koder: list[str], *, elim: bool = True, tekster: dict | None = None):
    return {
        "label": etikett,
        "category": {
            "index": {k: i for i, k in enumerate(koder)},
            "label": tekster or {k: k for k in koder},
        },
        "extension": {"elimination": elim},
    }


def _meta(dims: dict[str, dict], rekkefolge: list[str], roller: dict) -> dict:
    return {"id": rekkefolge, "dimension": dims, "role": roller}


def _kommunetabell_meta(ekstra: dict | None = None, ekstra_navn: str | None = None) -> dict:
    dims = {
        "Region": _dim("region", ["0", "1103", "1108"]),
        "ContentsCode": _dim("statistikkvariabel", ["Tall"], elim=False),
        "Tid": _dim("kvartal", ["2025K2", "2026K2"], elim=False),
    }
    rekkefolge = ["Region", "ContentsCode", "Tid"]
    if ekstra and ekstra_navn:
        dims[ekstra_navn] = ekstra
        rekkefolge.insert(1, ekstra_navn)
    return _meta(dims, rekkefolge, {"geo": ["Region"], "time": ["Tid"], "metric": ["ContentsCode"]})


def _data(perioder: list[str], verdier: list[float], *, metrikker: list[str] | None = None,
          tekster: dict | None = None) -> dict:
    """Kube med Region(1103,1108) x ContentsCode x Tid, rad-major som json-stat2."""
    metrikker = metrikker or ["Tall"]
    return {
        "id": ["Region", "ContentsCode", "Tid"],
        "size": [2, len(metrikker), len(perioder)],
        "dimension": {
            "Region": _dim("region", ["1103", "1108"]),
            "ContentsCode": _dim("statistikkvariabel", metrikker, tekster=tekster),
            "Tid": _dim("kvartal", perioder),
        },
        "value": verdier,
    }


RAD = {
    "id": "99999",
    "label": "99999: Testtabell (K) 2020K1-2026K2",
    "updated": "2026-07-20T06:00:00Z",
    "_spor": "test",
    "timeUnit": "Quarterly",
}


# ── Strukturvurdering: hvilke tabeller kan vi i det hele tatt bruke ──────────


def test_avviser_tabell_med_maanedsdimensjon():
    """Regresjonstest for det falske funnet «Døde ned 50 %» (SSB 12983).

    Aar som tidsvariabel PLUSS en maanedsdimensjon vi summerer bort = et
    paagaaende aar mot et helt aar. Da skal vi lage null saker, ikke én feil.
    """
    meta = _kommunetabell_meta(_dim("måned", [f"{m:02d}" for m in range(1, 13)]), "Maaned")
    verdikt, roller = ssb_sok._vurder(meta)
    assert verdikt == "delvis-periode"
    assert roller is None
    # ... og avslaget maa vaere permanent, ellers prober vi tabellen igjen og igjen.
    assert "delvis-periode" in storage.PERMANENTE_AVSLAG


@pytest.mark.parametrize("etikett", ["måned", "kvartal", "uke", "år", "halvår"])
def test_alle_tidsord_avvises(etikett: str):
    meta = _kommunetabell_meta(_dim(etikett, ["1", "2"]), "Ekstra")
    assert ssb_sok._vurder(meta)[0] == "delvis-periode"


def test_alder_er_ikke_et_tidsord():
    """«alder» og «årsak» inneholder tidsord-lyder men er vanlige dimensjoner."""
    for etikett in ("alder", "aldersgruppe", "dødsårsak", "årslønn"):
        meta = _kommunetabell_meta(_dim(etikett, ["a", "b"]), "Ekstra")
        assert ssb_sok._vurder(meta)[0] == "ok", etikett


def test_avviser_tabell_uten_kommunetall():
    dims = {
        "Region": _dim("region", ["0", "11", "03"]),   # land + fylker, ingen kommune
        "ContentsCode": _dim("statistikkvariabel", ["Tall"], elim=False),
        "Tid": _dim("kvartal", ["2025K2", "2026K2"], elim=False),
    }
    meta = _meta(dims, ["Region", "ContentsCode", "Tid"],
                 {"geo": ["Region"], "time": ["Tid"], "metric": ["ContentsCode"]})
    assert ssb_sok._vurder(meta)[0] == "ingen-kommune"


def test_avviser_dimensjon_som_ikke_kan_elimineres():
    """Kan vi ikke summere bort «næring», vet vi ikke hvilken naering tallet gjelder."""
    meta = _kommunetabell_meta(_dim("næring", ["01", "02"], elim=False), "NACE")
    assert ssb_sok._vurder(meta)[0] == "ikke-eliminerbar"


def test_godtar_ren_kommunetabell():
    verdikt, roller = ssb_sok._vurder(_kommunetabell_meta())
    assert verdikt == "ok"
    assert roller == ("Region", "Tid", "ContentsCode")


# ── Selve funnet: naar blir et tall en sak? ─────────────────────────────────


def test_sammenligner_med_samme_periode_i_fjor_ikke_forrige_kvartal():
    """Sesong: 4. kvartal mot 3. kvartal er nesten alltid feil sammenligning."""
    perioder = ["2025K2", "2025K3", "2025K4", "2026K1", "2026K2"]
    # Stavanger: fjoraarets 2. kvartal = 100, siste = 200 (+100 %).
    # Kvartalet rett foer (2026K1) er 190 - hadde vi brukt det, ville vi meldt +5 %.
    stavanger = [100, 500, 500, 190, 200]
    sandnes = [50, 50, 50, 50, 50]
    sak = ssb_sok._case(RAD, ("Region", "Tid", "ContentsCode"),
                        _data(perioder, [*stavanger, *sandnes]), steg=4)
    assert sak is not None
    assert sak.metric_value == "+100 %"
    assert sak.metric_period == "2026K2 mot 2025K2"
    assert "Stavanger" in sak.title


def test_smaa_tall_gir_ingen_sak():
    """«3 mot 8» er +167 % og likevel ren stoy - begge sider maa vaere store nok."""
    sak = ssb_sok._case(RAD, ("Region", "Tid", "ContentsCode"),
                        _data(["2025K2", "2026K2"], [3, 8, 4, 9]), steg=1)
    assert sak is None


def test_liten_endring_gir_ingen_sak():
    sak = ssb_sok._case(RAD, ("Region", "Tid", "ContentsCode"),
                        _data(["2025K2", "2026K2"], [1000, 1050, 2000, 2080]), steg=1)
    assert sak is None


def test_manglende_tall_velter_ingenting():
    sak = ssb_sok._case(RAD, ("Region", "Tid", "ContentsCode"),
                        _data(["2025K2", "2026K2"], [None, 900, 100, 400]), steg=1)
    assert sak is not None
    assert "Sandnes" in sak.title       # Stavanger manglet tall, Sandnes ga saken


def test_sterkeste_utslag_vinner_paa_tvers_av_statistikkvariabler():
    """Én sak per tabell - den kraftigste, ikke fem varianter av samme funn."""
    perioder = ["2025K2", "2026K2"]
    # Region x ContentsCode x Tid, rad-major: Stavanger(A,B), Sandnes(A,B)
    verdier = [100, 130,   100, 400,      # Stavanger: A +30 %, B +300 %
               100, 105,   100, 110]      # Sandnes: smaatt
    tekster = {"A": "Kort", "B": "Ogsaa kort"}
    sak = ssb_sok._case(RAD, ("Region", "Tid", "ContentsCode"),
                        _data(perioder, verdier, metrikker=["A", "B"], tekster=tekster), steg=1)
    assert sak is not None
    assert sak.metric_value == "+300 %"
    assert "Ogsaa kort" in sak.title


def test_funnet_inneholder_begge_raatallene():
    """Journalisten skal kunne kontrollere prosenten mot tallene den kom fra."""
    sak = ssb_sok._case(RAD, ("Region", "Tid", "ContentsCode"),
                        _data(["2025K2", "2026K2"], [30, 261, 40, 45]), steg=1)
    assert sak is not None
    assert "30" in sak.finding and "261" in sak.finding
    assert "99999" in sak.data_source and sak.data_url.endswith("99999")


# ── Smaating som likevel avgjor om UI-et er lesbart ─────────────────────────


def test_hovedtall_velger_korteste_etiketter_forst():
    dim = _dim("statistikkvariabel", ["lang", "kort", "mellom"], tekster={
        "lang": "Korrigerte brutto driftsutgifter til lokaler og skyss per barn",
        "kort": "Døde",
        "mellom": "Godkjente boliger",
    })
    assert ssb_sok._hovedtall(dim, 2) == ["kort", "mellom"]


def test_kort_kutter_paa_ordgrense():
    assert ssb_sok._kort("Kort nok", 20) == "Kort nok"
    lang = ssb_sok._kort("Korrigerte brutto driftsutgifter til lokaler og skyss", 25)
    assert lang.endswith("…") and len(lang) <= 27 and not lang.startswith(" ")


def test_rydder_tabellnavn():
    assert ssb_sok._rydd_tittel("07165: Opna konkursar (K) 2006K1-2026K2") == "Opna konkursar (K)"


def test_tidssteg_folger_tidsenhet():
    assert ssb_sok._tidssteg({"timeUnit": "Quarterly"}) == 4
    assert ssb_sok._tidssteg({"timeUnit": "Monthly"}) == 12
    assert ssb_sok._tidssteg({"timeUnit": "Annual"}) == 1
    assert ssb_sok._tidssteg({}) == 1          # ukjent enhet: anta aarlig


# ── Hukommelsen: derfor gir «soek igjen» noe nytt ───────────────────────────


@pytest.fixture()
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", str(tmp_path / "test.sqlite3"))
    return tmp_path


def test_permanent_avslag_probes_aldri_igjen(db):
    storage.marker_ssb_tabell("111", "ingen-kommune", oppdatert="2026-01-01")
    kjent = storage.ssb_utforsket()
    assert storage.bor_probes("111", "2026-09-09", kjent) is False   # selv med nye tall


def test_midlertidig_avslag_probes_paa_nytt_naar_ssb_har_nye_tall(db):
    storage.marker_ssb_tabell("222", "under-terskel", oppdatert="2026-01-01")
    kjent = storage.ssb_utforsket()
    assert storage.bor_probes("222", "2026-01-01", kjent) is False   # samme tall som sist
    assert storage.bor_probes("222", "2026-04-01", kjent) is True    # SSB har publisert nytt


def test_ukjent_tabell_alltid_verdt_et_forsok(db):
    assert storage.bor_probes("333", "2026-01-01", storage.ssb_utforsket()) is True


def test_rotasjonen_gaar_videre_og_runder(db):
    tema = ["a", "b", "c"]
    assert storage.neste_i_rotasjon("t", tema, 2) == ["a", "b"]
    assert storage.neste_i_rotasjon("t", tema, 2) == ["c", "a"]      # runder rundt
    assert storage.neste_i_rotasjon("t", tema, 2) == ["b", "c"]


def test_rotasjonen_taaler_soppel_i_markoeren(db):
    storage.meta_set("t", "ikke et tall")
    assert storage.neste_i_rotasjon("t", ["a", "b"], 1) == ["a"]
