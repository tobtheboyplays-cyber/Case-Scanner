"""Tallene i funnene — lesbare, men fortsatt eksakte.

Eieren 26.07.2026, i tre meldinger:

    «Viktig at vi skjønner hva faktaen er, så kan gjerne forenkle faktaen.»
    «Gjerne oversett tallene med at faktaen er barn kan forstå.»
    «Så gjør at alle faktaene som du finner blir oversatt automatisk.»

Den farligste testen her er `test_roerer_ikke_*`. En omskriving som treffer et
årstall, et organisasjonsnummer eller en tabell-ID ødelegger kildehenvisningen —
og en kildehenvisning som er feil er verre enn et tall som er tungt å lese.
"""

from __future__ import annotations

import pytest
from app import tall

# ── Store tall i ord ────────────────────────────────────────────────────────


@pytest.mark.parametrize("verdi,vent", [
    (40832836.0, "40,8 millioner (40 832 836)"),
    (3031484.0, "3,0 millioner (3 031 484)"),
    (2_400_000_000.0, "2,4 milliarder (2 400 000 000)"),
    (34860.0, "34 860"),        # under en million: grupperingen holder
    (65.0, "65"),
])
def test_lesbart(verdi, vent):
    assert tall.lesbart(verdi) == vent


def test_det_eksakte_tallet_folger_alltid_med():
    """Journalisten skal PUBLISERE dette. En avrunding kan ikke siteres som
    fasit, og han må kunne finne igjen tallet hos SSB."""
    assert "40 832 836" in tall.lesbart(40832836.0)


# ── Målestokken ─────────────────────────────────────────────────────────────


def test_penger_blir_kroner_om_dagen():
    assert tall.skala(3031484, "2025", "Kostnader (kr)") == \
        "Det er i snitt 8 300 kroner om dagen."


def test_hendelser_blir_per_uke():
    assert tall.skala(65, "2025", "Ulykker") == "Det er i snitt 1,2 i uka."


def test_sjeldne_hendelser_blir_per_maaned():
    assert "i måneden" in tall.skala(12, "2025", "Branner")


def test_beholdning_faar_ingen_maalestokk():
    """DEN VIKTIGSTE. «Menn i kvalifiseringsprogram: 128» er hvor mange som ER i
    programmet, ikke hvor mange som kommer til. «2,5 i uka» ville vært feil.

    Forskjellen kan ikke leses ut av tallet, bare av hva det teller — derfor er
    `_HENDELSER` en allowlist, ikke en blokkliste.
    """
    assert tall.skala(128, "2025", "Menn i kvalifiseringsprogram") == ""


@pytest.mark.parametrize("navn", [
    "Godkjent bruksareal", "Årstimer til morsmålsopplæring",
    "Andel med høyere utdanning", "Gjennomsnittlig botid",
])
def test_maal_som_ikke_er_hendelser_faar_ingen_maalestokk(navn):
    assert tall.skala(13821, "2026K2", navn) == ""


def test_ukjent_periode_gir_ingen_maalestokk():
    """Vet vi ikke hvor lang perioden er, kan vi ikke dele på den."""
    assert tall.skala(50000, "siste 30 dager", "Ulykker") == ""


def test_maalestokken_sier_i_snitt():
    """Ulykker skjer ikke jevnt utover året. «Det skjer én i uka» ville vært en
    påstand kilden ikke dekker."""
    assert tall.skala(65, "2025", "Ulykker").startswith("Det er i snitt")


def test_en_desimal_ikke_to():
    assert "1,2 i uka" in tall.skala(65, "2025", "Ulykker")
    assert "1,20" not in tall.skala(65, "2025", "Ulykker")


# ── Den automatiske omskrivingen ────────────────────────────────────────────


def test_forenkler_alle_store_tall_i_en_setning():
    ut = tall.forenkle(
        "Kostnader i Sandnes: 3 031 484 i 2025, mot 1 545 902 i 2024.")
    assert "3,0 millioner (3 031 484)" in ut
    assert "1,5 millioner (1 545 902)" in ut


def test_virker_paa_en_kilde_den_aldri_har_sett():
    """Poenget med å legge den i `run_scan`: Brønnøysund-funnet er skrevet av en
    kollektor som ikke vet at oversettelsen finnes."""
    ut = tall.forenkle("Selskapet omsatte for 4 120 500 kroner i 2025.")
    assert "4,1 millioner (4 120 500) kroner" in ut


@pytest.mark.parametrize("tekst", [
    "Kilde: SSB tabell 12139.",
    "Organisasjonsnummer 921456875",
    "I 2025, mot 2024",
    "Tellepunktet registrerte 1 039 sykler i døgnet",
    "Snittprisen blir 142,3 øre per kWh",
])
def test_roerer_ikke_det_som_ikke_er_store_tall(tekst):
    """Årstall, orgnr og tabell-ID-er skrives uten mellomrom, så mønsteret kan
    ikke treffe dem. Uten den begrensningen ble «SSB tabell 12 160» til
    «12,2 tusen», og kildehenvisningen var ødelagt."""
    assert tall.forenkle(tekst) == tekst


def test_skriver_ikke_om_et_tall_to_ganger():
    """Kjøres funnet gjennom to ganger, skal det se likt ut."""
    en = tall.forenkle("Kostnader: 3 031 484 kroner.")
    to = tall.forenkle(en)
    assert en == to, to


def test_tom_tekst_velter_ingenting():
    assert tall.forenkle("") == ""
    assert tall.forenkle(None) is None
