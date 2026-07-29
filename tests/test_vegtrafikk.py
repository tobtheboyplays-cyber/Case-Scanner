"""Vegvesenets tellepunkter — regnestykket, og de tre fellene i dataene.

Eieren 26.07.2026: «Flere Stavanger kilder du kan legge til.»

Den viktigste testen her er `test_delvis_maalt_doegn_teller_ikke`. Første ekte
kjøring meldte «Sykkelstamvegen 62 % opp mot i fjor» — men flere av
fjorårsdøgnene var målt med 67 prosent dekning, så fjorårssnittet var kunstig
lavt og hele endringen blåst opp. Det tallet ville stått på trykk.

Testene bygger svarene på det EKTE svarformatet fra API-et (verifisert mot
`trafikkdata-api.atlas.vegvesen.no` 26.07.2026), ikke på en forenklet form. En
attrapp som er enklere enn virkeligheten beviser ingenting om virkeligheten.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
from app.collectors import vegtrafikk


class Svar:
    def __init__(self, kropp: dict) -> None:
        self._k = kropp
        self.status_code = 200

    def json(self) -> dict:
        return self._k

    def raise_for_status(self) -> None:
        return None


def punkt(pid: str, navn: str, kommune: str = "Stavanger") -> dict:
    return {"id": pid, "name": navn, "location": {"municipality": {"name": kommune}}}


def doegn(volum: int | None, dekning: float | None = 100.0) -> dict:
    """Én node i `byDay`, i API-ets egen form.

    `volumeNumbers: null` er hvordan et dødt punkt faktisk svarer — ikke med en
    feilkode. «Kannik (sykkel)» sto som `isOperational: true` og ga 14 slike på
    rad.
    """
    tall = None if volum is None else {"volume": volum}
    return {"node": {"total": {
        "volumeNumbers": tall,
        "coverage": None if dekning is None else {"percentage": dekning},
    }}}


def nett(punkter: list[dict], serier: dict[str, list[dict]], monkeypatch):
    """Fake API: første POST gir punktlista, deretter volumene per alias.

    `serier` er {punkt-id: [doegn(...), ...]} og brukes for BEGGE årene med
    mindre id-en finnes med suffikset `:fjor`.
    """
    kall = {"n": 0}

    def post(url: str, **kw):
        sporsmaal = kw["json"]["query"]
        kall["n"] += 1
        if "trafficRegistrationPoints" in sporsmaal:
            # Kollektoren spør per type; vi svarer bare på sykkel.
            if "BICYCLE" not in sporsmaal:
                return Svar({"data": {"trafficRegistrationPoints": []}})
            return Svar({"data": {"trafficRegistrationPoints": punkter}})
        # Volumkall. Hvilket år? Datoene står i spørringen som `"2026-07-08T…`,
        # så vi ser etter årstallet rett etter et hermetegn — ikke etter en
        # bindestrek, som første utkast gjorde. Da traff mønsteret aldri, og
        # begge årene fikk årets serie.
        i_aar = datetime.now(tz=UTC).year
        fjor = f'"{i_aar - 1}-' in sporsmaal
        ut = {}
        for i, p in enumerate(punkter):
            nokkel = f"{p['id']}:fjor" if fjor else p["id"]
            kanter = serier.get(nokkel, serier.get(p["id"], []))
            ut[f"p{i}"] = {"volume": {"byDay": {"edges": kanter}}}
        return Svar({"data": ut})

    monkeypatch.setattr(httpx, "post", post)
    return kall


TEMA = ["transport og reiseliv"]


# ── Temavalget ─────────────────────────────────────────────────────────────


def test_hopper_over_utenfor_temavalget(monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda *a, **k: pytest.fail(
        "kilden ble spurt selv om temaet ikke var valgt"))
    cases, status = vegtrafikk.collect(["helse"])
    assert cases == []
    assert "hoppet over" in status[0]


def test_tomt_temavalg_betyr_alle(monkeypatch):
    nett([], {}, monkeypatch)
    cases, _ = vegtrafikk.collect([])
    assert cases == []          # ingen punkter, men den SPURTE


# ── Regnestykket ───────────────────────────────────────────────────────────


def test_stor_oekning_blir_en_sak(monkeypatch):
    nett([punkt("A", "Sykkelstamvegen: Asser jåtten bru sør")],
         {"A": [doegn(1000)] * 14, "A:fjor": [doegn(600)] * 14}, monkeypatch)
    cases, _ = vegtrafikk.collect(TEMA)
    assert len(cases) == 1
    c = cases[0]
    assert "67 %" in c.title and "opp" in c.title
    assert "1000" in c.finding and "600" in c.finding
    assert c.data_source.startswith("Statens vegvesen")


def test_nedgang_sies_som_nedgang(monkeypatch):
    nett([punkt("A", "Bybrua øst")],
         {"A": [doegn(400)] * 14, "A:fjor": [doegn(800)] * 14}, monkeypatch)
    cases, _ = vegtrafikk.collect(TEMA)
    assert "ned" in cases[0].title
    assert "50 %" in cases[0].title


def test_liten_endring_er_ingen_sak(monkeypatch):
    """Trafikk svinger med vær og ferie. 10 % er en tirsdag, ikke en nyhet."""
    nett([punkt("A", "Lassa sykkel")],
         {"A": [doegn(1000)] * 14, "A:fjor": [doegn(920)] * 14}, monkeypatch)
    cases, status = vegtrafikk.collect(TEMA)
    assert cases == []
    assert any("ingen sak" in s for s in status)


def test_smaa_punkter_gir_ikke_sak(monkeypatch):
    """Et punkt med 20 syklister i døgnet kan doble seg av at det slutter å regne."""
    nett([punkt("A", "Bråstein (sykkel)")],
         {"A": [doegn(40)] * 14, "A:fjor": [doegn(10)] * 14}, monkeypatch)
    assert vegtrafikk.collect(TEMA)[0] == []


# ── De tre fellene i dataene ───────────────────────────────────────────────


def test_doedt_punkt_gir_ingen_sak(monkeypatch):
    """`volumeNumbers: null` er hvordan et dødt punkt svarer — ikke med feil."""
    nett([punkt("A", "Kannik (sykkel)")],
         {"A": [doegn(None)] * 14, "A:fjor": [doegn(600)] * 14}, monkeypatch)
    assert vegtrafikk.collect(TEMA)[0] == []


def test_delvis_maalt_doegn_teller_ikke(monkeypatch):
    """DEN VIKTIGSTE. Et døgn målt til 67 % er ufullstendig, ikke lavt.

    Fjoråret her har 14 døgn, men bare 4 er komplett målt. Tas de delvise med,
    blir fjorårssnittet ~343 og «økningen» 191 %. Riktig svar er å la være å
    lage en sak i det hele tatt — det er for få komplette døgn til å
    sammenligne.
    """
    fjor = [doegn(600)] * 4 + [doegn(200, dekning=67.0)] * 10
    nett([punkt("A", "Sykkelstamvegen: Asser jåtten bru sør")],
         {"A": [doegn(1000)] * 14, "A:fjor": fjor}, monkeypatch)
    cases, _ = vegtrafikk.collect(TEMA)
    assert cases == [], f"delvis målte døgn ble regnet med: {cases and cases[0].title}"


def test_dekning_uten_verdi_teller_ikke(monkeypatch):
    """`coverage: null` er ukjent dekning, og ukjent er ikke det samme som full."""
    nett([punkt("A", "Hillevåg sykkel")],
         {"A": [doegn(1000)] * 14,
          "A:fjor": [doegn(600)] * 4 + [doegn(600, dekning=None)] * 10}, monkeypatch)
    assert vegtrafikk.collect(TEMA)[0] == []


def test_for_faa_doegn_gir_ingen_sak(monkeypatch):
    nett([punkt("A", "Hoveveien sykkel")],
         {"A": [doegn(1000)] * 5, "A:fjor": [doegn(600)] * 14}, monkeypatch)
    assert vegtrafikk.collect(TEMA)[0] == []


# ── Utvalget ───────────────────────────────────────────────────────────────


def test_bare_storbyomraadet(monkeypatch):
    """Rogaland har 245 punkter. Leserne kjenner ikke igjen de fleste stedsnavn."""
    nett([punkt("A", "Krossmoen", kommune="Eigersund")],
         {"A": [doegn(1000)] * 14, "A:fjor": [doegn(600)] * 14}, monkeypatch)
    cases, status = vegtrafikk.collect(TEMA)
    assert cases == []
    assert any("ingen bicycle-punkter" in s for s in status)


def test_stoerste_endring_vinner(monkeypatch):
    nett([punkt("A", "Lassa sykkel"), punkt("B", "Bybrua øst")],
         {"A": [doegn(1000)] * 14, "A:fjor": [doegn(800)] * 14,
          "B": [doegn(1000)] * 14, "B:fjor": [doegn(400)] * 14}, monkeypatch)
    cases, _ = vegtrafikk.collect(TEMA)
    assert "Bybrua" in cases[0].title


def test_dagtallene_oppgis_for_begge_aar(monkeypatch):
    """Første utkast skrev bare årets antall døgn, og lot det se ut som
    fjoråret var like godt målt. Det er nettopp der en slik sammenligning
    kan bomme."""
    nett([punkt("A", "Siddishallen Sykkel")],
         {"A": [doegn(1000)] * 14,
          "A:fjor": [doegn(600)] * 11 + [doegn(600, dekning=50.0)] * 3}, monkeypatch)
    funn = vegtrafikk.collect(TEMA)[0][0].finding
    assert "14 komplett målte døgn i år og 11 i fjor" in funn


def test_navnet_sier_ikke_sykkel_to_ganger(monkeypatch):
    nett([punkt("A", "Siddishallen Sykkel")],
         {"A": [doegn(1000)] * 14, "A:fjor": [doegn(600)] * 14}, monkeypatch)
    t = vegtrafikk.collect(TEMA)[0][0].title
    assert t.startswith("Sykkeltrafikken ved Siddishallen ")


# ── Fail-soft ──────────────────────────────────────────────────────────────


def test_kilden_nede_stopper_ikke_skannet(monkeypatch):
    def sprekk(*_a, **_k):
        raise httpx.ConnectError("nede")

    monkeypatch.setattr(httpx, "post", sprekk)
    cases, status = vegtrafikk.collect(TEMA)
    assert cases == []
    assert any("[FEIL]" in s for s in status)


def test_graphql_feil_er_ikke_et_krasj(monkeypatch):
    monkeypatch.setattr(httpx, "post",
                        lambda *a, **k: Svar({"errors": [{"message": "ugyldig"}]}))
    cases, status = vegtrafikk.collect(TEMA)
    assert cases == []
    assert any("[FEIL]" in s for s in status)
