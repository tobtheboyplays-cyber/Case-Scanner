"""Deterministiske sjekker rundt KI-en. Ingen modell dommer over seg selv her.

Bygget paa to funn fra research-runden (docs/RESEARCH_FUNN.md):

- Sourcing/attribusjon er den dominerende feilmodusen i KI-generert nyhetsarbeid
  (EBU/BBC 2025: sourcing er storste enkeltkategori av signifikante problemer).
  Derfor: hvert tall i utkastet spores mekanisk tilbake til kildegrunnlaget.
- Modeller velger selvsikre feilsvar framfor aa avstaa naar konteksten er tynn.
  Derfor: en gate UTENFOR modellen avgjor om det er nok grunnlag til aa skrive.
"""

from __future__ import annotations

import re

# Tall i norsk format: 1,9 / 1 234 / 12.5 / 2026. Prosenttegn og fortegn holdes utenfor
# selve matchen slik at "+1,9 %" og "1,9" gir samme normaliserte form.
_TALL = re.compile(r"\d[\d\s.,]*")


def _normaliser(tall: str) -> str:
    """Gjor «1 234,5», «1.234,5» og «1234,5» sammenlignbare."""
    t = tall.strip().rstrip(".,").replace(" ", "").replace(" ", "")
    t = t.replace(".", "")           # tusenskille
    t = t.replace(",", ".")          # desimalkomma
    return t.lstrip("0") or "0"


def tall_i(tekst: str) -> set[str]:
    """Alle tall i en tekst, normalisert."""
    return {n for m in _TALL.findall(tekst or "") if (n := _normaliser(m))}


def usporbare_tall(body: str, kildegrunnlag: str) -> list[str]:
    """Tall i utkastet som IKKE finnes i kildegrunnlaget.

    Aarstall og smaa heltall (0-31) utelates: de er datoer, avsnittstall og
    alminnelige mengdeord, ikke paastander som maa spores. Resten skal kunne
    peles tilbake til en kilde - kan de ikke det, er de en risiko."""
    kilde = tall_i(kildegrunnlag)
    ut: list[str] = []
    for n in tall_i(body):
        if n in kilde:
            continue
        try:
            v = float(n)
        except ValueError:
            continue
        if 1900 <= v <= 2100 and v == int(v):   # aarstall
            continue
        if 0 <= v <= 31 and v == int(v):        # sma heltall
            continue
        ut.append(n)
    return sorted(ut, key=lambda x: (len(x), x))


def nok_grunnlag(case_dict: dict) -> tuple[bool, list[str]]:
    """Sufficient-context-gate: er det nok her til at noen bor skrive en sak?

    Kjores FOER journalisten bruker tid. Returnerer (ok, mangler). Dette er
    bevisst mekanisk - ingen modell far avgjore om den har nok kontekst, fordi
    den systematisk svarer ja."""
    mangler: list[str] = []
    if not (case_dict.get("finding") or "").strip():
        mangler.append("mangler selve funnet i klartekst")
    if not (case_dict.get("metric_value") or "").strip():
        mangler.append("mangler tallet")
    if not (case_dict.get("data_url") or "").strip():
        mangler.append("mangler lenke til datakilden")
    if not (case_dict.get("data_source") or "").strip():
        mangler.append("mangler navn paa datakilden")
    if (case_dict.get("coverage_status") or "unknown") == "unknown":
        mangler.append("dekningssjekken kom ikke igjennom")
    return (not mangler), mangler


def prosessnotat(case_dict: dict, *, leverandor: str, godkjent_av: str = "") -> str:
    """Kort, konkret notat om hvordan KI ble brukt.

    Research-funn: 81-84 % av lesere vil ha aapenhet, og 78 % av dem ber om et
    forklarende PROSESSNOTAT framfor en ettordsetikett - men svaert detaljerte
    avsloringer kan koste mer tillit enn korte. Derfor: presist og kort."""
    kilde = case_dict.get("data_source") or "aapen statistikk"
    url = case_dict.get("data_url") or ""
    deler = [
        f"Tallene er hentet fra {kilde}" + (f" ({url})" if url else "") + ".",
        f"{leverandor} foreslo vinkler og skrev et utkast.",
    ]
    if godkjent_av:
        deler.append(f"{godkjent_av} valgte vinkel og godkjente saken.")
    deler.append("Teksten er et utkast og maa faktasjekkes for publisering.")
    return " ".join(deler)
