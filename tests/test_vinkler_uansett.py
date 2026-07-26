"""Vinklene skal komme uansett om redaktøren liker saken eller ei.

Eieren 26.07.2026: «Vinklene skal komme uansett om saken er dårlig eller ei,
slik han kan be om utkast.»

Før sto det en stille sperre i `run_workflow`: sa KI-redaktøren nei, ble saken
liggende i lista uten en eneste tittel og uten utkastknapp. Journalisten kunne
ikke overprøve dommen — han fikk ikke engang se hva saken kunne vært. Den samme
sperren lå i den mekaniske grunnlagssjekken: mangler en SSB-lenke, forsvant hele
saken lydløst.

Begge er nå ADVARSLER, ikke porter. Det er den forskjellen disse testene vokter —
og den er lett å reversere ved et uhell, fordi et `continue` ser ufarlig ut.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from app import agents, storage
from app.agents import run_workflow
from app.models import Case


@pytest.fixture(autouse=True)
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", str(tmp_path / "t.sqlite3"))


def sak(i: int, **kw) -> Case:
    base = dict(
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
    return Case(**{**base, **kw})


class FalskKI:
    """Redaktør som sier det testen ber om, og en journalist som svarer alle.

    Tar vare på hver user-prompt, slik at testene kan sjekke HVA agentene
    faktisk fikk se — ikke bare hva som kom ut.
    """

    def __init__(self, *, is_story: bool | dict[str, bool] = True) -> None:
        self.is_story = is_story
        self.journalist_prompt = ""
        self.redaktor_prompt = ""

    def _dom(self, key: str) -> bool:
        return self.is_story[key] if isinstance(self.is_story, dict) else self.is_story

    def __call__(self, system, user, *, model, max_tokens=1500, si=None):
        ider = [
            linje.split("=== SAK ")[1].split(" ===")[0]
            for linje in user.splitlines()
            if linje.startswith("=== SAK ")
        ]
        if not ider:
            return {"picks": []}
        if "IDEMOETE" in system:
            self.journalist_prompt = user
            return {"saker": [{"id": i, "angles": [
                {"title": f"370 flere i Stavanger mister jobben ({i}-{n})",
                 "kort": "k", "headline_fact": f"faktum {n} {i}",
                 "vinkel": "uventet", "styrke": 70}
                for n in range(2)]} for i in ider]}
        self.redaktor_prompt = user
        return {"saker": [{"id": i, "is_story": self._dom(i), "confidence": 80,
                           "headline": "H", "angle": "A",
                           "verdict": "For tynt til forsiden", "forbehold": "",
                           "novelty": "fersk"} for i in ider]}


@pytest.fixture()
def ki(monkeypatch):
    def lag(**kw):
        falsk = FalskKI(**kw)
        monkeypatch.setattr(agents.llm, "complete_json", falsk)
        monkeypatch.setattr(agents.llm, "has_llm", lambda: True)
        monkeypatch.setattr(agents.llm, "last_error", lambda: None)
        return falsk
    return lag


# ── Kjernen: et nei fra redaktøren stopper ingenting ────────────────────────


def test_saker_redaktoren_sier_nei_til_faar_likevel_vinkler(ki):
    """Det eieren faktisk ba om. Uten dette står saken der uten tittel og uten
    knapp — journalisten ser bare at KI-en har avvist den, ikke hvorfor eller
    hva den kunne blitt."""
    ki(is_story=False)
    saker = [sak(i) for i in range(3)]
    run_workflow(saker)

    for c in saker:
        assert c.editor.get("is_story") is False, "testen måler ikke det den tror"
        assert c.angles, f"{c.key} fikk ingen vinkler selv om redaktøren bare var skeptisk"
        assert len(c.angles) == 2, "to overskrifter per sak var kravet"


def test_journalisten_faar_vite_at_redaktoren_sa_nei(ki):
    """Vinkler uansett betyr ikke vinkler i blinde. Sier redaktøren nei, endres
    oppdraget fra «skriv den» til «finn vinkelen som ville snudd ham» — og da må
    journalist-agenten faktisk få vite hva dommen var."""
    falsk = ki(is_story=False)
    run_workflow([sak(0)])

    assert "Dom: NEI" in falsk.journalist_prompt, falsk.journalist_prompt[:400]
    assert "For tynt til forsiden" in falsk.journalist_prompt, "begrunnelsen ble ikke sendt med"


def test_ja_saker_prioriteres_naar_kvoten_ikke_rekker_alle(ki, monkeypatch):
    """Dommen er ikke lenger en port, men den er fortsatt et råd: rekker vi bare
    to saker, skal de to redaktøren tror på gå først. Ellers ville endringen ha
    gjort verktøyet dårligere, ikke bedre.

    Merk at sak-0 og sak-1 har HØYEST score — uten prioriteringen ville de to
    vraket sakene tatt plassen fra de to redaktøren anbefalte."""
    falsk = ki(is_story={"sak-0": False, "sak-1": False, "sak-2": True, "sak-3": True})
    monkeypatch.setattr(agents, "JOURNALIST_CAP", 2)
    saker = [sak(i) for i in range(4)]
    run_workflow(saker)

    med_vinkler = {c.key for c in saker if c.angles}
    assert med_vinkler == {"sak-2", "sak-3"}, med_vinkler
    blokker = [x for x in falsk.journalist_prompt.splitlines() if x.startswith("=== SAK ")]
    assert len(blokker) == 2, blokker


# ── Grunnlagssjekken advarer, den forkaster ikke ────────────────────────────


def test_tynt_grunnlag_gir_vinkler_men_merkes(ki):
    """Mangler SSB-lenken, forsvant hele saken lydløst før. Nå kommer titlene,
    men mangelen står i kortet slik at journalisten sjekker den selv."""
    ki()
    tynn = sak(0, data_url="")
    run_workflow([tynn])

    assert tynn.angles, "saken forsvant fordi grunnlaget var tynt"
    assert tynn.editor.get("gate_mangler"), "mangelen ble ikke registrert"
    assert any("lenke" in m for m in tynn.editor["gate_mangler"])


def test_journalisten_faar_vite_hva_som_mangler(ki):
    """Å slippe en tynn sak gjennom uten å si fra ville byttet én feil mot en
    verre: modellen fyller hullet med noe som høres bra ut. Mangelen sendes
    derfor med inn i prompten."""
    falsk = ki()
    run_workflow([sak(0, data_url="", data_source="")])

    assert "SVAKHETER I GRUNNLAGET" in falsk.journalist_prompt
    assert "lenke" in falsk.journalist_prompt


def test_fullt_grunnlag_gir_ingen_falsk_advarsel(ki):
    """Advarselen må bety noe. Står den på hver sak, slutter man å lese den."""
    ki()
    hel = sak(0)
    run_workflow([hel])
    assert not hel.editor.get("gate_mangler")


# ── Titlene: reglene som skal gi noe man faktisk stopper for ────────────────


def test_tittelreglene_naar_agentene_som_skriver_titler():
    """Faller reglene ut av én prompt, blir det den agenten som lager «Økning i
    antall arbeidsledige».

    Journalisten får hele blokka — han er den som faktisk leverer titlene.
    Redaktøren får kortversjonen: han skriver bare en arbeidstittel journalisten
    uansett erstatter, og de 440 tokenene vi sparer der er nettopp det som gjorde
    at journalistkallet fikk plass under Groqs minuttak."""
    from app import prompts

    for p in (prompts.JOURNALIST_ANGLES_SYSTEM, prompts.JOURNALIST_BATCH_SYSTEM):
        assert "TRE KRAV TIL EN TITTEL" in p
        assert "FORBUDTE AAPNINGER" in p
        assert "TEST TITTELEN SELV" in p

    for p in (prompts.EDITOR_SYSTEM, prompts.EDITOR_BATCH_SYSTEM):
        assert "SKARPT:" in p and "aktivt verb" in p
        assert "Setter soekelys paa" in p

    # Analytikeren skriver ingen tittel og skal ikke betale for reglene.
    assert "FORBUDTE AAPNINGER" not in prompts.ANALYST_SYSTEM
    assert "SKARPT:" not in prompts.ANALYST_SYSTEM


def test_siden_viser_titler_og_utkastknapp_paa_en_vraket_sak(tmp_path, monkeypatch):
    """Ende-til-ende på det journalisten faktisk ser i nettleseren.

    Logikken over kan være riktig og siden likevel vise «⛔ Ikke sak» uten en
    eneste tittel — det var nettopp slik feilen så ut. Denne testen renderer
    HTML-en og krever at titlene OG utkast-knappen står der på en sak KI-
    redaktøren har sagt nei til.
    """
    from app import storage as s
    from app.main import app
    from fastapi.testclient import TestClient

    monkeypatch.setattr(s, "DB_PATH", str(tmp_path / "t.sqlite3"))
    monkeypatch.setattr("app.main.DB_PATH", str(tmp_path / "t.sqlite3"), raising=False)
    s.save_scan({
        "cases": [{
            "key": "ssb-sok:05889:1103:2026K2",
            "title": "Godkjente boliger opp 770 % i Stavanger",
            "score": 40, "geo": "lokal", "topics": ["bolig og leie"],
            "angle": "a", "why": "w", "kind": "data",
            "finding": "Godkjente boliger i Stavanger: 261 i 2026K2, mot 30 i 2025K2.",
            "metric_value": "+770 %", "metric_period": "2026K2 mot 2025K2",
            "data_source": "SSB tabell 05889",
            "data_url": "https://www.ssb.no/statbank/table/05889",
            "coverage_status": "green", "coverage_examples": [],
            "editor": {"is_story": False, "headline": "H", "angle": "A",
                       "verdict": "For tynt til forsiden", "confidence": 30,
                       "gate_mangler": ["mangler lenke til datakilden"]},
            "angles": [
                {"vinkel": "konsekvens",
                 "title": "Boligkjøperne i Stavanger må ut med en halv million mer"},
                {"vinkel": "menneske", "title": "Slik merker familien på Storhaug det"},
            ],
        }],
        "plan": {}, "status": [], "summary": {}, "ai_mode": "llm",
    })

    html = TestClient(app).get("/").text
    assert "Boligkjøperne i Stavanger må ut med en halv million mer" in html
    assert "Lag utkast" in html, "vraket sak fikk titler, men ingen vei til utkast"
    # Advarsel, ikke sperre - ordlyden er selve poenget.
    assert "Tynt grunnlag" in html and "For tynt grunnlag til å skrive" not in html
    assert "Skeptisk" in html and "Ikke sak" not in html


def test_batchprompten_krever_vinkler_ogsaa_paa_nei_saker():
    """Koden slipper dem gjennom; prompten må be om dem. Uten begge deler leverer
    modellen tomt for de sakene den selv synes er svake."""
    from app import prompts

    assert "ogsaa de redaktoeren sa NEI til" in prompts.JOURNALIST_BATCH_SYSTEM
    assert "Noeyaktig TO overskrifter" in prompts.JOURNALIST_BATCH_SYSTEM
    assert "SVAKHETER I GRUNNLAGET" in prompts.JOURNALIST_BATCH_SYSTEM
