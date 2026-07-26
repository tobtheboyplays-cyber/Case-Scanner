"""Fra menyvalget til kortet på skjermen — med ekte kode hele veien.

Eieren 26.07.2026: «Synes testene dine ikke er gode nok siden vi alltid må
dobbeltsjekke. Jeg vil at du har grundigere tester.»

Han har rett, og diagnosen er konkret. De gamle testene byttet ut `collect_all`,
`run_workflow` og `coverage.check` med attrapper, og målte så at resten oppførte
seg. Men feilen han meldte — «den gir ikke det jeg velger i menyen» — lå NØYAKTIG
i koblingen de hadde byttet ut: `collect_all` sendte temavalget til én av tre
SSB-kilder. 236 grønne tester merket ingenting.

Her byttes bare `httpx.get` og `httpx.post` (se tests/nett.py). Alt annet er ekte:
menyskjemaet, temafilteret, probene, json-stat-parsingen, dekningssjekken,
scoringen, uendret-filteret, rangeringen, lagringen og HTML-en. En test som består
her, sier noe om det journalisten faktisk ser.

Testene påstår to slags ting, og begge trengs:
  · HVA SOM BLE SPURT OM  — `nett.spurte_om("07459")`. Fanger døde koblinger.
  · HVA SOM STÅR PÅ SIDA  — teksten i HTML-en. Fanger at riktig data likevel
    aldri når fram til malen.
"""

from __future__ import annotations

import re
from urllib.parse import urlencode

import httpx
import pytest
from fastapi.testclient import TestClient

from tests.nett import Nett


@pytest.fixture()
def app_uten_nett(tmp_path, monkeypatch):
    """En ekte app med et falskt internett. Returnerer (klient, nett)."""
    from app import agents, llm, main, storage

    monkeypatch.setattr(storage, "DB_PATH", str(tmp_path / "t.sqlite3"))

    # KI-en er AV: den krever nøkkel og ekte kvote. Vinklene har egne tester
    # (test_vinkler_uansett.py) — disse handler om kilder, filtre og visning.
    monkeypatch.setattr(main, "ENABLE_AI", False)
    monkeypatch.setattr(agents.llm, "has_llm", lambda: False)
    monkeypatch.setattr(llm, "has_llm", lambda: False)

    nett = Nett()
    koble_til(nett, monkeypatch)

    # TestClient bruker sin egen transport, ikke modulnivå-httpx, så appen selv
    # svarer fortsatt normalt.
    return TestClient(main.app), nett


def koble_til(nett: Nett, monkeypatch) -> None:
    """Sett det falske nettet inn der kollektorene faktisk henter.

    To steder, og begge må med:
      · `http_get` er importert INN i hver kollektormodul (`from ...base import
        http_get`), så navnet må byttes i deres modul — conftest har allerede
        satt det til en `pytest.fail`, og siste tilordning vinner.
      · `app/collectors/ssb.py` kaller `httpx.post` direkte.

    Merk hvorfor dette ikke kan gjøres med bare `httpx.get`: conftest-stubben
    ligger foran, og den kaster `Failed` — som arver fra `BaseException` og
    dermed går rett forbi alle `except Exception` i fail-soft-kollektorene, ut
    av `run_scan`, forbi feilfangsten i `jobs.start`, og etterlater jobben i
    «kjorer» for alltid. Et helt skann hang i 240 sekunder på det.
    """
    from app.collectors import (
        brreg,
        coverage,
        news_rss,
        reddit,
        ssb,
        ssb_flytting,
        ssb_kalender,
        ssb_sok,
    )

    for mod in (brreg, coverage, news_rss, reddit, ssb, ssb_flytting,
                ssb_kalender, ssb_sok):
        if hasattr(mod, "http_get"):
            monkeypatch.setattr(mod, "http_get", nett.get)
    monkeypatch.setattr(httpx, "post", nett.post)


