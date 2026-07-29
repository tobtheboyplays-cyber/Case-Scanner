"""Etterfylling av vinkler etter et skann som traff kvotetaket.

Eieren 27.07.2026: «Står KI er av, fiks det også.» Skannet 11:03 traff Groqs
minuttak; to timer senere sto varselet der fortsatt, fordi ingenting prøvde
igjen av seg selv. Testene under holder på de to tingene som må stemme:

  1. Den prøver igjen når — og BARE når — det faktisk kan hjelpe.
  2. Når den lykkes, følger varselet på toppen virkeligheten.
"""
from __future__ import annotations

import app.main as main


def _fanget(monkeypatch) -> list:
    startet = []

    class FalskTraad:
        def __init__(self, **kw):
            self.kw = kw

        def start(self):
            startet.append(self.kw)

    monkeypatch.setattr(main.threading, "Thread", lambda **kw: FalskTraad(**kw))
    return startet


SKANN = {"cases": [{"key": "a"}, {"key": "b"}, {"key": "c"}, {"key": "d"}]}


def test_etterfyller_naar_kvoten_sprakk(monkeypatch):
    monkeypatch.setattr(main, "ENABLE_AI", True)
    startet = _fanget(monkeypatch)
    main._kanskje_etterfyll("llm-feilet", "Groq (gratis): kvotetak (429)", SKANN)
    assert len(startet) == 1
    # Bare toppsakene. Flere ville sprengt taket paa nytt.
    assert startet[0]["args"][0] == ["a", "b", "c"]


def test_etterfyller_ikke_paa_noekkelfeil(monkeypatch):
    """En feil noekkel gaar ikke over av seg selv. Da er det aa mase."""
    monkeypatch.setattr(main, "ENABLE_AI", True)
    startet = _fanget(monkeypatch)
    main._kanskje_etterfyll("llm-feilet", "authentication_error", SKANN)
    assert startet == []


def test_etterfyller_ikke_naar_noe_lyktes(monkeypatch):
    """«Delvis» betyr at toppsakene allerede har ekte vinkler."""
    monkeypatch.setattr(main, "ENABLE_AI", True)
    startet = _fanget(monkeypatch)
    main._kanskje_etterfyll("llm-delvis", "kvotetak (429)", SKANN)
    assert startet == []


def test_etterfyller_ikke_naar_ki_er_avslaatt(monkeypatch):
    """Er KI-en skrudd av, er «av» riktig svar — ikke en feil aa reparere."""
    monkeypatch.setattr(main, "ENABLE_AI", False)
    startet = _fanget(monkeypatch)
    main._kanskje_etterfyll("llm-feilet", "kvotetak (429)", SKANN)
    assert startet == []


def test_lykkes_den_slutter_varselet_aa_si_av(monkeypatch):
    """Selve poenget: varselet paa toppen skal foelge virkeligheten."""
    lagret: dict = {}
    data = {"cases": [{"key": "a", "ai_mode": "mal"}], "ai_mode": "llm-feilet"}

    monkeypatch.setattr(main, "load_latest", lambda: data)
    monkeypatch.setattr(main, "save_scan", lambda d: lagret.update(d))
    monkeypatch.setattr(main, "_case_from_dict", lambda d: object())
    monkeypatch.setattr(main, "journalist_angles",
                        lambda case, editor, taalmodig=False: [{"title": "En vinkel"}])
    monkeypatch.setattr(main.storage, "ki_lagre", lambda *a, **k: None)
    monkeypatch.setattr(main.time, "sleep", lambda s: None)

    main._etterfyll_vinkler(["a"])

    assert lagret["ai_mode"] == "llm-delvis"
    assert lagret["cases"][0]["ai_mode"] == "llm"
    assert lagret["cases"][0]["angles"] == [{"title": "En vinkel"}]


def test_gir_seg_ved_ekte_feil(monkeypatch):
    """Ikke mas paa en leverandoer som svarer noe annet enn «vent litt»."""
    kall = []
    data = {"cases": [{"key": "a", "ai_mode": "mal"}, {"key": "b", "ai_mode": "mal"}]}

    def ingen_vinkler(case, editor, taalmodig=False):
        kall.append(1)
        return []

    monkeypatch.setattr(main, "load_latest", lambda: data)
    monkeypatch.setattr(main, "save_scan", lambda d: None)
    monkeypatch.setattr(main, "_case_from_dict", lambda d: object())
    monkeypatch.setattr(main, "journalist_angles", ingen_vinkler)
    monkeypatch.setattr(main.llm, "last_error", lambda: "invalid_api_key")
    monkeypatch.setattr(main.time, "sleep", lambda s: None)

    main._etterfyll_vinkler(["a", "b"])
    assert len(kall) == 1
