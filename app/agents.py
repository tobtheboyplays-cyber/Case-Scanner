"""Redaksjonell KI-arbeidsflyt: analytiker -> redaktor -> journalist.

VINKLER LAGES KUN AV KI. Eierens beslutning 26.07.2026, og den er riktig: en mal
kan ikke foreslaa en vinkel. Den kan bare omskrive tallet den allerede har faatt,
og resultatet ble tre varianter av «hva betyr dette for Stavanger?». Tre svake
forslag ser ut som et valg uten aa vaere det, og spiser plassen der de ekte skulle
staatt. Uten KI leverer vi tom liste, og UI-et sier hvorfor.

Redaktoerdommen har fortsatt en mekanisk reserve (`_editor_mal`), for den er en
PORT - noe maa avgjore om saken slipper videre naar KI-en ikke svarer. Den er
merket «mal» i UI-et og skal aldri se ut som en redaktoervurdering.
"""

from __future__ import annotations

import json
from collections.abc import Callable

from app import llm, prompts, storage, verify
from app.config import EDITOR_CAP, JOURNALIST_CAP, KI_BUDSJETT_TOKENS
from app.models import Case


# --- Tokenbudsjettet for ETT skann -------------------------------------------
class Budsjett:
    """Hvor mye KI ett skann faar lov til aa bruke.

    Eierens loesning paa 429-en, og den er bedre enn aa vente lenge inne i ett
    skann: gjor mindre per trykk, og la journalisten trykke «Skann igjen» for
    resten. Forutsetningen er at neste skann tar de NESTE sakene - derfor
    lagres hvert ekte KI-svar (storage.ki_lagre), saa koen faktisk toemmer seg.

    Uten budsjett er dette en no-op (`Budsjett(0)` brukes naar det ikke finnes
    noekkel - da er alt maler uansett, og «kø» ville vaert en loegn).
    """

    def __init__(self, tokens: int) -> None:
        self.start = max(0, tokens)
        self.igjen = self.start
        self.i_ko = 0

    @property
    def aktivt(self) -> bool:
        return self.start > 0

    def be_om(self, system: str, user: str, max_tokens: int) -> bool:
        """Er det plass til dette kallet? Trekker fra hvis ja, teller kø hvis nei."""
        if not self.aktivt:
            return True
        if self.igjen <= 0:
            self.i_ko += 1
            return False
        # Foerste kall slipper alltid gjennom selv om anslaget er stoerre enn
        # resten av budsjettet. Et budsjett satt for lavt skal gi ETT kall, ikke
        # et skann helt uten KI - da ville tallet stille slaatt av verktoyet.
        self.igjen -= llm.anslaa_tokens(system, user, max_tokens)
        return True


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
def analyst_pick(cases: list[Case], budsjett: Budsjett | None = None) -> dict[str, dict]:
    """Velg de journalistisk interessante funnene. Returner {key: {score, reason}}."""
    data_cases = [c for c in cases if c.kind == "data"]
    if not data_cases:
        return {}

    payload = [
        {"id": c.key, "finding": c.finding, "topics": c.topics, "geo": c.geo}
        for c in data_cases
    ]
    user = "Funn:\n" + json.dumps(payload, ensure_ascii=False)
    result = None
    if budsjett is None or budsjett.be_om(prompts.ANALYST_SYSTEM, user, 1200):
        result = llm.complete_json(
            prompts.ANALYST_SYSTEM, user, model=llm.MODEL_ANALYST, max_tokens=1200
        )
    # `isinstance`-vakten er ikke pynt: _extract_json kan returnere en LISTE hvis
    # modellen svarer med `[...]`, og da ville `result.get` kastet AttributeError
    # rett gjennom run_workflow og run_scan - som ikke fanger noe - og drept hele
    # skannet. Ingen nye leads, dashbordet staaende paa gammel data.
    if isinstance(result, dict) and isinstance(result.get("picks"), list):
        picks = {}
        for p in result["picks"]:
            if isinstance(p, dict) and p.get("id") and p.get("interesting", True):
                picks[p["id"]] = {"score": p.get("score", 50), "reason": p.get("reason", "")}
        if picks:
            return picks

    # Fallback: velg alle datafunn, begrunnet med storrelsen paa avviket.
    return {
        c.key: {"score": min(int(c.score) * 3, 100), "reason": "Tydelig lokalt avvik i tallene."}
        for c in data_cases
    }


