"""Tall som folk faktisk leser — brukt av alle kilder, ikke bare én.

Eieren 26.07.2026, i tre meldinger etter hverandre:

    «Viktig at vi skjønner hva faktaen er, så kan gjerne forenkle faktaen.»
    «Gjerne oversett tallene med at faktaen er barn kan forstå.»
    «Så gjør at alle faktaene som du finner blir oversatt automatisk.»

Derfor ligger dette her og ikke i én kollektor. `forenkle()` kjores paa HVERT
funn i `run_scan`, saa en ny kilde arver oversettelsen uten aa gjore noe - og
ingen framtidig okt kan glemme aa koble den paa.

## Tre regler, og den tredje er den viktigste

1. **Store tall skrives om.** «40 832 836» er et tall man maa telle sifrene i.
   «40,8 millioner» er noe man forstaar med én gang.

2. **Det eksakte tallet foelger alltid med.** Journalisten skal PUBLISERE dette.
   En avrunding kan ikke siteres som fasit, og han maa kunne finne igjen tallet
   hos SSB. De tolv ekstra tegnene er billige.

3. **Er vi i tvil, sier vi ingenting.** En maalestokk som ikke stemmer er verre
   enn ingen maalestokk. Se `_HENDELSER` for hvorfor dette er en allowlist.
"""

from __future__ import annotations

import re

MILLION = 1_000_000
MILLIARD = 1_000_000_000


def norsk(v: float) -> str:
    """1234.0 -> «1 234», 3.75 -> «3,75». Uten locale-avhengighet."""
    if float(v).is_integer():
        return f"{int(v):,}".replace(",", " ")
    return f"{v:,.2f}".replace(",", " ").replace(".", ",")


def en_desimal(v: float) -> str:
    """«1,2», ikke «1,20». En maalestokk med to desimaler er ikke en maalestokk."""
    if float(v).is_integer():
        return str(int(v))
    return f"{v:.1f}".replace(".", ",")


def lesbart(v: float) -> str:
    """Store tall i ord, med det eksakte tallet i parentes.

    Under en million er grupperingen god nok i seg selv: «34 860» leses greit.
    """
    if abs(v) >= MILLIARD:
        tall = f"{v / MILLIARD:.1f}".replace(".", ",")
        return f"{tall} milliarder ({norsk(v)})"
    if abs(v) >= MILLION:
        tall = f"{v / MILLION:.1f}".replace(".", ",")
        return f"{tall} millioner ({norsk(v)})"
    return norsk(v)


# ── Maalestokk: «det er i snitt X om dagen» ────────────────────────────────

# Ord som avsloerer at tallet er KRONER og ikke en telling. SSB og de andre
# kildene skriver enheten i variabelnavnet, saa vi slipper aa gjette.
_PENGEORD = ("kr", "nok", "utgift", "kostnad", "inntekt", "stønad", "stonad",
             "lønn", "lonn", "beløp", "belop", "gebyr", "tilskudd", "omsetning")

# HENDELSER som skjer gjennom perioden, og som derfor kan regnes om til «per
# uke». Dette er en ALLOWLIST, ikke en blokkliste, og det er et bevisst valg.
#
# Foerste utkast blokkerte det aabenbare (areal, timer) og slapp resten
# gjennom. Da kom «Menn i kvalifiseringsprogram: 128 - det er i snitt 2,5 i
# uka». Det er feil: 128 er hvor mange som ER i programmet, ikke hvor mange som
# kommer til. En BEHOLDNING kan ikke deles paa uker.
#
# Forskjellen kan ikke leses ut av tallet, bare av hva det teller. Da er den
# eneste aerlige loesningen aa liste opp det vi VET er hendelser, og tie i alle
# andre tilfeller.
_HENDELSER = ("ulykk", "brann", "konkurs", "anmeld", "innleggels", "fødte",
              "fodte", "døde", "dode", "flytting", "tilfell", "hendels",
              "søknad", "soknad", "klage", "vedtak", "dødsfall", "dodsfall",
              "skade", "avgang", "tilgang", "registrer", "besøk", "besok",
              "kansell", "forsinkels", "passering")

