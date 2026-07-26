"""Fanene i «Kommer snart» — ett tema per fane, med nytt-prikk.

Eieren 26.07.2026, med skjermbilde: «Rotete, hva skjer. Ha det slik det er med et
sånn fanesystem med forskjellige farger med ulike temaer som kan komme inn. Så kan
det komme en liten notifikasjon-ikon over den fanen der det har kommet noe nytt.»

Panelet blandet konkurser som HAR skjedd med SSB-tall som IKKE er sluppet — 52
rader der man måtte lese hver enkelt for å vite hva slags sak det var.
"""

from __future__ import annotations

from app import faner


def hendelse(navn="Kafe As", type_="konkurs", dager=3, orgnr="1"):
    return {"type": type_, "navn": navn, "kommune": "Stavanger",
            "dager_siden": dager, "orgnr": orgnr, "dato": "2026-07-20"}


def varsel(tittel="Byggeareal", emne="bygg-bolig-og-eiendom", dager=5):
    return {"tittel": tittel, "emne": emne, "dager_til": dager,
            "lenke": f"https://ssb.no/{tittel}", "kontakter": []}


def slugs(f):
    return [x["slug"] for x in f]


# ── Delingen, som er hele poenget ──────────────────────────────────────────


def test_konkurser_og_ssb_tall_havner_i_hver_sin_fane():
    f = faner.bygg([hendelse()], [varsel()])
    assert slugs(f) == ["konkurser", "bolig-og-bygg"], slugs(f)


def test_naeringsliv_staar_foerst():
    """Det man kan ringe på i dag, før det som slippes om to uker."""
    f = faner.bygg([hendelse()], [varsel(), varsel("Lønn", "arbeid-og-lonn")])
    assert slugs(f)[0] == "konkurser"


def test_konkurs_og_nyaapning_er_ikke_samme_sak():
    f = faner.bygg([hendelse(orgnr="1"), hendelse("Ny As", "nytt", 2, "2")], [])
    assert set(slugs(f)) == {"konkurser", "nyapninger"}


def test_hvert_ssb_emne_faar_sin_farge():
    """«Forskjellige farger med ulike temaer» — fargen er halve beskjeden."""
    f = faner.bygg([], [
        varsel("Bygg", "bygg-bolig-og-eiendom"),
        varsel("Lønn", "arbeid-og-lonn"),
        varsel("Priser", "priser-og-prisindekser"),
    ])
    assert len({x["farge"] for x in f}) == 3, [x["farge"] for x in f]


def test_beslektede_emner_slaas_sammen():
    """SSB skiller «arbeid-og-lonn» fra «inntekt-og-forbruk». For en journalist
    er begge lommeboka — to nesten like faner er rot, ikke oversikt."""
    f = faner.bygg([], [varsel("Lønn", "arbeid-og-lonn"),
                        varsel("Forbruk", "inntekt-og-forbruk")])
    assert len(f) == 1 and f[0]["antall"] == 2


def test_ukjent_emne_lager_ikke_sin_egen_fane():
    """Ellers får vi tolv faner med ett element i hver, og da har vi flyttet
    rotet i stedet for å fjerne det."""
    f = faner.bygg([], [varsel("Rart", "et-emne-vi-ikke-kjenner"),
                        varsel("Rart2", "enda-et-ukjent")])
    assert slugs(f) == ["annet"] and f[0]["antall"] == 2


# ── Nytt-prikken ───────────────────────────────────────────────────────────


def test_prikken_teller_bare_det_ferske():
    """Står den på alle faner, slutter man å se den."""
    f = faner.bygg([hendelse(dager=2, orgnr="1"), hendelse(dager=40, orgnr="2")], [])
    assert f[0]["antall"] == 2
    assert f[0]["nytt"] == 1, f[0]


def test_ingen_prikk_naar_ingenting_er_nytt():
    f = faner.bygg([hendelse(dager=40)], [varsel(dager=30)])
    assert all(x["nytt"] == 0 for x in f), f


def test_ssb_varsel_er_ferskt_naar_det_slippes_snart():
    """For et varsel betyr «ferskt» det samme som «nært» — det han må rekke å
    forberede, ikke det som ble lagt til i lista sist."""
    f = faner.bygg([], [varsel(dager=1), varsel("Sen", "bygg-bolig-og-eiendom", 40)])
    assert f[0]["nytt"] == 1, f[0]


# ── Sortering og tak ───────────────────────────────────────────────────────


def test_ferskeste_konkurs_oeverst():
    f = faner.bygg([hendelse("Gammel", dager=40, orgnr="1"),
                    hendelse("Fersk", dager=1, orgnr="2")], [])
    assert [e["navn"] for e in f[0]["elementer"]] == ["Fersk", "Gammel"]


def test_varselet_som_kommer_foerst_staar_oeverst():
    f = faner.bygg([], [varsel("Sen", dager=30), varsel("Snart", dager=2)])
    assert [e["tittel"] for e in f[0]["elementer"]] == ["Snart", "Sen"]


def test_taket_hindrer_at_en_fane_blir_en_vegg():
    """40 konkurser i én fane er det samme rotet, bare flyttet."""
    mange = [hendelse(f"Nr {i}", dager=i, orgnr=str(i)) for i in range(40)]
    f = faner.bygg(mange, [])
    assert len(f[0]["elementer"]) == faner.MAKS_PER_FANE
    # Totalen skal fortsatt være ærlig, ellers ser 40 ut som 12.
    assert f[0]["antall"] == 40


def test_tomt_skann_gir_ingen_faner():
    assert faner.bygg([], []) == []
    assert faner.bygg(None, None) == []


def test_hvert_element_har_en_stabil_id():
    """Nettleseren bruker id-en til å huske hva han har sett. Bygges den av
    navnet, blir alt «nytt» igjen så snart registeret retter en skrivemåte."""
    f = faner.bygg([hendelse(orgnr="921456875")], [])
    assert f[0]["elementer"][0]["id"] == "h:921456875"
