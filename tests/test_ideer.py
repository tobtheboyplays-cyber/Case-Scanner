"""Ideer for Tobias — fra kommentarfeltet nederst til fanen øverst.

Eieren 26.07.2026: «Legg til ideer for Tobias. Legg det helt nederst. Er
kommentar felt så står det ideer for Tobias over. Så kan han skrive det, trykker
send. Og den blir lagret på en av fanene der det står ideer til Tobias.»

Testene her går gjennom EKTE HTTP mot appen — skjemaet postes, redirecten følges,
og påstandene handler om hva som faktisk står i HTML-en. Grunnen er den samme som
i test_ende_til_ende.py: en test som bytter ut lagringen og måler at ruten kaller
den, ville vært grønn selv om malen aldri tegnet feltet.

Én ting testes med vilje i to lag: at fanen kommer SIST. Rekkefølgen er et løfte
til journalisten — ideene skal aldri dytte konkursene ut av synsfeltet — og den
kan brytes både i `faner.bygg()` og av en sorteringslinje lagt til senere.
"""

from __future__ import annotations

from urllib.parse import urlencode

import pytest
from app import faner
from fastapi.testclient import TestClient


def klient(tmp_path, monkeypatch) -> TestClient:
    from app import main, storage

    monkeypatch.setattr(storage, "DB_PATH", str(tmp_path / "t.sqlite3"))
    monkeypatch.setattr(main, "ENABLE_AI", False)
    return TestClient(main.app)


def send(c: TestClient, tekst: str, tilbake: str = "/"):
    """POST med manuelt UTF-8-kodet kropp.

    TestClient/httpx mangler ikke-ASCII i `data=`-felt — en tidligere test
    trodde den sendte «bør» og sendte noe annet, og påstanden ble meningsløs.
    """
    return c.post(
        "/ideer",
        content=urlencode({"tekst": tekst, "tilbake": tilbake}, encoding="utf-8"),
        headers={"content-type": "application/x-www-form-urlencoded"},
        follow_redirects=False,
    )


# ── Lagringen ──────────────────────────────────────────────────────────────


def test_lagres_og_kommer_tilbake(tmp_path, monkeypatch):
    from app import storage

    monkeypatch.setattr(storage, "DB_PATH", str(tmp_path / "t.sqlite3"))
    ok, grunn = storage.ide_legg_til("Sjekk om studentboligene står tomme")
    assert ok, grunn
    lista = storage.ide_liste()
    assert [i["tekst"] for i in lista] == ["Sjekk om studentboligene står tomme"]
    assert lista[0]["lest"] is False


def test_nyeste_foerst(tmp_path, monkeypatch):
    """Den ferskeste tanken er den han vil se øverst."""
    from app import storage

    monkeypatch.setattr(storage, "DB_PATH", str(tmp_path / "t.sqlite3"))
    for t in ("først", "så", "sist"):
        storage.ide_legg_til(t)
    assert [i["tekst"] for i in storage.ide_liste()] == ["sist", "så", "først"]


@pytest.mark.parametrize("tom", ["", "   ", "\n\t "])
def test_tomt_felt_lagrer_ingenting(tmp_path, monkeypatch, tom):
    """Et uhell med send-knappen skal ikke fylle fanen med blanke rader."""
    from app import storage

    monkeypatch.setattr(storage, "DB_PATH", str(tmp_path / "t.sqlite3"))
    ok, grunn = storage.ide_legg_til(tom)
    assert not ok
    assert grunn
    assert storage.ide_liste() == []


def test_lang_tekst_klippes_i_stedet_for_aa_kraesje(tmp_path, monkeypatch):
    from app import storage

    monkeypatch.setattr(storage, "DB_PATH", str(tmp_path / "t.sqlite3"))
    assert storage.ide_legg_til("a" * 9000)[0]
    assert len(storage.ide_liste()[0]["tekst"]) == storage.MAKS_IDE


def test_lista_vokser_ikke_i_det_uendelige(tmp_path, monkeypatch):
    from app import storage

    monkeypatch.setattr(storage, "DB_PATH", str(tmp_path / "t.sqlite3"))
    for i in range(storage.MAKS_IDEER + 15):
        storage.ide_legg_til(f"idé {i}")
    lista = storage.ide_liste()
    assert len(lista) == storage.MAKS_IDEER
    # Det er de ELDSTE som ryker, ikke de nyeste.
    assert lista[0]["tekst"] == f"idé {storage.MAKS_IDEER + 14}"


def test_slett_fjerner_bare_én(tmp_path, monkeypatch):
    from app import storage

    monkeypatch.setattr(storage, "DB_PATH", str(tmp_path / "t.sqlite3"))
    storage.ide_legg_til("behold")
    storage.ide_legg_til("slett")
    mål = storage.ide_liste()[0]["id"]
    storage.ide_slett(mål)
    assert [i["tekst"] for i in storage.ide_liste()] == ["behold"]


# ── Fanen ──────────────────────────────────────────────────────────────────


def hendelse():
    return {"type": "konkurs", "navn": "Kafe As", "kommune": "Stavanger",
            "dager_siden": 3, "orgnr": "1", "dato": "2026-07-20"}


def varsel():
    return {"tittel": "Byggeareal", "emne": "bygg-bolig-og-eiendom",
            "dager_til": 5, "lenke": "https://ssb.no/x", "kontakter": []}


