"""FastAPI-app: dashboard + scan-endepunkt.

Kjor:  uv run uvicorn app.main:app --reload
"""

from __future__ import annotations

import contextlib
import re
import threading
from calendar import monthrange
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import __version__, jobs, llm, verify
from app.agents import run_workflow, write_draft
from app.collectors import brreg, collect_all, coverage, ssb_kalender
from app.config import ENABLE_AI, ENABLE_BRREG, TEMAER, temagrupper
from app.models import Case
from app.planner import build_plan
from app.scoring import build_cases, finalize_scores
from app.storage import (
    STAGE_LABELS,
    STAGES,
    approve_lead,
    arkiver,
    calendar_month,
    dagskapasitet,
    decisions_map,
    fullfor,
    gjenapne,
    gjenopprett,
    list_approved,
    load_latest,
    mark_seen,
    sette_verdier,
    oppgaver,
    reject_lead,
    save_scan,
    seen_map,
    set_plan,
    sett_dagskapasitet,
    sett_temaer,
    timer_per_dag,
    valgte_temaer,
)

# Ikon per vinkel-inngang. Brukes i UI saa valget kan tas uten aa aapne noe.
INNGANG_IKON = {
    "menneske": "👤", "konsekvens": "📈", "naerhet": "📍", "ytterpunkt": "📊",
    "milepael": "🏁", "uventet": "❗", "motsetning": "⚖", "handling": "🧭",
    # gamle noekler, saa eldre skann fortsatt viser riktig ikon
    "aarsak": "🔍", "fremtid": "🔮", "sammenligning": "🗺",
}
VINKEL_NAVN = {
    "menneske": "Menneske", "konsekvens": "Konsekvens", "naerhet": "Nærhet",
    "ytterpunkt": "Ytterpunkt", "milepael": "Milepæl", "uventet": "Uventet",
    "motsetning": "Motsetning", "handling": "Handling",
    "aarsak": "Årsak", "fremtid": "Fremtid", "sammenligning": "Sammenligning",
}

MONTHS_NO = [
    "januar", "februar", "mars", "april", "mai", "juni",
    "juli", "august", "september", "oktober", "november", "desember",
]

BASE_DIR = Path(__file__).resolve().parent.parent
app = FastAPI(title="Case-radar", version=__version__)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def kortkilde(navn: str) -> str:
    """«SSB tabell 05887 (Byggeareal. Bruksareal til annet enn bolig ...)» -> «SSB tabell 05887».

    Det fulle tabellnavnet er nyttig i en fotnote, men paa mobil tok det to linjer
    og sto tre steder i samme kort. Lenken peker uansett rett til tabellen."""
    # Kutt ved FORSTE parentes, ikke den siste: tabellnavnene har parenteser
    # inni parenteser («... bygningstype (m²) (K)»), saa et regex som bare tar
    # den ytterste gruppa lar halve beskrivelsen staa igjen.
    helt = (navn or "").strip()
    kort = helt.split(" (", 1)[0].strip(" ,;-")
    if not kort:
        return helt
    # Eldre kilder skriver «SSB (befolkning, 07459)» - da ligger tabellnummeret
    # inne i parentesen, og aa kutte den bort fjerner det eneste som er presist.
    tabell = re.search(r"\b(\d{5})\b", helt)
    if tabell and tabell.group(1) not in kort:
        kort = f"{kort} tabell {tabell.group(1)}"
    return kort


templates.env.filters["kortkilde"] = kortkilde


