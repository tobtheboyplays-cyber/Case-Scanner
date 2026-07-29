"""Kolumbus (Entur) og MET-farevarsel — tersklene og de to fellene.

Eieren 26.07.2026: «mer kilde mer. Masse nyheter» og «redaktøren sjekker
kvaliteten og analytikeren».

Redaktøren og analytikeren avgjør *hvilken* sak som er verdt en plass. Disse
testene gjør en annen jobb: at tallet og teksten i saken er riktige når den
først når fram. Begge lagene trengs — en redaktør kan velge bort en kjedelig
sak, men ikke oppdage at et snitt er regnet på halve datagrunnlaget.

Svarene er bygget på de EKTE svarformatene, verifisert mot `api.entur.io` og
`api.met.no` 26.07.2026.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from app.collectors import farevarsel, kolumbus


class Svar:
    def __init__(self, kropp: dict, status: int = 200) -> None:
        self._k = kropp
        self.status_code = status

    def json(self) -> dict:
        return self._k

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("feil", request=None, response=None)  # type: ignore[arg-type]


# ══ Kolumbus ═══════════════════════════════════════════════════════════════


def avgang(linje="4", *, innstilt=False, sanntid=True, forsinket=0, mot="Sandnes"):
    rute = datetime.now(tz=UTC) + timedelta(hours=1)
    return {
        "aimedDepartureTime": rute.isoformat(),
        "expectedDepartureTime": (rute + timedelta(minutes=forsinket)).isoformat(),
        "cancellation": innstilt,
        "realtime": sanntid,
        "destinationDisplay": {"frontText": mot},
        "serviceJourney": {"line": {"publicCode": linje}},
    }


def entur(avganger: list[dict], monkeypatch):
    """Avgangene legges paa FOERSTE holdeplass; resten er tomme.

    Foerste utkast ga den samme lista til alle tre, og da ble hver avgang talt
    tre ganger — «1 innstilt» ble til 3 og traff terskelen. En attrapp som
    ganger opp tallene tester noe annet enn den later som.
    """
    def post(url, **kw):
        data = {f"h{i}": {"name": navn, "estimatedCalls": avganger if i == 0 else []}
                for i, (navn, _) in enumerate(kolumbus.HOLDEPLASSER)}
        return Svar({"data": data})
    monkeypatch.setattr(httpx, "post", post)


TEMA = ["transport og reiseliv"]


def test_kolumbus_hopper_over_utenfor_temavalget(monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda *a, **k: pytest.fail("ble spurt likevel"))
    assert kolumbus.collect(["helse"])[0] == []


def test_normal_drift_er_ingen_sak(monkeypatch):
    entur([avgang() for _ in range(20)], monkeypatch)
    cases, status = kolumbus.collect(TEMA)
    assert cases == []
    assert any("normal drift" in s for s in status)


def test_én_innstilt_avgang_er_ikke_en_nyhet(monkeypatch):
    """Terskelen finnes fordi en innstilt buss er en tirsdag."""
    entur([avgang(innstilt=True)] + [avgang() for _ in range(19)], monkeypatch)
    assert kolumbus.collect(TEMA)[0] == []


def test_mange_innstilte_blir_en_sak(monkeypatch):
    entur([avgang(linje=str(i), innstilt=True) for i in range(4)]
          + [avgang() for _ in range(10)], monkeypatch)
    cases, _ = kolumbus.collect(TEMA)
    assert len(cases) == 1
    assert "4 bussavganger innstilt" in cases[0].title
    assert cases[0].data_source.startswith("Kolumbus")


def test_avgang_uten_sanntid_teller_ikke_som_presis(monkeypatch):
    """DEN VIKTIGSTE FELLA. `realtime: false` betyr «ingen sanntidsdata», ikke
    «går presis» — for slike er expected bare en kopi av rutetida.

    Her har 30 av 33 avganger ingen sanntid. Tas de med i nevneren, ser en
    morgen der sanntiden er nede ut som en morgen uten problemer.
    """
    entur([avgang(sanntid=False) for _ in range(10)]
          + [avgang(sanntid=True, forsinket=25) for _ in range(1)], monkeypatch)
    _cases, status = kolumbus.collect(TEMA)
    linje = next(s for s in status if "med sanntid" in s)
    assert "(av 1 med sanntid)" in linje, linje


def test_mange_forsinkede_blir_en_sak(monkeypatch):
    entur([avgang(forsinket=20) for _ in range(8)]
          + [avgang() for _ in range(5)], monkeypatch)
    cases, _ = kolumbus.collect(TEMA)
    assert "8 bussavganger forsinket" in cases[0].title
    assert "20 minutter etter rutetid" in cases[0].finding


def test_kolumbus_nede_stopper_ikke_skannet(monkeypatch):
    def sprekk(*_a, **_k):
        raise httpx.ConnectError("nede")
    monkeypatch.setattr(httpx, "post", sprekk)
    cases, status = kolumbus.collect(TEMA)
    assert cases == []
    assert any("[FEIL]" in s for s in status)


# ══ Farevarsel ═════════════════════════════════════════════════════════════


def varsel(nivaa="3; orange; Severe", *, severity="Severe", vid="v1",
           navn="Stor skogbrannfare", omraade="Jæren"):
    return {"properties": {
        "id": vid, "awareness_level": nivaa, "severity": severity,
        "eventAwarenessName": navn, "area": omraade,
        "description": "Stor skogbrannfare inntil det kommer nedbør.",
        "consequences": "Vegetasjonen kan svært lett antennes.",
        "instruction": "Ikke bruk åpen ild.",
        "eventEndingTime": "2026-08-01T12:00:00+00:00",
    }}


def met(varsler: list[dict], monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: Svar({"features": varsler}))


MTEMA = ["natur og miljø"]


def test_nivaa_leses_av_fargeordet():
    """Feltet er «3; orange; Severe». Tallet foran er METs egen skala og er
    IKKE det samme som rangen vår — fargeordet er det entydige."""
    assert farevarsel._nivaa({"awareness_level": "2; yellow; Moderate"}) == 1
    assert farevarsel._nivaa({"awareness_level": "3; orange; Severe"}) == 2
    assert farevarsel._nivaa({"awareness_level": "4; red; Extreme"}) == 3
    assert farevarsel._nivaa({}) == 0


def test_gult_varsel_er_ikke_en_sak(monkeypatch):
    """Gult om «lokalt kraftige regnbyger» kommer stadig vekk i Rogaland."""
    met([varsel("2; yellow; Moderate", severity="Moderate")], monkeypatch)
    cases, status = farevarsel.collect(MTEMA)
    assert cases == []
    assert any("ingen over gult" in s for s in status)


def test_oransje_varsel_blir_en_sak(monkeypatch):
    met([varsel()], monkeypatch)
    cases, _ = farevarsel.collect(MTEMA)
    assert len(cases) == 1
    c = cases[0]
    assert "stor skogbrannfare" in c.title.lower()
    assert "Konsekvenser:" in c.finding and "Råd fra MET:" in c.finding
    # Ikke den interne koden på et saksforslag.
    assert c.metric_value == "oransje nivå"


def test_alvorlig_slipper_gjennom_selv_med_gul_farge(monkeypatch):
    """CAP-alvorlighet og fargeskalaen måler ikke helt det samme."""
    met([varsel("2; yellow; Moderate", severity="Extreme")], monkeypatch)
    assert len(farevarsel.collect(MTEMA)[0]) == 1


def test_samme_varsel_paa_flere_punkter_telles_én_gang(monkeypatch):
    """Tre punkter spørres. Et varsel som dekker hele byen treffer alle tre."""
    met([varsel(vid="samme")], monkeypatch)
    cases, status = farevarsel.collect(MTEMA)
    assert len(cases) == 1
    assert "1 aktive varsler" in status[0], status[0]


def test_alvorligste_varsel_vinner(monkeypatch):
    met([varsel("2; yellow; Moderate", severity="Moderate", vid="a", navn="Regn"),
         varsel("4; red; Extreme", severity="Extreme", vid="b", navn="Storm")],
        monkeypatch)
    assert "storm" in farevarsel.collect(MTEMA)[0][0].title.lower()


def test_noekkelen_er_varselets_id(monkeypatch):
    """Samme varsel skal ikke dukke opp som nytt ved hvert skann mens det står."""
    met([varsel(vid="CAP-123")], monkeypatch)
    assert farevarsel.collect(MTEMA)[0][0].key == "farevarsel:CAP-123"


def test_met_nede_stopper_ikke_skannet(monkeypatch):
    def sprekk(*_a, **_k):
        raise httpx.ConnectError("nede")
    monkeypatch.setattr(httpx, "get", sprekk)
    cases, status = farevarsel.collect(MTEMA)
    assert cases == []
    assert any("[FEIL]" in s for s in status)