def ide(id_=1, tekst="test", lest=False):
    return {"id": id_, "tekst": tekst, "lagt_inn": "2026-07-26T09:00:00", "lest": lest}


def test_ingen_ideer_gir_ingen_fane():
    f = faner.bygg([hendelse()], [varsel()], [])
    assert "ideer" not in [x["slug"] for x in f]


def test_fanen_kommer_sist():
    """Ideene skal aldri skyve konkursene ut av synsfeltet."""
    f = faner.bygg([hendelse()], [varsel()], [ide()])
    assert [x["slug"] for x in f][-1] == "ideer"
    assert len(f) == 3


def test_fanen_staar_sist_ogsaa_naar_den_er_stoerst():
    """Sorteringen ellers er «flest først» — ideene skal ikke arve den."""
    mange = [ide(i, f"idé {i}") for i in range(1, 40)]
    f = faner.bygg([hendelse()], [varsel()], mange)
    assert [x["slug"] for x in f][-1] == "ideer"


def test_ulest_teller_som_nytt():
    f = faner.bygg([], [], [ide(1, "ny"), ide(2, "sett", lest=True)])
    fane = f[-1]
    assert fane["nytt"] == 1
    assert fane["antall"] == 2


def test_rad_id_beholdes_saa_sletteknappen_har_noe_aa_peke_paa():
    """`id` blir en tekstnøkkel for fanesystemet; `ide_id` er raden i basen."""
    f = faner.bygg([], [], [ide(7, "x")])
    e = f[-1]["elementer"][0]
    assert e["id"] == "i:7"
    assert e["ide_id"] == 7
    assert e["slag"] == "ide"


# ── Hele veien: skjema → base → skjerm ─────────────────────────────────────


def test_send_lagrer_og_viser_ideen_paa_sida(tmp_path, monkeypatch):
    c = klient(tmp_path, monkeypatch)

    r = send(c, "Kan den sjekke byggesaker i Stavanger kommune?")
    assert r.status_code == 303
    assert r.headers["location"].endswith("#ideer")

    html = c.get("/").text
    assert "Kan den sjekke byggesaker i Stavanger kommune?" in html
    assert "Ideer til Tobias" in html


def test_kvittering_vises_etter_send(tmp_path, monkeypatch):
    """Uten skann finnes ikke fanen — da MÅ boksen selv si at det gikk bra.

    En idé som ser ut til å forsvinne blir ikke skrevet på nytt; den blir ikke
    skrevet i det hele tatt.
    """
    c = klient(tmp_path, monkeypatch)
    mål = send(c, "noe").headers["location"]
    assert "sendt=1" in mål
    assert "Sendt" in c.get(mål).text


def test_tom_sending_sier_fra_i_stedet_for_aa_late_som(tmp_path, monkeypatch):
    c = klient(tmp_path, monkeypatch)
    mål = send(c, "   ").headers["location"]
    assert "tomt=1" in mål
    assert "Skriv noe først." in c.get(mål).text


def test_tilbake_med_spoersmaalstegn_faar_ikke_to(tmp_path, monkeypatch):
    """`/?ym=..` + `sendt=1` ble til `/?ym=..?sendt=1` i første utkast — og da
    var `sendt` en del av verdien til `ym`, ikke et eget parameter."""
    c = klient(tmp_path, monkeypatch)
    mål = send(c, "noe", tilbake="/?ym=2026-08").headers["location"]
    assert mål.count("?") == 1
    assert "&sendt=1" in mål


def test_skjemaet_staar_nederst_paa_sida(tmp_path, monkeypatch):
    """Eieren: «legg det helt nederst». Under fanepanelet, ikke over.

    Målt på rekkefølgen i HTML-en og ikke på CSS: en `order:`-regel kan flytte
    boksen visuelt, men skjermlesere og tastaturnavigasjon følger dokumentet.
    """
    c = klient(tmp_path, monkeypatch)
    send(c, "noe, så fanepanelet finnes")
    html = c.get("/").text
    assert html.index("Ideer for Tobias") > html.index('class="temafaner"')


def test_skjemaet_finnes_ogsaa_uten_skann(tmp_path, monkeypatch):
    """En idé kommer like gjerne når radaren var tom — ofte nettopp da."""
    c = klient(tmp_path, monkeypatch)
    html = c.get("/").text
    assert "Ingen skann ennå" in html          # ingen data i basen
    assert 'action="/ideer"' in html


def test_teksten_blir_ikke_tolket_som_html(tmp_path, monkeypatch):
    """Feltet er fritekst fra en annen person. Jinja escaper som standard —
    denne testen er vakten mot at noen senere setter `|safe` på den."""
    c = klient(tmp_path, monkeypatch)
    send(c, "<script>alert(1)</script>")
    html = c.get("/").text
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_slett_fra_sida(tmp_path, monkeypatch):
    c = klient(tmp_path, monkeypatch)
    send(c, "en idé som skal bort")

    from app import storage

    ide_id = storage.ide_liste()[0]["id"]
    r = c.post(f"/ideer/{ide_id}/slett", data={"tilbake": "/"},
               follow_redirects=False)
    assert r.status_code == 303
    assert "en idé som skal bort" not in c.get("/").text
