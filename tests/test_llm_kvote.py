"""Tester for KI-lagets kvotestyring, 429-håndtering og leverandørkjede.

Bakgrunn: 26.07.2026 kom dette fra journalistens telefon midt i et skann:

    Groq (gratis): HTTPStatusError: Client error '429 Too Many Requests'

Nøkkelen var riktig. Ett skann fyrte av inntil 15 kall uten pause mot et tak på
12 000 tokens/minutt. Verre: appen kunne fortsatt si «KI: på» etterpå, fordi ett
enkelt vellykket kall holdt. Testene her holder begge feilene lukket.

Ingen av testene rører nettet - httpx.post byttes ut.
"""

from __future__ import annotations

import time
from datetime import UTC

import pytest
from app import llm


@pytest.fixture(autouse=True)
def rene_kvoter(monkeypatch):
    """Hver test starter med tomme kvotevinduer og et kjent miljø."""
    for navn in llm.LEVERANDORER:
        llm._KVOTER[navn] = llm._Kvote(llm.LEVERANDORER[navn].tpm)
    for n in ("GROQ_API_KEY", "OPENROUTER_API_KEY", "ANTHROPIC_API_KEY",
              "GEMINI_API_KEY", "CASE_RADAR_OLLAMA"):
        monkeypatch.delenv(n, raising=False)
    llm._sett_feil(None)


class FalsktSvar:
    """Minimal httpx.Response-erstatter."""

    def __init__(self, status=200, json_data=None, headers=None, text=""):
        self.status_code = status
        self._json = json_data or {}
        self.headers = headers or {}
        self.text = text

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def _ok(innhold: str = '{"svar": "ja"}', headers=None) -> FalsktSvar:
    return FalsktSvar(
        200, {"choices": [{"message": {"content": innhold}}]}, headers or {}
    )


def _429(retry_after: str | None = "3", tekst: str = "") -> FalsktSvar:
    return FalsktSvar(429, {}, {"retry-after": retry_after} if retry_after else {}, tekst)


# ── 429 er en beskjed om å vente, ikke en feil ───────────────────────────────


def test_429_gir_retry_med_leverandorens_egen_ventetid(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "x")
    svar = [_429("2"), _ok()]
    ventet = []
    monkeypatch.setattr("httpx.post", lambda *a, **k: svar.pop(0))
    monkeypatch.setattr(llm.time, "sleep", ventet.append)

    assert llm.complete_json("s", "u", model="m") == {"svar": "ja"}
    assert 2.0 in ventet, f"skulle ventet 2 s som retry-after sa, ventet: {ventet}"
    assert llm.last_error() is None


def test_retry_after_leses_fra_teksten_naar_headeren_mangler(monkeypatch):
    """Groq skriver «Please try again in 7.5s» i kroppen. Den er like god."""
    monkeypatch.setenv("GROQ_API_KEY", "x")
    svar = [_429(None, "Rate limit reached. Please try again in 7.5s"), _ok()]
    ventet = []
    monkeypatch.setattr("httpx.post", lambda *a, **k: svar.pop(0))
    monkeypatch.setattr(llm.time, "sleep", ventet.append)

    assert llm.complete_json("s", "u", model="m") is not None
    assert 7.5 in ventet


def test_vi_venter_aldri_lenger_enn_taket(monkeypatch):
    """Et skann som står stille i ti minutter er ikke et skann."""
    monkeypatch.setenv("GROQ_API_KEY", "x")
    svar = [_429("600"), _ok()]
    ventet = []
    monkeypatch.setattr("httpx.post", lambda *a, **k: svar.pop(0))
    monkeypatch.setattr(llm.time, "sleep", ventet.append)

    llm.complete_json("s", "u", model="m")
    assert max(ventet) <= llm.MAKS_VENT


def test_429_hele_veien_gir_aerlig_feil_ikke_stillhet(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "x")
    monkeypatch.setattr("httpx.post", lambda *a, **k: _429("1"))
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)

    assert llm.complete_json("s", "u", model="m") is None
    assert "kvotetak" in (llm.last_error() or "")


# ── Leverandørkjede ─────────────────────────────────────────────────────────


