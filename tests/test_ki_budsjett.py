"""Tester for KI-budsjettet og køen.

Eierens egen løsning på 429-en fra journalistens telefon: gjør mindre KI-arbeid per
skann, og la ham trykke «Skann igjen» for resten. Den løsningen holder bare hvis
neste skann tar de NESTE sakene — gjør den ikke det, brenner hvert trykk kvoten
på nøyaktig de samme topp-sakene og køen tømmes aldri. Det er den egenskapen
disse testene vokter.
"""

from __future__ import annotations

import re

from datetime import UTC, datetime

import pytest
from app import agents, storage
from app.agents import Budsjett, run_workflow
from app.models import Case


@pytest.fixture(autouse=True)
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", str(tmp_path / "t.sqlite3"))



def _blokker(user: str) -> list[tuple[str, str]]:
    """[(id-en modellen ser, noekkelen som staar i blokka)] fra en samleprompt.

    Attrappene bruker denne for aa oppfoere seg som en ekte modell: de kjenner
    bare loepenummeret, og alt annet maa de lese ut av teksten de fikk."""
    ut = []
    for bit in user.split("=== SAK ")[1:]:
        nr = bit.split(" ===")[0].strip()
        m = re.search(r"(sak-\d+)", bit)
        ut.append((nr, m.group(1) if m else nr))
    return ut


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
            # Noekkelen staar I FUNNET, ikke bare i `key`. Da kan attrappen
            # under lese den ut av blokka den faktisk fikk - noeyaktig som en
            # ekte modell ville gjort - og testen kan bevise at vinkelen havnet
            # paa saken den ble skrevet for.
            finding=f"Tallet for sak-{i} gikk opp {i} prosent i Stavanger",
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


def test_journalisten_gaar_foran_redaktoren_nar_kvoten_er_knapp(ki, monkeypatch):
    """Reserven, og hvorfor den finnes.

    Målt 26.07.2026: analytiker 2 524 + redaktør 5 055 + journalist 8 007 =
    15 586 tokens i samme minutt mot Groqs tak på 12 000. Journalisten sto SIST,
    så det var alltid vinklene som ble strupet — og eieren satt med saker uten en
    eneste forslagstittel. Det er selve poenget med verktøyet som forsvant.

    Nå er en andel holdt av til journalisten. Blir det trangt, er det RANGERINGEN
    og DOMMEN som havner i kø; titlene kommer uansett. Dommen merkes «ko» slik at
    UI-et sier «trykk igjen» og ikke «dette er alt du får»."""
    monkeypatch.setattr(agents, "KI_BUDSJETT_TOKENS", 2500)
    saker = lag_saker(10)
    regnskap = run_workflow(saker)

    assert regnskap["i_ko"] > 0, "budsjettet var ikke knapt — testen måler ingenting"

    med_vinkler = [c for c in saker if c.angles]
    assert med_vinkler, "journalisten ble strupet selv med reserve — det var feilen"

    dommer_i_ko = [c for c in saker if c.editor.get("mode") == "ko"]
    assert dommer_i_ko, "ingenting havnet i kø — da er ikke reserven det som virket"
    for c in dommer_i_ko:
        # «mal» og «kø» betyr helt forskjellige ting: mal = dette er alt du får,
        # kø = trykk igjen. Blandes de, ser verktøyet ødelagt ut når det gjør
        # jobben sin.
        assert c.editor["mode"] != "mal"


