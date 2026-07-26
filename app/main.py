"""FastAPI-app: dashboard + scan-endepunkt.

Kjor:  uv run uvicorn app.main:app --reload
"""

from __future__ import annotations

import contextlib
import hashlib
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
    oppgaver,
    publisert_antall,
    publisert_legg_til,
    publisert_liste,
    publisert_slett,
    reject_lead,
    rekkefolge_map,
    save_scan,
    seen_map,
    set_plan,
    sett_dagskapasitet,
    sett_rekkefolge,
    sett_temaer,
    sette_verdier,
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


def _css_versjon() -> str:
    """Kort hash av style.css, brukt som `?v=` paa lenka til den.

    Dette er ikke pynt - det er en feil som allerede har rammet eieren. Hele
    fiksen som gjorde sveipen synlig laa i CSS, og CSS-en er en EGEN fil uten
    cache-buster. JS-en ligger inline i dashboard.html og oppdateres ved hver
    sidelast; CSS-en gjorde det ikke. Foran appen staar en Cloudflare-tunnel som
    cacher statiske filer hardt, og en pull-to-refresh henter HTML - ikke en
    cachet CSS-fil. Resultat: ny kode, gammel CSS, og en sveip som fortsatt var
    usynlig.

    Innholdshash og ikke versjonsnummer, fordi den da buster seg selv hver eneste
    gang fila endres. `__version__` sto paa 0.1.0 gjennom hele arbeidet - et
    versjonsnummer noen maa huske aa bumpe er ingen garanti.

    md5 fordi det er kort og raskt. Ingen sikkerhetsrolle: dette skal skille to
    versjoner av en stilfil, ikke motstaa noen.
    """
    try:
        raa = (BASE_DIR / "static" / "style.css").read_bytes()
    except OSError:
        return "0"
    return hashlib.md5(raa, usedforsecurity=False).hexdigest()[:8]


CSS_V = _css_versjon()


def _bygg_id() -> str:
    """Hvilken commit som FAKTISK kjoerer, lest fra BUILD.txt.

    Eieren 26.07.2026: «Foeler ikke updates kommer igjennom.» Han hadde grunn til
    aa lure: ingenting paa sida sa hvilken kode som kjoerte. `__version__` sto paa
    0.1.0 gjennom alt arbeidet, og en deploy som stille bygget gammel kode saa
    noeyaktig ut som en vellykket.

    `deploy.sh` skriver denne fila med commit-SHA og tidspunkt rett foer
    docker build, saa den er stoept inn i imaget. Da kan tre ting sammenlignes,
    og alle tre maa stemme: koden paa disk, containeren som kjoerer, og det
    nettleseren viser.
    """
    try:
        return (BASE_DIR / "BUILD.txt").read_text().strip().splitlines()[0][:40]
    except (OSError, IndexError):
        return "ukjent"


BYGG = _bygg_id()

# Lang max-age er trygt NETTOPP fordi URL-en endrer seg med innholdet. Uten
# hashen over ville dette gjort problemet permanent i stedet for aa loese det.
app.mount(
    "/static",
    StaticFiles(directory=BASE_DIR / "static"),
    name="static",
)
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
# Global, saa ingen sidevisning kan glemme aa sende den med.
templates.env.globals["css_v"] = CSS_V
templates.env.globals["bygg"] = BYGG


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


# Hvor mange broennoeysund-hendelser som blir SAKER. Resten staar fortsatt i
# «hva som kommer»-fanen. Taket finnes fordi redaktoer og journalist bare rekker
# fire saker per skann: slipper vi inn 40 konkurser, druknr SSB-funnene i dem, og
# da har vi byttet ett problem mot et annet.
HENDELSER_SOM_SAKER = 6


def _hendelse_tittel(h: dict) -> str:
    """«Ekte Kafe As gikk konkurs» - lesbart, uten aa paastaa noe som ikke staar."""
    navn = h.get("navn") or "Foretak uten navn"
    return {
        "konkurs": f"{navn} har gaatt konkurs",
        "avvikling": f"{navn} er under avvikling",
        "nytt": f"{navn} er registrert i Stavanger-omraadet",
    }.get(h.get("type", ""), navn)