def test_kjeden_gaar_videre_naar_forste_leverandor_er_tom(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "x")
    monkeypatch.setenv("OPENROUTER_API_KEY", "y")
    assert llm.leverandorkjede() == ["groq", "openrouter"]

    brukt = []

    def falsk_post(url, **k):
        brukt.append(url)
        return _429("1") if "groq" in url else _ok()

    monkeypatch.setattr("httpx.post", falsk_post)
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)

    assert llm.complete_json("s", "u", model="m") == {"svar": "ja"}
    assert any("groq" in u for u in brukt)
    assert any("openrouter" in u for u in brukt)


def test_feil_nokkel_gir_ikke_retry_mot_samme_leverandor(monkeypatch):
    """401 blir ikke bedre av å vente. Da er poenget å komme videre."""
    monkeypatch.setenv("GROQ_API_KEY", "x")
    monkeypatch.setenv("OPENROUTER_API_KEY", "y")
    kall = []

    def falsk_post(url, **k):
        kall.append(url)
        if "groq" in url:
            return FalsktSvar(401)
        return _ok()

    monkeypatch.setattr("httpx.post", falsk_post)
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)

    assert llm.complete_json("s", "u", model="m") is not None
    assert sum(1 for u in kall if "groq" in u) == 1, "401 skal ikke prøves om igjen"


def test_uten_noen_nokkel_er_svaret_none_og_grunnen_tydelig():
    assert llm.complete_json("s", "u", model="m") is None
    assert "ingen KI-nokkel" in (llm.last_error() or "")


# ── Kvotestyring: vent heller enn å bli avvist ──────────────────────────────


def test_kvoten_venter_naar_minuttvinduet_er_fullt():
    kvote = llm._Kvote(tpm=1000)
    kvote.registrer(900)
    assert kvote.ventetid(50) == 0.0, "det er plass til 50 til"
    assert kvote.ventetid(500) > 0, "500 sprenger vinduet - vi må vente"


def test_kvoten_slipper_alt_gjennom_uten_kjent_tak():
    """Ollama kjører lokalt. Å pace mot en grense som ikke finnes er bare treghet."""
    assert llm._Kvote(tpm=0).ventetid(999_999) == 0.0


def test_leverandorens_egen_telling_slaar_vaart_anslag():
    kvote = llm._Kvote(tpm=1000)
    kvote.registrer(2000)                 # vårt anslag sier: fullt
    assert kvote.ventetid(100) > 0
    kvote.fasit(5000)                     # leverandøren sier: masse igjen
    assert kvote.ventetid(100) == 0.0


def test_gammelt_forbruk_faller_ut_av_vinduet():
    kvote = llm._Kvote(tpm=1000)
    kvote._brukt = [(time.monotonic() - 120, 5000)]   # to minutter gammelt
    assert kvote.ventetid(500) == 0.0


def test_pacing_venter_for_kallet_i_stedet_for_aa_bli_avvist(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "x")
    llm._KVOTER["groq"].registrer(llm.LEVERANDORER["groq"].tpm)   # fyll vinduet
    ventet = []
    monkeypatch.setattr("httpx.post", lambda *a, **k: _ok())
    monkeypatch.setattr(llm.time, "sleep", ventet.append)

    llm.complete_json("s" * 400, "u" * 400, model="m")
    assert ventet and ventet[0] > 0, "skulle ventet før kallet, ikke etter"


def test_leverandoren_forteller_hvor_mye_kvote_som_er_igjen(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "x")
    monkeypatch.setattr(
        "httpx.post",
        lambda *a, **k: _ok(headers={"x-ratelimit-remaining-tokens": "9000"}),
    )
    llm.complete_json("s", "u", model="m")
    assert llm._KVOTER["groq"]._fasit == 9000


# ── Framdrift og feilmelding ────────────────────────────────────────────────


def test_brukeren_faar_vite_at_vi_venter(monkeypatch):
    """Uten dette står skannet bare stille og ser hengt ut."""
    monkeypatch.setenv("GROQ_API_KEY", "x")
    svar = [_429("2"), _ok()]
    linjer = []
    monkeypatch.setattr("httpx.post", lambda *a, **k: svar.pop(0))
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)

    llm.complete_json("s", "u", model="m", si=linjer.append)
    assert any("venter" in x.lower() for x in linjer), linjer