def test_reserven_kan_aldri_ta_mer_enn_halve_budsjettet():
    """En reserve større enn potten ville satt analytikeren og redaktøren i kø fra
    første kall — det er ikke en prioritering, det er en avslått KI."""
    b = Budsjett(2000, reservert=9999)
    assert b.reservert == 1000
    assert b.be_om("s", "u", 10) is True, "det første kallet ble sperret av reserven"


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
            # Agentene merker sakene «SAK 1», «SAK 2» … og oversetter tilbake
            # selv - se agents._id_kart. En ekte modell ser ALDRI den ekte
            # noekkelen, saa attrappen skal ikke gjore det heller. Den leser
            # noekkelen ut av selve BLOKKA, akkurat som modellen ville gjort,
            # og legger den i faktumet. Da beviser testen under at vinkelen
            # havnet paa saken den ble skrevet for.
            return {"saker": [
                {"id": nr, "angles": [
                    {"title": f"Overskrift A for {nokkel}", "headline_fact": f"a {nokkel}",
                     "kort": "k", "vinkel": "uventet", "pitch": "p"},
                    {"title": f"Overskrift B for {nokkel}", "headline_fact": f"b {nokkel}",
                     "kort": "k", "vinkel": "konsekvens", "pitch": "p"},
                ]} for nr, nokkel in _blokker(user)
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


def test_takene_holder_seg_under_groqs_minuttak():
    """Regnestykket bak EDITOR_CAP/JOURNALIST_CAP = 3, voktet mekanisk.

    Eieren spurte 26.07.2026: «Hva om den tar bare 3 saker med 2 vinkler
    istedenfor 4?» Målingen ga ham rett:

        saker   analytiker   redaktør   journalist      SUM   margin
            4         1236       4036         6548    11820      180
            3         1236       3451         5726    10413     1587

    Marginen på 180 var én lang SSB-tabelltittel unna å sprekke — og når den
    sprekker, er det journalist-kallet som ryker, altså forslagstitlene.

    Denne testen er her fordi takene har blitt endret tre ganger (8 → 4 → 3) og
    kommer til å bli fristende å skru opp igjen. Gjør noen det, eller vokser en
    systemprompt forbi det kvoten tåler, skal DETTE feile — ikke journalistens
    skann.
    """
    from app import llm, prompts
    from app.config import EDITOR_CAP, JOURNALIST_CAP

    GROQ_TPM = 12_000
    # Romsligere enn et ekte kildegrunnlag, så testen ikke gir falsk trygghet.
    kilde = "=== SAK ssb-sok:12345:1103:2026K2 ===\n" + ("x" * 1100)

    # Analytikertaket foelger nå ANTALLET funn. Det faste 450 var for lite for
    # atten funn: svaret ble avkortet, JSON-en ugyldig, og kallet talt som
    # mislykket i hvert eneste skann - «KI delvis» hos eieren 26.07.2026.
    analyst_tak = min(900, max(300, 60 * agents.ANALYST_MAKS_FUNN + 120))
    analytiker = llm.anslaa_tokens(prompts.ANALYST_SYSTEM, "Funn:\n" + "y" * 800, analyst_tak)
    redaktor = llm.anslaa_tokens(
        prompts.EDITOR_BATCH_SYSTEM,
        "\n\n".join([kilde] * EDITOR_CAP),
        max(700, 300 * EDITOR_CAP),
    )
    journalist = llm.anslaa_tokens(
        prompts.JOURNALIST_BATCH_SYSTEM,
        "\n\n".join([kilde + "\n" + "z" * 350] * JOURNALIST_CAP),
        max(1000, 450 * JOURNALIST_CAP),
    )
    sum_ett_skann = analytiker + redaktor + journalist

    assert sum_ett_skann < GROQ_TPM, (
        f"Ett skann anslås til {sum_ett_skann} tokens mot Groqs {GROQ_TPM}. "
        f"analytiker={analytiker} redaktør={redaktor} journalist={journalist}. "
        f"Senk EDITOR_CAP/JOURNALIST_CAP (nå {EDITOR_CAP}/{JOURNALIST_CAP}) "
        "eller kort ned en systemprompt."
    )
    # Margin, ikke bare «akkurat innafor». 180 tokens klaring var det vi hadde
    # da forslagstitlene uteble hos eieren.
    assert GROQ_TPM - sum_ett_skann > 800, (
        f"Bare {GROQ_TPM - sum_ett_skann} tokens klaring — for tynt. "
        "Ett ekstra langt tabellnavn spiser den."
    )


# ── Id-ene modellen faktisk klarer å gjenta ─────────────────────────────────


def test_agentene_ber_aldri_modellen_gjenta_den_ekte_nokkelen():
    """Eieren 26.07.2026: «Ingen vinkler ble skrevet.»

    Sakene ble merket med `case.key` — `ssb-sok:05889:1103:2026K2` — og svaret
    ble matchet eksakt mot den. Det er 25 tegn med kolon og siffer som en
    gratismodell skal gjenta ordrett for hver sak. Bommer den på ett tegn,
    faller vinklene ut uten en lyd, og kallet telles som vellykket.

    Nå ser modellen «SAK 1». Denne testen leser prompten og krever at nøkkelen
    IKKE står som id — den er lett å legge tilbake ved et uhell."""
    saker = lag_saker(3)
    for c in saker:
        c.editor = {"is_story": True, "headline": "H", "angle": "A", "verdict": "V"}

    sett = {}

    def fang(system, user, *, model, max_tokens=1500, si=None):
        sett["user"] = user
        return {"saker": []}

    agents.llm.complete_json, gammel = fang, agents.llm.complete_json
    try:
        agents.journalist_angles_batch(saker)
        overskrifter = [x for x in sett["user"].splitlines() if x.startswith("=== SAK ")]
        assert overskrifter == ["=== SAK 1 ===", "=== SAK 2 ===", "=== SAK 3 ==="], overskrifter

        agents.editor_judge_batch(saker)
        overskrifter = [x for x in sett["user"].splitlines() if x.startswith("=== SAK ")]
        assert overskrifter == ["=== SAK 1 ===", "=== SAK 2 ===", "=== SAK 3 ==="], overskrifter
    finally:
        agents.llm.complete_json = gammel


def test_slurvete_id_fra_modellen_treffer_likevel(samle_ki, monkeypatch):
    """Modeller pynter på formatet: «SAK 2», «sak_2», « 2 ». Alle betyr sak 2,
    og å kaste vinkelen for et mellomrom ville vært den samme feilen på nytt."""
    saker = lag_saker(3)
    for c in saker:
        c.editor = {"is_story": True, "headline": "H", "angle": "A", "verdict": "V"}

    def slurvete(system, user, *, model, max_tokens=1500, si=None):
        return {"saker": [
            {"id": "SAK 1", "angles": [{"title": "A", "headline_fact": "f"}]},
            {"id": " 2 ", "angles": [{"title": "B", "headline_fact": "f"}]},
            {"id": "sak_3", "angles": [{"title": "C", "headline_fact": "f"}]},
        ]}

    monkeypatch.setattr(agents.llm, "complete_json", slurvete)
    vinkler, ok = agents.journalist_angles_batch(saker)
    assert ok
    assert set(vinkler) == {"sak-0", "sak-1", "sak-2"}, vinkler


def test_avkortet_svar_berges_i_stedet_for_aa_kastes():
    """Tar `max_tokens` slutt midt i svaret, er hele JSON-en ugyldig — også de
    fire vinklene som var ferdige. Før ble alt kastet og kallet talt som
    mislykket; det var «KI delvis» skann etter skann."""
    from app import llm

    avkortet = (
        '{"saker": [{"id": "1", "angles": [{"title": "Ferdig vinkel"}]},'
        ' {"id": "2", "angles": [{"title": "Også ferdig"}]},'
        ' {"id": "3", "angles": [{"title": "Halv v'
    )
    berget = llm._extract_json(avkortet)
    assert isinstance(berget, dict), berget
    assert [s["id"] for s in berget["saker"]] == ["1", "2"], berget


def test_bergingen_finner_ikke_paa_data():
    """En berging som gjetter er verre enn ingen. Er ingenting komplett, skal
    den si nei — ikke levere et halvt objekt med tomme felt."""
    from app import llm

    assert llm._extract_json('{"saker": [{"id": "1", "ang') is None
    assert llm._extract_json("ikke json i det hele tatt") is None


# ── «Lag vinkler» på én sak: kvotetaket skal ikke drepe den ────────────────
#
# Eieren 26.07.2026, med skjermbilde:
#   «RuntimeError: Journalisten leverte ingen vinkler. Groq (gratis): kvotetak (429)»
#   «Kvotetak. Finn en løsning.»
#
# Løsningen er ikke mer kvote — den er gratis og fast på 12 000 tokens i minuttet.
# Løsningen er å VENTE. Et skann bruker ~10 800 av dem, så et knappetrykk rett
# etterpå har ikke plass på noen sekunder — men det HAR plass når minuttvinduet
# ruller, for kallet trenger bare 2 000.


def test_knappen_venter_ut_kvoten_i_stedet_for_aa_gi_opp(monkeypatch):
    """Kjernen. Første forsøk får 429, andre går gjennom — som i virkeligheten
    når minuttvinduet har rullet."""
    from app import llm

    forsok = {"n": 0}
    ventet: list[float] = []

    def flakete(navn, system, user, *, model, max_tokens):
        forsok["n"] += 1
        if forsok["n"] == 1:
            raise llm.KvoteSprengt(2.0, "Groq (gratis): kvotetak naadd (429)")
        return '{"angles": [{"title": "En ekte tittel", "vinkel": "uventet"}]}'

    monkeypatch.setattr(llm, "_ett_kall", flakete)
    monkeypatch.setattr(llm, "leverandorkjede", lambda: ["groq"])
    monkeypatch.setattr(llm.time, "sleep", lambda s: ventet.append(s))

    svar = llm.complete_json("sys", "user", model="m", max_tokens=100, taalmodig=True)
    assert svar == {"angles": [{"title": "En ekte tittel", "vinkel": "uventet"}]}
    assert forsok["n"] == 2
    # Minst 20 s: kortere vent treffer det SAMME minuttvinduet, og da er
    # «forsøk nr. 2» bare den samme feilen en gang til.
    assert ventet and max(ventet) >= 20, ventet


def test_skannet_er_fortsatt_utaalmodig(monkeypatch):
    """Taalmodigheten må være kallerens valg. Et SKANN som står stille i to
    minutter er et ødelagt skann — der er det ingen som ser på en linje."""
    from app import llm

    forsok = {"n": 0}

    def alltid_429(navn, system, user, *, model, max_tokens):
        forsok["n"] += 1
        raise llm.KvoteSprengt(2.0, "429")

    monkeypatch.setattr(llm, "_ett_kall", alltid_429)
    monkeypatch.setattr(llm, "leverandorkjede", lambda: ["groq"])
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)

    llm.complete_json("sys", "user", model="m", max_tokens=100)
    assert forsok["n"] == llm.MAKS_FORSOK, forsok
    forsok["n"] = 0
    llm.complete_json("sys", "user", model="m", max_tokens=100, taalmodig=True)
    assert forsok["n"] == llm.TAALMODIG_FORSOK, forsok


def test_ventingen_meldes_til_framdriftslinja(monkeypatch):
    """Uten dette står linja stille i førti sekunder og ser ut som en henging.
    Beskjeden er halve løsningen — den andre halvdelen er at vi venter."""
    from app import llm

    meldt: list[str] = []

    def alltid_429(navn, system, user, *, model, max_tokens):
        raise llm.KvoteSprengt(30.0, "429")

    monkeypatch.setattr(llm, "_ett_kall", alltid_429)
    monkeypatch.setattr(llm, "leverandorkjede", lambda: ["groq"])
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)

    llm.complete_json("sys", "u", model="m", max_tokens=100,
                      si=meldt.append, taalmodig=True)
    assert any("kvotetak" in m and "venter" in m for m in meldt), meldt


