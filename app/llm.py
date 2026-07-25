"""Tynn KI-klient for agentene, med to leverandorer og gratis-vei.

Velger leverandor automatisk ut fra hvilken nokkel som ligger i server-miljoet:
  - ANTHROPIC_API_KEY  -> Claude (betalt API-kreditt, ikke abonnement)
  - GEMINI_API_KEY     -> Google Gemini (GRATIS-nivaa, ingen kort)
  - ingen nokkel       -> maler (demo)

Nokler leses kun fra miljoet, aldri hardkodet. Ved feil settes last_error() slik at
UI kan vise HVORFOR live falt tilbake til mal (feil nokkel, tom kvote, ukjent modell,
ugyldig svar) i stedet for a tie stille.
"""

from __future__ import annotations

import json
import os
import re

# --- Claude-modeller (betalt) -----------------------------------------------
MODEL_ANALYST = os.getenv("CASE_RADAR_MODEL_FAST", "claude-haiku-4-5")
MODEL_EDITOR = os.getenv("CASE_RADAR_MODEL_FAST", "claude-haiku-4-5")
MODEL_JOURNALIST = os.getenv("CASE_RADAR_MODEL_WRITER", "claude-sonnet-5")

# --- Gemini-modell (gratis-nivaa) -------------------------------------------
# gemini-2.0-flash ligger paa gratis-nivaaet (rimelige daglige grenser).
GEMINI_MODEL = os.getenv("CASE_RADAR_GEMINI_MODEL", "gemini-2.0-flash")

# Siste grunn til at et kall ikke ga brukbart svar (for diagnose i UI).
# Ikke en hemmelighet: feilene er ting som "authentication_error" eller
# "quota exceeded" - aldri selve nokkelen.
_LAST_ERROR: str | None = None


def last_error() -> str | None:
    """Kort forklaring paa siste live-feil, eller None om alt gikk bra / ikke provd."""
    return _LAST_ERROR


def provider() -> str | None:
    """Hvilken leverandor er aktiv ut fra miljoet: 'anthropic', 'gemini' eller None.

    Claude foretrekkes hvis begge nokler finnes (eksplisitt betalt valg)."""
    if os.getenv("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.getenv("GEMINI_API_KEY"):
        return "gemini"
    return None


def provider_label() -> str:
    """Menneskevennlig navn for UI."""
    return {"anthropic": "Claude", "gemini": "Gemini (gratis)"}.get(provider() or "", "demo")


def has_llm() -> bool:
    return provider() is not None


def _extract_json(text: str):
    """Robust JSON-parsing: prov hele strengen, ellers forste {...} eller [...]."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"(\{.*\}|\[.*\])", text, re.S)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            return None
    return None


def _anthropic_text(system: str, user: str, *, model: str, max_tokens: int) -> str:
    import anthropic  # kun her; case-radar har ingen import-grense

    client = anthropic.Anthropic()
    resp = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return "".join(b.text for b in resp.content if b.type == "text")


def _gemini_text(system: str, user: str, *, max_tokens: int) -> str:
    """Gemini via REST (httpx er allerede en avhengighet - ingen ny pakke).

    responseMimeType=application/json ber Gemini svare med ren JSON, som passer
    agentene. Gratis-nivaaet krever bare en AI-Studio-nokkel (ingen kort)."""
    import httpx

    key = os.getenv("GEMINI_API_KEY", "")
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent?key={key}"
    )
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {
            "maxOutputTokens": max_tokens,
            "responseMimeType": "application/json",
        },
    }
    resp = httpx.post(url, json=body, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    candidates = data.get("candidates") or []
    if not candidates:
        raise ValueError("Gemini ga ingen kandidater (mulig blokkert/tom kvote)")
    parts = candidates[0].get("content", {}).get("parts", [])
    return "".join(p.get("text", "") for p in parts)


def complete_json(system: str, user: str, *, model: str, max_tokens: int = 1500):
    """Kall aktiv leverandor og returner parset JSON (eller None ved feil). Fail-soft.

    Ved feil settes last_error() med en kort, ufarlig grunn slik at appen kan vise
    hvorfor den falt tilbake til mal - i stedet for a se ut som "ingen nokkel".
    """
    global _LAST_ERROR
    prov = provider()
    if prov is None:
        _LAST_ERROR = "ingen ANTHROPIC_API_KEY eller GEMINI_API_KEY i miljoet"
        return None
    try:
        if prov == "anthropic":
            text = _anthropic_text(system, user, model=model, max_tokens=max_tokens)
        else:
            text = _gemini_text(system, user, max_tokens=max_tokens)
        parsed = _extract_json(text)
        if parsed is None:
            _LAST_ERROR = f"{provider_label()} svarte ikke gyldig JSON"
            return None
        _LAST_ERROR = None
        return parsed
    except Exception as exc:  # noqa: BLE001 - fail-soft (nettverk/kvote/nokkel/modell)
        _LAST_ERROR = f"{provider_label()}: {type(exc).__name__}: {str(exc)[:160]}"
        return None


def check_live() -> tuple[bool, str]:
    """Ett bittelite ekte kall for a bekrefte at live faktisk virker.

    Returnerer (True, "ok") hvis leverandoren svarer, ellers (False, kort-grunn).
    Gir et aerlig live/demo-signal i UI uten a gjette.
    """
    global _LAST_ERROR
    prov = provider()
    if prov is None:
        return False, "ingen ANTHROPIC_API_KEY eller GEMINI_API_KEY i miljoet"
    try:
        if prov == "anthropic":
            _anthropic_text("", "ping", model=MODEL_JOURNALIST, max_tokens=4)
        else:
            _gemini_text("", "ping", max_tokens=4)
        _LAST_ERROR = None
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        reason = f"{provider_label()}: {type(exc).__name__}: {str(exc)[:160]}"
        _LAST_ERROR = reason
        return False, reason