def _hendelse_finding(h: dict) -> str:
    """Selve faktumet, i klartekst - det KI-agentene faar som eneste grunnlag.

    Regnskapstallene er det som gjoer en konkurs til en SAK i stedet for et navn:
    «Firma X gikk konkurs» er en notis, «Firma X omsatte for 4,1 millioner og gikk
    med underskudd aaret foer» er noe en journalist kan ringe paa."""
    deler = [_hendelse_tittel(h) + "."]
    if h.get("dato"):
        deler.append(f"Dato: {h['dato']} ({h.get('dager_siden', '?')} dager siden).")
    if h.get("kommune"):
        deler.append(f"Kommune: {h['kommune']}.")
    if h.get("bransje"):
        deler.append(f"Bransje: {h['bransje']}.")
    if isinstance(h.get("ansatte"), int):
        deler.append(f"Ansatte: {h['ansatte']}.")
    r = h.get("regnskap") or {}
    if r.get("omsetning") is not None:
        deler.append(f"Omsetning {r.get('aar', 'siste aar')}: {r['omsetning']:,.0f} kr."
                     .replace(",", " "))
    if r.get("resultat") is not None:
        deler.append(f"Aarsresultat: {r['resultat']:,.0f} kr.".replace(",", " "))
    return " ".join(deler)


def _hendelse_cases(hendelser: list[dict]) -> list[Case]:
    """Gjoer broennoeysund-hendelser til leads paa lik linje med SSB-funn.

    Eieren 26.07.2026: verktoyet skal bruke kilder som kan LAGE artikler. En
    konkurs er akkurat det - et vedtak ingen har skrevet ut enda, med et orgnr
    man kan slaa opp og et regnskap man kan lese.
    """
    ut: list[Case] = []
    for h in hendelser[:HENDELSER_SOM_SAKER]:
        orgnr = h.get("orgnr") or ""
        if not orgnr:
            continue          # uten orgnr finnes ingen stabil noekkel og ingen lenke
        r = h.get("regnskap") or {}
        # Tallet som staar oeverst i kortet: omsetningen naar vi har den, ellers
        # hvor ferskt vedtaket er. Begge deler er konkret; ingen av dem er gjettet.
        if r.get("omsetning") is not None:
            verdi = f"{r['omsetning']:,.0f} kr".replace(",", " ")
            periode = f"omsetning {r.get('aar', 'siste aar')}"
        else:
            verdi = h.get("dato", "")
            periode = f"{h.get('dager_siden', '?')} dager siden"
        ut.append(Case(
            key=f"brreg:{h.get('type', 'hendelse')}:{orgnr}",
            title=_hendelse_tittel(h),
            kind="hendelse",
            geo="lokal",
            # Vekten fra brreg._hendelse() er allerede journalistisk: publikumsnaere
            # bransjer og ferske konkurser veier tyngst. Gjenbrukes som score i
            # stedet for aa finne paa en ny skala.
            score=float(h.get("vekt", 1)) * 4,
            topics=["jobb og okonomi"],
            angle="Ring konkursboet og de ansatte - hva skjer med lokalene og jobbene?",
            why="Hendelse i naeringslivet lokalt, hentet fra Broennoeysundregistrene.",
            signals=[],
            created_at=datetime.now(UTC),
            finding=_hendelse_finding(h),
            coverage_query=h.get("navn") or "",
            data_source="Brønnøysundregistrene",
            data_url=h.get("lenke", ""),
            metric_value=verdi,
            metric_period=periode,
        ))
    return ut


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

    # Naeringslivet: hva som aapner og hva som gaar under. Hendelser, ikke tall -
    # saker journalisten kan ringe paa i DAG.
    #
    # Denne blokka sto FOER nedenfor KI-flyten, og da var hendelsene bare en liste
    # i «hva som kommer»-fanen: de rakk verken dekningssjekk, scoring eller
    # vinkler. Broennoeysund er en primaerkilde - konkursvedtak og nyregistreringer
    # er raastoff ingen har skrevet ut enda - saa de hoerer hjemme her oppe,
    # sammen med SSB-tallene. Egen try: en doed kilde skal aldri velte et skann.
    hendelser: list[dict] = []
    if ENABLE_BRREG:
        si("Brønnøysund: konkurser og nyregistreringer")
        try:
            hendelser, br_status = brreg.collect()
            status.extend(br_status)
            hendelse_cases = _hendelse_cases(hendelser)
            if hendelse_cases:
                status.append(
                    f"Brønnøysund: {len(hendelse_cases)} hendelser lagt inn som saker"
                )
        except Exception as exc:  # noqa: BLE001
            hendelse_cases = []
            status.append(f"[FEIL] Brønnøysund: {exc}")
    else:
        hendelse_cases = []

    cases = ssb_cases + hendelse_cases + grassroots

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
        # Alle noekler er naa stabile (SSB-tabell + periode, eller orgnr), saa
        # «ny» betyr det den skal: verktoyet fant noe det ikke hadde foer.
        #
        # Det gjorde den ikke da avis-RSS var en kilde: noekkelen var laget av
        # overskriften, og feeder bytter overskrifter hele tiden - saa de var
        # teknisk «aldri sett foer» ved hvert eneste skann og la seg oeverst.
        c.er_ny = c.key not in tidligere

    # PRIMAERKILDER FOERST. Eieren 26.07.2026: «Kilder som kan lage artikler,
    # ikke artikler for aa lage artikler - de skal vaere foerst.»
    #
    # SSB-tall og Broennoeysund-hendelser er likestilt paa toppen: begge er
    # raastoff ingen har skrevet ut enda. Google Trends er et signal om hva folk
    # SOEKER paa - nyttig som bakteppe, men det baerer sjelden en sak alene.
    RANG = {"data": 0, "hendelse": 0, "grasrot": 1}
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
    beslutninger = decisions_map()

    # Forkastede saker skal VAERE borte, ogsaa etter en refresh.
    #
    # Skannet filtrerte dem bort, men denne siden gjorde det ikke - den viste det
    # lagrede skannet raatt. Verifisert i Chromium 26.07.2026: sveip bort tre
    # saker, last siden paa nytt, og alle tre var tilbake. Med Forkast-knappen
    # saa man i det minste merkelappen «Forkastet» og skjonte at noe var
    # registrert; med sveip forsvant kortet og kom stille tilbake, som ser ut som
    # at appen mistet det han nettopp gjorde.
    #
    # Kopi, ikke mutasjon: `data` er det lagrede skannet, og det skal ikke endres
    # av at noen aapner forsiden.
    if data and data.get("cases"):
        synlige = [
            c for c in data["cases"]
            if beslutninger.get(c.get("key")) != "rejected"
        ]
        # Har han dratt sakene i en egen rekkefolge, er DEN fasiten. Saker uten
        # plass (nye siden sist han sorterte) legger seg bakerst i sin egen
        # rangering i stedet for aa sprette opp foerst og velte sorteringen hans.
        plasser = rekkefolge_map()
        if plasser:
            synlige.sort(
                key=lambda c: (plasser.get(c.get("key"), len(plasser) + 1_000),)
            )
        data = {**data, "cases": synlige}

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
            "publisert_antall": publisert_antall(),
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


