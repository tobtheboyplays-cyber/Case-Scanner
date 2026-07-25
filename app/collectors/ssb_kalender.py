"""SSBs publiseringskalender - forspranget.

Dette er den eneste kilden i verktoyet som varsler om noe som IKKE har skjedd enda.
Alt annet forteller hva som allerede er publisert; denne forteller hva som KOMMER,
med eksakt dato - og med navn, e-post og telefon til statistikeren som eier tallet.

Journalisten faar altsaa ikke tallet tidlig (det er embargobelagt til kl. 08.00
hverdager), men han faar tid til aa forberede saken, ringe kilden og ha vinkelen klar
den morgenen tallet slippes. Det er der forspranget ligger.

Kilde: https://www.ssb.no/rss/statkal - aapen, gratis, ingen noekkel. 31 dagers
horisont. Verifisert live 25.07.2026: HTTP 200, 54 framtidsdaterte oppforinger.
Egen namespace `ssbrss` baerer dato, kortnavn, emne og kontaktperson.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from xml.etree import ElementTree

from app.collectors.base import http_get

FEED = "https://www.ssb.no/rss/statkal"
NS = {"ssbrss": "http://www.ssb.no/ns/ssbrss"}

# Emner som betyr noe for lesere i 20-40-aarene i Stavanger-omraadet. SSB bruker
# disse som `subject` i feeden. Alt annet slippes gjennom med lavere vekt i stedet
# for aa filtreres bort - en journalist skal kunne se hele lista hvis han vil.
VIKTIGE_EMNER: dict[str, int] = {
    "arbeid-og-lonn": 10,
    "priser-og-prisindekser": 9,
    "bygg-bolig-og-eiendom": 9,
    "befolkning": 8,
    "utdanning": 7,
    "inntekt-og-forbruk": 7,
    "helse": 6,
    "sosiale-forhold-og-kriminalitet": 6,
    "energi-og-industri": 5,
    "transport-og-reiseliv": 4,
}

# Ord i tittelen som gjor en publisering ekstra lokalt interessant.
LOKALE_ORD = ("kommune", "fylke", "region", "bolig", "leie", "arbeidsledig", "student")


def _tekst(item: ElementTree.Element, tag: str) -> str:
    el = item.find(tag, NS) if ":" in tag else item.find(tag)
    return (el.text or "").strip() if el is not None and el.text else ""


def _kontakter(item: ElementTree.Element) -> list[dict]:
    """Statistikerne som eier tallet. Feeden kan oppgi flere per publisering -
    alle tas med, for det er nettopp disse journalisten skal ringe FOER slippet."""
    ut: list[dict] = []
    for c in item.findall("ssbrss:contact", NS):
        navn = _tekst(c, "ssbrss:person")
        if not navn:
            continue
        ut.append({
            "navn": navn,
            "telefon": _tekst(c, "ssbrss:phone"),
            "epost": _tekst(c, "ssbrss:email"),
        })
    return ut


def _ryddig_tittel(raa: str) -> str:
    """«27.07.2026: Byggekostnadsindeks, Tall for 2. kvartal» -> uten datoprefiks."""
    return re.sub(r"^\d{2}\.\d{2}\.\d{4}:\s*", "", raa).strip()


def collect(*, i_dag: date | None = None, maks: int = 12) -> tuple[list[dict], list[str]]:
    """Kommende SSB-publiseringer, viktigste foerst.

    Returnerer (varsler, statuslinjer). Feiler aldri oppover: en dod feed skal
    aldri velte et skann - da faar journalisten bare ikke varslene denne gangen.
    """
    status: list[str] = []
    try:
        resp = http_get(FEED, timeout=20, headers={"Accept": "application/rss+xml"})
        root = ElementTree.fromstring(resp.content)
    except Exception as exc:  # noqa: BLE001 - fail-soft
        return [], [f"[FEIL] SSB-kalender: {exc}"]

    today = i_dag or date.today()
    varsler: list[dict] = []

    for item in root.iter("item"):
        iso = _tekst(item, "ssbrss:date")
        try:
            naar = date.fromisoformat(iso)
        except ValueError:
            continue
        dager = (naar - today).days
        if dager < 0:
            continue  # allerede publisert - ikke lenger et forsprang

        emne = _tekst(item, "ssbrss:subject")
        tittel = _ryddig_tittel(_tekst(item, "title"))
        vekt = VIKTIGE_EMNER.get(emne, 2)
        if any(o in tittel.lower() for o in LOKALE_ORD):
            vekt += 3
        # Det som kommer snart er mest verdt aa forberede.
        if dager <= 3:
            vekt += 4
        elif dager <= 7:
            vekt += 2

        varsler.append(
            {
                "dato": iso,
                "dager_til": dager,
                "tittel": tittel,
                "emne": emne,
                "kortnavn": _tekst(item, "ssbrss:shortname"),
                "lenke": _tekst(item, "link"),
                "kontakter": _kontakter(item),
                "vekt": vekt,
            }
        )

    varsler.sort(key=lambda v: (-v["vekt"], v["dager_til"]))
    if varsler:
        naermeste = varsler[0]
        status.append(
            f"SSB-kalender: {len(varsler)} kommende publiseringer "
            f"(naermeste om {naermeste['dager_til']} dager)"
        )
    else:
        status.append("SSB-kalender: ingen kommende publiseringer funnet")
    return varsler[:maks], status


def hvor_ferskt(iso: str) -> str:
    """«om 2 dager» / «i morgen» / «i dag» - til visning."""
    try:
        d = (date.fromisoformat(iso) - date.today()).days
    except ValueError:
        return iso
    if d == 0:
        return "i dag kl. 08.00"
    if d == 1:
        return "i morgen kl. 08.00"
    return f"om {d} dager"


def _parse_pubdate(raw: str) -> datetime | None:
    """Reservetolkning av RFC-822-dato hvis ssbrss:date mangler."""
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None