def test_feilmeldingen_sier_hva_han_skal_gjore():
    """«RuntimeError: ... Groq (gratis): kvotetak (429)» sto på kortet hans. Det
    er sant og ubrukelig: det sier ikke hva han skal gjøre, og «RuntimeError» er
    et ord fra vår verden, ikke hans."""
    from app.main import _vinkelfeil

    kvote = _vinkelfeil("Groq (gratis): kvotetak (429)")
    assert "RuntimeError" not in kvote and "429" not in kvote
    assert "Vent" in kvote and "trykk igjen" in kvote

    ingen = _vinkelfeil("ingen KI-nokkel i miljoet (GROQ/OPENROUTER)")
    assert "nøkkel" in ingen and "GROQ" not in ingen


def test_vinklene_lagres_saa_de_ikke_maa_kjopes_paa_nytt(tmp_path, monkeypatch):
    """Ett kall koster kvote. Forsvant svaret ved neste skann, ville den samme
    saken kostet kvote om og om igjen — og køen ville aldri tømt seg."""
    from app import jobs, main, storage

    monkeypatch.setattr(storage, "DB_PATH", str(tmp_path / "t.sqlite3"))
    sak = {**lag_saker(1)[0].to_dict(), "angles": [], "editor": {}}
    storage.save_scan({"cases": [sak], "plan": {}, "status": [], "summary": {},
                       "ai_mode": "mal"})

    monkeypatch.setattr(main, "journalist_angles",
                        lambda c, e, **k: [{"title": "T", "vinkel": "uventet"}])

    main._lag_vinkler(jobs.Jobb("x", main.VINKEL_FASER), sak["key"])
    assert storage.load_latest()["cases"][0]["angles"], "vinklene ble ikke lagret"
    assert storage.ki_hent([sak["key"]])[sak["key"]]["angles"], "ikke i hurtiglageret"


