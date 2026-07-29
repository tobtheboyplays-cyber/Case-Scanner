"""Brønnøysund-kollektoren: hva som åpner og hva som går under.

Eieren ba om at «hva som kommer» også skulle vise at en butikk eller restaurant
åpner, eller at noe skal rives på grunn av konkurs. SSB gir tall som allerede er
talt opp; dette gir hendelser man kan ringe på samme dag.

Testene her vokter de tre tingene som måtte verifiseres mot ekte API-svar, og
som alle ville gitt feil på en måte ingen oppdager.
"""

from __future__ import annotations

from datetime import date

import pytest
from app.collectors import brreg


def enhet(**kw) -> dict:
    """En Brreg-enhet med de feltene kollektoren faktisk leser."""
    base = {
        "navn": "TESTBEDRIFT AS",
        "organisasjonsnummer": "123456789",
        "organisasjonsform": {"kode": "AS", "beskrivelse": "Aksjeselskap"},
        "naeringskode1": {"kode": "56.101", "beskrivelse": "Drift av restauranter"},
    }
    return {**base, **kw}


@pytest.fixture()
def svar(monkeypatch):
    """La kollektoren se nøyaktig de enhetene testen bestemmer.

    Svarer KUN for Stavanger (1103). Kollektoren spør to kommuner, så uten det
    ville hver testenhet telt dobbelt — og testene målt noe annet enn de tror."""
    def sett(per_sporring: dict[str, list[dict]]):
        def falsk(params):
            if params.get("kommunenummer") != "1103":
                return []
            for noekkel, enheter in per_sporring.items():
                if noekkel in params:
                    return enheter
            return []
        monkeypatch.setattr(brreg, "_hent", falsk)
    return sett


@pytest.fixture(autouse=True)
def uten_regnskap(monkeypatch):
    """Regnskapsoppslaget er et EKSTRA HTTP-kall per hendelse. Nettverksvakten i
    conftest stopper det (som den skal), så det stubbes av her — testene som
    faktisk handler om regnskap overstyrer selv."""
    monkeypatch.setattr(brreg, "_regnskap", lambda orgnr: None)


I_DAG = date(2026, 7, 26)


# ── Felle 1: konkursbo er ikke en nyåpning ──────────────────────────────────


def test_konkursbo_regnes_ikke_som_ny_virksomhet(svar):
    """Verifisert mot ekte data 26.07.2026: når et selskap går konkurs,
    opprettes det automatisk et konkursbo som EGEN enhet med fersk
    registreringsdato.

    «BLÅVEISEN BLOMSTER AS KONKURSBO» ville altså dukket opp som «ny
    blomsterbutikk åpnet» — stikk motsatt av sannheten. Det er den verste
    varianten av feil: den ser ut som en god sak."""
    svar({"fraRegistreringsdatoEnhetsregisteret": [
        enhet(navn="BLÅVEISEN BLOMSTER AS KONKURSBO",
              organisasjonsform={"kode": "KBO", "beskrivelse": "Konkursbo"},
              registreringsdatoEnhetsregisteret="2026-07-20"),
        enhet(navn="EKTE KAFE AS", registreringsdatoEnhetsregisteret="2026-07-20"),
    ]})
    h, _ = brreg.collect(i_dag=I_DAG)
    navn = [x["navn"] for x in h]
    assert not any("Konkursbo" in n for n in navn), navn
    assert any("Ekte Kafe" in n for n in navn)


def test_da_selskaper_beholdes(svar):
    """DA er en helt vanlig selskapsform for små butikker og frisører. Å
    filtrere den bort ville fjernet nettopp de publikumsnære virksomhetene."""
    svar({"fraRegistreringsdatoEnhetsregisteret": [
        enhet(navn="PREUS FRISØR DA",
              organisasjonsform={"kode": "DA", "beskrivelse": "Ansvarlig selskap"},
              naeringskode1={"kode": "96.021", "beskrivelse": "Frisering"},
              registreringsdatoEnhetsregisteret="2026-07-20"),
    ]})
    h, _ = brreg.collect(i_dag=I_DAG)
    assert len(h) == 1 and h[0]["publikum"] == "frisør og personlig tjeneste"


# ── Felle 2: «er konkurs nå» er ikke «gikk konkurs nylig» ───────────────────


def test_gamle_konkurser_faller_ut(svar):
    """`konkurs=true` gir alle som ER konkurs — også fra 1995. Uten datofilter
    ville journalisten fått 30 år gamle selskaper servert som nyheter."""
    svar({"konkurs": [
        enhet(navn="GAMMEL AS", konkursdato="1995-02-19"),
        enhet(navn="FERSK AS", konkursdato="2026-07-17"),
    ]})
    h, _ = brreg.collect(i_dag=I_DAG)
    navn = [x["navn"] for x in h]
    assert "Fersk As" in navn
    assert "Gammel As" not in navn, navn


