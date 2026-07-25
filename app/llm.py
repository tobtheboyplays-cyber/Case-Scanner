"""KI-klient for agentene: flere leverandorer, kvotestyring og aerlig feilrapport.

Leverandorer velges ut fra hvilke noekler som ligger i server-miljoet, i denne
rekkefolgen - og de brukes som en KJEDE, ikke som ett valg:

  GROQ_API_KEY       -> Groq        GRATIS, ingen kort, raskt (anbefalt)
  OPENROUTER_API_KEY -> OpenRouter  GRATIS modeller (:free), ingen kort
  ANTHROPIC_API_KEY  -> Claude      betalt API-kreditt (ikke abonnementet)
  GEMINI_API_KEY     -> Gemini      gratis-nivaa, MEN Google blokkerer enkelte
                                    datasenter-IP-er (HTML 403 foer API-et)
  CASE_RADAR_OLLAMA  -> Ollama      helt lokalt, ingen noekkel, ingen kvote
  ingen              -> maler (demo)

## Hvorfor denne fila ser ut som den gjor

26.07.2026 kom dette fra journalistens telefon midt i et skann:

    Groq (gratis): HTTPStatusError: Client error '429 Too Many Requests'

Noekkelen var riktig. Feilen var strukturell: ett skann fyrte av inntil 15 kall
uten pause, og Groqs gratis-nivaa taaler 12 000 tokens i minuttet
(llama-3.3-70b-versatile, console.groq.com/docs/rate-limits, hentet 26.07.2026).
Hvert vinkel-kall er grovt 3 000-3 500 tokens. Skannet var GARANTERT aa sprenge
taket - det var ikke uflaks.

Tre ting maatte derfor paa plass, og de er kjernen i denne fila:

1. **Kvotestyring** (`_Kvote`) - vi teller tokens i et rullende minuttvindu og
   venter FOER kallet i stedet for aa bli avvist. Anslaget korrigeres mot
   `x-ratelimit-remaining-tokens` fra leverandoren, saa fasit slaar gjetning.
2. **429 er ikke en feil, det er en beskjed om aa vente.** Vi leser `retry-after`
   og proever igjen. Skannet er en bakgrunnsjobb med framdrift, saa ventingen
   koster ingenting - den vises for brukeren via `si`-tilbakekallingen.
3. **Kjede, ikke enkeltvalg.** Er Groq nede eller tom for kvote, gaar kallet
   videre til neste konfigurerte noekkel. Forbehold: OpenRouters gratis-nivaa er
   50 kall i DOGNET uten kreditt (openrouter.ai/docs/api-reference/limits) - det
   er et sikkerhetsnett, ikke en erstatning.

Noekler leses kun fra miljoet, aldri hardkodet. Feilmeldinger inneholder aldri
selve noekkelen - bare ting som "authentication_error" eller "quota exceeded".
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

# --- Claude-modeller (betalt) -----------------------------------------------
MODEL_ANALYST = os.getenv("CASE_RADAR_MODEL_FAST", "claude-haiku-4-5")
MODEL_EDITOR = os.getenv("CASE_RADAR_MODEL_FAST", "claude-haiku-4-5")
MODEL_JOURNALIST = os.getenv("CASE_RADAR_MODEL_WRITER", "claude-sonnet-5")

# --- Gemini (gratis-nivaa) ---------------------------------------------------
GEMINI_MODEL = os.getenv("CASE_RADAR_GEMINI_MODEL", "gemini-3.6-flash")

# --- OpenAI-kompatible leverandorer -----------------------------------------
GROQ_MODEL = os.getenv("CASE_RADAR_GROQ_MODEL", "llama-3.3-70b-versatile")
OPENROUTER_MODEL = os.getenv(
    "CASE_RADAR_OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free"
)
OLLAMA_MODEL = os.getenv("CASE_RADAR_OLLAMA_MODEL", "llama3.2:3b")


def _ollama_url() -> str:
    """Leses ved kall, ikke ved import - saa en endring ikke krever restart."""
    return os.getenv("CASE_RADAR_OLLAMA", "")


@dataclass(frozen=True)
class Leverandor:
    navn: str
    etikett: str
    # Tokens per minutt paa leverandorens GRATIS-nivaa. 0 = ingen kjent grense
    # (Ollama kjorer lokalt; Anthropic er betalt og har helt andre tak).
    tpm: int
    kilde: str


# Grensene er hentet fra leverandorenes egen dokumentasjon 26.07.2026. De er
# konservative med vilje: aa vente et halvt sekund for mye er gratis, aa bli
# avvist koster hele vinkelen.
LEVERANDORER: dict[str, Leverandor] = {
    "groq": Leverandor("groq", "Groq (gratis)", 12_000, "console.groq.com/docs/rate-limits"),
    "openrouter": Leverandor(
        "openrouter", "OpenRouter (gratis)", 0, "openrouter.ai/docs/api-reference/limits"
    ),
    "anthropic": Leverandor("anthropic", "Claude", 0, "betalt API - egne tak"),
    "gemini": Leverandor("gemini", "Gemini (gratis)", 0, "ai.google.dev/pricing"),
    "ollama": Leverandor("ollama", "Ollama (lokal)", 0, "lokal - ingen kvote"),
}

# Hvor mange ganger vi proever samme leverandor foer vi gaar videre i kjeden.
MAKS_FORSOK = 2
# Vi venter aldri lenger enn dette paa én 429, uansett hva retry-after sier.
# Et skann som staar stille i to minutter er ikke et skann.
MAKS_VENT = 45.0


class KvoteSprengt(Exception):
    """429 fra leverandoren. `sekunder` er dens eget forslag til ventetid."""

    def __init__(self, sekunder: float, melding: str) -> None:
        super().__init__(melding)
        self.sekunder = sekunder


# --- Feilmelding per traad ---------------------------------------------------
# Skann og utkast kjorer i hver sin bakgrunnstraad (app/jobs.py). Med en delt
# modulglobal overskrev de hverandres feilmelding, og en vellykket jobb slettet
# beviset for at en annen hadde feilet.
_traad = threading.local()


def last_error() -> str | None:
    """Kort forklaring paa siste live-feil i DENNE traaden, eller None."""
    return getattr(_traad, "feil", None)


def _sett_feil(melding: str | None) -> None:
    _traad.feil = melding


# --- Kvotestyring ------------------------------------------------------------


class _Kvote:
    """Rullende minuttvindu over tokenbruk mot én leverandor.

    Poenget er ikke aa vaere presis, men aa aldri gaa i taket: vi venter litt for
    tidlig heller enn litt for sent. Naar leverandoren forteller oss hvor mye som
    faktisk er igjen, stoler vi paa den framfor vaart eget anslag.
    """

    VINDU = 60.0

    def __init__(self, tpm: int) -> None:
        self.tpm = tpm
        self._laas = threading.Lock()
        self._brukt: list[tuple[float, int]] = []
        self._fasit: int | None = None       # x-ratelimit-remaining-tokens
        self._fasit_tid = 0.0

    def _rydd(self, naa: float) -> None:
        grense = naa - self.VINDU
        self._brukt = [(t, n) for t, n in self._brukt if t > grense]

    def _i_vinduet(self, naa: float) -> int:
        self._rydd(naa)
        return sum(n for _, n in self._brukt)

    def ventetid(self, anslag: int) -> float:
        """Hvor lenge vi maa vente foer `anslag` tokens faar plass. 0 = kjor."""
        if self.tpm <= 0:
            return 0.0
        with self._laas:
            naa = time.monotonic()
            # Fersk fasit fra leverandoren slaar vaart eget regnskap.
            fersk = self._fasit is not None and naa - self._fasit_tid < self.VINDU
            if fersk and self._fasit > anslag:
                return 0.0
            if self._i_vinduet(naa) + anslag <= self.tpm:
                return 0.0
            # Vent til det eldste forbruket faller ut av vinduet.
            eldst = min((t for t, _ in self._brukt), default=naa)
            return max(0.0, eldst + self.VINDU - naa) + 0.5

    def registrer(self, tokens: int) -> None:
        with self._laas:
            self._brukt.append((time.monotonic(), max(0, tokens)))

    def fasit(self, gjenstaende: int | None) -> None:
        if gjenstaende is None:
            return
        with self._laas:
            self._fasit = gjenstaende
            self._fasit_tid = time.monotonic()


_KVOTER: dict[str, _Kvote] = {
    navn: _Kvote(lev.tpm) for navn, lev in LEVERANDORER.items()
}


def _anslaa_tokens(system: str, user: str, max_tokens: int) -> int:
    """Grovt anslag: fire tegn per token, pluss det vi ber om tilbake.

    Presist nok til aa holde seg unna taket, og vi korrigerer mot leverandorens
    egen telling saa snart den svarer."""
    return (len(system) + len(user)) // 4 + max_tokens


def _vent(sekunder: float, si: Callable[[str], None] | None, hvorfor: str) -> None:
    if sekunder <= 0:
        return
    sekunder = min(sekunder, MAKS_VENT)
    if si is not None:
        si(f"{hvorfor} — venter {sekunder:.0f} s")
    time.sleep(sekunder)


# --- Leverandorvalg ----------------------------------------------------------


def leverandorkjede() -> list[str]:
    """Alle konfigurerte leverandorer, best foerst. Kalles ved hvert kall, saa en
    ny noekkel virker uten restart."""
    kjede: list[str] = []
    if os.getenv("GROQ_API_KEY"):
        kjede.append("groq")
    if os.getenv("OPENROUTER_API_KEY"):
        kjede.append("openrouter")
    if os.getenv("ANTHROPIC_API_KEY"):
        kjede.append("anthropic")
    if os.getenv("GEMINI_API_KEY"):
        kjede.append("gemini")
    if _ollama_url():
        kjede.append("ollama")
    return kjede


def provider() -> str | None:
    """Foerstevalget. Beholdt for bakoverkompatibilitet i UI og tester."""
    kjede = leverandorkjede()
    return kjede[0] if kjede else None


def provider_label(navn: str | None = None) -> str:
    """Menneskevennlig navn for UI."""
    valgt = navn or provider()
    lev = LEVERANDORER.get(valgt or "")
    return lev.etikett if lev else "demo"


def has_llm() -> bool:
    return bool(leverandorkjede())


def _openai_konfig(navn: str) -> tuple[str, str, str] | None:
    """(base_url, modell, noekkel) for en OpenAI-kompatibel leverandor."""
    if navn == "groq":
        return "https://api.groq.com/openai/v1", GROQ_MODEL, os.getenv("GROQ_API_KEY", "")
    if navn == "openrouter":
        return (
            "https://openrouter.ai/api/v1",
            OPENROUTER_MODEL,
            os.getenv("OPENROUTER_API_KEY", ""),
        )
    if navn == "ollama":
        return f"{_ollama_url().rstrip('/')}/v1", OLLAMA_MODEL, "ollama"
    return None


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


# --- De tre kodeveiene -------------------------------------------------------


def _anthropic_text(system: str, user: str, *, model: str, max_tokens: int) -> str:
    try:
        import anthropic
    except ModuleNotFoundError as exc:  # pakken er en valgfri avhengighet
        raise RuntimeError(
            "anthropic-pakken mangler - installer med: pip install '.[ai]'"
        ) from exc

    client = anthropic.Anthropic()
    resp = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return "".join(b.text for b in resp.content if b.type == "text")


def _retry_after(resp) -> float:
    """Leverandorens eget forslag til ventetid. Groq sender `retry-after` kun ved
    429; teksten inneholder ofte «Please try again in 7.2s» som reserve."""
    raa = resp.headers.get("retry-after") or resp.headers.get("Retry-After")
    if raa:
        try:
            return float(raa)
        except ValueError:
            pass
    m = re.search(r"try again in ([\d.]+)\s*s", resp.text or "", re.I)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass
    return 10.0


def _gjenstaende_tokens(resp) -> int | None:
    raa = resp.headers.get("x-ratelimit-remaining-tokens")
    if raa is None:
        return None
    try:
        return int(float(raa))
    except ValueError:
        return None


def _openai_chat(navn: str, system: str, user: str, *, max_tokens: int) -> str:
    """OpenAI-kompatibel chat - dekker Groq, OpenRouter og Ollama.

    429 kastes som KvoteSprengt med leverandorens egen ventetid, slik at den kan
    behandles som «vent litt» i stedet for aa bli slaatt sammen med feil noekkel
    og ukjent modell."""
    import httpx

    konf = _openai_konfig(navn)
    if konf is None:
        raise ValueError(f"{navn} er ikke en OpenAI-kompatibel leverandor")
    base, model, key = konf

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

    _KVOTER[navn].fasit(_gjenstaende_tokens(resp))

    if resp.status_code == 429:
        raise KvoteSprengt(
            _retry_after(resp), f"{provider_label(navn)}: kvotetak naadd (429)"
        )

    resp.raise_for_status()
    data = resp.json()
    choices = data.get("choices") or []
    if not choices:
        raise ValueError(f"{provider_label(navn)} ga ingen svar (mulig tom kvote)")
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

    new_url = "https://generativelanguage.googleapis.com/v1beta/interactions"
    new_body = {
        "model": GEMINI_MODEL,
        "system_instruction": system,
        "input": user,
        "generation_config": {"max_output_tokens": max_tokens},
    }
    resp = httpx.post(new_url, json=new_body, headers=headers, timeout=60)
    if resp.status_code == 429:
        raise KvoteSprengt(_retry_after(resp), "Gemini: kvotetak naadd (429)")

    if resp.status_code == 200:
        text = _interaction_text(resp.json())
        if text:
            return text

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
    if old.status_code == 429:
        raise KvoteSprengt(_retry_after(old), "Gemini: kvotetak naadd (429)")
    if old.status_code == 200:
        text = _interaction_text(old.json())
        if text:
            return text

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


def _ett_kall(navn: str, system: str, user: str, *, model: str, max_tokens: int) -> str:
    if navn == "anthropic":
        return _anthropic_text(system, user, model=model, max_tokens=max_tokens)
    if navn == "gemini":
        return _gemini_text(system, user, max_tokens=max_tokens)
    return _openai_chat(navn, system, user, max_tokens=max_tokens)


# --- Hovedinngangen ----------------------------------------------------------


def complete_json(
    system: str,
    user: str,
    *,
    model: str,
    max_tokens: int = 1500,
    si: Callable[[str], None] | None = None,
):
    """Kall KI-en og returner parset JSON, eller None om ingen leverandor klarte det.

    `si` er en valgfri tilbakekalling som faar én linje naar vi venter paa kvote
    eller bytter leverandor - saa journalisten ser at noe skjer i stedet for at
    skannet bare staar stille.

    Fail-soft: returnerer None i stedet for aa kaste, og setter last_error() med
    en kort, ufarlig grunn.
    """
    kjede = leverandorkjede()
    if not kjede:
        _sett_feil("ingen KI-nokkel i miljoet (GROQ/OPENROUTER/ANTHROPIC/GEMINI)")
        return None

    anslag = _anslaa_tokens(system, user, max_tokens)
    siste_feil = ""

    for i, navn in enumerate(kjede):
        if i > 0 and si is not None:
            si(f"Prøver {provider_label(navn)} i stedet")

        for forsok in range(1, MAKS_FORSOK + 1):
            # Vent heller enn aa bli avvist.
            _vent(
                _KVOTER[navn].ventetid(anslag),
                si,
                f"{provider_label(navn)}: nær kvotetaket",
            )
            try:
                text = _ett_kall(navn, system, user, model=model, max_tokens=max_tokens)
            except KvoteSprengt as exc:
                siste_feil = f"{provider_label(navn)}: kvotetak (429)"
                _KVOTER[navn].registrer(anslag)
                if forsok < MAKS_FORSOK:
                    _vent(exc.sekunder, si, f"{provider_label(navn)}: kvotetak")
                    continue
                break  # gi opp denne leverandoren, prov neste i kjeden
            except Exception as exc:  # noqa: BLE001 - nettverk/noekkel/modell
                siste_feil = f"{provider_label(navn)}: {type(exc).__name__}: {str(exc)[:120]}"
                break  # ikke retry paa feil noekkel eller ukjent modell

            _KVOTER[navn].registrer(anslag)
            parsed = _extract_json(text)
            if parsed is None:
                siste_feil = f"{provider_label(navn)} svarte ikke gyldig JSON"
                break
            _sett_feil(None)
            return parsed

    _sett_feil(siste_feil or "ukjent feil i KI-kallet")
    return None


def check_live() -> tuple[bool, str]:
    """Ett bittelite ekte kall for aa bekrefte at live faktisk virker.

    Returnerer (True, "ok") hvis en leverandor i kjeden svarer, ellers
    (False, kort-grunn)."""
    kjede = leverandorkjede()
    if not kjede:
        return False, "ingen KI-nokkel i miljoet (GROQ/OPENROUTER/ANTHROPIC/GEMINI)"
    siste = ""
    for navn in kjede:
        try:
            if navn == "anthropic":
                _anthropic_text("", "ping", model=MODEL_JOURNALIST, max_tokens=4)
            elif navn == "gemini":
                _gemini_text("", "ping", max_tokens=4)
            else:
                _openai_chat(navn, "Svar med JSON.", "ping", max_tokens=8)
        except Exception as exc:  # noqa: BLE001
            siste = f"{provider_label(navn)}: {type(exc).__name__}: {str(exc)[:120]}"
            continue
        _sett_feil(None)
        return True, f"ok ({provider_label(navn)})"
    _sett_feil(siste)
    return False, siste