def run_scan(jobb: jobs.Jobb | None = None) -> dict:
    """Hent kilder, bygg caser + plan, lagre og returner resultatet.

    `jobb` er valgfri. Er den satt, meldes framdrift underveis slik at UI-et kan
    vise hva som faktisk skjer i de 40-60 sekundene skannet tar - i stedet for at
    journalisten sitter og ser paa den samme skjermen og lurer paa om noe henger."""
    def steg(nr: int, tekst: str = "") -> None:
        if jobb is not None:
            jobb.fase(nr, tekst)

    def si(tekst: str) -> None:
        if jobb is not None:
            jobb.notat(tekst)

    # Valget leses her, ikke sendes inn: da gjelder menyen ogsaa naar skannet
    # startes fra cron eller autodeploy, ikke bare fra knappen.
    temaer = valgte_temaer()
    signals, ssb_cases, status = collect_all(si, temaer)
    status.insert(
        0,
        f"Temaer: {', '.join(temaer)}" if temaer
        else "Temaer: alle (ingen valgt - verktoyet leter bredt)",
    )

    # Grasrot-leads (Trends/Reddit) klynges; SSB-leads er ferdige.
    grassroots = build_cases(signals)  # tagger signals med geo/tema in-place
    for c in grassroots:
        if not c.coverage_query:
            c.coverage_query = c.title

    cases = ssb_cases + grassroots

    # Originalitetssjekk: har noen allerede skrevet om dette?
    steg(1)
    n_green = 0
    for i, c in enumerate(cases, 1):
        si(f"Sjekker dekning {i} av {len(cases)}: {c.title[:60]}")
        cov = coverage.check(c.coverage_query or c.title)
        c.coverage_status = cov["status"]
        c.coverage_examples = cov["examples"]
        if cov["status"] == "green":
            n_green += 1
    status.append(f"Dekningssjekk: {n_green}/{len(cases)} leads uskrevet (gronn)")

    # Originalitet legges paa scoren, deretter sorteres alt samlet.
    finalize_scores(cases)
    cases.sort(key=lambda c: c.score, reverse=True)

    # Redaksjonell KI-arbeidsflyt: analytiker -> redaktor -> journalist.
    ai_mode = "av"
    ai_regnskap: dict = {}
    if ENABLE_AI:
        steg(2, "Analytiker plukker ut de sterkeste funnene")
        ai_regnskap = run_workflow(cases, si)
        ai_mode = ai_regnskap["mode"]
        n = f"{ai_regnskap['lyktes']}/{ai_regnskap['forsokt']}"
        gjenbrukt = ai_regnskap.get("gjenbrukt", 0)
        if gjenbrukt:
            status.append(
                f"KI-arbeidsflyt: {gjenbrukt} saker hadde ekte KI-svar fra før "
                "(gjenbrukt, kostet ingen kvote)"
            )
        if ai_regnskap.get("i_ko"):
            # Ikke en feil, og skal ikke se ut som en. Budsjettet er der nettopp
            # for at skannet skal holde seg under kvotetaket - resten hentes ved
            # neste trykk.
            status.append(
                f"KI-kø: {ai_regnskap['i_ko']} saker venter på neste skann "
                "(budsjettet for dette skannet er brukt opp — trykk «Skann igjen»)"
            )
        if ai_mode == "llm":
            status.append(f"KI-arbeidsflyt: ekte KI ({llm.provider_label()}) ✓ {n} kall")
        elif ai_mode == "llm-delvis":
            # Det viktigste av alle statuslinjene: noen saker har ekte vinkler,
            # andre har maler. Foer sa appen bare «✓» her, og journalisten kunne
            # ikke se forskjell paa dem.
            status.append(
                f"KI-arbeidsflyt: DELVIS - {n} kall lyktes, "
                f"{ai_regnskap['feilet']} feilet ({ai_regnskap['feil']})"
            )
        elif ai_mode == "llm-feilet":
            status.append(f"KI-arbeidsflyt: nokkel finnes, men live feilet - {ai_regnskap['feil']}")
        else:
            status.append("KI-arbeidsflyt: demo-modus (maler, ingen nokkel)")

    # Forsprang: hva SSB slipper de neste ukene. Egen try - en dod feed skal aldri
    # velte et skann.
    steg(3, "Henter SSBs publiseringskalender")
    try:
        kommende, kal_status = ssb_kalender.collect(temaer=temaer)
        status.extend(kal_status)
    except Exception as exc:  # noqa: BLE001
        kommende, _ = [], status.append(f"[FEIL] SSB-kalender: {exc}")

    # Naeringslivet: hva som aapner og hva som gaar under. Hendelser, ikke tall -
    # saker journalisten kan ringe paa i dag. Egen try av samme grunn som over.
    hendelser: list[dict] = []
    if ENABLE_BRREG:
        try:
            hendelser, br_status = brreg.collect()
            status.extend(br_status)
        except Exception as exc:  # noqa: BLE001
            status.append(f"[FEIL] Brønnøysund: {exc}")

    # Nytt siden sist: samme kilder gir de samme funnene om igjen. Vi markerer hva
    # som ikke er sett foer, skjuler det journalisten allerede har forkastet, og loefter
    # det nye oeverst - saa et nytt soek faktisk gir noe nytt.
    for_dette_skannet = [c.key for c in cases]
    tidligere = seen_map()
    beslutninger = decisions_map()
    cases = [c for c in cases if beslutninger.get(c.key) != "rejected"]

    # «Trykker jeg soek igjen, skal nye tall dukke opp - aldri de samme.»
    #
    # De faste SSB-probene (config.SSB_PROBES) spor de SAMME tabellene hver gang,
    # og flyttetallene likesaa. Uten dette kom de samme fem funnene tilbake ved
    # hvert eneste skann, med identiske tall, og druknet det som faktisk var nytt.
    #
    # Vi sammenligner avtrykket av selve TALLET, ikke bare noekkelen: samme sak
    # med nytt tall er en ny sak og skal fram. Samme sak med samme tall er noe
    # journalisten allerede har sett, og da er det stoy.
    avtrykk = {c.key: f"{c.metric_value}|{c.metric_period}|{c.finding}" for c in cases}
    sett_verdier = sette_verdier()
    uendret = sum(1 for c in cases if sett_verdier.get(c.key) == avtrykk[c.key])
    cases = [c for c in cases if sett_verdier.get(c.key) != avtrykk[c.key]]
    if uendret:
        status.append(
            f"Skjult: {uendret} funn med uendret tall siden sist "
            "(samme sak, samme tall - kommer tilbake naar SSB oppdaterer)"
        )

    for c in cases:
        # Gjenbruks-leadene fra soesteravisene faar ALDRI «ny»-loeftet, og det er
        # ikke en smakssak. Noekkelen deres er laget av overskriften
        # (schibsted.py: «schibsted:<avis>:<tittel>»), og RSS-feeder bytter
        # overskrifter hele tiden - saa de er teknisk «aldri sett foer» ved hvert
        # eneste skann. Med er_ny som PRIMAER sorteringsnoekkel la de seg dermed
        # oeverst hver gang, mens SSB-funnene - som har stabile noekler og er hele
        # poenget med verktoyet - sank ned saa snart de var sett én gang.
        #
        # «Ny» skal bety «verktoyet fant noe nytt», ikke «avisa byttet forside».
        c.er_ny = c.kind != "schibsted" and c.key not in tidligere

    # Egne datafunn foer gjenbrukte avissaker. Originalitet er hele forspranget:
    # et SSB-tall ingen har skrevet om slaar en Aftenposten-sak som allerede er
    # publisert, uansett hvor godt den scorer.
    RANG = {"data": 0, "grasrot": 1, "schibsted": 2}
    cases.sort(key=lambda c: (RANG.get(c.kind, 1), not c.er_ny, -c.score))
    mark_seen(for_dette_skannet, avtrykk)
    antall_nye = sum(1 for c in cases if c.er_ny)
    status.append(
        f"Nytt siden sist: {antall_nye} av {len(cases)} leads"
        + (" (ingen nye - kildene har ikke endret seg)" if not antall_nye else "")
    )

    plan = build_plan(cases)
    summary = {
        "total": len(cases),
        "green": sum(1 for c in cases if c.coverage_status == "green"),
        "yellow": sum(1 for c in cases if c.coverage_status == "yellow"),
        "red": sum(1 for c in cases if c.coverage_status == "red"),
        "data": sum(1 for c in cases if c.kind == "data"),
        "grassroots": sum(1 for c in cases if c.kind == "grasrot"),
    }
    payload = {
        "cases": [c.to_dict() for c in cases],
        "plan": plan,
        "status": status,
        "signal_count": len(signals),
        "ssb_count": len(ssb_cases),
        "summary": summary,
        "antall_nye": antall_nye,
        "topic_trends": _case_topic_trends(cases),
        "kommende": kommende,
        "hendelser": hendelser,
        "ai_mode": ai_mode,
        # Grunnen hoerer hjemme ved siden av varselet, ikke nederst under
        # «Kildestatus» der ingen leter naar noe ser rart ut. Merk at den nå
        # settes OGSAA ved «llm-delvis» - foer kastet vi feilinfoen bort i det
        # oyeblikket ett kall lyktes, selv om ti feilet.
        "ai_feil": ai_regnskap.get("feil", ""),
        "ai_regnskap": ai_regnskap,
    }
    save_scan(payload)
    return payload