# ── Køen: to trykk samtidig ────────────────────────────────────────────────
#
# Eieren 26.07.2026: «Hvis han trykker på fler så stiller de seg bare i kø og
# venter 1 minutt til det er dems tur. Men aldri la det være en feilmelding, men
# heller en treig progress bar. Hvis han tar to samtidig så sier den andre venter
# i kø.»
#
# Dette er ikke pynt. To KI-kall samtidig deler det samme minuttvinduet på
# 12 000 tokens og feller hverandre; to etter hverandre får hvert sitt vindu og
# går begge gjennom. Køen ER løsningen på kvotetaket.


def _skann_med_en_sak(tmp_path, monkeypatch):
    from app import storage

    monkeypatch.setattr(storage, "DB_PATH", str(tmp_path / "t.sqlite3"))
    sak = {**lag_saker(1)[0].to_dict(), "angles": [], "editor": {}}
    storage.save_scan({"cases": [sak], "plan": {}, "status": [], "summary": {},
                       "ai_mode": "mal"})
    return sak["key"]


def test_to_samtidige_trykk_kjorer_etter_hverandre(tmp_path, monkeypatch):
    """Overlapper de, deler de minuttvinduet og feller hverandre."""
    import threading
    import time as t

    from app import jobs, main

    key = _skann_med_en_sak(tmp_path, monkeypatch)
    inne: list[int] = []
    samtidige = {"maks": 0, "naa": 0}
    laas = threading.Lock()

    def treg(case, editor, **kw):
        with laas:
            samtidige["naa"] += 1
            samtidige["maks"] = max(samtidige["maks"], samtidige["naa"])
        t.sleep(0.25)
        with laas:
            samtidige["naa"] -= 1
        inne.append(1)
        return [{"title": "T", "vinkel": "uventet"}]

    monkeypatch.setattr(main, "journalist_angles", treg)

    traader = [
        threading.Thread(target=main._lag_vinkler,
                         args=(jobs.Jobb(f"j{i}", main.VINKEL_FASER), key))
        for i in range(3)
    ]
    for x in traader:
        x.start()
    for x in traader:
        x.join(timeout=20)

    assert len(inne) == 3, "ikke alle tre kom gjennom"
    assert samtidige["maks"] == 1, f"{samtidige['maks']} kall gikk samtidig"


