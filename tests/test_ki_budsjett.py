"""Tester for KI-budsjettet og køen.

Eierens egen løsning på 429-en fra journalistens telefon: gjør mindre KI-arbeid per
skann, og la ham trykke «Skann igjen» for resten. Den løsningen holder bare hvis
neste skann tar de NESTE sakene — gjør den ikke det, brenner hvert trykk kvoten
på nøyaktig de samme topp-sakene og køen tømmes aldri. Det er den egenskapen
disse testene vokter.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from app import agents, storage
from app.agents import Budsjett, run_workflow
from app.models import Case


@pytest.fixture(autouse=True)
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", str(tmp_path / "t.sqlite3"))


def lag_saker(n: int) -> list[Case]:
    return [
        Case(
            key=f"sak-{i}",
            title=f"Tall {i} opp i Stavanger",
            kind="data",
            geo="lokal",
            score=100 - i,
            topics=["jobb og okonomi"],
            angle="Hva betyr tallet?",
            why="Tallet har flyttet seg.",
            signals=[],
            created_at=datetime.now(UTC),
            finding=f"Tallet gikk opp {i} prosent i Stavanger",
            coverage_status="green",
            data_source="SSB tabell 12345",
            data_url="https://data.ssb.no/x",
            metric_value=f"{100 + i}",
            metric_period="2026",
        )
        for i in range(n)
    ]


class FalskKI:
    """Teller kall og svarer som en ekte leverandør ville gjort."""

    def __init__(self) -> None:
        self.kall = 0

    def __call__(self, system, user, *, model, max_tokens=1500, si=None):
        # Skiller på max_tokens, ikke på ord i prompten: 800 = redaktør,
        # 1400 = vinkler, 1200 = analytiker. Entydig, og testen brekker ikke
        # neste gang en prompt omformuleres.
        self.kall += 1
        if max_tokens == 800:
            return {"is_story": True, "confidence": 80, "headline": "H",
                    "angle": "A", "verdict": "V", "forbehold": "", "novelty": "fersk"}
        if max_tokens == 1400:
            return {"angles": [
                {"title": f"Vinkel {i}", "kort": "k", "headline_fact": f"faktum {i}",
                 "vinkel": "uventet", "styrke": 70}
                for i in range(3)
            ]}
        return {"picks": []}


@pytest.fixture()
def ki(monkeypatch):
    falsk = FalskKI()
    monkeypatch.setattr(agents.llm, "complete_json", falsk)
    monkeypatch.setattr(agents.llm, "has_llm", lambda: True)
    monkeypatch.setattr(agents.llm, "last_error", lambda: None)
    return falsk


# ── Budsjettet i seg selv ────────────────────────────────────────────────────


def test_budsjettet_slipper_alltid_gjennom_forste_kall():
    """Et budsjett satt altfor lavt skal gi ETT kall, ikke null. Ellers ville et
    tall i en miljøvariabel stille slått av hele KI-en."""
    b = Budsjett(1)
    assert b.be_om("s" * 4000, "u" * 4000, 1400) is True
    assert b.be_om("s", "u", 10) is False
    assert b.i_ko == 1


def test_uten_budsjett_er_alt_lov():
    b = Budsjett(0)
    for _ in range(50):
        assert b.be_om("s" * 4000, "u" * 4000, 1400) is True
    assert b.i_ko == 0


# ── Kjernen: ett skann holder seg under taket ────────────────────────────────


def test_skannet_stopper_for_kvotetaket(ki, monkeypatch):
    """12 000 tokens i minuttet er Groqs gratis-tak. Et skann skal ikke komme
    i nærheten av det — det var nettopp derfor 429-en traff."""
    monkeypatch.setattr(agents, "KI_BUDSJETT_TOKENS", 9000)
    saker = lag_saker(12)
    regnskap = run_workflow(saker)

    assert regnskap["i_ko"] > 0, "12 saker på 9 000 tokens skal gi kø"
    # Grovt anslag per kall er ~1 000-3 000 tokens; med budsjettet skal vi ligge
    # langt under 12 000 uansett hvordan anslaget bommer i den ene retningen.
    assert ki.kall <= 8, f"{ki.kall} kall er for mange for ett skann"


def test_saker_i_ko_merkes_ko_og_ikke_mal(ki, monkeypatch):
    """«mal» og «kø» betyr helt forskjellige ting for journalisten: mal = dette
    er alt du får, kø = trykk igjen. Blandes de, ser verktøyet ødelagt ut når
    det faktisk gjør jobben sin."""
    monkeypatch.setattr(agents, "KI_BUDSJETT_TOKENS", 2500)
    saker = lag_saker(10)
    run_workflow(saker)

    i_ko = [c for c in saker if c.ai_mode == "ko"]
    assert i_ko, "ingen saker ble merket «ko»"
    for c in i_ko:
        assert c.editor.get("mode") == "ko" or any(
            a.get("mode") == "ko" for a in c.angles
        )


# ── Det som gjør «trykk igjen» meningsfullt ──────────────────────────────────


def test_andre_skann_bruker_kvoten_paa_nye_saker(ki, monkeypatch):
    """Selve kravet. Uten hurtiglageret ville skann nr. 2 kjørt de samme
    topp-sakene om igjen, og køen aldri tømt seg."""
    monkeypatch.setattr(agents, "KI_BUDSJETT_TOKENS", 6000)

    forste = lag_saker(10)
    r1 = run_workflow(forste)
    kall_1 = ki.kall
    assert r1["i_ko"] > 0

    # Samme kilder gir de samme sakene igjen — det er nettopp poenget.
    andre = lag_saker(10)
    r2 = run_workflow(andre)

    assert r2["gjenbrukt"] > 0, "skann nr. 2 gjenbrukte ingenting"
    nye_kall = ki.kall - kall_1
    assert nye_kall > 0, "skann nr. 2 gjorde ingenting nytt"
    # Køen skal krympe, ikke stå stille.
    assert r2["i_ko"] < r1["i_ko"], f"køen krympet ikke: {r1['i_ko']} → {r2['i_ko']}"


def test_koen_tommes_til_slutt(ki, monkeypatch):
    """Trykker han nok ganger, skal alt til slutt ha ekte KI. Et system der køen
    aldri blir tom, er verre enn ingen kø."""
    monkeypatch.setattr(agents, "KI_BUDSJETT_TOKENS", 6000)
    for _ in range(12):
        saker = lag_saker(8)
        regnskap = run_workflow(saker)
        if regnskap["i_ko"] == 0:
            break
    assert regnskap["i_ko"] == 0, "køen tømte seg ikke på 12 skann"


def test_maler_lagres_aldri_som_ekte_ki(monkeypatch):
    """Feilet kallet, skal det prøves på nytt neste gang — ikke fryses fast som
    om KI-en hadde svart."""
    monkeypatch.setattr(agents.llm, "has_llm", lambda: True)
    monkeypatch.setattr(agents.llm, "complete_json", lambda *a, **k: None)
    monkeypatch.setattr(agents.llm, "last_error", lambda: "testfeil")

    saker = lag_saker(3)
    run_workflow(saker)
    assert storage.ki_hent([c.key for c in saker]) == {}


def test_uten_nokkel_er_ingenting_i_ko(monkeypatch):
    """Uten nøkkel står det ingenting i kø — det finnes bare ikke noen KI. Å
    love «trykk igjen» der ville vært en løgn."""
    monkeypatch.setattr(agents.llm, "has_llm", lambda: False)
    monkeypatch.setattr(agents.llm, "complete_json", lambda *a, **k: None)

    regnskap = run_workflow(lag_saker(10))
    assert regnskap["mode"] == "mal"
    assert regnskap["i_ko"] == 0


# ── Hurtiglageret ────────────────────────────────────────────────────────────


def test_delvis_lagring_beholder_det_andre(monkeypatch):
    """Fikk saken redaktørdom, men gikk tom for budsjett før vinklene, skal
    dommen overleve — ellers betaler neste skann for den på nytt."""
    storage.ki_lagre("k", editor={"is_story": True})
    storage.ki_lagre("k", angles=[{"title": "T"}])
    lagret = storage.ki_hent(["k"])["k"]
    assert lagret["editor"] == {"is_story": True}
    assert lagret["angles"] == [{"title": "T"}]


def test_hurtiglageret_vokser_ikke_i_det_uendelige():
    for i in range(storage.KI_CACHE_MAKS + 25):
        storage.ki_lagre(f"k{i}", editor={"is_story": True})
    igjen = storage.ki_hent([f"k{i}" for i in range(storage.KI_CACHE_MAKS + 25)])
    assert len(igjen) <= storage.KI_CACHE_MAKS