def _case_topic_trends(cases: list) -> list[dict]:
    """Tema-fordeling basert paa leadene (ikke raa signaler)."""
    counts: dict[str, dict] = {}
    for c in cases:
        for t in c.topics:
            d = counts.setdefault(t, {"name": t, "count": 0, "local": 0})
            d["count"] += 1
            if c.geo == "lokal":
                d["local"] += 1
    return sorted(counts.values(), key=lambda d: d["count"], reverse=True)


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, apen: str = "", ferskt: str = ""):
    """`apen` er «<sakskey>|<vinkelnr>» og aapner den vinkelen ved sidelast.

    Uten dette landet journalisten paa en side der alt var slaatt sammen igjen -
    utkastet var skrevet, men usynlig. Det saa ut som ingenting hadde skjedd."""
    data = load_latest()
    scanned_at = None
    if data and data.get("created_at"):
        scanned_at = _human_time(data["created_at"])
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "data": data,
            "apen": apen,
            "ferskt": bool(ferskt),
            "scanned_at": scanned_at,
            "version": __version__,
            "decisions": decisions_map(),
            "INNGANG_IKON": INNGANG_IKON,
            "VINKEL_NAVN": VINKEL_NAVN,
            "approved_count": len(list_approved()),
            "TEMAER": TEMAER,
            "temagrupper": temagrupper(),
            "valgte_temaer": valgte_temaer(),
        },
    )


