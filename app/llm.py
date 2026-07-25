"""Tynn KI-klient for agentene, med flere leverandorer og gratis-veier.

Velger leverandor automatisk ut fra hvilken nokkel som ligger i server-miljoet
(foerste treff vinner):

  GROQ_API_KEY       -> Groq        GRATIS, ingen kort, raskt (anbefalt)
  OPENROUTER_API_KEY -> OpenRouter  GRATIS modeller (:free), ingen kort
  ANTHROPIC_API_KEY  -> Claude      betalt API-kreditt (ikke abonnementet)
  GEMINI_API_KEY     -> Gemini      gratis-nivaa, MEN Google blokkerer enkelte
                                    datasenter-IP-er (HTML 403 foer API-et)
  CASE_RADAR_OLLAMA  -> Ollama      helt lokalt paa serveren, ingen nokkel,
                                    ingen ekstern avhengighet
  ingen              -> maler (demo)

Groq, OpenRouter og Ollama snakker alle OpenAI-kompatibel chat, saa de deler én
kodevei. Nokler leses kun fra miljoet, aldri hardkodet. Ved feil settes
last_error() slik at UI kan vise HVORFOR live falt tilbake til mal.
"""

from __future__ import annotations

import json
import os
import re

# --- Claude-modeller (betalt) -----------------------------------------------
MODEL_ANALYST = os.getenv("CASE_RADAR_MODEL_FAST", "claude-haiku-4-5")
MODEL_EDITOR = os.getenv("CASE_RADAR_MODEL_FAST", "claude-haiku-4-5")
MODEL_JOURNALIST = os.getenv("CASE_RADAR_MODEL_WRITER", "claude-sonnet-5")

# --- Gemini (gratis-nivaa) ---------------------------------------------------
GEMINI_MODEL = os.getenv("CASE_RADAR_GEMINI_MODEL", "gemini-3.6-flash")

# --- OpenAI-kompatible leverandorer -----------------------------------------
# (base_url, default-modell). Alle tre bruker samme /chat/completions-format.
GROQ_MODEL = os.getenv("CASE_RADAR_GROQ_MODEL", "llama-3.3-70b-versatile")
OPENROUTER_MODEL = os.getenv(
    "CASE_RADAR_OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free"
)
OLLAMA_MODEL = os.getenv("CASE_RADAR_OLLAMA_MODEL", "llama3.2:3b")
OLLAMA_URL = os.getenv("CASE_RADAR_OLLAMA", "")  # f.eks. http://localhost:11434

# Siste grunn til at et kall ikke ga brukbart svar (for diagnose i UI).
# Ikke en hemmelighet: feilene er ting som "authentication_error" eller
# "quota exceeded" - aldri selve nokkelen.
_LAST_ERROR: str | None = None


def last_error() -> str | None:
    """Kort forklaring paa siste live-feil, eller None om alt gikk bra / ikke provd."""
    return _LAST_ERROR


