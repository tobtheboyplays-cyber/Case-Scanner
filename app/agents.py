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
from app.config import (
    EDITOR_CAP,
    JOURNALIST_CAP,
    KI_BUDSJETT_TOKENS,
    KI_RESERVE_JOURNALIST,
)
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

    def __init__(self, tokens: int, reservert: int = 0) -> None:
        self.start = max(0, tokens)
        self.igjen = self.start
        self.i_ko = 0
        # Holdt av til journalisten. Se `be_om(..., er_journalisten=True)`.
        #
        # Aldri mer enn HALVE budsjettet: en reserve stoerre enn potten ville satt
        # analytikeren og redaktoeren i koe fra foerste kall, og da er det ikke
        # lenger en prioritering - det er en avslaatt KI. Settes budsjettet lavt i
        # en miljoevariabel, skal reserven krympe med det.
        self.reservert = min(max(0, reservert), self.start // 2)

    @property
    def aktivt(self) -> bool:
        return self.start > 0

    def be_om(
        self, system: str, user: str, max_tokens: int, *, er_journalisten: bool = False
    ) -> bool:
        """Er det plass til dette kallet? Trekker fra hvis ja, teller kø hvis nei.

        `er_journalisten` gir tilgang til reserven. Uten den kunne analytikeren og
        redaktoeren spise hele budsjettet foer vinklene skulle lages - og det var
        noeyaktig det som skjedde: eieren fikk saker uten en eneste forslagstittel.
        Vinklene er hele poenget med verktoyet; rangeringen er det ikke.
        """
        if not self.aktivt:
            return True
        gulv = 0 if er_journalisten else self.reservert
        if self.igjen - gulv <= 0:
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

    # TREND foer dekning: dette er den sterkeste vinkelen paa siden av selve
    # tallet. «Falt 17 %» er en notis; «tredje kvartal paa rad» er en sak. Én
    # linje, fordi den skal koste nesten ingenting av minuttkvoten.
    if case.trend and case.trend.get("tekst"):
        serie = ", ".join(
            f"{p} {v:g}" for p, v in case.trend.get("punkter", [])[-4:]
        )
        lines.append("")
        lines.append("UTVIKLING OVER TID:")
        lines.append(f"  {case.trend['tekst']} ({serie})")

    # OPPFOELGER: Aftenbladet har skrevet om dette FOER. Modellen skal vite det,
    # for da endres oppdraget fra «finn en sak» til «hva har skjedd siden sist?»
    # - og det siste er en langt lettere artikkel aa faa paa trykk.
    if case.oppfolger:
        o = case.oppfolger
        lines.append("")
        lines.append("AFTENBLADET HAR SKREVET OM DETTE FOER:")
        lines.append(f"  «{o.get('title', '')}» - {o.get('date', '')}")
        lines.append(
            f"  Det er {o.get('dager', 0)} dager siden. Tallet er nytt; saken er kjent."
        )

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
        lines.append(
            f"  Dekningsstatus: {case.coverage_status} "
            "(gronn=uskrevet, gul=delvis, rod=godt dekket)"
        )
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
# Kildene analytikeren rangerer: primaerfunn. Broennoeysund-hendelser kom med
# 26.07.2026 - de er saker paa lik linje med SSB-tallene, og skal rangeres av
# samme oeye. Google Trends holdes utenfor; den er et signal, ikke et funn.
ANALYSERBARE = ("data", "hendelse")

# Hvor mange funn analytikeren faar rangere. Nedstroems rekker vi uansett bare
# EDITOR_CAP (3) saker, saa aa be om en rangering av atten er tokens brukt paa et
# svar ingen leser - og det var nettopp det som avkortet svaret og ga «KI delvis».
# Aatte gir rikelig med kandidater til de tre plassene.
ANALYST_MAKS_FUNN = 8


def analyst_pick(
    cases: list[Case], budsjett: Budsjett | None = None
) -> tuple[dict[str, dict], str]:
    """Velg de journalistisk interessante funnene.

    Returnerer ({key: {score, reason}}, utfall) der utfall er ett av:

        "llm"       - ekte KI-svar, brukt
        "mal"       - kallet gikk, men ga ikke noe brukbart -> mekanisk fallback
        "ko"        - ikke forsoekt, budsjettet var brukt opp
        "ingenting" - det fantes ingen funn aa rangere

    UTFALLET er halve poenget med funksjonen, og grunnen til at den ble skrevet
    om. Foer returnerte den bare dicten, og `run_workflow` gjettet paa resten:

        tell(bool(picks) and llm.last_error() is None)

    Den gjetningen var feil i to retninger. Fantes det ingen datafunn, returnerte
    den `{}` - og et tomt resultat ble talt som et MISLYKKET KI-kall, selv om
    ingen kall var forsoekt. Det var det eieren saa som «KI: delvis» 26.07.2026,
    og det ble mye vanligere idet konkurser kom inn i lista: et skann med bare
    hendelser hadde null `data`-saker.

    Motsatt vei loey den ogsaa: sto kallet i koe, ga fallbacken en full dict, og
    det ble talt som en SUKSESS. En statuslinje som lyver i begge retninger er
    verre enn ingen statuslinje.
    """
    funn = [c for c in cases if c.kind in ANALYSERBARE]
    if not funn:
        return {}, "ingenting"

    # Analytikeren fikk ALLE funnene - i et ekte skann 11-18 stykker - med et fast
    # `max_tokens=450`. Ett svarelement er {id, score, reason}, altsaa 35-45
    # tokens, saa 18 av dem er 700-800. Svaret ble avkortet midt i JSON-en,
    # parsingen feilet, og kallet ble talt som MISLYKKET. Det var derfor eieren
    # saa «KI delvis» skann etter skann 26.07.2026 - ikke uflaks, men aritmetikk.
    #
    # To ting fikser det: send bare de sterkeste funnene (nedstroems rekker vi
    # uansett bare EDITOR_CAP saker), og la taket foelge antallet i stedet for aa
    # staa fast.
    rangert = sorted(funn, key=lambda c: c.score, reverse=True)[:ANALYST_MAKS_FUNN]
    payload = [
        {"id": str(i), "finding": c.finding, "topics": c.topics, "geo": c.geo}
        for i, c in enumerate(rangert, 1)
    ]
    kart = _id_kart(rangert)
    user = "Funn:\n" + json.dumps(payload, ensure_ascii=False)
    tak = min(900, max(300, 60 * len(payload) + 120))

    # Mekanisk fallback: alle funn, rangert etter storrelsen paa avviket. Den
    # brukes i alle utfall som ikke er "llm", saa saken aldri forsvinner bare
    # fordi rangeringen ikke ble gjort.
    reserve = {
        c.key: {"score": min(int(c.score) * 3, 100), "reason": "Tydelig lokalt avvik i tallene."}
        for c in funn
    }

    if budsjett is not None and not budsjett.be_om(prompts.ANALYST_SYSTEM, user, tak):
        return reserve, "ko"

    result = llm.complete_json(
        prompts.ANALYST_SYSTEM, user, model=llm.MODEL_ANALYST, max_tokens=tak
    )
    # `isinstance`-vakten er ikke pynt: _extract_json kan returnere en LISTE hvis
    # modellen svarer med `[...]`, og da ville `result.get` kastet AttributeError
    # rett gjennom run_workflow og run_scan - som ikke fanger noe - og drept hele
    # skannet. Ingen nye leads, dashbordet staaende paa gammel data.
    if isinstance(result, dict) and isinstance(result.get("picks"), list):
        picks = {}
        for p in result["picks"]:
            if not isinstance(p, dict) or not p.get("interesting", True):
                continue
            # Ingen posisjons-fallback her, med vilje: analytikeren SKAL kunne
            # utelate funn den ikke synes er interessante, saa plass nr. 3 i
            # svaret er ikke noedvendigvis funn nr. 3 i lista.
            key = _slaa_opp(p, kart)
            if key:
                picks[key] = {"score": p.get("score", 50), "reason": p.get("reason", "")}
        if picks:
            return picks, "llm"

    return reserve, "mal"


# --- Id-ene agentene faar se -------------------------------------------------
# Eieren 26.07.2026: «Ingen vinkler ble skrevet.»
#
# Grunnen sto her. Batch-agentene fikk sakene merket med den ekte noekkelen —
# `ssb-sok:05889:1103:2026K2`, `brreg:konkurs:921456875` — og svaret ble matchet
# EKSAKT mot den:
#
#     if key not in gyldige: continue
#
# Det er 25 tegn med kolon og siffer som en gratismodell skal gjenta ordrett for
# hver eneste sak. Bommer den paa ETT tegn, faller vinklene for den saken ut
# uten en lyd — og bommer den systematisk, kommer det ingen vinkler i det hele
# tatt. Kallet gikk fint, saa ingenting ble talt som feil heller. Det var
# usynlig fra utsiden.
#
# Loesningen er aa ikke be modellen om det: den ser «SAK 1», «SAK 2», «SAK 3»,
# og vi oversetter tilbake selv. Ett siffer kan den ikke rote bort. Det er
# billigere ogsaa — noeklene kostet tokens i hver eneste blokk.


def _id_kart(saker: list[Case]) -> dict[str, str]:
    """{det modellen ser: den ekte noekkelen}.

    Baade loepenummeret og den ekte noekkelen godtas, saa et hurtiglagret svar
    fra foer omleggingen fortsatt treffer."""
    kart = {str(i): c.key for i, c in enumerate(saker, 1)}
    kart.update({c.key: c.key for c in saker})
    return kart


def _slaa_opp(post: dict, kart: dict[str, str]) -> str:
    """Finn hvilken sak et svarelement gjelder. Tom streng = kunne ikke avgjores.

    Eksakt oppslag foerst, deretter et tall gjemt i en streng som «SAK 2» eller
    «sak_3» — modeller pynter gjerne paa formatet.

    **Ingen posisjons-fallback**, og det er et bevisst valg vi tok og saa forkastet.
    «Element nr. 3 i svaret maa vaere sak nr. 3» ville reddet enda flere svar, men
    en vinkel baerer et `headline_fact`. Fester vi det til feil sak, er det ikke en
    tapt vinkel - det er et feil tall som ser riktig ut, paa vei mot trykk. Da er
    det bedre aa miste vinkelen. Testene `test_oppdiktet_id_droppes` og
    `test_vinkler_havner_paa_riktig_sak` vokter nettopp dette.
    """
    raa = str(post.get("id") or "").strip()
    if raa in kart:
        return kart[raa]
    siffer = "".join(ch for ch in raa if ch.isdigit())
    return kart.get(siffer, "")


# --- Agent 2: Redaktor -------------------------------------------------------
def editor_judge_batch(
    saker: list[Case], budsjett: Budsjett | None = None
) -> tuple[dict[str, dict], bool]:
    """Redaktoerdom for ALLE sakene i ETT kall.

    Returnerer ({sakskey: dom}, kallet_gikk_bra). Flagget er viktig: at modellen
    UTELATER en sak er ikke det samme som at kallet feilet. Uten skillet ble
    hver utelatte sak talt som et mislykket KI-kall, og statuslinja sa «delvis»
    selv om KI-en var paa og svarte fint.

    Samme grunn som for vinklene, og oppdaget paa samme maate: EDITOR_SYSTEM er
    lang - den maa vaere det, for det er der redaktoerens 25 aars erfaring staar.
    Med ett kall per sak ble hele den prompten sendt fire ganger, og da var
    budsjettet brukt opp av redaktoeren alene. Journalisten fikk aldri slippe
    til, og sakene sto uten vinkler.

    Maalt: fire separate redaktoerkall kostet rundt 9 000 tokens - hele
    skannbudsjettet. Samlet koster de under 3 000.
    """
    if not saker:
        return {}, True

    kart = _id_kart(saker)
    blokker = [
        f"=== SAK {i} ===\n{kildegrunnlag(c)}" for i, c in enumerate(saker, 1)
    ]
    user = (
        "\n\n".join(blokker)
        + f"\n\nVurder ALLE {len(saker)} funnene over, hver for seg. "
        "Bruk sakens id noeyaktig som den staar etter «=== SAK » (1, 2, 3 …)."
    )
    # Redaktoerdommen er sju korte felt per sak - rundt 200 tokens. 350 er
    # fortsatt romslig, og de 150 vi sparer per sak gaar til journalisten.
    tak = max(700, 300 * len(saker))

    if budsjett is not None and not budsjett.be_om(prompts.EDITOR_BATCH_SYSTEM, user, tak):
        return {}, True          # ikke forsoekt - koe, ikke feil

    result = llm.complete_json(
        prompts.EDITOR_BATCH_SYSTEM, user, model=llm.MODEL_EDITOR, max_tokens=tak
    )
    if not isinstance(result, dict) or not isinstance(result.get("saker"), list):
        return {}, False

    ut: dict[str, dict] = {}
    for post in result["saker"]:
        if not isinstance(post, dict) or "is_story" not in post:
            continue
        key = _slaa_opp(post, kart)
        if not key or key in ut:
            continue
        # `mode` SIST, saa et modellsvar som inneholder feltet ikke kan overskrive
        # det - og dermed styre baade merkingen i UI og tellingen av vellykkede kall.
        ut[key] = {**{k: v for k, v in post.items() if k != "id"}, "mode": "llm"}
    return ut, True


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
def journalist_angles_batch(
    saker: list[Case], budsjett: Budsjett | None = None
) -> tuple[dict[str, list[dict]], bool]:
    """Vinkler for ALLE sakene i ETT kall.

    Returnerer ({sakskey: [vinkler]}, kallet_gikk_bra) - se editor_judge_batch
    for hvorfor de to er forskjellige ting.

    Dette er fiksen paa det eieren saa 26.07.2026: «KI-en rakk ikke alt - 4 av 4
    kall feilet», med `Groq (gratis): kvotetak (429)`.

    Aarsaken var strukturen, ikke uflaks. Ett kall PER SAK betyr seks kall mot et
    minuttak paa 12 000 tokens, og hvert kall sender hele systemprompten paa nytt.
    Systemprompten er den store posten - den er lang nettopp fordi den maa vaere
    det. Seks ganger den samme prompten er fem ganger sloesing.

    Med ett samlet kall sendes prompten én gang, og alle sakene faar vinkler for
    prisen av den dyreste enkeltsaken. Da rekker kvoten hele veien, og
    journalisten faar minst to overskrifter per funn - som var kravet.
    """
    if not saker:
        return {}, True

    kart = _id_kart(saker)
    blokker = []
    for nr, c in enumerate(saker, 1):
        ed = c.editor or {}
        # Redaktoerens dom foelger med som OPPLYSNING, ikke som port. Eierens
        # beslutning 26.07.2026: vinklene skal komme uansett om saken er god
        # eller ikke, slik at journalisten kan be om utkast og se selv. Da maa
        # journalist-agenten faa vite hva redaktoeren mente - et nei endrer
        # oppdraget fra «skriv den» til «finn vinkelen som ville snudd ham».
        dom = "JA - kjoer paa" if ed.get("is_story") else "NEI - han er skeptisk"
        blokk = (
            f"=== SAK {nr} ===\n"
            f"{kildegrunnlag(c)}\n"
            f"REDAKTOERENS BESTILLING:\n"
            f"  Dom: {dom}\n"
            f"  Arbeidstittel: {ed.get('headline', c.title)}\n"
            f"  Oppdrag: {ed.get('angle', c.angle)}\n"
            f"  Begrunnelse: {ed.get('verdict', '-')}\n"
            f"  Forbehold: {ed.get('forbehold', '-')}"
        )
        # Den mekaniske grunnlagssjekken stopper ikke lenger vinklene, men den
        # skal ikke bli usynlig heller: modellen faar vite noeyaktig hva som
        # mangler, saa svakheten havner i «mangler» og «risiko» i stedet for aa
        # bli fylt inn med noe som hoeres bra ut.
        if ed.get("gate_mangler"):
            blokk += "\nSVAKHETER I GRUNNLAGET (skal naevnes i «mangler»):\n  " + "\n  ".join(
                ed["gate_mangler"]
            )
        blokker.append(blokk)
    user = (
        "\n\n".join(blokker)
        + f"\n\nLever vinkler for ALLE {len(saker)} sakene over. "
        "Bruk sakens id noeyaktig som den staar etter «=== SAK » (1, 2, 3 …)."
    )
    # Taket teller MED i tokenanslaget, saa et rundhaandet tak koster kvote selv
    # naar modellen svarer kort. Maalt paa ekte svar: en vinkel med tittel, pitch,
    # kilder og risiko lander rundt 130 tokens, saa TO vinkler per sak er ~270.
    # 450 gir god margin; 900 var ren luft vi betalte for i hvert eneste skann.
    tak = max(1000, 450 * len(saker))

    if budsjett is not None and not budsjett.be_om(
        prompts.JOURNALIST_BATCH_SYSTEM, user, tak, er_journalisten=True
    ):
        return {}, True          # ikke forsoekt - koe, ikke feil

    result = llm.complete_json(
        prompts.JOURNALIST_BATCH_SYSTEM, user, model=llm.MODEL_ANALYST, max_tokens=tak
    )
    if not isinstance(result, dict) or not isinstance(result.get("saker"), list):
        return {}, False

    ut: dict[str, list[dict]] = {}
    for post in result["saker"]:
        if not isinstance(post, dict) or not isinstance(post.get("angles"), list):
            continue
        key = _slaa_opp(post, kart)
        if not key or key in ut:
            continue
        rene = _uten_gjengangere(
            [a for a in post["angles"] if isinstance(a, dict) and a.get("title")]
        )
        if rene:
            for a in rene:
                a["mode"] = "llm"
            # TO forslag, ikke tre. Eierens beslutning 26.07.2026: tallet foerst,
            # to skarpe titler, saa velger han én og ber om utkast fra den.
            ut[key] = rene[:2]
    return ut, True


def journalist_angles(
    case: Case, editor: dict, budsjett: Budsjett | None = None
) -> list[dict]:
    """To KORTE vinkelforslag - ingen artikkel enda.

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
        "Foreslaa to ulike vinkler. Ikke skriv artikkelen."
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
            return clean[:2]
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
    budsjett = Budsjett(
        KI_BUDSJETT_TOKENS if has_key else 0,
        reservert=KI_RESERVE_JOURNALIST if has_key else 0,
    )
    hurtiglager = storage.ki_hent([c.key for c in cases]) if has_key else {}

    def tell(fikk_llm: bool) -> None:
        regnskap["forsokt"] += 1
        regnskap["lyktes" if fikk_llm else "feilet"] += 1

    def melde(tekst: str) -> None:
        if si is not None:
            si(tekst)

    picks, analyse = analyst_pick(cases, budsjett)
    # Analytikeren telles BARE naar det faktisk ble gjort et forsoek. «Ingenting
    # aa rangere» og «stod i koe» er ikke mislykkede kall, og aa telle dem som
    # det var nettopp det som ga «KI: delvis» paa et skann der alt gikk bra.
    if analyse in ("llm", "mal"):
        tell(analyse == "llm")
    for c in cases:
        if c.key in picks:
            c.analyst_reason = picks[c.key].get("reason", "")

    # Redaktor vurderer datadrevne + Schibsted-leads (analytiker-valgte prioritert).
    ranked = sorted(cases, key=lambda c: c.score, reverse=True)
    # KUN primaerkilder. Gjenbrukte avissaker sto her og spiste plasser i en
    # kvote som bare rekker fire saker per skann.
    candidates = [c for c in ranked if c.kind in ("data", "hendelse")]
    editor_cases = (
        [c for c in candidates if c.key in picks] + [c for c in candidates if c.key not in picks]
    )[:EDITOR_CAP] or ranked[:EDITOR_CAP]

    # Redaktoerdom for alle sakene i ETT kall - se editor_judge_batch. Med ett
    # kall per sak ble den lange EDITOR_SYSTEM sendt fire ganger, og budsjettet
    # var brukt opp foer journalisten fikk lage en eneste vinkel.
    maa_vurderes: list[Case] = []
    for c in editor_cases:
        lagret = hurtiglager.get(c.key, {})
        if isinstance(lagret.get("editor"), dict):
            # Ekte dom fra et tidligere skann. Gratis - og det er nettopp derfor
            # «trykk Skann igjen» flytter koen framover i stedet for aa betale
            # for de samme topp-sakene om igjen.
            c.editor = {**lagret["editor"], "mode": "llm"}
            c.ai_mode = "llm"
            regnskap["gjenbrukt"] += 1
        else:
            maa_vurderes.append(c)

    if maa_vurderes:
        melde(f"Redaktøren vurderer {len(maa_vurderes)} funn")
        ko_for = budsjett.i_ko
        dommer, kallet_ok = editor_judge_batch(maa_vurderes, budsjett)
        # ETT kall, saa ETT utfall i regnskapet. Foer telte vi per sak, og en
        # sak modellen utelot ble til et «mislykket kall» - det var derfor
        # statuslinja sa «delvis» selv om KI-en svarte fint.
        if budsjett.i_ko == ko_for:
            tell(bool(dommer) or kallet_ok)
        for c in maa_vurderes:
            dom = dommer.get(c.key)
            if dom:
                c.editor = dom
                c.ai_mode = "llm"
                storage.ki_lagre(c.key, editor=dom)
            elif budsjett.i_ko > ko_for:
                # Ikke forsoekt - budsjettet var brukt opp. Malen brukes bare som
                # PORT (slipper saken videre), og merkes «ko» saa UI-et sier
                # «trykk igjen» og ikke «dette er alt du faar».
                c.editor = {**_editor_mal(c), "mode": "ko"}
                c.ai_mode = "ko"
            else:
                c.editor = _editor_mal(c)
                c.ai_mode = "mal"

    # ALLE vurderte saker gaar videre til journalisten - ogsaa de redaktoeren sa
    # nei til. Eierens beslutning 26.07.2026: «Vinklene skal komme uansett om
    # saken er daarlig eller ei, slik han kan be om utkast.»
    #
    # Foer sto det en `if c.editor.get("is_story")` her, og den var en STILLE
    # sperre: sa KI-redaktoeren nei, sto saken igjen i lista uten en eneste
    # tittel og uten knapp for utkast. Journalisten kunne ikke overproeve dommen
    # - han fikk ikke engang se hva saken kunne vaert. Dommen er et raad, ikke en
    # port; den vises fortsatt i kortet, og den styrer rekkefolgen (ja foerst),
    # men den stopper ingenting.
    til_journalist = sorted(editor_cases, key=lambda c: not c.editor.get("is_story"))

    # Journalisten foreslaar KUN vinkler her. Artikkelen skrives naar journalisten ber om
    # den (write_draft), slik at vi ikke bruker kvote paa saker som aldri aapnes.
    # Vinkler for ALLE sakene i ETT kall. Foer var det ett kall per sak, og med
    # seks saker ble systemprompten sendt seks ganger mot et minuttak paa 12 000
    # tokens. Det var derfor eieren saa «4 av 4 kall feilet» med 429 - strukturen,
    # ikke uflaks. Naa sendes prompten én gang.
    trenger: list[Case] = []
    for c in til_journalist[:JOURNALIST_CAP]:
        # Sufficient-context-gate: modeller avstaar ikke selv naar grunnlaget er
        # tynt. Sjekken staar derfor fortsatt her og er fortsatt mekanisk - men
        # den FORKASTER ikke lenger saken. Den merker den, og manglene sendes med
        # inn i prompten (se journalist_angles_batch), slik at svakheten havner i
        # «mangler» og «risiko» i stedet for aa bli fylt inn med noe som hoeres
        # bra ut. Den harde sporingen av tall staar urort i write_draft.
        nok, mangler = verify.nok_grunnlag(c.to_dict())
        if not nok:
            c.editor = {**c.editor, "gate_mangler": mangler}
        lagret = hurtiglager.get(c.key, {})
        if isinstance(lagret.get("angles"), list) and lagret["angles"]:
            c.angles = lagret["angles"]
            c.ai_mode = "llm"
            regnskap["gjenbrukt"] += 1
            continue
        trenger.append(c)

    if trenger:
        melde(f"Journalisten lager vinkler for {len(trenger)} saker")
        ko_for = budsjett.i_ko
        vinkler, kallet_ok = journalist_angles_batch(trenger, budsjett)
        if budsjett.i_ko == ko_for:
            tell(bool(vinkler) or kallet_ok)
        for c in trenger:
            c.angles = vinkler.get(c.key, [])
            if c.angles:
                c.ai_mode = "llm"
                storage.ki_lagre(c.key, angles=c.angles)
            elif budsjett.i_ko > ko_for:
                c.ai_mode = "ko"
            else:
                # Saken merkes etter det SVAKESTE leddet: uten vinkler er den
                # ikke «KI» selv om redaktoren tilfeldigvis kom gjennom. Men den
                # telles IKKE som et feilet kall - kallet gikk, modellen utelot
                # bare denne saken.
                c.ai_mode = "mal"

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