# Skannet tar 40-60 sekunder. Tidene er maalt paa ekte kjoringer, ikke gjettet.
SKANN_FASER: list[tuple[int, str, float]] = [
    (2, "Henter kilder", 30.0),
    (46, "Sjekker om noen allerede har skrevet om det", 14.0),
    (70, "Redaktør og journalist vurderer funnene", 22.0),
    (92, "Rangerer og lagrer", 4.0),
]


@app.post("/scan")
async def scan(request: Request):
    """Lagre temavalget og start et skann - i den rekkefolgen.

    Temavalg og skann er samme handling for journalisten: han aapner menyen,
    huker av hva han leter etter, og trykker start. Foer laa de i hver sin knapp,
    saa man kunne skanne uten aa ha sett paa temaene - og da var menyen pynt.

    Skjemaet leses raatt fordi avkryssingsbokser sender samme feltnavn flere
    ganger; `Form()` ville bare gitt oss den siste.

    `meny=1` skiller «journalisten sendte inn menyen» fra «skannet ble startet et
    annet sted» (kø-knappen, cron, uten JS). Uten det ville et skann uten meny
    sett ut som «ingen temaer huket av» og stille nullstilt valget hans.
    """
    skjema = await request.form()
    if str(skjema.get("meny") or ""):
        sett_temaer([str(v) for v in skjema.getlist("tema")])
    js = str(skjema.get("js") or "")
    jobb = jobs.start(SKANN_FASER, run_scan)
    if js:
        return JSONResponse({"jobb": jobb.id})
    jobs.vent(jobb, 240)
    return RedirectResponse(url="/", status_code=303)


def _find_lead(key: str) -> dict | None:
    data = load_latest()
    if not data:
        return None
    return next((c for c in data.get("cases", []) if c.get("key") == key), None)


# Utkastet gaar gjennom disse fasene. Prosenten er et anslag (se app/jobs.py),
# teksten er alltid det som faktisk skjer.
UTKAST_FASER: list[tuple[int, str, float]] = [
    (4, "Henter kildegrunnlaget", 1.5),
    (14, "Journalisten skriver artikkelen …", 22.0),
    (88, "Sporer hvert tall tilbake til kilden", 3.0),
]

# To utkast samtidig ville ellers lese samme skann, skrive hver sin kopi tilbake,
# og den siste ville slette den forstes arbeid.
_SKANN_LAAS = threading.Lock()