def test_den_som_staar_bak_faar_vite_det(tmp_path, monkeypatch):
    """«Hvis han tar to samtidig så sier den andre venter i kø.» En stille
    venting er ikke til å skille fra en henging."""
    import threading
    import time as t

    from app import jobs, main

    key = _skann_med_en_sak(tmp_path, monkeypatch)
    slipp = threading.Event()

    def foerste(case, editor, **kw):
        slipp.wait(timeout=5)
        return [{"title": "T", "vinkel": "uventet"}]

    monkeypatch.setattr(main, "journalist_angles", foerste)

    j1 = jobs.Jobb("j1", main.VINKEL_FASER)
    j2 = jobs.Jobb("j2", main.VINKEL_FASER)
    t1 = threading.Thread(target=main._lag_vinkler, args=(j1, key))
    t1.start()
    t.sleep(0.3)                       # la den første ta låsen

    t2 = threading.Thread(target=main._lag_vinkler, args=(j2, key))
    t2.start()
    t.sleep(0.3)                       # la den andre rekke å melde fra

    # `siste` er «hva skjer akkurat nå»; `tekst` er bare navnet på fasen.
    # UI-et viser `siste || tekst` - se pollVinkler i dashboard.html.
    tilstand = j2.tilstand()
    naa = tilstand.get("siste") or tilstand.get("tekst", "")
    assert "kø" in naa.lower(), f"nr. 2 sa ikke fra: {naa!r}"

    slipp.set()
    t1.join(timeout=10)
    t2.join(timeout=10)