def test_enhet_uten_dato_kaster_ikke(svar):
    """Et manglende eller ugyldig datofelt skal droppe enheten, ikke skannet."""
    svar({"konkurs": [
        enhet(navn="UTEN DATO AS"),
        enhet(navn="RAR DATO AS", konkursdato="ikke-en-dato"),
        enhet(navn="OK AS", konkursdato="2026-07-17"),
    ]})
    h, _ = brreg.collect(i_dag=I_DAG)
    assert [x["navn"] for x in h] == ["Ok As"]


def test_konkurs_teller_ikke_ogsaa_som_avvikling(svar):
    """Et selskap er ofte BÅDE under avvikling og konkurs. Da er konkursen den
    sterkeste opplysningen — ellers står samme firma to ganger i lista."""
    felles = enhet(navn="DOBBEL AS", konkursdato="2026-07-17",
                   underAvviklingDato="2026-07-10", konkurs=True, underAvvikling=True)
    svar({"konkurs": [felles], "underAvvikling": [felles]})
    h, _ = brreg.collect(i_dag=I_DAG)
    assert len(h) == 1 and h[0]["type"] == "konkurs"


# ── Vekting: det folk ser i gata skal opp ───────────────────────────────────


def test_publikumsnaere_bransjer_veier_tyngst(svar):
    """159 nyregistreringer på 30 dager er stort sett konsulent- og
    holdingselskaper. En restaurant er en sak; «Bedriftsrådgivning AS» er det
    ikke. NACE-koden skiller dem langt mer pålitelig enn ord i beskrivelsen."""
    svar({"fraRegistreringsdatoEnhetsregisteret": [
        enhet(navn="KONSULENT AS",
              naeringskode1={"kode": "70.220", "beskrivelse": "Bedriftsrådgivning"},
              registreringsdatoEnhetsregisteret="2026-07-25"),
        enhet(navn="NY RESTAURANT AS", registreringsdatoEnhetsregisteret="2026-07-25"),
    ]})
    h, _ = brreg.collect(i_dag=I_DAG)
    assert h[0]["navn"] == "Ny Restaurant As", [x["navn"] for x in h]
    assert h[0]["publikum"] == "restaurant og servering"
    assert h[1]["publikum"] == ""      # konsulenten er med, men bakerst


def test_hendelsen_har_lenke_til_ekte_oppslag(svar):
    svar({"konkurs": [enhet(organisasjonsnummer="921456875", konkursdato="2026-07-17")]})
    h, _ = brreg.collect(i_dag=I_DAG)
    assert h[0]["lenke"].endswith("/921456875")


# ── Fail-soft: en død kilde skal aldri velte et skann ───────────────────────


def test_en_kommune_som_feiler_stopper_ikke_resten(monkeypatch):
    def av_og_til(params):
        if params.get("kommunenummer") == "1103":
            raise ConnectionError("nede")
        if "konkurs" in params:
            return [enhet(navn="OVERLEVDE AS", konkursdato="2026-07-17")]
        return []

    monkeypatch.setattr(brreg, "_hent", av_og_til)
    h, status = brreg.collect(i_dag=I_DAG)
    assert any("[FEIL]" in s for s in status), status
    assert any(x["navn"] == "Overlevde As" for x in h), "andre kommune ga ingenting"


# ── Regnskapstall: det som gjør en konkurs til en sak ───────────────────────


def test_regnskap_legges_paa_konkurser(svar, monkeypatch):
    """«Firma X gikk konkurs» er en notis. «Firma X omsatte for 4,1 millioner og
    gikk med underskudd året før» er noe en journalist kan ringe på."""
    svar({"konkurs": [enhet(organisasjonsnummer="916029802", konkursdato="2026-07-17")]})
    monkeypatch.setattr(brreg, "_regnskap", lambda o: {
        "aar": "2024", "omsetning": 4125952.0, "resultat": -78790.0})
    h, _ = brreg.collect(i_dag=I_DAG)
    assert h[0]["regnskap"]["omsetning"] == 4125952.0


def test_nye_foretak_slipper_regnskapskallet(svar, monkeypatch):
    """Et foretak registrert for tre uker siden har ikke levert årsregnskap.
    Å spørre er et bortkastet HTTP-kall per hendelse — og skanntid."""
    kall = []
    svar({"fraRegistreringsdatoEnhetsregisteret": [
        enhet(registreringsdatoEnhetsregisteret="2026-07-20")]})
    monkeypatch.setattr(brreg, "_regnskap", lambda o: kall.append(o) or None)
    brreg.collect(i_dag=I_DAG)
    assert kall == [], f"spurte om regnskap for nyregistrerte: {kall}"


def test_manglende_regnskap_fjerner_ikke_hendelsen(svar, monkeypatch):
    """Små og ferske foretak mangler ofte regnskap. Da skal hendelsen stå uten
    tall — ikke forsvinne."""
    svar({"konkurs": [enhet(konkursdato="2026-07-17")]})
    monkeypatch.setattr(brreg, "_regnskap", lambda o: None)
    h, _ = brreg.collect(i_dag=I_DAG)
    assert len(h) == 1 and "regnskap" not in h[0]