def _skriv_utkast(jobb: jobs.Jobb, key: str, vinkel: int) -> dict:
    """Selve arbeidet bak «Be om utkast». Kjorer i en bakgrunnstraad."""
    with _SKANN_LAAS:
        data = load_latest()
        if not data:
            raise RuntimeError("Ingen skann å skrive fra — kjør et søk først.")
        sak = next((c for c in data.get("cases", []) if c.get("key") == key), None)
        if sak is None:
            raise RuntimeError("Fant ikke saken i siste skann. Kjør søk på nytt.")
        angles = sak.get("angles") or []
        if not 0 <= vinkel < len(angles):
            raise RuntimeError("Fant ikke vinkelen.")

        jobb.fase(1)
        utkast = write_draft(_case_from_dict(sak), sak.get("editor") or {}, angles[vinkel])
        if not utkast.get("body"):
            raise RuntimeError(f"Journalisten leverte ingen tekst. {llm.last_error()}".strip())

        jobb.fase(2)
        angles[vinkel] = utkast
        sak["angles"] = angles
        save_scan({k: v for k, v in data.items() if k != "created_at"})
    return {"key": key, "vinkel": vinkel, "mode": utkast.get("mode", "mal")}


@app.post("/leads/{key:path}/utkast")
def be_om_utkast(key: str, vinkel: int = Form(0), js: str = Form("")):
    """Start skrivingen. Med JavaScript svarer vi med én gang og UI-et viser framdrift.

    Foer dette blokkerte hele POST-en i 10-30 sekunder mens modellen skrev. Paa
    mobil saa det ut som knappen var doed. Uten JS beholder vi den gamle oppforselen
    (vent, saa omdiriger) slik at siden fortsatt virker."""
    jobb = jobs.start(UTKAST_FASER, lambda j: _skriv_utkast(j, key, vinkel))
    if js:
        return JSONResponse({"jobb": jobb.id})
    jobs.vent(jobb, 120)
    return RedirectResponse(url=_apen_url(key, vinkel), status_code=303)


def _apen_url(key: str, vinkel: int) -> str:
    return f"/?apen={quote(key)}%7C{vinkel}#sak-{key}"


@app.get("/jobb/{jobb_id}")
def jobb_status(jobb_id: str):
    """Framdrift for en bakgrunnsjobb. Ukjent id betyr som regel at appen er restartet."""
    jobb = jobs.hent(jobb_id)
    if jobb is None:
        return JSONResponse(
            {"status": "ukjent", "pct": 0, "tekst": "", "feil": "Jobben finnes ikke lenger."},
            status_code=404,
        )
    return JSONResponse({**jobb.tilstand(), "resultat": jobb.resultat})


def _case_from_dict(d: dict) -> Case:
    """Minimal Case for aa bygge kildegrunnlaget - kun feltene agenten bruker."""
    return Case(
        key=d.get("key", ""), title=d.get("title", ""), score=d.get("score", 0) or 0,
        geo=d.get("geo", "nasjonal"), topics=d.get("topics") or [],
        angle=d.get("angle", ""), why=d.get("why", ""), signals=[],
        created_at=datetime.now(tz=UTC), kind=d.get("kind", "data"),
        finding=d.get("finding", ""), metric_value=d.get("metric_value", ""),
        metric_period=d.get("metric_period", ""), data_source=d.get("data_source", ""),
        data_url=d.get("data_url", ""), coverage_status=d.get("coverage_status", "unknown"),
        coverage_examples=d.get("coverage_examples") or [],
    )


@app.post("/leads/{key:path}/approve")
def approve(
    key: str,
    vinkel: int = Form(0),
    start_date: str = Form(""),
    deadline: str = Form(""),
):
    """Godkjenn EN av journalistens tre vinkler og legg den i Godkjente saker.

    Start og deadline settes i samme handling - de styrer hvor saken dukker opp i
    kalenderen. Saken lagres samme sted som alle andre godkjente saker; kalenderen
    er bare en visning av dem."""
    lead = _find_lead(key)
    if lead:
        angles = lead.get("angles") or []
        if 0 <= vinkel < len(angles):
            lead = {**lead, "draft": angles[vinkel], "valgt_vinkel": vinkel}
        approve_lead(key, lead)
        if start_date or deadline:
            set_plan(key, start_date=start_date, deadline=deadline)
    return RedirectResponse(url="/godkjente", status_code=303)


@app.post("/leads/{key:path}/plan")
def plan_lead(
    key: str,
    start_date: str = Form(""),
    deadline: str = Form(""),
    stage: str = Form(""),
    timer: str = Form(""),
    tilbake: str = Form("/godkjente"),
):
    """Endre start, deadline, stadium og/eller timer per dag paa en godkjent sak."""
    set_plan(
        key, start_date=start_date, deadline=deadline,
        stage=stage or None, timer=timer or None,
    )
    return RedirectResponse(url=tilbake or "/godkjente", status_code=303)


