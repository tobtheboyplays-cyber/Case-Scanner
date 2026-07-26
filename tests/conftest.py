"""Felles testoppsett.

Én regel, og den er viktigere enn den ser ut: **ingen test skal roere den ekte
databasen.** Uten dette skrev testene til `data/case_radar.sqlite3` — journalistens
faktiske data — og leste hverandres tilstand på veien.

Det ble oppdaget da KI-hurtiglageret kom til: `run_workflow` husker nå ekte
KI-svar mellom skann, så en test som kjørte tidligere kunne gi en senere test
et «gjenbrukt» treff den aldri ba om. To ærlighetstester på KI-merkingen ble
grønne av feil grunn. Testene var ikke feil — isolasjonen manglet.
"""

from __future__ import annotations

import importlib

import pytest


@pytest.fixture(autouse=True)
def isolert_database(tmp_path, monkeypatch):
    from app import storage

    monkeypatch.setattr(storage, "DB_PATH", str(tmp_path / "test.sqlite3"))


# Kollektorer som gjør HTTP-kall. Hver av dem gjør `from ...base import http_get`,
# så navnet må patches i DERES modul — å patche base-modulen treffer ikke.
_NETTKOLLEKTORER = (
    "brreg", "coverage", "news_rss", "reddit",
    "ssb", "ssb_flytting", "ssb_kalender", "ssb_sok", "stortinget",
)


@pytest.fixture(autouse=True)
def ingen_nett(monkeypatch):
    """Ingen test skal ringe ut på ekte nett.

    Oppdaget da Brønnøysund-kollektoren kom til: `run_scan` begynte å hente fra
    et ekte API, og testsuiten gikk fra 6 til 77 sekunder uten at noen test
    feilet. Det er den farlige varianten — treg og avhengig av at en fremmed
    tjeneste er oppe, men grønn, så ingen ser det.

    Feilmeldingen sier hvilken modul som slapp gjennom, slik at neste kollektor
    ikke gjentar det. Trenger en test ekte svar, stubber den `http_get` i sin
    egen modul etterpå — den siste tilordningen vinner.
    """
    for navn in _NETTKOLLEKTORER:
        try:
            mod = importlib.import_module(f"app.collectors.{navn}")
        except ImportError:      # valgfri avhengighet mangler - da kalles den ikke
            continue
        if hasattr(mod, "http_get"):
            monkeypatch.setattr(
                mod, "http_get",
                lambda *a, _n=navn, **k: pytest.fail(
                    f"app.collectors.{_n} prøvde et ekte HTTP-kall i en test. "
                    "Stubb kilden i testen, eller legg den til i _NETTKOLLEKTORER."
                ),
            )
