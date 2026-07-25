"""FastAPI-app: dashboard + scan-endepunkt.

Kjor:  uv run uvicorn app.main:app --reload
"""

from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import __version__, llm, verify
from app.agents import run_workflow, write_draft
from app.collectors import collect_all, coverage, ssb_kalender
from app.config import ENABLE_AI
from app.models import Case
from app.planner import build_plan
from app.scoring import build_cases, finalize_scores
from app.storage import (
    STAGE_LABELS,
    mark_seen,
    seen_map,
    STAGES,
    calendar_month,
    set_plan,
    approve_lead,
    decisions_map,
    list_approved,
    load_latest,
    reject_lead,
    save_scan,
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


def run_scan() -> dict:
    """Hent kilder, bygg caser + plan, lagre og returner resultatet."""
    signals, ssb_cases, status = collect_all()

    # Grasrot-leads (Trends/Reddit) klynges; SSB-leads er ferdige.
    grassroots = build_cases(signals)  # tagger signals med geo/tema in-place
    for c in grassroots:
        if not c.coverage_query:
            c.coverage_query = c.title

    cases = ssb_cases + grassroots

    # Originalitetssjekk: har noen allerede skrevet om dette?
    n_green = 0
    for c in cases:
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
    if ENABLE_AI:
        ai_mode = run_workflow(cases)
        if ai_mode == "llm":
            status.append(f"KI-arbeidsflyt: ekte KI ({llm.provider_label()}) ✓")
        elif ai_mode == "llm-feilet":
            # Nokkel finnes, men kallet feilet - vis HVORFOR (feil nokkel, tom kvote,
            # ukjent modell ...) i stedet for a se ut som demo uten grunn.
            status.append(f"KI-arbeidsflyt: nokkel finnes, men live feilet - {llm.last_error()}")
        else:
            status.append("KI-arbeidsflyt: demo-modus (maler, ingen nokkel)")

    # Forsprang: hva SSB slipper de neste ukene. Egen try - en dod feed skal aldri
    # velte et skann.
    try:
        kommende, kal_status = ssb_kalender.collect()
        status.extend(kal_status)
    except Exception as exc:  # noqa: BLE001
        kommende, _ = [], status.append(f"[FEIL] SSB-kalender: {exc}")

    # Nytt siden sist: samme kilder gir de samme funnene om igjen. Vi markerer hva
    # som ikke er sett foer, skjuler det Mathias allerede har forkastet, og loefter
    # det nye oeverst - saa et nytt soek faktisk gir noe nytt.
    for_dette_skannet = [c.key for c in cases]
    tidligere = seen_map()
    beslutninger = decisions_map()
    cases = [c for c in cases if beslutninger.get(c.key) != "rejected"]
    for c in cases:
        c.er_ny = c.key not in tidligere
    cases.sort(key=lambda c: (not c.er_ny, -c.score))
    mark_seen(for_dette_skannet)
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
        "ai_mode": ai_mode,
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
def dashboard(request: Request):
    data = load_latest()
    scanned_at = None
    if data and data.get("created_at"):
        scanned_at = _human_time(data["created_at"])
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "data": data,
            "scanned_at": scanned_at,
            "version": __version__,
            "decisions": decisions_map(),
            "INNGANG_IKON": INNGANG_IKON,
            "VINKEL_NAVN": VINKEL_NAVN,
            "approved_count": len(list_approved()),
        },
    )


@app.post("/scan")
def scan():
    run_scan()
    return RedirectResponse(url="/", status_code=303)


def _find_lead(key: str) -> dict | None:
    data = load_latest()
    if not data:
        return None
    return next((c for c in data.get("cases", []) if c.get("key") == key), None)


@app.post("/leads/{key:path}/utkast")
def be_om_utkast(key: str, vinkel: int = Form(0)):
    """Skriv ut ÉN valgt vinkel. Kalles paa knappetrykk - ikke ved skann.

    Resultatet lagres tilbake i siste skann slik at utkastet ikke maa skrives paa
    nytt hvis siden lastes om."""
    data = load_latest()
    if not data:
        return RedirectResponse(url="/", status_code=303)
    for c in data.get("cases", []):
        if c.get("key") != key:
            continue
        angles = c.get("angles") or []
        if 0 <= vinkel < len(angles):
            case = _case_from_dict(c)
            angles[vinkel] = write_draft(case, c.get("editor") or {}, angles[vinkel])
            c["angles"] = angles
            save_scan({k: v for k, v in data.items() if k != "created_at"})
        break
    return RedirectResponse(url=f"/#sak-{key}", status_code=303)


def _case_from_dict(d: dict) -> Case:
    """Minimal Case for aa bygge kildegrunnlaget - kun feltene agenten bruker."""
    return Case(
        key=d.get("key", ""), title=d.get("title", ""), score=d.get("score", 0) or 0,
        geo=d.get("geo", "nasjonal"), topics=d.get("topics") or [],
        angle=d.get("angle", ""), why=d.get("why", ""), signals=[],
        created_at=datetime.now(tz=timezone.utc), kind=d.get("kind", "data"),
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
    tilbake: str = Form("/godkjente"),
):
    """Endre start, deadline og/eller stadium paa en sak som alt er godkjent."""
    set_plan(key, start_date=start_date, deadline=deadline, stage=stage or None)
    return RedirectResponse(url=tilbake or "/godkjente", status_code=303)


@app.post("/leads/{key:path}/reject")
def reject(key: str):
    reject_lead(key)
    return RedirectResponse(url="/", status_code=303)


@app.get("/godkjente", response_class=HTMLResponse)
def godkjente(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="godkjente.html",
        context={
            "leads": [
                {**x, "_prosessnotat": verify.prosessnotat(
                    x, leverandor=llm.provider_label(), godkjent_av="Redaksjonen")}
                for x in list_approved()
            ],
            "version": __version__,
        },
    )


@app.get("/kalender", response_class=HTMLResponse)
def kalender(request: Request, ym: str = ""):
    """Redaksjonell kalender: maanedsrutenett med planlagte saker.

    Ingen Google-innlogging, ingen oppsett - den bygger paa saker Mathias selv har
    godkjent. Saker uten dato vises som "uplanlagt" slik at de ikke forsvinner."""
    today = date.today()
    try:
        year, month = (int(x) for x in ym.split("-", 1)) if ym else (today.year, today.month)
        date(year, month, 1)  # kaster paa tull som 2026-13
    except (ValueError, TypeError):
        year, month = today.year, today.month

    by_day = calendar_month(year, month)
    approved = list_approved()
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


def _human_time(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso).astimezone(timezone.utc)
        return dt.strftime("%d.%m.%Y %H:%M UTC")
    except (ValueError, TypeError):
        return iso