def provider() -> str | None:
    """Aktiv leverandor ut fra miljoet. Gratis-veiene foerst, saa betalt."""
    if os.getenv("GROQ_API_KEY"):
        return "groq"
    if os.getenv("OPENROUTER_API_KEY"):
        return "openrouter"
    if os.getenv("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.getenv("GEMINI_API_KEY"):
        return "gemini"
    if OLLAMA_URL:
        return "ollama"
    return None


def provider_label() -> str:
    """Menneskevennlig navn for UI."""
    return {
        "groq": "Groq (gratis)",
        "openrouter": "OpenRouter (gratis)",
        "anthropic": "Claude",
        "gemini": "Gemini (gratis)",
        "ollama": "Ollama (lokal)",
    }.get(provider() or "", "demo")


def _openai_compatible() -> tuple[str, str, str] | None:
    """(base_url, modell, noekkel) for den aktive OpenAI-kompatible leverandoren."""
    prov = provider()
    if prov == "groq":
        return "https://api.groq.com/openai/v1", GROQ_MODEL, os.getenv("GROQ_API_KEY", "")
    if prov == "openrouter":
        return (
            "https://openrouter.ai/api/v1",
            OPENROUTER_MODEL,
            os.getenv("OPENROUTER_API_KEY", ""),
        )
    if prov == "ollama":
        return f"{OLLAMA_URL.rstrip('/')}/v1", OLLAMA_MODEL, "ollama"
    return None


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


def _openai_chat(system: str, user: str, *, max_tokens: int) -> str:
    """OpenAI-kompatibel chat - dekker Groq, OpenRouter og Ollama.

    Alle tre eksponerer POST /chat/completions med Bearer-noekkel. response_format
    json_object ber om ren JSON; leverandorer som ikke stotter det ignorerer feltet,
    og _extract_json plukker uansett ut JSON-en fra teksten."""
    import httpx

    conf = _openai_compatible()
    if conf is None:
        raise ValueError("ingen OpenAI-kompatibel leverandor aktiv")
    base, model, key = conf

    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    resp = httpx.post(f"{base}/chat/completions", json=body, headers=headers, timeout=90)

    # Noen modeller/leverandorer avviser response_format - prov en gang til uten.
    if resp.status_code == 400:
        body.pop("response_format", None)
        resp = httpx.post(
            f"{base}/chat/completions", json=body, headers=headers, timeout=90
        )

    resp.raise_for_status()
    data = resp.json()
    choices = data.get("choices") or []
    if not choices:
        raise ValueError(f"{provider_label()} ga ingen svar (mulig tom kvote)")
    return (choices[0].get("message") or {}).get("content") or ""


def _gemini_text(system: str, user: str, *, max_tokens: int) -> str:
    """Gemini via REST (httpx er allerede en avhengighet - ingen ny pakke).

    Google flyttet Gemini til /v1beta/interactions, der modellen ligger i body og
    noekkelen sendes som headeren x-goog-api-key. Det gamle
    /v1beta/models/<model>:generateContent svarer 403 for nyere noekler. Vi proever
    det nye foerst og faller tilbake til det gamle, saa koden taaler at Google
    endrer seg igjen.
    """
    import httpx

    key = os.getenv("GEMINI_API_KEY", "")
    headers = {"x-goog-api-key": key, "Content-Type": "application/json"}

    # --- Nytt API: /v1beta/interactions --------------------------------------
    new_url = "https://generativelanguage.googleapis.com/v1beta/interactions"
    new_body = {
        "model": GEMINI_MODEL,
        "system_instruction": system,
        "input": user,
        "generation_config": {"max_output_tokens": max_tokens},
    }
    resp = httpx.post(new_url, json=new_body, headers=headers, timeout=60)

    if resp.status_code == 200:
        data = resp.json()
        text = _interaction_text(data)
        if text:
            return text

    # --- Gammelt API som reserve ---------------------------------------------
    old_url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent"
    )
    old_body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {
            "maxOutputTokens": max_tokens,
            "responseMimeType": "application/json",
        },
    }
    old = httpx.post(old_url, json=old_body, headers=headers, timeout=60)
    if old.status_code == 200:
        text = _interaction_text(old.json())
        if text:
            return text

    # Ingen av dem ga brukbart svar - la den mest informative feilen tale.
    resp.raise_for_status()
    old.raise_for_status()
    raise ValueError("Gemini ga tomt svar (mulig blokkert innhold eller tom kvote)")


def _interaction_text(data: object) -> str:
    """Trekk ut teksten uansett hvilken svarform Google bruker.

    Doekker output_text (ny convenience), steps/content-blokker (ny raa form) og
    candidates/parts (gammel form)."""
    if not isinstance(data, dict):
        return ""
    direct = data.get("output_text") or data.get("outputText")
    if isinstance(direct, str) and direct.strip():
        return direct
    chunks: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, dict):
            txt = node.get("text")
            if isinstance(txt, str):
                chunks.append(txt)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    for field in ("steps", "output", "candidates"):
        if field in data:
            walk(data[field])
    return "".join(chunks)


def complete_json(system: str, user: str, *, model: str, max_tokens: int = 1500):
    """Kall aktiv leverandor og returner parset JSON (eller None ved feil). Fail-soft.

    Ved feil settes last_error() med en kort, ufarlig grunn slik at appen kan vise
    hvorfor den falt tilbake til mal - i stedet for a se ut som "ingen nokkel".
    """
    global _LAST_ERROR
    prov = provider()
    if prov is None:
        _LAST_ERROR = "ingen KI-nokkel i miljoet (GROQ/OPENROUTER/ANTHROPIC/GEMINI)"
        return None
    try:
        if prov == "anthropic":
            text = _anthropic_text(system, user, model=model, max_tokens=max_tokens)
        elif prov == "gemini":
            text = _gemini_text(system, user, max_tokens=max_tokens)
        else:
            text = _openai_chat(system, user, max_tokens=max_tokens)
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
        return False, "ingen KI-nokkel i miljoet (GROQ/OPENROUTER/ANTHROPIC/GEMINI)"
    try:
        if prov == "anthropic":
            _anthropic_text("", "ping", model=MODEL_JOURNALIST, max_tokens=4)
        elif prov == "gemini":
            _gemini_text("", "ping", max_tokens=4)
        else:
            _openai_chat("Svar med JSON.", "ping", max_tokens=8)
        _LAST_ERROR = None
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        reason = f"{provider_label()}: {type(exc).__name__}: {str(exc)[:160]}"
        _LAST_ERROR = reason
        return False, reason
