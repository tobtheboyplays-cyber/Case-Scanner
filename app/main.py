"""FastAPI-app: dashboard + scan-endepunkt.

Kjor:  uv run uvicorn app.main:app --reload
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import re
import threading
import time
from calendar import monthrange
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import __version__, faner, jobs, llm, storage, tall, trend, verify
from app.agents import journalist_angles, run_workflow, write_draft
from app.collectors import brreg, collect_all, coverage, ssb_kalender
from app.config import (
    ENABLE_AI,
    ENABLE_BRREG,
    TEMAER,
    demografi_for,
    temagrupper,
)
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
    ide_legg_til,
    ide_liste,
    ide_slett,
    lagre_maalinger,
    list_approved,
    load_latest,
    maalinger_for,
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
    # Hasher ALLE stilfilene, ikke bare style.css. Da Tobias kom til fikk han en
    # egen `tobias.css`, og med bare style.css i hashen ville en endring der
    # aldri busta cachen - nøyaktig den fella denne funksjonen finnes for.
    biter = b""
    for navn in ("style.css", "tobias/tobias.css"):
        try:
            biter += (BASE_DIR / "static" / navn).read_bytes()
        except OSError:
            continue
    if not biter:
        return "0"
    return hashlib.md5(biter, usedforsecurity=False).hexdigest()[:8]


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
# Sparkline-geometrien regnes i Python, ikke i Jinja: en SVG-punktliste bygget
# med lopende min/max i en mal blir uleselig, og den ville vaert utestbar.
templates.env.filters["sti"] = trend.sti


# Hvor mange broennoeysund-hendelser som blir SAKER. Resten staar fortsatt i
# «hva som kommer»-fanen. Taket finnes fordi redaktoer og journalist bare rekker
# fire saker per skann: slipper vi inn 40 konkurser, druknr SSB-funnene i dem, og
# da har vi byttet ett problem mot et annet.
HENDELSER_SOM_SAKER = 6

# Har INGENTING endret seg siden forrige skann, viser vi saa mange av de sterkeste
# gjengangerne paa nytt - merket «uendret» - i stedet for en tom skjerm. Tallet er
# lavt med vilje: dette er et aerlig naest-beste svar, ikke et fullt skann.
UENDRET_VISES = 5

# Hvor gammel Aftenbladets egen artikkel maa vaere foer et nytt tall er en
# OPPFOELGER og ikke en gjentakelse. Under dette har de nettopp skrevet om det,
# og da er saken tatt. 60 dager er to maaneder - lenge nok til at «hva har skjedd
# siden?» er et ekte spoersmaal.
OPPFOLGER_MIN_DAGER = int(os.getenv("CASE_RADAR_OPPFOLGER_DAGER", "60"))

# Konkurser, avviklinger og nyregistreringer er naeringsliv. Treffer temavalget
# ingen av disse merkelappene, hoerer hendelsene ikke hjemme i lead-lista - de
# staar fortsatt i «Kommer snart»-fanen.
BRREG_DEMOGRAFI = {"jobb og okonomi", "uteliv og kultur", "bolig og leie"}


# Ord som finnes i annenhver Stavanger-overskrift. Deler to tekster BARE disse,
# handler de ikke om det samme - de er begge paa norsk og begge fra Rogaland.
_TOMME_ORD = frozenset({
    "stavanger", "sandnes", "rogaland", "aftenblad", "aftenbladet", "norge",
    "norsk", "norske", "kommune", "kommunen", "fylke", "sier", "skal", "blir",
    "etter", "flere", "mange", "nye", "ikke", "dette", "dermed", "mener",
})


def _ord(tekst: str) -> set[str]:
    """Meningsbaerende ord, smaa bokstaver. Korte ord er stoppord i praksis."""
    reint = "".join(ch if ch.isalnum() else " " for ch in (tekst or "").lower())
    return {o for o in reint.split() if len(o) >= 5 and o not in _TOMME_ORD}


# En artikkel eldre enn dette er ikke en oppfoelger, den er arkivmateriale.
# Google News ga oss en sak fra 2015 (3878 dager) paa et byggetall fra i aar.
OPPFOLGER_MAKS_DAGER = int(os.getenv("CASE_RADAR_OPPFOLGER_MAKS", "900"))


def _er_oppfolger(c: Case, artikkel: dict) -> bool:
    """Handler Aftenbladets gamle artikkel om SAMME sak som dette funnet?

    Uten denne var oppfoelgeren verre enn ingenting. Maalt paa ekte data:

        «Blaaveisen Blomster har gaatt konkurs»
            -> «Omsetningen til Hafrsfjordbroa Blomster har ikke vaert hoeyere»
        «Familiefasen (30-34 aar) i Stavanger ned 0,4 %»
            -> «Slutt for India Tandoori Stavanger etter 34 aar»

    Ingen av dem er oppfoelgere. Presenterer vi dem som det, sender vi
    journalisten paa et blindspor med et loefte om at noen alt har gjort
    forarbeidet - og det er dyrere enn aa ikke si noe.

    Tre krav, og alle tre maa holde:
      · gammel nok til aa vaere en oppfoelger og ikke en gjentakelse
      · fersk nok til at «hva skjedde siden?» finnes som spoersmaal
      · faktisk om det samme
    """
    dager = artikkel.get("dager", 0)
    if not OPPFOLGER_MIN_DAGER <= dager <= OPPFOLGER_MAKS_DAGER:
        return False

    tittel = artikkel.get("title", "")

    # Naeringslivshendelser: FORETAKSNAVNET maa staa i overskriften. «Et annet
    # blomsterfirma i samme by» er ikke samme sak, og for en konkurs er den
    # forvekslingen den dyreste vi kan gjore.
    if c.kind == "hendelse":
        navn = c.title.split(" har gaatt")[0].split(" er ")[0].strip()
        kjerne = [o for o in _ord(navn) if o not in {"holding"}]
        return bool(kjerne) and all(o in tittel.lower() for o in kjerne[:2])

    # Tall: hvor mange felles ord som kreves, foelger hvor mange saken HAR.
    #
    # Fast «minst to» hoertes riktig ut og var maalbart feil: dekningssoeket for
    # «Godkjente boliger» er to ord, saa artikkelen «3800 boliger i Stavanger og
    # Sandnes staar tomme» falt ut - og det er en aapenbart god oppfoelger.
    # Samtidig maa «Stavanger unge voksne befolkning tilflytting» kreve to, ellers
    # slipper «Slutt for India Tandoori etter 34 aar» inn paa ordet «voksne».
    #
    # Halvparten av sakens egne ord, men aldri under ett og aldri over to.
    sakens = _ord(c.coverage_query) | _ord(c.title)
    if not sakens:
        return False
    kreves = max(1, min(2, (len(sakens) + 1) // 2))
    return len(_ord(tittel) & sakens) >= kreves


def _varsel(cases: list[Case], temaer: list[str], antall_nye: int) -> dict:
    """{tittel, tekst} til pop-in-en, eller {} naar skannet gikk som det skal.

    Tre utfall er verdt aa si fra om, og bare tre. Sier den fra om alt, blir den
    stoey - og da er vi tilbake til statuslinja ingen leste.
    """
    if not cases:
        # `viktig` betyr: ikke svipp ut av seg selv. Eieren 26.07.2026: «maa
        # ogsaa legge til tydelig naar en scan kommer tom ... og at du maa bytte
        # tema. Du kan legge til en 'trykk ok' paa den popuppen.»
        #
        # Et tomt skann er det ENE utfallet der beskjeden er en handling og ikke
        # en opplysning. Svipper den ut etter fem sekunder mens han ser en annen
        # vei, sitter han igjen med en tom side og ingen anelse om hvorfor.
        return {
            "tittel": "Skannet fant ingenting",
            "tekst": (
                f"Ingen nye funn innenfor {'de valgte temaene' if temaer else 'noen av temaene'}. "
                "Du må bytte tema for å lete et annet sted — eller fjerne alle "
                "avhukinger for å lete bredt."
                if temaer else
                "Kildene svarte, men hadde ingenting nytt. Huk av flere temaer, "
                "eller prøv igjen senere — SSB publiserer på faste datoer."
            ),
            "viktig": True,
            "handling": "temaer" if temaer else "",
        }
    # Ogsaa VIKTIG, av samme grunn som det helt tomme skannet. Maalt paa tre
    # ekte skann etter hverandre 26.07.2026: runde 2 ga 5 saker, 0 nye, alle
    # merket «uendret». Skjermen er ikke tom, men journalisten fikk ingenting
    # NYTT - og forskjellen mellom «0 kort» og «5 gamle kort» er usynlig for
    # han. Begge er en beskjed han maa ta stilling til, ikke en opplysning som
    # kan svippe forbi mens han ser en annen vei.
    if any(c.uendret for c in cases):
        return {
            "tittel": "Ingenting nytt denne gangen",
            # «Viser de 1 sterkeste funnene» er ikke norsk. Ett funn er
            # vanligere enn man tror naar temavalget er smalt.
            "tekst": (
                "Kildene svarte, men ingen tall har endret seg. Viser "
                + ("det sterkeste funnet" if len(cases) == 1
                   else f"de {len(cases)} sterkeste funnene")
                + " på nytt, merket «uendret». Bytt tema for å lete et annet "
                  "sted — SSB publiserer nye tall på faste datoer."
            ),
            "viktig": True,
            "handling": "temaer",
        }
    if not antall_nye:
        return {
            "tittel": "Ingen nye saker",
            "tekst": (
                "Alt i lista har vært her før. Bytt tema for å lete et annet "
                "sted, eller fjern alle avhukinger for å lete bredt."
            ),
            "viktig": True,
            "handling": "temaer",
        }
    return {}


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
    #
    # Temavalget gjelder ogsaa her. Et konkursvedtak er naeringsliv - velger
    # journalisten bare «natur og miljø», er seks konkurser ikke det han spurte
    # om, og de tar plassene fra det han faktisk ba om. Hendelsene staar fortsatt
    # i «Kommer snart»-fanen uansett tema; det er bare LEAD-lista som filtreres.
    hendelser: list[dict] = []
    tema_passer_brreg = not temaer or bool(demografi_for(temaer) & BRREG_DEMOGRAFI)
    if ENABLE_BRREG and not tema_passer_brreg:
        hendelse_cases = []
        si("Brønnøysund: konkurser og nyregistreringer")
        try:
            hendelser, br_status = brreg.collect()
            status.extend(br_status)
        except Exception as exc:  # noqa: BLE001
            status.append(f"[FEIL] Brønnøysund: {exc}")
        status.append(
            "Brønnøysund: hendelsene er utenfor temavalget - vises bare i "
            "«Kommer snart», ikke som saksforslag"
        )
    elif ENABLE_BRREG:
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

        # OPPFOELGER: Aftenbladet har skrevet om dette FOER, og det er lenge
        # siden. Da er ikke dekningen et minus - det er den letteste publiserte
        # saken som finnes. Avisa eier premisset, bildene og kildene fra sist,
        # og «hva skjedde etterpaa?» er en ferdig bestilling.
        #
        # Kravet om alder er poenget: skrev de om det i forrige uke, er dette en
        # gjentakelse, ikke en oppfoelger. Da skal den ligge unna.
        egne = [e for e in cov.get("aftenbladet", []) if _er_oppfolger(c, e)]
        if egne:
            c.oppfolger = egne[0]
    n_opp = sum(1 for c in cases if c.oppfolger)
    status.append(f"Dekningssjekk: {n_green}/{len(cases)} leads uskrevet (gronn)")
    if n_opp:
        status.append(
            f"Oppfølgere: {n_opp} funn Aftenbladet har skrevet om før "
            f"(eldre enn {OPPFOLGER_MIN_DAGER} dager - tallet er nytt, saken er kjent)"
        )

    # TRENDLINJE. Vi har allerede tallene; foer kastet vi dem mellom skann.
    # Maalingen lagres per PERIODE, ikke per skann - se app/trend.py for hvorfor
    # den forskjellen avgjor om linja beskriver statistikken eller knappetrykkene.
    try:
        punkter = []
        serier: dict[str, str] = {}          # {sakens noekkel: seriens noekkel}
        for c in cases:
            periode = trend.periode_av(c.metric_period)
            # KUN kildens egen tidsserie. `metric_value` ser ut som et tall vi
            # kunne brukt, men er ofte PROSENTENDRINGEN («+154 %») mens serien er
            # absolutte tall (kvadratmeter). Blandet vi dem, ble siste punkt 154
            # der de foerste var 8893 og 5432 - og kortet fikk overskriften
            # «opp 154 %» med «tredje kvartal paa rad med NEDGANG» under.
            #
            # Det er ikke en skjonnhetsfeil. Det er et feil tall som ser riktig
            # ut, i et verktoy hvis eneste jobb er aa gi journalisten noe han kan
            # trykke. Én kilde til linja, og bare én.
            #
            # SSB sender fem perioder i det samme svaret, saa serien gjor ogsaa at
            # linja staar der FOERSTE gang han skanner - i stedet for aa trenge
            # maaneder med morgenskann paa aa bygge seg selv opp.
            if periode and len(c.serie) >= trend.MIN_PUNKTER:
                nokkel = trend.serie_av(c.key, periode)
                serier[c.key] = nokkel
                for p, v in c.serie:
                    punkter.append((nokkel, str(p), float(v)))
        lagre_maalinger(punkter)

        historikk = maalinger_for(sorted(set(serier.values())))
        n_trend = 0
        for c in cases:
            linje = trend.beregn(historikk.get(serier.get(c.key, ""), []))
            if linje:
                c.trend = linje
                if linje["tekst"]:
                    n_trend += 1
        if n_trend:
            status.append(
                f"Trend: {n_trend} funn har beveget seg samme vei flere perioder på rad"
            )
    except Exception as exc:  # noqa: BLE001 - en trendlinje skal aldri velte et skann
        status.append(f"[FEIL] Trendlinje: {type(exc).__name__}")

    # Originalitet legges paa scoren, deretter sorteres alt samlet.
    finalize_scores(cases)
    cases.sort(key=lambda c: c.score, reverse=True)

    # ── Hva journalisten faktisk skal se, avgjores FOER KI-en kalles ──────────
    #
    # Denne blokka sto EN GANG etter KI-arbeidsflyten, og det var grunnen til at
    # eieren 26.07.2026 meldte «naar jeg scanner saa kommer det ingenting».
    #
    # Rekkefolgen gjorde to skader samtidig: KI-en brukte hele budsjettet (tre
    # saker per skann) paa de hoyest scorede funnene - som er de faste
    # SSB-probene - og rett etterpaa fjernet uendret-filteret nettopp de sakene
    # fordi tallene sto stille. Kvota var brukt opp paa noe som aldri ble vist,
    # og siden var tom. Naa filtreres det forst, og KI-en jobber bare paa det som
    # faktisk naar skjermen.
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
    ferske = [c for c in cases if sett_verdier.get(c.key) != avtrykk[c.key]]
    gjengangere = [c for c in cases if sett_verdier.get(c.key) == avtrykk[c.key]]

    if ferske:
        cases = ferske
        if gjengangere:
            status.append(
                f"Skjult: {len(gjengangere)} funn med uendret tall siden sist "
                "(samme sak, samme tall - kommer tilbake naar SSB oppdaterer)"
            )
    elif gjengangere:
        # ALDRI en tom skjerm. Har ingenting endret seg, er det et aerlig svar -
        # men et blankt dashboard ser ut som en feil, og journalisten kan ikke
        # skille «kildene sto stille» fra «verktoyet er i stykker». Da viser vi
        # de sterkeste gjengangerne, tydelig merket, i stedet for ingenting.
        for c in gjengangere:
            c.uendret = True
        cases = gjengangere[:UENDRET_VISES]
        status.append(
            f"Ingen tall har endret seg siden forrige skann. Viser de "
            f"{len(cases)} sterkeste funnene paa nytt, merket «uendret» - "
            "SSB publiserer nye tall paa faste datoer (se «Kommer snart»)."
        )

    # Oversettelsen av tallene skjer ETT sted, for ALLE kilder. Eieren
    # 26.07.2026: «saa gjor at alle faktaene som du finner blir oversatt
    # automatisk.» Ligger den her og ikke i hver kollektor, arver en ny kilde
    # den uten aa gjore noe - og ingen framtidig okt kan glemme aa koble den paa.
    for c in cases:
        c.finding = tall.forenkle(c.finding)

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
    #
    # Sorteringen ligger FOER KI-kallet med vilje: analytikeren og redaktoeren
    # rekker bare tre saker, og de tre skal vaere de tre oeverste her.
    RANG = {"data": 0, "hendelse": 0, "grasrot": 1}
    cases.sort(key=lambda c: (RANG.get(c.kind, 1), not c.er_ny, -c.score))
    mark_seen(for_dette_skannet, avtrykk)
    antall_nye = sum(1 for c in cases if c.er_ny)
    status.append(
        f"Nytt siden sist: {antall_nye} av {len(cases)} leads"
        + (" (ingen nye - kildene har ikke endret seg)" if not antall_nye else "")
    )

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
        # Ett kort varsel som svipper inn ved siden av skjermen naar skannet ikke
        # ga noe nytt. Eieren 26.07.2026: «ikke la en beskjed om at soeket ikke
        # ble noe komme nederst der ingen ser det - dropp den helt. Legg heller
        # inn en liten pop-in paa siden av skjermen.»
        #
        # Diagnosen hans er riktig: en statuslinje under tjue kort er en beskjed
        # til ingen. Den som trenger aa vite at soeket kom tomt tilbake, trenger
        # aa vite det MENS han ser paa skjermen. Statuslinjene blir staaende
        # under «Kildestatus» - de er etterretteligheten, ikke beskjeden.
        "varsel": _varsel(cases, temaer, antall_nye),
    }
    save_scan(payload)

    # ## Kvotetak skal ikke bli staaende som «KI-en er AV»
    #
    # Eieren 27.07.2026, med skjermbilde av sitt eget kort: «Staar KI er av,
    # fiks det ogsaa.» Kortet hadde rett — skannet 11:03 traff Groqs minuttak,
    # og alle vinklene ble maler. Men taket gjelder per MINUTT, og to timer
    # senere sto varselet der fortsatt, fordi INGENTING proever igjen av seg
    # selv. Journalisten maa vite at det finnes en «Lag vinkler»-knapp, og at
    # det er kvota og ikke noekkelen som er problemet, for aa komme videre.
    #
    # Derfor: naar skannet feilet PAA KVOTE — ikke paa noekkel, ikke paa nett —
    # fyller vi etter i bakgrunnen naar vinduet har rullet. Samme taalmodige vei
    # som «Lag vinkler», bare uten at noen maa trykke.
    _kanskje_etterfyll(ai_mode, ai_regnskap.get("feil", ""), payload)
    return payload


# Hvor mange saker etterfyllinga tar. Tre er ikke tilfeldig: det er omtrent hva
# ett minuttvindu hos Groq rekker, og det er de tre oeverste journalisten ser
# foerst. Flere ville sprengt taket paa nytt og gjort vondt verre.
ETTERFYLL_SAKER = 3
ETTERFYLL_PAUSE = 70          # sekunder foer foerste forsoek: ett helt minuttvindu


def _kanskje_etterfyll(ai_mode: str, feil: str, payload: dict) -> None:
    """Start etterfylling i bakgrunnen — men bare naar det faktisk hjelper.

    Vilkaarene er strenge med vilje. En bakgrunnstraad som proever igjen paa noe
    som ikke gaar over, brenner kvote uten aa gi noe, og da er kuren verre enn
    sykdommen:

      · `llm-feilet`  — noen kall lyktes ikke i det hele tatt. Var det delvis,
                        har journalisten allerede ekte vinkler paa toppsakene.
      · 429/kvotetak  — feil noekkel eller nede nett gaar ikke over av seg selv.
      · ENABLE_AI     — er KI-en skrudd av, er «av» riktig svar, ikke en feil.
    """
    if not ENABLE_AI or ai_mode != "llm-feilet":
        return
    if "429" not in feil and "kvotetak" not in feil:
        return
    noekler = [c.get("key") for c in payload.get("cases", [])[:ETTERFYLL_SAKER]]
    noekler = [k for k in noekler if k]
    if not noekler:
        return
    threading.Thread(
        target=_etterfyll_vinkler, args=(noekler,), daemon=True,
        name="etterfyll-vinkler",
    ).start()


def _etterfyll_vinkler(noekler: list[str]) -> None:
    """Hent ekte vinkler for de oeverste sakene naar kvotevinduet har rullet.

    Kjoerer utenfor jobbsystemet fordi ingen sitter og ser paa den: den skal
    bare vaere ferdig neste gang journalisten laster sida. Alt den skriver gaar
    gjennom `_SKANN_LAAS`, og den gir seg ved foerste feil som ikke er kvote —
    da er det noe annet i veien, og da skal varselet staa."""
    time.sleep(ETTERFYLL_PAUSE)
    for key in noekler:
        try:
            with _SKANN_LAAS:
                data = load_latest() or {}
                sak = next(
                    (c for c in data.get("cases", []) if c.get("key") == key), None
                )
                if sak is None or sak.get("ai_mode") == "llm":
                    continue
                case = _case_from_dict(sak)
                editor = sak.get("editor") or {}

            angles = journalist_angles(case, editor, taalmodig=True)
            if not angles:
                feil = llm.last_error() or ""
                if "429" in feil or "kvotetak" in feil:
                    time.sleep(ETTERFYLL_PAUSE)
                    continue
                return          # ekte feil — slutt aa mase paa leverandoeren

            with _SKANN_LAAS:
                data = load_latest() or {}
                fersk = next(
                    (c for c in data.get("cases", []) if c.get("key") == key), None
                )
                if fersk is not None:
                    fersk["angles"] = angles
                    fersk["ai_mode"] = "llm"
                    # Varselet paa toppen skal foelge virkeligheten: har noen
                    # saker ekte vinkler naa, er det ikke lenger «KI-en er AV».
                    data["ai_mode"] = "llm-delvis"
                    data["ai_feil"] = (
                        "Skannet traff kvotetaket, men vinklene ble hentet "
                        "etterpaa da kvota var ledig igjen."
                    )
                    save_scan(data)
                storage.ki_lagre(key, angles=angles)
        except Exception as exc:  # noqa: BLE001
            # En bakgrunnstraad som kaster tar med seg ingenting synlig. Logg og
            # gi deg — skannet staar uansett, med maler.
            print(f"[etterfyll] ga opp paa {key}: {type(exc).__name__}: {exc}")
            return


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
            # Fanene for «Kommer snart». Bygges her og ikke i malen fordi
            # gruppering, sortering og telling er logikk - se app/faner.py.
            # Bygges ogsaa naar det ikke finnes et skann: ideene ligger i basen
            # uansett, og «jeg sendte en idé og ingenting skjedde» er nettopp den
            # opplevelsen som gjor at neste idé ikke blir sendt.
            "faner": faner.bygg(
                (data or {}).get("hendelser"),
                (data or {}).get("kommende"),
                ide_liste(),
            ),
            "ideer": ide_liste(),
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


# Fasene bak «Lag vinkler». Den siste er LANG med vilje - eieren 26.07.2026:
# «bare la loadingen bruke litt tid», «aldri la det vaere en feilmelding, men
# heller en treig progress bar».
#
# Prosenten kryper mot toppen av fasen sin og naar den aldri foer fasen er over
# (se app/jobs.py), saa en lang fase gir noeyaktig den treige linja han ber om.
# Teksten ved siden av byttes ut med det som FAKTISK skjer (`jobb.notat`): «Venter
# i koe - 1 sak foran deg» eller «Groq (gratis): kvotetak - venter 40 s».
VINKEL_FASER: list[tuple[int, str, float]] = [
    (4, "Henter kildegrunnlaget", 1.0),
    (10, "Journalisten finner vinkler …", 150.0),
]

# ÉN vinkeljobb om gangen, og resten staar i koe. Eieren 26.07.2026: «hvis han
# trykker paa fler saa stiller de seg bare i koe og venter 1 minutt til det er
# dems tur. Hvis han tar to samtidig saa sier den andre venter i koe.»
#
# Dette er ikke bare pynt - det er selve loesningen paa kvotetaket. To kall
# samtidig deler det samme minuttvinduet paa 12 000 tokens og feller hverandre;
# to kall etter hverandre faar hvert sitt vindu og gaar begge gjennom.
_VINKEL_LAAS = threading.Lock()
_VINKEL_KO_LAAS = threading.Lock()
_VINKEL_I_KO = 0

# Hvor mange runder vi proever foer vi gir oss. Hver runde venter ut et
# minuttvindu, saa dette er rundt fire minutter - og i praksis lykkes det paa
# foerste eller andre runde.
VINKEL_RUNDER = 4


def _vent_paa_tur(jobb: jobs.Jobb) -> None:
    """Ta plass i koen, og hold journalisten oppdatert mens han staar der.

    Vi laaser med timeout i en loekke i stedet for et blokkerende `with`: staar
    han bak noen andre, skal linja fortsatt fortelle ham hvorfor. En stille
    venting er ikke til aa skille fra en henging."""
    global _VINKEL_I_KO
    with _VINKEL_KO_LAAS:
        _VINKEL_I_KO += 1
        foran = _VINKEL_I_KO - 1
    if foran:
        jobb.notat(f"Venter i kø — {foran} sak{'' if foran == 1 else 'er'} foran deg")
    while not _VINKEL_LAAS.acquire(timeout=2.0):
        with _VINKEL_KO_LAAS:
            foran = max(0, _VINKEL_I_KO - 1)
        jobb.notat(
            f"Venter i kø — {foran} sak{'' if foran == 1 else 'er'} foran deg"
            if foran else "Venter på tur …"
        )


def _forlat_koen() -> None:
    global _VINKEL_I_KO
    with _VINKEL_KO_LAAS:
        _VINKEL_I_KO = max(0, _VINKEL_I_KO - 1)
    with contextlib.suppress(RuntimeError):
        _VINKEL_LAAS.release()


def _lag_vinkler(jobb: jobs.Jobb, key: str) -> dict:
    """Vinkler for ÉN sak, paa forespoersel.

    Eieren 26.07.2026, med skjermbilde: «Ingen vinkler. Fiks dette.» Kortet sa
    «journalisten lager forslag for de hoeyest rangerte sakene ved hvert skann» -
    sant, men en blindvei: Groqs minuttak rekker TRE saker, og et skann finner
    atten. Femten kort sto uten en eneste tittel.

    Aa heve taket i skannet er ikke loesningen - da ryker hele skannet paa en
    429, og han faar null i stedet for tre. Men taket gjelder per MINUTT: naar
    han peker paa én sak, er det bare aa vente til vinduet ruller.

    Da han proevde, fikk han «RuntimeError: ... kvotetak (429)», og sa: «Kvotetak,
    finn en loesning. Hvis han trykker paa fler saa stiller de seg bare i koe og
    venter 1 minutt til det er dems tur. Men aldri la det vaere en feilmelding,
    men heller en treig progress bar.»

    Det er noeyaktig det som skjer her:

      1. KOE. Én jobb om gangen (`_vent_paa_tur`). To kall samtidig deler det
         samme minuttvinduet og feller hverandre; to etter hverandre faar hvert
         sitt vindu og gaar begge gjennom. Den som staar bak, faar vite det.
      2. TAALMODIGHET. `taalmodig=True` lar llm-laget vente ut kvoten i stedet
         for aa gi opp, og `si=jobb.notat` skriver ventingen inn i linja.
      3. FLERE RUNDER. Holder ikke ett vindu, tar vi neste. Fire runder er rundt
         fire minutter, og i praksis lykkes det paa den foerste eller andre.

    Laasen om skannfila holdes BARE rundt lesing og skriving. Holdt vi den
    gjennom KI-kallet, ville et fire minutters vinkelkall blokkert «Lag utkast»
    like lenge - to funksjoner som ikke har noe med hverandre aa gjore.
    """
    _vent_paa_tur(jobb)
    try:
        with _SKANN_LAAS:
            data = load_latest()
            if not data:
                raise RuntimeError("Ingen skann å jobbe fra — kjør et søk først.")
            sak = next((c for c in data.get("cases", []) if c.get("key") == key), None)
            if sak is None:
                raise RuntimeError("Fant ikke saken i siste skann. Kjør søk på nytt.")
            case = _case_from_dict(sak)
            editor = sak.get("editor") or {}

        jobb.fase(1)
        angles: list[dict] = []
        for runde in range(1, VINKEL_RUNDER + 1):
            angles = journalist_angles(case, editor, si=jobb.notat, taalmodig=True)
            if angles:
                break
            feil = llm.last_error() or ""
            if not ("429" in feil or "kvotetak" in feil):
                break        # en ekte feil kommer ikke til aa gaa over av seg selv
            if runde < VINKEL_RUNDER:
                jobb.notat(
                    f"Kvoten er full — venter på neste minutt "
                    f"(forsøk {runde + 1} av {VINKEL_RUNDER})"
                )
                time.sleep(20)

        if not angles:
            raise RuntimeError(_vinkelfeil(llm.last_error() or ""))

        # Les paa nytt: skannet kan ha skrevet mens vi ventet i fire minutter.
        with _SKANN_LAAS:
            data = load_latest() or {}
            fersk = next(
                (c for c in data.get("cases", []) if c.get("key") == key), None
            )
            if fersk is not None:
                fersk["angles"] = angles
                fersk["ai_mode"] = "llm"
                save_scan(data)
            # Hurtiglageret uansett: da overlever vinklene selv om saken
            # tilfeldigvis falt ut av skannet mens vi holdt paa, og neste skann
            # slipper aa betale kvote for dem om igjen.
            storage.ki_lagre(key, angles=angles)
        return {"angles": len(angles)}
    finally:
        _forlat_koen()


def _vinkelfeil(raa: str) -> str:
    """Gjor leverandoerens feil om til noe journalisten kan handle paa.

    «RuntimeError: Journalisten leverte ingen vinkler. Groq (gratis): kvotetak
    (429)» stod paa kortet hans 26.07.2026. Det er sant, og det er ubrukelig:
    det sier ikke hva han skal gjore, og «RuntimeError» er et ord fra vaar
    verden, ikke hans."""
    if "429" in raa or "kvotetak" in raa:
        return (
            "KI-en har brukt opp minuttkvoten sin. Vent et minutt og trykk igjen "
            "— skannet du nettopp kjørte tok nesten hele kvoten."
        )
    if "noekkel" in raa or "nokkel" in raa or "ingen KI" in raa:
        return "Ingen KI-nøkkel er satt på serveren, så vinkler kan ikke lages."
    return f"Journalisten leverte ingen vinkler. {raa}".strip()


@app.post("/leads/{key:path}/vinkler")
def be_om_vinkler(key: str, js: str = Form("")):
    """«Lag vinkler» paa et kort som ikke fikk noen under skannet."""
    jobb = jobs.start(VINKEL_FASER, lambda j: _lag_vinkler(j, key))
    if js:
        return JSONResponse({"jobb": jobb.id})
    jobs.vent(jobb, 90)
    return RedirectResponse(url=f"/#sak-{key}", status_code=303)


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


def _med_flagg(url: str, flagg: str) -> str:
    """`/` + `sendt=1` -> `/?sendt=1`, men `/?ym=..` -> `/?ym=..&sendt=1`.

    Naiv strengsammenslaaing ga `/?ym=..?sendt=1` - to spoersmaalstegn, og
    `sendt` ble en del av verdien til `ym` i stedet for et eget parameter."""
    return f"{url}{'&' if '?' in url else '?'}{flagg}"


@app.post("/ideer")
def ny_ide(tekst: str = Form(""), tilbake: str = Form("/")):
    """Mathias skriver en idé, trykker send, og Tobias ser den i fanen.

    Eieren 26.07.2026: «Legg til ideer for Tobias. Legg det helt nederst ... saa
    kan han skrive det, trykker send, og den blir lagret paa en av fanene der det
    staar ideer til Tobias.»

    Ingen validering utover «skriv noe foerst». En idé er ikke et skjema.

    Kvitteringen (`sendt=1`) staar paa selve boksen og ikke bare i fanen: har han
    ikke skannet enda, finnes ikke fanen, og da ville «send» sett ut som at
    ingenting skjedde. En idé som ser ut til aa forsvinne blir ikke skrevet to
    ganger - den blir ikke skrevet i det hele tatt."""
    ok, _grunn = ide_legg_til(tekst)
    return RedirectResponse(
        url=f"{_med_flagg(tilbake, 'sendt=1' if ok else 'tomt=1')}#ideer",
        status_code=303,
    )


@app.post("/ideer/{ide_id}/slett")
def slett_ide(ide_id: int, tilbake: str = Form("/")):
    ide_slett(ide_id)
    return RedirectResponse(url=f"{tilbake}#ideer", status_code=303)


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

    # ── Saker gruppert per MAANED ────────────────────────────────────────────
    # Eieren 26.07.2026, med skjermbilde: «Istedenfor at det staar den samme
    # saken igjen og igjen. Saa kan det heller staa: hvis det er en sak den
    # maaneden, saa staar den saken - dette skal du lage denne maaneden.»
    #
    #     august      gutter med testo
    #     september   jenter med kort haar
    #                 voksne blir mer barnslige
    #
    # Dagpanelene under rutenettet gjentok en sak som gikk fra 27. til 31. paa
    # fem dager. Med fire planlagte saker ble sida flere skjermlengder lang, og
    # man scrollet forbi den samme overskriften om og om igjen i den tro at det
    # var fem ulike saker.
    #
    # Her staar hver sak NOEYAKTIG ÉN gang, under maaneden den skal lages i.
    # Fristen bestemmer maaneden - det er den datoen som styrer arbeidet; en
    # startdato kan flyttes, en frist er en avtale. Uten frist faller den
    # tilbake paa start, og har den ingen av delene staar den under «Uten dato».
    maaneder: dict[str, dict] = {}
    for lead in approved:
        naar = lead.get("_deadline") or lead.get("_start") or ""
        if not naar:
            continue                      # vises under «Uten dato»
        try:
            d = date.fromisoformat(naar)
        except ValueError:
            continue
        n = f"{d.year:04d}-{d.month:02d}"
        bolk = maaneder.setdefault(n, {
            "ym": n,
            "navn": f"{MONTHS_NO[d.month - 1]} {d.year}",
            "er_denne": (d.year, d.month) == (today.year, today.month),
            "saker": [],
        })
        draft = lead.get("draft") or {}
        bolk["saker"].append({
            "key": lead.get("key", ""),
            "tittel": draft.get("title") or lead.get("title", ""),
            "frist": lead.get("_deadline") or "",
            "dag": d.day,
            "stage": lead.get("_stage") or "ide",
            "forfalt": bool(lead.get("_deadline")) and naar < today.isoformat(),
        })

    for bolk in maaneder.values():
        # Innad i maaneden: naermeste frist foerst. Det er rekkefolgen han
        # faktisk jobber i.
        bolk["saker"].sort(key=lambda s: (s["frist"] or "9999", s["tittel"]))
    maanedsliste = [maaneder[k] for k in sorted(maaneder)]

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
            "maanedsliste": maanedsliste,
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