# --- Agent 2: Redaktor -------------------------------------------------------
def editor_judge(case: Case, budsjett: Budsjett | None = None) -> dict:
    """Porten: kan dette baere en sak? Kjoeres FOER journalisten bruker tid."""
    user = (
        f"{kildegrunnlag(case)}\n\n"
        "Vurder dette funnet som mulig sak. Journalisten har ikke begynt enda."
    )
    if budsjett is not None and not budsjett.be_om(prompts.EDITOR_SYSTEM, user, 800):
        # Ikke forsoekt - budsjettet for dette skannet er brukt opp. Merkes «ko»
        # og ikke «mal», fordi de to betyr helt forskjellige ting for
        # journalisten: mal = dette er alt du faar, ko = trykk Skann igjen.
        return {**_editor_mal(case), "mode": "ko"}

    result = llm.complete_json(prompts.EDITOR_SYSTEM, user, model=llm.MODEL_EDITOR, max_tokens=800)
    if isinstance(result, dict) and "is_story" in result:
        # `mode` maa staa SIST. Med `{"mode": "llm", **result}` kunne et modellsvar
        # som inneholdt feltet «mode» overskrive det - og dermed styre baade
        # sakens merking i UI og tellingen av hvor mange kall som lyktes.
        return {**result, "mode": "llm"}
    return _editor_mal(case)


def _editor_mal(case: Case) -> dict:
    """Redaktoerdom uten KI: dekningsstatus + eksisterende vinkel."""
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
def journalist_angles(
    case: Case, editor: dict, budsjett: Budsjett | None = None
) -> list[dict]:
    """Tre KORTE vinkelforslag - ingen artikkel enda.

    Bevisst lat: aa skrive tre fulle artikler for hver sak ved hvert skann brenner
    kvote paa saker som aldri blir aapnet, og gjor skannet tregt. Artikkelen skrives
    av write_draft() naar journalisten faktisk ber om den.

    **Kun ekte KI-vinkler. Ingen maler.** Eierens beslutning 26.07.2026, og den er
    riktig: en mal kan ikke foreslaa en vinkel. Den kan bare omskrive tallet den
    allerede har faatt, og resultatet ble tre varianter av «hva betyr dette for
    Stavanger?». Tre daarlige forslag er verre enn ingen - de ser ut som et valg,
    men er det ikke, og de spiser plassen der de ekte vinklene skulle staatt.
    Uten KI leverer vi tom liste, og UI-et sier hvorfor."""
    user = (
        f"{kildegrunnlag(case)}\n\n"
        f"REDAKTOERENS BESTILLING:\n"
        f"  Arbeidstittel: {editor.get('headline', case.title)}\n"
        f"  Oppdrag: {editor.get('angle', case.angle)}\n"
        f"  Forbehold aa ta hensyn til: {editor.get('forbehold', '-')}\n\n"
        "Foreslaa tre ulike vinkler. Ikke skriv artikkelen."
    )
    if budsjett is not None and not budsjett.be_om(
        prompts.JOURNALIST_ANGLES_SYSTEM, user, 1400
    ):
        return []      # i koe - neste skann tar den

    result = llm.complete_json(
        prompts.JOURNALIST_ANGLES_SYSTEM, user, model=llm.MODEL_ANALYST, max_tokens=1400
    )
    angles = result.get("angles") if isinstance(result, dict) else None
    if isinstance(angles, list):
        clean = _uten_gjengangere(
            [a for a in angles if isinstance(a, dict) and a.get("title")]
        )
        if clean:
            for a in clean:
                a["mode"] = "llm"
            return clean[:3]
    return []          # KI-en leverte ikke - da leverer vi ingenting


def _nokkel(tekst: str) -> str:
    """Grov normalisering, saa to formuleringer av samme sak kjennes igjen."""
    return " ".join(
        "".join(ch for ch in (tekst or "").lower() if ch.isalnum() or ch.isspace()).split()
    )


