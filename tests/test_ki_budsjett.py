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
        """Redaktoer og journalist kjoerer SAMLET: alle sakene i ett kall.
        Vi skiller paa «IDEMOETE» i prompten (journalisten) mot resten."""
        self.kall += 1
        ider = [linje.split("=== SAK ")[1].split(" ===")[0]
                for linje in user.splitlines() if linje.startswith("=== SAK ")]
        if not ider:
            return {"picks": []}                       # analytikeren
        if "IDEMOETE" in system:
            return {"saker": [{"id": i, "angles": [
                {"title": f"Vinkel {n} for {i}", "kort": "k",
                 "headline_fact": f"faktum {n} {i}", "vinkel": "uventet", "styrke": 70}
                for n in range(3)]} for i in ider]}
        return {"saker": [{"id": i, "is_story": True, "confidence": 80,
                           "headline": "H", "angle": "A", "verdict": "V",
                           "forbehold": "", "novelty": "fersk"} for i in ider]}


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
    monkeypatch.setattr(agents, "KI_BUDSJETT_TOKENS", 3000)
    saker = lag_saker(12)
    regnskap = run_workflow(saker)

    assert regnskap["i_ko"] > 0, "12 saker på 9 000 tokens skal gi kø"
    # Grovt anslag per kall er ~1 000-3 000 tokens; med budsjettet skal vi ligge
    # langt under 12 000 uansett hvordan anslaget bommer i den ene retningen.
    assert ki.kall <= 3, f"{ki.kall} kall - samlekallene slo ikke inn"


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
        # Enten ble redaktørdommen satt i kø, eller så ble vinklene det. Vinkler
        # i kø er nå en TOM liste — maler ble fjernet, så det finnes ikke lenger
        # noe «ko»-merket vinkelobjekt å se etter.
        assert c.editor.get("mode") == "ko" or c.angles == [], (
            f"{c.key} er merket «ko» men har verken kø-dom eller tom vinkelliste"
        )


# ── Det som gjør «trykk igjen» meningsfullt ──────────────────────────────────


def test_andre_skann_bruker_kvoten_paa_nye_saker(ki, monkeypatch):
    """Selve kravet. Uten hurtiglageret ville skann nr. 2 kjørt de samme
    topp-sakene om igjen, og køen aldri tømt seg."""
    monkeypatch.setattr(agents, "KI_BUDSJETT_TOKENS", 3000)

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
    monkeypatch.setattr(agents, "KI_BUDSJETT_TOKENS", 3000)
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


# ── Ett kall for alle sakene ─────────────────────────────────────────────────


class TellendeKI(FalskKI):
    """Som FalskKI, men svarer i samleformat og teller kallene."""

    def __call__(self, system, user, *, model, max_tokens=1500, si=None):
        self.kall += 1
        if "=== SAK" in user:
            ider = [linje.split("=== SAK ")[1].split(" ===")[0]
                    for linje in user.splitlines() if linje.startswith("=== SAK ")]
            return {"saker": [
                {"id": i, "angles": [
                    {"title": f"Overskrift A for {i}", "headline_fact": f"a{i}",
                     "kort": "k", "vinkel": "uventet", "pitch": "p"},
                    {"title": f"Overskrift B for {i}", "headline_fact": f"b{i}",
                     "kort": "k", "vinkel": "konsekvens", "pitch": "p"},
                ]} for i in ider
            ]}
        if max_tokens == 800:
            return {"is_story": True, "confidence": 80, "headline": "H",
                    "angle": "A", "verdict": "V", "forbehold": "", "novelty": "fersk"}
        return {"picks": []}


@pytest.fixture()
def samle_ki(monkeypatch):
    falsk = TellendeKI()
    monkeypatch.setattr(agents.llm, "complete_json", falsk)
    monkeypatch.setattr(agents.llm, "has_llm", lambda: True)
    monkeypatch.setattr(agents.llm, "last_error", lambda: None)
    return falsk


def test_alle_saker_far_minst_to_overskrifter(samle_ki):
    """Eierens krav 26.07.2026: «minimum 2 overskrifter per fakta», og vinkler
    på ALLE temaene — ikke bare de første som fikk plass i kvoten."""
    saker = lag_saker(4)
    run_workflow(saker)

    med_vinkler = [c for c in saker if c.angles]
    assert med_vinkler, "ingen saker fikk vinkler i det hele tatt"
    for c in med_vinkler:
        assert len(c.angles) >= 2, f"{c.key} fikk bare {len(c.angles)} overskrift(er)"
        assert len({a["title"] for a in c.angles}) == len(c.angles)


def test_vinkler_koster_ett_kall_uansett_antall_saker(samle_ki):
    """Kjernen i fiksen. Før var det ett kall PER sak, så seks saker ga seks
    kall mot et minuttak på 12 000 tokens — det var derfor eieren så «4 av 4
    kall feilet» med 429. Nå sendes systemprompten én gang."""
    run_workflow(lag_saker(4))
    # 1 analytiker + 4 redaktør + 1 samlet vinkelkall = 6.
    # Med gammel struktur ville det vært 1 + 4 + 4 = 9.
    assert samle_ki.kall <= 6, f"{samle_ki.kall} kall - samlekallet slo ikke inn"


def test_vinkler_havner_paa_riktig_sak(samle_ki):
    """Med flere saker i ett svar er id-koblingen det som kan gå galt. En vinkel
    på feil sak er verre enn ingen vinkel — den bygger på feil tall."""
    saker = lag_saker(4)
    run_workflow(saker)
    for c in saker:
        for a in c.angles:
            assert c.key in a["headline_fact"], (
                f"{c.key} fikk en vinkel som hører til en annen sak: {a}"
            )


def test_oppdiktet_id_droppes(monkeypatch):
    """Finner modellen på en id, hører vinklene ingen steder hjemme. Å gjette
    hvilken sak de gjaldt ville vært verre enn å droppe dem."""
    def rar(system, user, *, model, max_tokens=1500, si=None):
        if "=== SAK" in user:
            return {"saker": [{"id": "finnes-ikke", "angles": [{"title": "T"}]}]}
        if max_tokens == 800:
            return {"is_story": True, "headline": "H", "angle": "A", "verdict": "V"}
        return {"picks": []}

    monkeypatch.setattr(agents.llm, "complete_json", rar)
    monkeypatch.setattr(agents.llm, "has_llm", lambda: True)
    monkeypatch.setattr(agents.llm, "last_error", lambda: None)
    saker = lag_saker(2)
    run_workflow(saker)
    assert all(c.angles == [] for c in saker)
