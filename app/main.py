"""FastAPI-app: dashboard + scan-endepunkt.

Kjor:  uv run uvicorn app.main:app --reload
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import __version__, llm
from app.agents import run_workflow
from app.collectors import collect_all, coverage
from app.config import ENABLE_AI
from app.planner import build_plan
from app.scoring import build_cases, finalize_scores
from app.storage import (
    approve_lead,
    decisions_map,
    list_approved,
    load_latest,
    reject_lead,
    save_scan,
)

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
        "topic_trends": _case_topic_trends(cases),
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


@app.post("/leads/{key:path}/approve")
def approve(key: str):
    lead = _find_lead(key)
    if lead:
        approve_lead(key, lead)
    return RedirectResponse(url="/", status_code=303)


@app.post("/leads/{key:path}/reject")
def reject(key: str):
    reject_lead(key)
    return RedirectResponse(url="/", status_code=303)


@app.get("/godkjente", response_class=HTMLResponse)
def godkjente(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="godkjente.html",
        context={"leads": list_approved(), "version": __version__},
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