def test_feilmeldingen_er_per_traad(monkeypatch):
    """To jobber kjører samtidig i hver sin tråd. Før overskrev de hverandres
    feilmelding, og en vellykket jobb slettet beviset for at en annen feilet."""
    import threading

    llm._sett_feil("min feil")
    andres = {}

    def annen_traad():
        andres["feil"] = llm.last_error()
        llm._sett_feil("noe helt annet")

    t = threading.Thread(target=annen_traad)
    t.start()
    t.join()

    assert andres["feil"] is None, "tråden skal ikke se en annen tråds feil"
    assert llm.last_error() == "min feil", "og min egen skal overleve"


def test_manglende_anthropic_pakke_sier_hva_som_mangler(monkeypatch):
    """`anthropic` er en valgfri avhengighet. Settes nøkkelen uten pakken, skal
    feilen si hvordan man fikser det - ikke bare «ModuleNotFoundError»."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    import builtins

    ekte_import = builtins.__import__

    def uten_anthropic(navn, *a, **k):
        if navn == "anthropic":
            raise ModuleNotFoundError("No module named 'anthropic'")
        return ekte_import(navn, *a, **k)

    monkeypatch.setattr(builtins, "__import__", uten_anthropic)
    assert llm.complete_json("s", "u", model="m") is None
    assert "pip install" in (llm.last_error() or "")


# ── Regnskapet: appen skal ikke si «KI: på» over en side full av maler ──────


def _sak(nr: int):
    from datetime import datetime

    from app.models import Case

    return Case(
        key=f"k{nr}", title=f"Sak {nr}", score=30 - nr, geo="lokal",
        topics=["jobb og okonomi"], angle="a", why="w", signals=[],
        created_at=datetime.now(tz=UTC), kind="data",
        finding=f"Et tall som endret seg {nr} prosent i Stavanger fra 2025 til 2026.",
        metric_value=f"+{nr} %", metric_period="2025–2026",
        data_source="SSB tabell 05889", data_url="https://www.ssb.no/statbank/table/05889",
        coverage_status="green",
    )


def test_ett_vellykket_kall_maskerer_ikke_lenger_at_resten_feilet(monkeypatch):
    """DEN VIKTIGSTE TESTEN HER.

    Tidligere holdt det at ETT kall lyktes for at run_workflow returnerte «llm».
    Slo kvotetaket inn etterpå - som er nettopp det som skjer på et gratis-nivå -
    fikk journalisten «KI: på» over en side der alle vinklene var maler, uten
    advarsel. Nå skal modus bli «llm-delvis» og tallene stemme."""
    from app import agents

    monkeypatch.setenv("GROQ_API_KEY", "x")
    # Kallene kommer i denne rekkefølgen: analytiker -> redaktør -> journalist.
    # Fikstur som gir ALLE det samme svaret måler ikke det den tror: et
    # redaktør-svar til analytikeren er ubrukelig for ham, og skal telle som et
    # mislykket kall. (Før gjettet run_workflow på analytikerens utfall og
    # bommet — det var «KI: delvis» på et skann der alt gikk bra.)
    svar = iter([
        # «1» er id-en analytikeren faktisk ser. Agentene merker sakene med
        # loepenummer og oversetter tilbake selv - se agents._id_kart - fordi
        # en modell som skal gjenta «ssb-sok:05889:1103:2026K2» ordrett bommer,
        # og da falt vinklene stille bort.
        {"picks": [{"id": "1", "interesting": True, "score": 90, "reason": "r"}]},
    ])

    def av_og_til(*a, **k):
        try:
            return next(svar)          # første kall lykkes
        except StopIteration:
            llm._sett_feil("Groq (gratis): kvotetak (429)")
            return None                # alle senere feiler

    monkeypatch.setattr(agents.llm, "complete_json", av_og_til)

    saker = [_sak(i) for i in range(4)]
    r = agents.run_workflow(saker)

    assert r["mode"] == "llm-delvis", r
    assert r["lyktes"] >= 1 and r["feilet"] >= 1
    assert r["lyktes"] + r["feilet"] == r["forsokt"]
    assert "429" in r["feil"]


def test_alt_lykkes_gir_ren_llm(monkeypatch):
    from app import agents

    monkeypatch.setenv("GROQ_API_KEY", "x")

    def alltid(system, user, **k):
        """Redaktoer og journalist kjoerer naa SAMLET - alle sakene i ett kall.
        Fakeen maa svare i samleformat, ellers matcher den ingen sak og alt ser
        ut som feil."""
        llm._sett_feil(None)
        ider = [linje.split("=== SAK ")[1].split(" ===")[0]
                for linje in user.splitlines() if linje.startswith("=== SAK ")]
        if "picks" in system.lower() or "analytiker" in system.lower():
            return {"picks": [{"id": "k0", "interesting": True, "score": 80}]}
        if "IDEMOETE" in system:                       # journalisten, samlet
            return {"saker": [{"id": i, "angles": [
                {"vinkel": "uventet", "title": f"T{i}-{n}", "headline_fact": f"F{i}-{n}"}
                for n in range(3)]} for i in ider]}
        return {"saker": [{"id": i, "is_story": True, "headline": "H",
                           "angle": "A", "verdict": "V"} for i in ider]}

    monkeypatch.setattr(agents.llm, "complete_json", alltid)
    r = agents.run_workflow([_sak(i) for i in range(3)])
    assert r["mode"] == "llm", r
    assert r["feilet"] == 0


def test_alt_feiler_gir_llm_feilet(monkeypatch):
    from app import agents

    monkeypatch.setenv("GROQ_API_KEY", "x")
    monkeypatch.setattr(
        agents.llm, "complete_json",
        lambda *a, **k: (llm._sett_feil("Groq (gratis): kvotetak (429)"), None)[1],
    )
    r = agents.run_workflow([_sak(i) for i in range(3)])
    assert r["mode"] == "llm-feilet", r
    assert r["lyktes"] == 0


def test_uten_nokkel_er_modus_mal():
    from app import agents

    r = agents.run_workflow([_sak(0)])
    assert r["mode"] == "mal"


def test_saken_merkes_etter_det_svakeste_leddet(monkeypatch):
    """Kommer redaktøren gjennom men vinklene feiler, skal saken se ut som mal -
    ikke som KI fordi redaktøren tilfeldigvis rakk det."""
    from app import agents

    monkeypatch.setenv("GROQ_API_KEY", "x")

    def redaktor_ok_vinkler_feiler(system, user, **k):
        if "is_story" in system or "REDAKT" in system.upper():
            llm._sett_feil(None)
            return {"is_story": True, "headline": "H", "angle": "A", "verdict": "V"}
        llm._sett_feil("kvotetak")
        return None

    monkeypatch.setattr(agents.llm, "complete_json", redaktor_ok_vinkler_feiler)
    saker = [_sak(0)]
    agents.run_workflow(saker)
    assert saker[0].ai_mode == "mal", "saken har maler og skal merkes deretter"


def test_listesvar_fra_modellen_velter_ikke_hele_skannet(monkeypatch):
    """_extract_json kan returnere en LISTE. Før ga det AttributeError rett
    gjennom run_scan, som ikke fanger noe - og hele skannet døde."""
    from app import agents

    monkeypatch.setenv("GROQ_API_KEY", "x")
    monkeypatch.setattr(agents.llm, "complete_json", lambda *a, **k: ["ikke", "et", "objekt"])

    r = agents.run_workflow([_sak(0)])       # skal ikke kaste
    assert r["mode"] in ("llm", "llm-delvis", "llm-feilet")


def test_modellsvar_kan_ikke_overstyre_sin_egen_merking(monkeypatch):
    """Et svar som inneholder feltet «mode» skal ikke få bestemme om det telles
    som ekte KI. Før sto {"mode": "llm", **result} - og result vant."""
    from app import agents

    monkeypatch.setenv("GROQ_API_KEY", "x")
    monkeypatch.setattr(
        agents.llm, "complete_json",
        lambda *a, **k: {"is_story": True, "mode": "mal", "headline": "H"},
    )
    dom = agents.editor_judge(_sak(0))
    assert dom["mode"] == "llm"