# Hvor mange dager en periode dekker.
_DAGER = {"aar": 365.0, "kvartal": 91.0, "maaned": 30.0}


def periodeslag(periode: str) -> str:
    """«2026K2» -> kvartal, «2025» -> aar, «2026M05» -> maaned, ellers «»."""
    p = (periode or "").strip()
    if re.fullmatch(r"\d{4}K[1-4]", p):
        return "kvartal"
    if re.fullmatch(r"\d{4}M\d{2}", p):
        return "maaned"
    if re.fullmatch(r"\d{4}", p):
        return "aar"
    return ""


def skala(verdi: float, periode: str, navn: str) -> str:
    """En setning som gjor tallet til noe man ser for seg. Tom naar den ikke kan.

    Regnestykket er rent: verdien delt paa antall dager i perioden. Ingen
    befolkningstall, ingen antakelser om noe vi ikke har hentet.

    **Formuleringen er med vilje «i snitt».** Ulykker skjer ikke jevnt utover
    aaret, og «det skjer én ulykke i uka» ville vaert en paastand kilden ikke
    dekker. «I snitt én i uka» er det tallet faktisk sier.
    """
    dager = _DAGER.get(periodeslag(periode), 0.0)
    if not dager or verdi <= 0:
        return ""
    lav = (navn or "").lower()

    if any(o in lav for o in _PENGEORD):
        per_dag = verdi / dager
        if per_dag < 1000:          # under tusenlappen sier det ingenting nytt
            return ""
        return f"Det er i snitt {norsk(round(per_dag, -2))} kroner om dagen."

    # Er det ikke penger, maa det vaere en TELLING av hendelser for at «per uke»
    # skal bety noe. Er vi i tvil, sier vi ingenting.
    if not float(verdi).is_integer() or not any(o in lav for o in _HENDELSER):
        return ""

    per_uke = verdi / (dager / 7.0)
    if per_uke >= 7:
        return f"Det er i snitt {en_desimal(round(verdi / dager, 1))} om dagen."
    if per_uke >= 0.7:
        return f"Det er i snitt {en_desimal(round(per_uke, 1))} i uka."
    per_mnd = verdi / (dager / 30.0)
    if per_mnd >= 0.5:
        return f"Det er i snitt {en_desimal(round(per_mnd, 1))} i måneden."
    return ""


# ── Den automatiske oversettelsen ──────────────────────────────────────────

# Bare tall som ALLEREDE er gruppert med mellomrom, og som er minst sju sifre.
# Det er nettopp det som gjor den trygg: aarstall (2026), organisasjonsnummer
# (921456875) og tabell-ID-er (07459) skrives uten mellomrom, saa de kan ikke
# treffes. Uten den begrensningen ville «SSB tabell 12 160» blitt til
# «12,2 tusen», og kildehenvisningen vaert oedelagt.
_STORT = re.compile(r"(?<![\d,.])(\d{1,3}(?: \d{3}){2,})(?![\d,.])")


def forenkle(tekst: str) -> str:
    """Skriv om store tall i en ferdig setning. Trygt aa kjore paa alt.

    Kjores paa hvert funn i `run_scan`, saa enhver kilde - ogsaa en som kommer
    til senere - faar oversettelsen uten aa gjore noe selv.

    Allerede oversatte tall roeres ikke: staar det «(40 832 836)» rett etter
    «40,8 millioner», lar vi det vaere.
    """
    if not tekst:
        return tekst

    def bytt(m: re.Match[str]) -> str:
        raa = m.group(1)
        # Staar tallet i en parentes rett etter en oversettelse, er jobben gjort.
        start = m.start(1)
        foran = tekst[max(0, start - 30):start]
        if "millioner (" in foran or "milliarder (" in foran:
            return raa
        try:
            v = float(raa.replace(" ", ""))
        except ValueError:
            return raa
        return lesbart(v) if abs(v) >= MILLION else raa

    return _STORT.sub(bytt, tekst)