def _uten_gjengangere(angles: list[dict]) -> list[dict]:
    """Kast vinkler som er samme sak skrevet om igjen.

    Modellen faar beskjed om at de tre skal vaere ulike, men en beskjed er ingen
    garanti. To vinkler som hviler paa NOEYAKTIG samme faktum er én vinkel med to
    titler - da er valget mellom dem falskt. Vi leverer heller to ekte vinkler enn
    tre der den ene er en omskrivning."""
    sett_faktum: set[str] = set()
    sett_tittel: set[str] = set()
    ut: list[dict] = []
    for a in angles:
        faktum = _nokkel(a.get("headline_fact", ""))
        tittel = _nokkel(a.get("title", ""))
        if tittel in sett_tittel or (faktum and faktum in sett_faktum):
            continue
        sett_tittel.add(tittel)
        if faktum:
            sett_faktum.add(faktum)
        ut.append(a)
    return ut


def write_draft(case: Case, editor: dict, angle: dict) -> dict:
    """Skriv ut ÉN valgt vinkel i sin helhet. Kalles paa knappetrykk, ikke ved skann."""
    user = (
        f"{kildegrunnlag(case)}\n\n"
        f"REDAKTOERENS BESTILLING:\n"
        f"  {editor.get('angle', case.angle)}\n\n"
        f"VALGT VINKEL ({angle.get('inngang', '-')}):\n"
        f"  Tittel: {angle.get('title', '')}\n"
        f"  Kjerne: {angle.get('kort', '')}\n\n"
        "Skriv ut denne vinkelen i sin helhet."
    )
    result = llm.complete_json(
        prompts.JOURNALIST_SYSTEM, user, model=llm.MODEL_JOURNALIST, max_tokens=2200
    )
    if isinstance(result, dict) and result.get("body"):
        draft = {**angle, **result, "mode": "llm"}
        # Sourcing er den dominerende feilmodusen (EBU 2025). Hvert tall i teksten
        # spores mekanisk tilbake til kildegrunnlaget; det som ikke lar seg spore
        # flagges for journalisten i stedet for aa gaa stille igjennom.
        draft["usporbare_tall"] = verify.usporbare_tall(
            draft.get("body", ""), kildegrunnlag(case)
        )
        return draft

    # Uten KI: behold vinkelen, men vaer aapen om at teksten er en mal.
    return {
        **angle,
        "mode": "mal",
        "title": angle.get("title") or case.title,
        "ingress": angle.get("kort") or case.finding,
        "body": (
            f"{case.finding}\n\n{angle.get('kort', '')}\n\n"
            f"[Utkast laget uten KI. Fyll ut med sitater og kontekst. "
            f"Tallet er hentet fra {case.data_source or 'SSB'} - se kildelista.]"
        ),
        "checks": angle.get("checks")
        or ["Ring SSB eller kommunen for aarsaken bak tallet", "Finn en case-person"],
        "kilder": angle.get("kilder")
        or [{"navn": case.data_source or "SSB", "hva": "tallet", "url": case.data_url}],
        "image_ideas": angle.get("image_ideas")
        or [{"motiv": "Case-person knyttet til temaet", "bildetekst": "Illustrasjonsfoto"}],
    }