@app.post("/rekkefolge")
async def lagre_rekkefolge(request: Request):
    """Rekkefolgen journalisten dro sakene i. Sendes som JSON fra dashbordet.

    Lagres med én gang, uten redirect: han skal ikke maatte trykke «lagre» etter
    aa ha flyttet et kort. Feiler den, staar rekkefolgen fortsatt riktig paa
    skjermen - men neste refresh viser sannheten, og det er riktigere enn aa
    late som."""
    data = await request.json()
    keys = data.get("keys") if isinstance(data, dict) else None
    if not isinstance(keys, list):
        return JSONResponse({"ok": False, "feil": "keys mangler"}, status_code=400)
    sett_rekkefolge([str(k) for k in keys[:200]])
    return JSONResponse({"ok": True})


@app.post("/leads/{key:path}/reject")
def reject(key: str):
    reject_lead(key)
    return RedirectResponse(url="/", status_code=303)


# --- Publiserte saker --------------------------------------------------------
# Eieren 26.07.2026: «Jeg vil at han skal kunne lagre det han legger ut ... slik
# at det blir lagret og han vet hvem som kom ut herfra.»
#
# Egen side, og bevisst plassert som en fjerde likestilt fane: radaren er hva som
# KAN bli en sak, «Lagret» er utkastene, kalenderen er naar de skal gjores - og
# dette er fasiten paa hva som faktisk kom paa trykk. Legges den inn under
# «Lagret» blander den utkast og publisert, og da svarer den ikke lenger paa
# spoersmaalet den finnes for.


@app.get("/publisert", response_class=HTMLResponse)
def publisert(request: Request, feil: str = ""):
    return templates.TemplateResponse(
        request=request,
        name="publisert.html",
        context={"saker": publisert_liste(), "feil": feil, "version": __version__},
    )


@app.post("/publisert")
def publisert_ny(
    url: str = Form(""), tittel: str = Form(""), notat: str = Form("")
):
    ok, grunn = publisert_legg_til(url, tittel, notat)
    # Feilen foelger med i URL-en i stedet for aa forsvinne i en redirect. En
    # lenke som stille ikke ble lagret er verre enn ingen lagring i det hele tatt.
    maal = "/publisert" if ok else f"/publisert?feil={quote(grunn)}"
    return RedirectResponse(url=maal, status_code=303)


@app.post("/publisert/{rad_id}/slett")
def publisert_fjern(rad_id: int):
    publisert_slett(rad_id)
    return RedirectResponse(url="/publisert", status_code=303)


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
            "publisert_antall": publisert_antall(),
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
            "publisert_antall": publisert_antall(),
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
    # `bygg` er det som gjoer deployen etterproevbar: oppdater.sh sammenligner
    # den med commit-en den nettopp sjekket ut. Stemmer de ikke, kjoerer
    # containeren gammel kode - og da skal deployen si det hoeyt.
    return {"status": "ok", "version": __version__, "bygg": BYGG}


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
