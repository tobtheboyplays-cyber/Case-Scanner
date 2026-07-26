"""Brønnøysundregistrene: hva som åpner og hva som går under, lokalt.

SSB forteller hva som ALLEREDE er talt opp. Denne kollektoren gjør noe annet:
den henter hendelser i nærmiljøet — en restaurant som er registrert, et firma
som gikk konkurs, et selskap under avvikling. Det er saker en journalist kan
ringe på samme dag, ikke tall som skal tolkes.

Åpent API, ingen nøkkel, ingen kvote:
  https://data.brreg.no/enhetsregisteret/api/enheter

## Tre ting som måtte verifiseres mot ekte data, ikke gjettes

1. **`sort=konkursdato,desc` virker ikke.** API-et svarer tomt. Men totalen er
   liten (110 konkursrammede foretak i Stavanger, 54 i Sandnes), så vi henter
   alle i ett kall og sorterer selv. Ett kall per kommune, ikke paginering.

2. **`konkurs=true` betyr «er konkurs nå», ikke «gikk konkurs nylig».** Uten
   datofilter får man tilbake selskaper som gikk over ende i 1995. Feltet
   `konkursdato` finnes derimot på hver enhet, og det er det vi filtrerer på.

3. **«AS KONKURSBO» er ikke en nyåpning.** Når et selskap går konkurs, opprettes
   det automatisk et konkursbo som EGEN enhet med fersk registreringsdato. Uten
   filter ville «BLÅVEISEN BLOMSTER AS KONKURSBO» dukket opp som «ny
   blomsterbutikk åpnet» — stikk motsatt av sannheten. De kjennes på
   `organisasjonsform.kode == "KBO"`.

Verifisert live 26.07.2026.

## Hva den IKKE gir

Ingenting om riving. Rivetillatelser ligger i kommunens byggesaksarkiv, ikke i
Brønnøysund. Skal det med, er det en annen kilde og en annen jobb.
"""

from __future__ import annotations

from datetime import date, timedelta
from urllib.parse import urlencode

from app.collectors.base import http_get

API = "https://data.brreg.no/enhetsregisteret/api/enheter"

# Kommunene journalisten dekker. Nummer, ikke navn - API-et vil ha nummer.
KOMMUNER: dict[str, str] = {"1103": "Stavanger", "1108": "Sandnes"}

# Hvor langt tilbake en hendelse fortsatt er ny nok til aa ringe paa.
DAGER = 45

# Tak per kommune per type, saa ett skann ikke drukner i smaaforetak.
MAKS_PER_TYPE = 10

# NACE-hovedgrupper der virksomheten er noe folk FAAR OEYE PAA i gata. Et
# konsulentselskap som registreres er ikke en sak; en restaurant er det.
# Koden er langt mer paalitelig enn aa lete etter ord i bransjebeskrivelsen.
PUBLIKUMSNAERE: dict[str, str] = {
    "47": "butikk",
    "55": "hotell og overnatting",
    "56": "restaurant og servering",
    "85": "skole og barnehage",
    "86": "helsetjeneste",
    "90": "kunst og kultur",
    "91": "bibliotek og museum",
    "93": "idrett og fritid",
    "96": "frisør og personlig tjeneste",
}

# Organisasjonsformer som ikke er en virksomhet som AAPNER.
#   KBO  = konkursbo, opprettes automatisk NAAR noen gaar konkurs (punkt 3 over)
#   ADOS = administrativ enhet i offentlig sektor
#   KTRF = kontorfellesskap
# Merk at DA (ansvarlig selskap med delt ansvar) IKKE staar her: det er en helt
# vanlig selskapsform for smaa butikker og frisoerer, og aa filtrere den bort
# ville fjernet nettopp de publikumsnaere virksomhetene vi er ute etter.
IKKE_VIRKSOMHET: frozenset[str] = frozenset({"KBO", "ADOS", "KTRF"})


def _hent(params: dict) -> list[dict]:
    url = f"{API}?{urlencode(params)}"
    svar = http_get(url, timeout=25, headers={"Accept": "application/json"}).json()
    return (svar.get("_embedded") or {}).get("enheter") or []


def _naering(enhet: dict) -> tuple[str, str]:
    """(bransjetekst, publikumsmerkelapp). Tom merkelapp = ikke publikumsnaer."""
    kode = (enhet.get("naeringskode1") or {}).get("kode") or ""
    tekst = (enhet.get("naeringskode1") or {}).get("beskrivelse") or ""
    return tekst, PUBLIKUMSNAERE.get(kode[:2], "")


def _dager_siden(iso: str, i_dag: date) -> int | None:
    try:
        return (i_dag - date.fromisoformat(iso)).days
    except (ValueError, TypeError):
        return None