def test_koen_toemmer_seg_selv_om_en_jobb_feiler(tmp_path, monkeypatch):
    """Slipper ikke en feilet jobb låsen, står alle etterfølgende for alltid —
    og «venter i kø» blir en løgn."""
    import threading

    from app import jobs, main

    key = _skann_med_en_sak(tmp_path, monkeypatch)

    def sprekker(case, editor, **kw):
        raise ValueError("noe gikk galt")

    monkeypatch.setattr(main, "journalist_angles", sprekker)
    with pytest.raises(ValueError):
        main._lag_vinkler(jobs.Jobb("j", main.VINKEL_FASER), key)

    # Låsen skal være fri: neste jobb må komme rett gjennom.
    monkeypatch.setattr(main, "journalist_angles",
                        lambda c, e, **k: [{"title": "T", "vinkel": "uventet"}])
    ferdig = threading.Event()

    def kjor():
        main._lag_vinkler(jobs.Jobb("j2", main.VINKEL_FASER), key)
        ferdig.set()

    threading.Thread(target=kjor, daemon=True).start()
    assert ferdig.wait(timeout=5), "køen var låst etter en feilet jobb"


def test_kvotetak_gir_flere_runder_ikke_en_feilmelding(tmp_path, monkeypatch):
    """«Aldri la det være en feilmelding.» Første runde møter kvotetaket, andre
    går gjennom — og journalisten ser bare at det tok litt tid."""
    from app import jobs, llm, main

    key = _skann_med_en_sak(tmp_path, monkeypatch)
    runder = {"n": 0}

    def foerst_kvotetak(case, editor, **kw):
        runder["n"] += 1
        if runder["n"] == 1:
            llm._sett_feil("Groq (gratis): kvotetak (429)")
            return []
        return [{"title": "Endelig", "vinkel": "uventet"}]

    monkeypatch.setattr(main, "journalist_angles", foerst_kvotetak)
    monkeypatch.setattr(main.time, "sleep", lambda s: None)

    jobb = jobs.Jobb("j", main.VINKEL_FASER)
    assert main._lag_vinkler(jobb, key) == {"angles": 1}
    assert runder["n"] == 2


def test_en_ekte_feil_venter_vi_ikke_ut(tmp_path, monkeypatch):
    """Taalmodighet er for kvotetak. En manglende nøkkel blir ikke bedre av at
    vi venter fire minutter på den."""
    from app import jobs, llm, main

    key = _skann_med_en_sak(tmp_path, monkeypatch)
    runder = {"n": 0}

    def ingen_nokkel(case, editor, **kw):
        runder["n"] += 1
        llm._sett_feil("ingen KI-nokkel i miljoet")
        return []

    monkeypatch.setattr(main, "journalist_angles", ingen_nokkel)
    monkeypatch.setattr(main.time, "sleep", lambda s: pytest.fail("ventet på en ekte feil"))

    with pytest.raises(RuntimeError, match="nøkkel"):
        main._lag_vinkler(jobs.Jobb("j", main.VINKEL_FASER), key)
    assert runder["n"] == 1
