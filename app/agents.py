"""Redaksjonell KI-arbeidsflyt: analytiker -> redaktor -> journalist.

Hver agent bruker Claude naar en API-nokkel finnes paa serveren, og faller ellers
tilbake til malbasert tekst (tydelig merket) slik at appen + demoen virker uten nokkel.
"""

from __future__ import annotations

import json

from app import llm, prompts
from app.config import EDITOR_CAP, JOURNALIST_CAP
from app.models import Case


# --- Agent 1: Analytiker -----------------------------------------------------
def analyst_pick(cases: list[Case]) -> dict[str, dict]:
    """Velg de journalistisk interessante funnene. Returner {key: {score, reason}}."""
    data_cases = [c for c in cases if c.kind == "data"]
    if not data_cases:
        return {}

    payload = [
        {"id": c.key, "finding": c.finding, "topics": c.topics, "geo": c.geo}
        for c in data_cases
    ]
    result = llm.complete_json(
        prompts.ANALYST_SYSTEM,
        "Funn:\n" + json.dumps(payload, ensure_ascii=False),
        model=llm.MODEL_ANALYST,
        max_tokens=1200,
    )
    if result and isinstance(result.get("picks"), list):
        picks = {}
        for p in result["picks"]:
            if p.get("id") and p.get("interesting", True):
                picks[p["id"]] = {"score": p.get("score", 50), "reason": p.get("reason", "")}
        if picks:
            return picks

    # Fallback: velg alle datafunn, begrunnet med storrelsen paa avviket.
    return {
        c.key: {"score": min(int(c.score) * 3, 100), "reason": "Tydelig lokalt avvik i tallene."}
        for c in data_cases
    }


# --- Agent 2: Redaktor -------------------------------------------------------
def editor_judge(case: Case) -> dict:
    """Vurder ett funn som mulig sak. Returner redaktor-dict."""
    cov = ", ".join(
        f"{e.get('source', '?')} ({e.get('date', '')})" for e in case.coverage_examples
    ) or "ingen ferske treff funnet"
    user = (
        f"Funn: {case.finding}\n"
        f"Tema: {', '.join(case.topics) or '-'}\n"
        f"Eksisterende mediedekning: {cov}\n"
        f"Dekningsstatus: {case.coverage_status}"
    )
    result = llm.complete_json(prompts.EDITOR_SYSTEM, user, model=llm.MODEL_EDITOR, max_tokens=700)
    if result and "is_story" in result:
        return {"mode": "llm", **result}

    # Fallback-mal: bruk dekningsstatus + eksisterende vinkel.
    novelty = {"green": "fersk", "yellow": "delvis", "red": "dekket"}.get(
        case.coverage_status, "delvis"
    )
    is_story = case.coverage_status in ("green", "yellow")
    return {
        "mode": "mal",
        "is_story": is_story,
        "confidence": 70 if case.coverage_status == "green" else 45,
        "headline": case.title,
        "angle": case.angle,
        "verdict": (
            "Uskrevet lokalt datafunn - god sak." if case.coverage_status == "green"
            else "Delvis dekket - trenger en frisk vinkel." if case.coverage_status == "yellow"
            else "Allerede godt dekket - lav prioritet."
        ),
        "novelty": novelty,
    }


# --- Agent 3: Journalist -----------------------------------------------------
def journalist_draft(case: Case, editor: dict) -> dict:
    """Skriv et proveutkast. Returner draft-dict."""
    user = (
        f"Tittel-forslag: {editor.get('headline', case.title)}\n"
        f"Vinkel: {editor.get('angle', case.angle)}\n"
        f"Datafunn: {case.finding}\n"
        f"Datakilde: {case.data_source}"
    )
    result = llm.complete_json(
        prompts.JOURNALIST_SYSTEM, user, model=llm.MODEL_JOURNALIST, max_tokens=1600
    )
    if result and result.get("body"):
        return {"mode": "llm", **result}

    # Fallback-mal: enkelt, tydelig merket utkast.
    sted = "Stavanger" if case.geo == "lokal" else "Norge"
    return {
        "mode": "mal",
        "title": editor.get("headline", case.title),
        "ingress": f"Nye SSB-tall viser en tydelig endring blant unge i {sted}. {case.finding}",
        "body": (
            f"{case.finding}\n\n"
            f"{editor.get('angle', case.angle)}\n\n"
            f"[Utkast laget uten KI - fyll ut med sitater og kontekst. "
            f"Tallene er hentet fra {case.data_source}.]"
        ),
        "checks": [
            "Ring SSB eller kommunen for aarsak bak tallene",
            "Finn en ung case-person som merker endringen",
            "Sjekk om en lokal ekspert kan kommentere",
        ],
        "image_ideas": [
            {"motiv": f"Ung person i typisk {sted}-miljø knyttet til temaet",
             "bildetekst": "Illustrasjonsfoto – finn en reell case-person."},
            {"motiv": "Enkel grafikk som viser tallutviklingen (kurve)",
             "bildetekst": case.finding[:80]},
        ],
    }


# --- Orkestrering ------------------------------------------------------------
def run_workflow(cases: list[Case]) -> str:
    """Kjor analytiker -> redaktor -> journalist paa leadene (in-place). Returner modus.

    Modus reflekterer HVA SOM FAKTISK SKJEDDE, ikke bare om en nokkel finnes:
      "mal"        -> ingen nokkel, alt fra maler (demo)
      "llm"        -> nokkel finnes OG minst ett ekte Claude-svar kom igjennom
      "llm-feilet" -> nokkel finnes, men alle kall feilet (kvote/nokkel/modell)
    """
    has_key = llm.has_llm()
    mode = "llm" if has_key else "mal"
    llm_ok = False  # ble minst ett ekte Claude-svar produsert?

    picks = analyst_pick(cases)
    for c in cases:
        if c.key in picks:
            c.analyst_reason = picks[c.key].get("reason", "")

    # Redaktor vurderer datadrevne + Schibsted-leads (analytiker-valgte prioritert).
    ranked = sorted(cases, key=lambda c: c.score, reverse=True)
    candidates = [c for c in ranked if c.kind in ("data", "schibsted")]
    editor_cases = (
        [c for c in candidates if c.key in picks] + [c for c in candidates if c.key not in picks]
    )[:EDITOR_CAP] or ranked[:EDITOR_CAP]
    approved = []
    for c in editor_cases:
        c.editor = editor_judge(c)
        c.ai_mode = c.editor.get("mode", mode)
        if c.editor.get("mode") == "llm":
            llm_ok = True
        if c.editor.get("is_story"):
            approved.append(c)

    # Journalist paa redaktor-godkjente.
    for c in approved[:JOURNALIST_CAP]:
        c.draft = journalist_draft(c, c.editor)
        c.ai_mode = c.draft.get("mode", c.ai_mode)
        if c.draft.get("mode") == "llm":
            llm_ok = True

    if not has_key:
        return "mal"
    return "llm" if llm_ok else "llm-feilet"