@app.post("/oppgaver/{key:path}/ferdig")
def oppgave_ferdig(key: str, tilbake: str = Form("/kalender?fane=oppgaver")):
    """«Ferdig» - saken ut av kalenderen og oppgavelista, men ikke slettet."""
    fullfor(key)
    return RedirectResponse(url=tilbake or "/kalender?fane=oppgaver", status_code=303)


@app.post("/oppgaver/{key:path}/angre")
def oppgave_angre(key: str, tilbake: str = Form("/kalender?fane=oppgaver")):
    gjenapne(key)
    return RedirectResponse(url=tilbake or "/kalender?fane=oppgaver", status_code=303)


@app.post("/temaer")
async def velg_temaer(request: Request):
    """Hvilke temaer skannet skal lete etter.

    Leser skjemaet raatt fordi avkryssingsbokser sender samme feltnavn flere
    ganger - `Form()` ville bare gitt oss den siste."""
    skjema = await request.form()
    sett_temaer([str(v) for v in skjema.getlist("tema")])
    return RedirectResponse(url=str(skjema.get("tilbake") or "/"), status_code=303)


@app.post("/kalender/kapasitet")
def endre_kapasitet(timer: str = Form(""), tilbake: str = Form("/kalender")):
    """Hvor mange timer journalisten faktisk har paa en dag. Justerbart, fordi en
    frilanser og en fast ansatt ikke har samme dag."""
    with contextlib.suppress(TypeError, ValueError):
        sett_dagskapasitet(float(timer.replace(",", ".")))
    return RedirectResponse(url=tilbake or "/kalender", status_code=303)


@app.post("/leads/{key:path}/reject")
def reject(key: str):
    reject_lead(key)
    return RedirectResponse(url="/", status_code=303)


@app.get("/godkjente", response_class=HTMLResponse)
def godkjente(request: Request, arkiv: int = 0):
    """Lagrede utkast. `arkiv=1` viser bunken man har sveipet bort."""
    def pynt(x: dict) -> dict:
        return {**x, "_prosessnotat": verify.prosessnotat(
            x, leverandor=llm.provider_label(), godkjent_av="Redaksjonen")}

    return templates.TemplateResponse(
        request=request,
        name="godkjente.html",
        context={
            "leads": [pynt(x) for x in list_approved(arkiverte=bool(arkiv))],
            "viser_arkiv": bool(arkiv),
            "antall_arkiverte": len(list_approved(arkiverte=True)),
            "version": __version__,
        },
    )


@app.post("/godkjente/{key:path}/arkiver")
def arkiver_sak(key: str, js: str = Form("")):
    """Sveip venstre. Saken legges bort - ikke slettet, alltid mulig aa angre."""
    ok = arkiver(key)
    if js:
        return JSONResponse({"ok": ok})
    return RedirectResponse(url="/godkjente", status_code=303)


@app.post("/godkjente/{key:path}/gjenopprett")
def gjenopprett_sak(key: str, js: str = Form("")):
    ok = gjenopprett(key)
    if js:
        return JSONResponse({"ok": ok})
    return RedirectResponse(url="/godkjente", status_code=303)