def _hendelse(
    enhet: dict, *, type_: str, dato: str, dager: int, kommune: str
) -> dict:
    bransje, publikum = _naering(enhet)
    orgnr = enhet.get("organisasjonsnummer") or ""
    ansatte = enhet.get("antallAnsatte")

    # Vekting. Publikumsnaere virksomheter foerst - det er dem journalisten kan
    # skrive om uten aa maatte forklare hva selskapet driver med. Ferskt slaar
    # gammelt, og et foretak med ansatte er en stoerre sak enn et uten.
    vekt = 4 if publikum else 1
    if dager <= 7:
        vekt += 3
    elif dager <= 21:
        vekt += 1
    if isinstance(ansatte, int) and ansatte >= 5:
        vekt += 2
    # En KONKURS er noe annet enn en frivillig avvikling: noen tapte penger,
    # ansatte mistet jobben, og et bo skal gjores opp. Med bare +1 druknet
    # konkursene bak ferskere avviklinger - maalt 26.07.2026 var alle aatte
    # oeverste treff «under avvikling» og ingen konkurser i det hele tatt.
    if type_ == "konkurs":
        vekt += 4

    return {
        "type": type_,
        "navn": (enhet.get("navn") or "").title(),
        "kommune": kommune,
        "dato": dato,
        "dager_siden": dager,
        "bransje": bransje,
        "publikum": publikum,
        "ansatte": ansatte if isinstance(ansatte, int) else None,
        "orgnr": orgnr,
        "lenke": f"https://virksomhet.brreg.no/nb/oppslag/enheter/{orgnr}",
        "vekt": vekt,
    }


def _konkurser(komm: str, navn: str, i_dag: date) -> list[dict]:
    """Foretak som har gaatt konkurs eller er under avvikling i vinduet."""
    ut: list[dict] = []
    for felt, datofelt, type_ in (
        ("konkurs", "konkursdato", "konkurs"),
        ("underAvvikling", "underAvviklingDato", "avvikling"),
    ):
        for e in _hent({"kommunenummer": komm, felt: "true", "size": 500}):
            iso = e.get(datofelt) or ""
            dager = _dager_siden(iso, i_dag)
            if dager is None or dager < 0 or dager > DAGER:
                continue
            # Et selskap som BAADE er under avvikling og konkurs skal telles én
            # gang - konkursen er den sterkeste opplysningen.
            if type_ == "avvikling" and e.get("konkurs"):
                continue
            ut.append(_hendelse(e, type_=type_, dato=iso, dager=dager, kommune=navn))
    return ut


def _nye(komm: str, navn: str, i_dag: date) -> list[dict]:
    """Nyregistrerte foretak - noe som skal aapne."""
    fra = (i_dag - timedelta(days=DAGER)).isoformat()
    ut: list[dict] = []
    for e in _hent({
        "kommunenummer": komm,
        "fraRegistreringsdatoEnhetsregisteret": fra,
        "size": 500,
    }):
        # Konkursbo er IKKE en nyaapning - se punkt 3 i modulteksten.
        if (e.get("organisasjonsform") or {}).get("kode") in IKKE_VIRKSOMHET:
            continue
        if e.get("konkurs") or e.get("underAvvikling"):
            continue      # registrert og allerede paa vei ned - ikke en aapning
        iso = e.get("registreringsdatoEnhetsregisteret") or ""
        dager = _dager_siden(iso, i_dag)
        if dager is None or dager < 0 or dager > DAGER:
            continue
        ut.append(_hendelse(e, type_="nytt", dato=iso, dager=dager, kommune=navn))
    return ut


def collect(i_dag: date | None = None) -> tuple[list[dict], list[str]]:
    """Hendelser i naeringslivet lokalt, tyngste foerst.

    Fail-soft per kommune: én kommune som feiler skal aldri velte skannet -
    da faar journalisten bare faerre hendelser denne gangen.
    """
    i_dag = i_dag or date.today()
    hendelser: list[dict] = []
    status: list[str] = []

    for komm, navn in KOMMUNER.items():
        try:
            ned = _konkurser(komm, navn, i_dag)
            opp = _nye(komm, navn, i_dag)
        except Exception as exc:  # noqa: BLE001 - fail-soft per kommune
            status.append(f"[FEIL] Brønnøysund {navn}: {type(exc).__name__}")
            continue

        ned.sort(key=lambda h: -h["vekt"])
        opp.sort(key=lambda h: -h["vekt"])
        hendelser.extend(ned[:MAKS_PER_TYPE] + opp[:MAKS_PER_TYPE])

        publikum = sum(1 for h in ned + opp if h["publikum"])
        status.append(
            f"Brønnøysund {navn}: {len(ned)} konkurs/avvikling, {len(opp)} nye "
            f"foretak siste {DAGER} dager ({publikum} publikumsrettet)"
        )

    hendelser.sort(key=lambda h: (-h["vekt"], h["dager_siden"]))
    return hendelser, status