# --- Orkestrering ------------------------------------------------------------
def run_workflow(cases: list[Case], si: Callable[[str], None] | None = None) -> dict:
    """Kjor analytiker -> redaktor -> journalist paa leadene (in-place).

    Returnerer et REGNSKAP, ikke ett ord:
        {"mode": ..., "forsokt": n, "lyktes": n, "feilet": n,
         "gjenbrukt": n, "i_ko": n, "feil": "..."}

    Modus:
      "mal"        -> ingen noekkel, alt fra maler (demo)
      "llm"        -> noekkel finnes og ALLE kall lyktes
      "llm-delvis" -> noen lyktes, noen feilet - de som feilet har maler
      "llm-feilet" -> noekkel finnes, men ingen kall lyktes

    Hvorfor regnskap: tidligere holdt det at ETT kall lyktes for aa returnere
    "llm". Slo kvotetaket inn etter de foerste kallene - som er nettopp det som
    skjer paa et gratis-nivaa - kunne alle seks vinkel-kall feile mens appen
    fortsatt sa «KI: paa», skjulte advarselen og viste en side full av maler som
    om de var journalistens. Det er den farligste feilen verktoyet kan gjore:
    den lyver stille. Naa telles hvert kall.
    """
    has_key = llm.has_llm()
    regnskap = {"forsokt": 0, "lyktes": 0, "feilet": 0, "gjenbrukt": 0, "i_ko": 0}

    # Budsjettet gjelder bare naar det FINNES en noekkel. Uten noekkel er alt
    # maler uansett, og da ville «i kø» vaert en loegn - det staar ingenting i
    # kø, det finnes bare ikke noen KI.
    budsjett = Budsjett(KI_BUDSJETT_TOKENS if has_key else 0)
    hurtiglager = storage.ki_hent([c.key for c in cases]) if has_key else {}

    def tell(fikk_llm: bool) -> None:
        regnskap["forsokt"] += 1
        regnskap["lyktes" if fikk_llm else "feilet"] += 1

    def melde(tekst: str) -> None:
        if si is not None:
            si(tekst)

    picks = analyst_pick(cases, budsjett)
    # Analytikeren telles ogsaa - foer var utfallet av den helt usynlig.
    tell(bool(picks) and llm.last_error() is None)
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
    for nr, c in enumerate(editor_cases, 1):
        lagret = hurtiglager.get(c.key, {})
        if isinstance(lagret.get("editor"), dict):
            # Ekte dom fra et tidligere skann. Gratis - og det er nettopp derfor
            # «trykk Skann igjen» flytter koen framover i stedet for aa betale
            # for de samme topp-sakene om igjen.
            c.editor = {**lagret["editor"], "mode": "llm"}
            c.ai_mode = "llm"
            regnskap["gjenbrukt"] += 1
        else:
            melde(f"Redaktøren vurderer {nr} av {len(editor_cases)}: {c.title[:50]}")
            c.editor = editor_judge(c, budsjett)
            c.ai_mode = c.editor.get("mode", "mal")
            if c.ai_mode == "llm":
                storage.ki_lagre(c.key, editor=c.editor)
                tell(True)
            elif c.ai_mode != "ko":
                tell(False)
        if c.editor.get("is_story"):
            approved.append(c)

    # Journalisten foreslaar KUN vinkler her. Artikkelen skrives naar journalisten ber om
    # den (write_draft), slik at vi ikke bruker kvote paa saker som aldri aapnes.
    for nr, c in enumerate(approved[:JOURNALIST_CAP], 1):
        # Sufficient-context-gate: modeller avstaar ikke selv naar grunnlaget er
        # tynt, saa avgjorelsen tas mekanisk her - foer det brukes tid paa vinkler.
        nok, mangler = verify.nok_grunnlag(c.to_dict())
        if not nok:
            c.editor = {**c.editor, "gate_mangler": mangler}
            continue
        lagret = hurtiglager.get(c.key, {})
        if isinstance(lagret.get("angles"), list) and lagret["angles"]:
            c.angles = lagret["angles"]
            c.ai_mode = "llm"
            regnskap["gjenbrukt"] += 1
            continue

        melde(f"Journalisten lager vinkler {nr} av {min(len(approved), JOURNALIST_CAP)}")
        # Koen telles FOER kallet, saa vi kan skille «ikke forsoekt» fra «forsoekt
        # og feilet». Begge gir tom vinkelliste, men de betyr helt forskjellige
        # ting for journalisten: ko = trykk igjen, feilet = noe er galt.
        ko_for = budsjett.i_ko
        c.angles = journalist_angles(c, c.editor, budsjett)
        if c.angles:
            c.ai_mode = "llm"
            storage.ki_lagre(c.key, angles=c.angles)
            tell(True)
        elif budsjett.i_ko > ko_for:
            c.ai_mode = "ko"
        else:
            # Saken merkes etter det SVAKESTE leddet: uten vinkler er den ikke
            # «KI» selv om redaktoren tilfeldigvis kom gjennom.
            c.ai_mode = "mal"
            tell(False)

    regnskap["i_ko"] = budsjett.i_ko
    if not has_key:
        return {**regnskap, "mode": "mal", "feil": ""}
    if regnskap["feilet"] == 0:
        modus = "llm"
    elif regnskap["lyktes"] + regnskap["gjenbrukt"] == 0:
        modus = "llm-feilet"
    else:
        modus = "llm-delvis"
    return {**regnskap, "mode": modus, "feil": llm.last_error() or ""}