def skann(klient, temaer: list[str] | None = None) -> str:
    """Trykk «Skann nå» med de temaene avhuket, og returner HTML-en etterpå.

    Går gjennom det EKTE skjemaet (POST /scan med `tema`-felter), ikke gjennom
    en intern funksjon — da måles også at menyen sender det den viser.
    """
    # `meny=1` er det skjemaet i malen sender. Uten det tolker /scan skannet som
    # startet et annet sted (kø-knappen, cron) og lar temavalget staa urort — og
    # da hadde testen malt noe annet enn den tror.
    #
    # Kroppen bygges for haand, ikke via `data=`: TestClient/httpx koder ikke
    # «ø» slik en nettleser gjor, saa «natur og miljø» kom fram forvansket og
    # ble stille forkastet av `sett_temaer` (ukjent navn). Da hadde ET TEMASOEK
    # I TESTEN VAERT ET BREDT SOEK, og temafiltrene ville sett grønne ut uansett
    # hva de gjorde. Slik ser en test ut som lyver. Her sendes nøyaktig det en
    # nettleser sender — UTF-8, prosentkodet — saa appens egen dekoding maales
    # ogsaa.
    par = [("meny", "1")] + [("tema", t) for t in (temaer or [])]
    kropp = urlencode(par, encoding="utf-8")
    svar = klient.post(
        "/scan", content=kropp, follow_redirects=True,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert svar.status_code == 200, svar.status_code
    return klient.get("/").text


# ── 1. Menyen styrer faktisk hva som hentes ────────────────────────────────


def test_bredt_soek_spor_om_befolkningstallene(app_uten_nett):
    """Grunnlinjen. Uten denne kan «klimasøket spurte ikke» skyldes at ingenting
    spør om noe som helst."""
    klient, nett = app_uten_nett
    skann(klient, [])
    assert nett.spurte_om("07459"), "de faste befolkningsprobene kjørte ikke i det hele tatt"
    assert nett.spurte_om("01222"), "flyttetallene kjørte ikke"


def test_klimasoek_spor_ikke_om_befolkning(app_uten_nett):
    """Selve feilen eieren meldte, målt der den oppstår: i trafikken ut.

    Dette er påstanden ingen av de 236 gamle testene kunne stille, fordi de
    hadde byttet ut kollektorlaget med en attrapp."""
    klient, nett = app_uten_nett
    skann(klient, ["natur og miljø"])
    assert not nett.spurte_om("07459"), "klimavalget kjørte befolkningsprobene likevel"
    assert not nett.spurte_om("01222"), "klimavalget kjørte flyttetallene likevel"


def test_boligsoek_spor_om_befolkning_igjen(app_uten_nett):
    """Motprøven. Et filter som slukker alt består den forrige testen også."""
    klient, nett = app_uten_nett
    skann(klient, ["bolig og bygg"])
    assert nett.spurte_om("07459"), "boligvalget mistet befolkningsprobene"


def test_valget_staar_igjen_i_menyen_etterpaa(app_uten_nett):
    """Menyen må vise det den faktisk skannet etter. Gjør den ikke det, tror
    journalisten han har valgt noe annet enn han har."""
    klient, _ = app_uten_nett
    html = skann(klient, ["bolig og bygg"])

    def avhuket(tema: str) -> bool:
        # `checked` staar paa linja etter `value=`, saa vi ser paa hele taggen.
        m = re.search(rf'value="{re.escape(tema)}"(.*?)/>', html, re.S)
        assert m, f"fant ikke avkryssingsboksen for «{tema}»"
        return "checked" in m.group(1)

    assert avhuket("bolig og bygg"), "det valgte temaet sto ikke avhuket etterpå"
    assert not avhuket("natur og miljø"), "et tema han IKKE valgte sto avhuket"


# ── 2. Tallene når helt fram til kortet ────────────────────────────────────


def test_funnet_fra_ssb_staar_paa_sida_med_tall_og_kilde(app_uten_nett):
    """Hele kjeden i én påstand: HTTP-svar → json-stat-parsing → prosentregning
    → Case → scoring → mal. Går noe i stykker underveis, faller denne."""
    klient, _ = app_uten_nett
    html = skann(klient, [])
    assert "Stavanger" in html
    assert "42,0 %" in html, "prosentendringen fra kuben nådde ikke kortet"
    assert "SSB" in html and "statbank/table/07459" in html, "kilden mangler"


def test_konkursen_blir_et_kort_med_lenke_til_brreg(app_uten_nett):
    """Brønnøysund er en primærkilde, ikke en fane. Kortet må ha lenka
    journalisten skal klikke."""
    klient, _ = app_uten_nett
    html = skann(klient, [])
    assert "TESTKAFEEN AS".title() in html or "Testkafeen As" in html
    assert "virksomhet.brreg.no/nb/oppslag/enheter/921456875" in html


# ── 3. Et skann kommer aldri tilbake tomt ──────────────────────────────────


def test_andre_skann_med_uendrede_tall_gir_merkede_kort_ikke_blank_side(app_uten_nett):
    """«Når jeg scanner så kommer det ingenting.»

    Kildene svarer helt likt to ganger — det vanligste tilfellet, siden SSB
    publiserer på faste datoer. Før ble sida da helt tom."""
    klient, _ = app_uten_nett
    skann(klient, [])
    html = skann(klient, [])

    assert "Skannet fant ingen nye saker" not in html, "sida ble tom likevel"
    assert "UENDRET" in html, "gjengangerne ble ikke merket"
    assert "Ingen tall har endret seg" in html, "statuslinjen forklarte ikke hvorfor"


def test_helt_tomt_resultat_forklarer_seg_i_stedet_for_aa_vaere_blankt(app_uten_nett):
    """Grensetilfellet: smalt tema OG ingen historikk å falle tilbake på. Da er
    tomt et ærlig svar — men det må si det, ikke bare vise ingenting."""
    klient, _ = app_uten_nett
    html = skann(klient, ["natur og miljø"])

    assert "Skannet fant ingen nye saker" in html
    assert "Temavalget er for smalt" in html
    assert "Kildestatus" in html, "svaret er ikke etterrettelig uten kildestatusen"


# ── 4. En død kilde velter ikke skannet ────────────────────────────────────


def test_brreg_nede_stopper_ikke_ssb_funnene(app_uten_nett, monkeypatch):
    """Fail-soft er en påstand om oppførsel, ikke en kommentar i koden."""
    klient, nett = app_uten_nett
    ekte_get = nett.get

    def av_og_til_nede(url, **kw):
        if "data.brreg.no" in url:
            raise httpx.ConnectError("brreg er nede")
        return ekte_get(url, **kw)

    monkeypatch.setattr(httpx, "get", av_og_til_nede)
    html = skann(klient, [])
    assert "42,0 %" in html, "en død sidekilde tok med seg hele skannet"


def test_ssb_nede_gir_en_forstaaelig_side_ikke_en_femhundre(app_uten_nett, monkeypatch):
    """Hele hovedkilden borte. Journalisten skal se hva som skjedde, ikke en
    feilside — og statuslinjene skal si hvilken kilde som sviktet."""
    klient, _ = app_uten_nett

    class Nede:
        def get(self, url, **kw):
            raise httpx.ConnectError("nett nede")

        post = get

    koble_til(Nede(), monkeypatch)   # type: ignore[arg-type]
    html = skann(klient, [])
    assert "Skannet fant ingen nye saker" in html
    assert "[FEIL]" in html, "feilen ble ikke rapportert i kildestatusen"


# ── 5. Journalistens egne valg overlever et nytt skann ─────────────────────


def test_forkastet_sak_kommer_ikke_tilbake_ved_neste_skann(app_uten_nett):
    """Sveiper han bort en sak, er den borte — også når kilden leverer den på
    nytt. Dette er lett å miste når rekkefølgen i run_scan endres, og det gjorde
    den nettopp."""
    klient, _ = app_uten_nett
    skann(klient, [])

    noekler = [c["key"] for c in klient.get("/api/cases").json()["cases"]]
    assert noekler, "ingen saker å forkaste — testen måler ikke det den tror"
    klient.post(f"/leads/{noekler[0]}/reject", follow_redirects=True)

    html = skann(klient, [])
    assert noekler[0] not in html, "en forkastet sak kom tilbake"


# ── 6. Trendlinja bygges opp over flere skann ──────────────────────────────


def test_trendlinja_staar_der_paa_foerste_skann(app_uten_nett, monkeypatch):
    """Trendlinja må virke FØRSTE gang han trykker, ikke om tre måneder.

    Det var den opprinnelige innvendingen mot funksjonen: en linje som bygger
    seg opp av ett punkt per skann er et løfte, ikke et verktøy. SSB sender hele
    tidsserien i det samme svaret — vi brukte to punkter og kastet resten.

    Alt mellom HTTP-svaret og setningen på sida er ekte kode her:
    json-stat-parsingen, serieuttrekket, serienøkkelen, lagringen per periode,
    trendberegningen og malen.
    """
    from tests import nett as N

    klient, _ = app_uten_nett
    # Fallende gjennom hele serien: fire år på rad ned.
    monkeypatch.setattr(N, "BEFOLKNING", N.jsonstat(
        {"1103": [1800, 1600, 1400, 1200], "11": [5000] * 4, "0": [50000] * 4},
        ["2023", "2024", "2025", "2026"],
    ), raising=False)

    html = skann(klient, [])
    assert "på rad med nedgang" in html, "trendsetningen nådde ikke sida"
    assert "<polyline" in html, "sparklinen ble ikke tegnet"


def test_trendlinja_tar_med_nye_perioder_over_flere_skann(app_uten_nett, monkeypatch):
    """Serien fra kilden er starten; morgenskannene forlenger den.

    Her flytter vinduet seg ett år per skann, slik SSB faktisk oppfører seg, og
    det eldste punktet skal fortsatt ligge i linja etterpå — det er hele poenget
    med å lagre per periode i stedet for per skann.
    """
    from tests import nett as N

    klient, _ = app_uten_nett
    aar = ["2022", "2023", "2024", "2025", "2026"]
    html = ""
    for i, verdi in enumerate((1400, 1200, 1000)):
        monkeypatch.setattr(N, "BEFOLKNING", N.jsonstat(
            {"1103": [1800, 1600, verdi], "11": [5000] * 3, "0": [50000] * 3},
            aar[i : i + 3],
        ), raising=False)
        html = skann(klient, [])

    assert "på rad med nedgang" in html
    # 2022 kom bare med i FØRSTE skann. Ligger det fortsatt i linja, er
    # historikken ekte og ikke bare siste svar tegnet opp.
    assert "2022" in html, "det eldste punktet forsvant mellom skannene"


def test_ett_skann_paastaar_ingen_trend(app_uten_nett):
    """Grensen som gjør linja etterrettelig. Ett skann er ett punkt, og en
    «trend» fra ett punkt ville vært ren oppdiktning."""
    klient, _ = app_uten_nett
    html = skann(klient, [])
    assert "på rad med" not in html, html[:200]
