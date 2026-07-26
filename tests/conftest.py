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

import pytest


@pytest.fixture(autouse=True)
def isolert_database(tmp_path, monkeypatch):
    from app import storage

    monkeypatch.setattr(storage, "DB_PATH", str(tmp_path / "test.sqlite3"))