@app.get("/kalender", response_class=HTMLResponse)
def kalender(request: Request, ym: str = "", fane: str = "kalender"):
    """Redaksjonell kalender: maanedsrutenett med planlagte saker.

    Ingen Google-innlogging, ingen oppsett - den bygger paa saker journalisten selv har
    godkjent. Saker uten dato vises som "uplanlagt" slik at de ikke forsvinner."""
    today = date.today()
    try:
        year, month = (int(x) for x in ym.split("-", 1)) if ym else (today.year, today.month)
        date(year, month, 1)  # kaster paa tull som 2026-13
    except (ValueError, TypeError):
        year, month = today.year, today.month

    by_day = calendar_month(year, month)
    dag_timer = timer_per_dag(by_day)
    kapasitet = dagskapasitet()
    # Hele kalendersida ser bare paa saker som fortsatt er i arbeid. En ferdig
    # sak skal ikke dukke opp igjen under «Uten dato» eller i «Kommende
    # deadlines» - den er jo gjort.
    approved = list_approved(fullforte=False)
    uplanlagt = [x for x in approved if not (x.get("_start") or x.get("_deadline"))]

    # Bygg rutenettet: hele uker, mandag foerst, med tomme celler rundt maaneden.
    first = date(year, month, 1)
    days_in_month = monthrange(year, month)[1]
    lead_blanks = first.weekday()  # 0 = mandag
    cells: list[dict | None] = [None] * lead_blanks
    for d in range(1, days_in_month + 1):
        iso = f"{year:04d}-{month:02d}-{d:02d}"
        cells.append(
            {
                "day": d,
                "iso": iso,
                "today": date(year, month, d) == today,
                "leads": by_day.get(iso, []),
                "timer": dag_timer.get(iso, 0.0),
                "overbooket": dag_timer.get(iso, 0.0) > kapasitet,
            }
        )
    while len(cells) % 7:
        cells.append(None)
    weeks = [cells[i : i + 7] for i in range(0, len(cells), 7)]

    # Kommende deadlines: neste 5 frister fra i dag, uansett maaned.
    kommende = []
    for lead in sorted(approved, key=lambda x: x.get("_deadline") or "9999"):
        dl = lead.get("_deadline") or ""
        if not dl or dl < today.isoformat():
            continue
        try:
            dd = date.fromisoformat(dl)
        except ValueError:
            continue
        draft = lead.get("draft") or {}
        kommende.append({
            "iso": dl,
            "label": f"{dd.day}. {MONTHS_NO[dd.month - 1][:3]}",
            "title": draft.get("title") or lead.get("title", ""),
        })
        if len(kommende) == 5:
            break

    prev_m = date(year, month, 1) - timedelta(days=1)
    next_m = date(year, month, days_in_month) + timedelta(days=1)

    return templates.TemplateResponse(
        request=request,
        name="kalender.html",
        context={
            "weeks": weeks,
            "year": year,
            "month": month,
            "month_name": MONTHS_NO[month - 1],
            "prev_ym": f"{prev_m.year:04d}-{prev_m.month:02d}",
            "next_ym": f"{next_m.year:04d}-{next_m.month:02d}",
            "today_ym": f"{today.year:04d}-{today.month:02d}",
            "uplanlagt": uplanlagt,
            "kommende": kommende,
            "planned_count": sum(len(v) for v in by_day.values()),
            # Oppgavefanen: det samme arbeidet som en liste, med naermeste frist
            # foerst. Kalenderen viser NAAR; denne viser HVA som staar for tur.
            "fane": "oppgaver" if fane == "oppgaver" else "kalender",
            "oppgaver": [
                {**x, "_dager_igjen": _dager_til(x.get("_deadline") or "")}
                for x in oppgaver()
            ],
            # Sist fullfoert oeverst - det er den man angrer paa hvis man
            # trykket feil, ikke den med fjernest deadline.
            "ferdige": sorted(
                list_approved(fullforte=True),
                key=lambda x: x.get("_fullfort") or "",
                reverse=True,
            )[:20],
            "kapasitet": kapasitet,
            "maaned_timer": round(sum(dag_timer.values()), 1),
            "overbookede_dager": sum(1 for t in dag_timer.values() if t > kapasitet),
            "stages": STAGES,
            "stage_labels": STAGE_LABELS,
            "version": __version__,
        },
    )


@app.get("/api/cases")
def api_cases():
    data = load_latest()
    if not data:
        return JSONResponse({"cases": [], "note": "Ingen skann enda. POST /scan."})
    return JSONResponse(data)


@app.get("/health")
def health():
    return {"status": "ok", "version": __version__}


# HTML-sidene har ikonet inline, men JSON-rutene har ingen <head> - da spor
# nettleseren etter /favicon.ico og faar 404 i konsollen. Ett svar, ingen stoy.
_FAVICON = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
    '<text y=".9em" font-size="90">📡</text></svg>'
)


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(
        content=_FAVICON,
        media_type="image/svg+xml",
        headers={"Cache-Control": "public, max-age=86400"},
    )


def _human_time(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso).astimezone(UTC)
        return dt.strftime("%d.%m.%Y %H:%M UTC")
    except (ValueError, TypeError):
        return iso


def _dager_til(iso: str) -> int | None:
    """Dager til frist. Negativt tall betyr at fristen er passert."""
    try:
        return (date.fromisoformat(iso) - date.today()).days
    except (ValueError, TypeError):
        return None
