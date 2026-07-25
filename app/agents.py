"""Redaksjonell KI-arbeidsflyt: analytiker -> redaktor -> journalist.

Hver agent bruker Claude naar en API-nokkel finnes paa serveren, og faller ellers
tilbake til malbasert tekst (tydelig merket) slik at appen + demoen virker uten nokkel.
"""

from __future__ import annotations

import json

from app import llm, prompts
from app.config import EDITOR_CAP, JOURNALIST_CAP
from app.models import Case


# --- Ankeret: kildegrunnlaget agentene faar -----------------------------------
def kildegrunnlag(case: Case) -> str:
    """Alt agenten har lov til aa bygge paa, som én lesbar blokk.

    Dette er hele verdensbildet til modellen. Alt som ikke staar her, skal den
    behandle som ukjent - ikke fylle inn selv. Ekte lenker tas med slik at bade
    modellen og journalisten kan spore tallet tilbake til kilden."""
    lines = ["KILDEGRUNNLAG", ""]

    lines.append("TALLET:")
    lines.append(f"  {case.finding or case.title}")
    if case.metric_value:
        lines.append(f"  Verdi: {case.metric_value}" + (f" ({case.metric_period})" if case.metric_period else ""))
    if case.data_source:
        lines.append(f"  Datakilde: {case.data_source}")
    if case.data_url:
        lines.append(f"  SSB-LENKE: {case.data_url}")

    lines.append("")
    lines.append("KONTEKST:")
    lines.append(f"  Geografi: {'Stavanger/Rogaland' if case.geo == 'lokal' else 'nasjonal'}")
    lines.append(f"  Tema: {', '.join(case.topics) or 'ikke tagget'}")

    lines.append("")
    lines.append("DEKNING (hva andre allerede har skrevet om temaet):")
    if case.coverage_examples:
        for e in case.coverage_examples:
            src = e.get("source") or "ukjent kilde"
            date = e.get("date") or ""
            title = e.get("title") or ""
            url = e.get("url") or ""
            lines.append(f"  - «{title}» - {src} {date}".rstrip())
            if url:
                lines.append(f"    {url}")
        lines.append(f"  Dekningsstatus: {case.coverage_status} (gronn=uskrevet, gul=delvis, rod=godt dekket)")
    else:
        lines.append("  Ingen ferske treff funnet - temaet ser uskrevet ut.")

    # Grasrot-saker har egne signaler med ekte lenker.
    if case.signals:
        lines.append("")
        lines.append("SIGNALER (hva folk snakker om):")
        for s in case.signals[:5]:
            lines.append(f"  - «{s.title}» - {s.source}")
            if getattr(s, "url", ""):
                lines.append(f"    {s.url}")

    return "\n".join(lines)


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
    """Porten: kan dette baere en sak? Kjoeres FOER journalisten bruker tid."""
    user = (
        f"{kildegrunnlag(case)}\n\n"
        "Vurder dette funnet som mulig sak. Journalisten har ikke begynt enda."
    )
    result = llm.complete_json(prompts.EDITOR_SYSTEM, user, model=llm.MODEL_EDITOR, max_tokens=800)
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
        "forbehold": "Vurdert uten KI - sjekk tallet mot SSB-lenken selv.",
        "novelty": novelty,
    }


# --- Agent 3: Journalist -----------------------------------------------------
def journalist_angles(case: Case, editor: dict) -> list[dict]:
    """Tre ULIKE vinkler, hver som en ferdig pakke: artikkel + bilder + kilder.

    Kjoeres KUN naar redaktoren har sagt ja. Returnerer alltid tre elementer -
    faller tilbake til maler hvis KI-en ikke svarer, slik at UI-et aldri staar tomt."""
    user = (
        f"{kildegrunnlag(case)}\n\n"
        f"REDAKTOERENS BESTILLING:\n"
        f"  Arbeidstittel: {editor.get('headline', case.title)}\n"
        f"  Oppdrag: {editor.get('angle', case.angle)}\n"
        f"  Forbehold aa ta hensyn til: {editor.get('forbehold', '-')}\n\n"
        "Lever tre ulike vinkler, hver med full artikkeltekst, bildeforslag og kilder."
    )
    result = llm.complete_json(
        prompts.JOURNALIST_SYSTEM, user, model=llm.MODEL_JOURNALIST, max_tokens=4000
    )
    angles = result.get("angles") if isinstance(result, dict) else None
    if isinstance(angles, list):
        clean = [a for a in angles if isinstance(a, dict) and a.get("body")]
        if clean:
            for a in clean:
                a["mode"] = "llm"
            return clean[:3]

    return _fallback_angles(case, editor)


def _fallback_angles(case: Case, editor: dict) -> list[dict]:
    """Malbaserte vinkler naar KI-en ikke er tilgjengelig. Tydelig merket."""
    sted = "Stavanger" if case.geo == "lokal" else "Norge"
    kilder = [{"navn": case.data_source or "SSB", "hva": "tallet i saken", "url": case.data_url}]
    for e in case.coverage_examples[:2]:
        kilder.append(
            {"navn": e.get("source", ""), "hva": e.get("title", ""), "url": e.get("url", "")}
        )
    maler = [
        ("menneske", f"Hvem merker dette i {sted}?",
         "Finn én person som kjenner endringen paa kroppen, og la tallet forklare hvorfor."),
        ("konsekvens", f"Hva betyr tallet i praksis for {sted}?",
         "Regn om endringen til kroner, koe eller tid - noe leseren kjenner igjen."),
        ("aarsak", f"Hvorfor skjer dette akkurat i {sted}?",
         "Ring kommunen og en fagperson: hva forklarer avviket fra landet?"),
    ]
    out = []
    for inngang, tittel, vinkel in maler:
        out.append(
            {
                "mode": "mal",
                "inngang": inngang,
                "styrke": 50,
                "risiko": "Laget uten KI - vurder selv om vinkelen baerer.",
                "title": tittel,
                "ingress": f"Nye tall fra {case.data_source or 'SSB'} viser: {case.finding}",
                "body": (
                    f"{case.finding}\n\n{vinkel}\n\n"
                    f"[Utkast laget uten KI. Fyll ut med sitater og kontekst. "
                    f"Tallet er hentet fra {case.data_source or 'SSB'} - se kildelista.]"
                ),
                "checks": [
                    "Ring SSB eller kommunen for aarsaken bak tallet",
                    f"Finn en case-person i {sted} som merker endringen",
                    "Sjekk om en lokal fagperson kan kommentere",
                ],
                "kilder": kilder,
                "image_ideas": [
                    {"motiv": f"Case-person i {sted} knyttet til temaet",
                     "bildetekst": "Illustrasjonsfoto - finn en reell case-person."},
                    {"motiv": "Enkel grafikk som viser tallutviklingen",
                     "bildetekst": case.finding[:80]},
                ],
            }
        )
    return out


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

    # Journalisten jobber KUN paa det redaktoren har godkjent.
    for c in approved[:JOURNALIST_CAP]:
        c.angles = journalist_angles(c, c.editor)
        if c.angles:
            c.draft = c.angles[0]  # bakoverkompatibelt for eldre visninger
            c.ai_mode = c.angles[0].get("mode", c.ai_mode)
            if any(a.get("mode") == "llm" for a in c.angles):
                llm_ok = True

    if not has_key:
        return "mal"
    return "llm" if llm_ok else "llm-feilet"
