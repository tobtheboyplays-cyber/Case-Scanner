"""Bakgrunnsjobber med aerlig framdrift.

Hvorfor dette finnes: aa be om et utkast tar 10-30 sekunder fordi en KI-modell
skriver artikkelen. Foer dette laa hele ventetiden i en POST som blokkerte -
journalisten trykket «Be om utkast», ingenting skjedde paa skjermen, og han
trodde knappen var oedelagt. Den var ikke det. Han fikk bare ikke vite noe.

Naa startes arbeidet i en traad, og UI-et spor status.

**Om prosenten:** den er et ANSLAG basert paa hvor lang tid fasen pleier aa ta,
ikke en maaling av hvor langt modellen er kommet - det tallet finnes ikke.
Teksten ved siden av («Journalisten skriver …») er derimot alltid sann: den sier
hva som faktisk skjer akkurat naa. Prosenten kryper mot toppen av fasen sin og
naar den aldri foer fasen er over, saa den kan ikke staa og lyve paa 99 %.
"""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable
from typing import Any

# En fase er (prosent den starter paa, tekst til brukeren, antatt varighet i sek).
Fase = tuple[int, str, float]

# Vi holder ferdige jobber en stund saa UI-et rekker aa lese resultatet, men ikke
# for evig - dette er en prosess som skal kunne kjore i ukevis.
LEVETID_FERDIG = 300.0     # sekunder
MAKS_JOBBER = 200


class Jobb:
    """Én bakgrunnsoppgave. Traadsikker; UI-et leser mens arbeideren skriver."""

    def __init__(self, jobb_id: str, faser: list[Fase]) -> None:
        self.id = jobb_id
        self.faser = faser or [(0, "Arbeider …", 10.0)]
        self._laas = threading.Lock()
        self._fase = 0
        self._fase_start = time.monotonic()
        self._siste = ""
        self.status = "kjorer"          # kjorer | ferdig | feilet
        self.resultat: Any = None
        self.feil = ""
        self.ferdig_tid = 0.0

    # -- skrives av arbeideren --------------------------------------------
    def fase(self, nr: int, tekst: str = "") -> None:
        with self._laas:
            if nr > self._fase:
                self._fase = min(nr, len(self.faser) - 1)
                self._fase_start = time.monotonic()
                self._siste = ""
        if tekst:
            self.notat(tekst)

    def notat(self, tekst: str) -> None:
        """Én linje om hva som skjer NAA. Vises under fasen i UI-et.

        Prosenten er et anslag; dette er ikke. Ser brukeren «SSB-soek: gikk
        gjennom katalogside 3 av 127», vet han at noe faktisk beveger seg."""
        with self._laas:
            self._siste = tekst.strip()[:120]

    def ferdig(self, resultat: Any = None) -> None:
        with self._laas:
            self.status = "ferdig"
            self.resultat = resultat
            self.ferdig_tid = time.monotonic()

    def feilet(self, melding: str) -> None:
        with self._laas:
            self.status = "feilet"
            self.feil = melding
            self.ferdig_tid = time.monotonic()

    # -- leses av UI-et ----------------------------------------------------
    def tilstand(self) -> dict:
        with self._laas:
            if self.status == "ferdig":
                return {"status": "ferdig", "pct": 100, "tekst": "Ferdig",
                        "siste": self._siste, "feil": ""}
            if self.status == "feilet":
                return {"status": "feilet", "pct": 100, "tekst": "Stoppet",
                        "siste": self._siste, "feil": self.feil}

            start_pct, tekst, antatt = self.faser[self._fase]
            neste_pct = (
                self.faser[self._fase + 1][0] if self._fase + 1 < len(self.faser) else 99
            )
            gaatt = time.monotonic() - self._fase_start
            # Kryper mot toppen av fasen, men naar den aldri: 90 % av spennet er
            # taket. Da kan ikke baren staa og late som den er ferdig.
            andel = min(1.0, gaatt / antatt) if antatt > 0 else 1.0
            pct = start_pct + (neste_pct - start_pct) * andel * 0.9
            return {"status": "kjorer", "pct": int(pct), "tekst": tekst,
                    "siste": self._siste, "feil": ""}


_JOBBER: dict[str, Jobb] = {}
_REGISTER_LAAS = threading.Lock()


def _rydd() -> None:
    """Kast ferdige jobber som har faatt ligge lenge nok til aa bli lest."""
    naa = time.monotonic()
    doede = [
        j for j, jobb in _JOBBER.items()
        if jobb.ferdig_tid and naa - jobb.ferdig_tid > LEVETID_FERDIG
    ]
    for j in doede:
        _JOBBER.pop(j, None)
    # Nodbrems mot lekkasje hvis noe henger: kast de eldste.
    if len(_JOBBER) > MAKS_JOBBER:
        for j in list(_JOBBER)[: len(_JOBBER) - MAKS_JOBBER]:
            _JOBBER.pop(j, None)


def start(faser: list[Fase], arbeid: Callable[[Jobb], Any]) -> Jobb:
    """Kjor `arbeid` i en traad. Returnerer jobben med én gang."""
    jobb = Jobb(uuid.uuid4().hex[:12], faser)
    with _REGISTER_LAAS:
        _rydd()
        _JOBBER[jobb.id] = jobb

    def kjor() -> None:
        try:
            jobb.ferdig(arbeid(jobb))
        except Exception as exc:  # noqa: BLE001 - en daarlig jobb skal ikke velte appen
            jobb.feilet(f"{type(exc).__name__}: {exc}"[:300])

    threading.Thread(target=kjor, daemon=True, name=f"jobb-{jobb.id}").start()
    return jobb


def hent(jobb_id: str) -> Jobb | None:
    with _REGISTER_LAAS:
        return _JOBBER.get(jobb_id)


def vent(jobb: Jobb, sekunder: float) -> None:
    """Blokker til jobben er ferdig - for nettlesere uten JavaScript."""
    frist = time.monotonic() + sekunder
    while jobb.status == "kjorer" and time.monotonic() < frist:
        time.sleep(0.1)
