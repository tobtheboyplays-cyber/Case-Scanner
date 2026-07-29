"""Nivåsporet: et tall kan være en sak uten å ha flyttet seg.

Eieren 26.07.2026: «Også kult med tall som omkostning og hvor mye folk tjener,
som kanskje kan være et sjokk.»

Søkesystemet fant bare ENDRING — minst 15 % år over år. At Stavanger ligger
langt over landssnittet på noe er ikke en endring, det er et nivå, og slike tall
ble derfor aldri funnet uansett hvor oppsiktsvekkende de var.

Målt mot ekte SSB-data etter fiksen: «Gjennomsnittlig fastsatt skatt i Stavanger:
203 200 kr, mot 157 500 for hele landet — 29 prosent høyere.»
"""

from __future__ import annotations

from app.collectors import ssb_sok as S


def kjor(verdier: dict[tuple[str, str], float | None], *, regioner=None):
    """Kjør _nivaacase med et håndlaget datasett.

    verdier: {(regionkode, metrikk): tall}
    """
    regioner = regioner or [*S.KOMMUNER, S.LANDET]
    metrikker = sorted({m for _, m in verdier})
    idx = {"Region": regioner, "ContentsCode": metrikker}

    def hent(region, periode, metrikk):
        return verdier.get((region, metrikk))

    return S._nivaacase(
        rad={"id": "12345", "label": "Testtabell"},
        idx=idx, geo="Region", metric="ContentsCode", hent=hent,
        naa_p="2024", etiketter={m: "Gjennomsnittlig lønn" for m in metrikker},
        tabell_id="12345", tittel_raa="Testtabell (K)",
    )


def test_stavanger_langt_over_landet_blir_en_sak():
    """Kjernen: 203 200 mot 157 500 er ingen endring, men det er en overskrift."""
    sak = kjor({("1103", "m"): 203200.0, ("0", "m"): 157500.0})
    assert sak is not None
    assert "29 %" in sak.title and "høyere" in sak.title
    assert "Stavanger" in sak.title
    assert "157 500" in sak.finding or "157500" in sak.finding.replace(" ", "")
    assert sak.key.startswith("ssb-nivaa:")


def test_smaa_avvik_er_ikke_en_sak():
    """En kommune ligger nesten alltid litt over eller under landet. Uten en høy
    terskel ville hver eneste tabell gitt et «funn»."""
    assert kjor({("1103", "m"): 105.0, ("0", "m"): 100.0}) is None


def test_sum_mot_del_fella_stenges():
    """Den farligste fella her: er landstallet en SUM (antall personer i Norge)
    og kommunetallet en liten del av den, er «Stavanger 99 % under Norge» ren
    aritmetikk — ikke en sak. Den ville truffet nesten hver eneste tabell."""
    assert kjor({("1103", "m"): 5000.0, ("0", "m"): 5_400_000.0}) is None


def test_kommune_over_landet_slipper_gjennom_selv_om_landet_er_stort():
    """Grensen må ikke bli så streng at ekte funn forsvinner: ligger kommunen
    OVER landssnittet, er det aldri en sum/del-effekt."""
    sak = kjor({("1103", "m"): 250.0, ("0", "m"): 100.0})
    assert sak is not None and "høyere" in sak.title


def test_uten_landstall_gir_ingenting():
    """Mangler tabellen hele landet, er dette bare ikke en slik tabell."""
    assert kjor({("1103", "m"): 900.0}, regioner=["1103"]) is None


def test_smaa_tall_forkastes_i_begge_ender():
    """Samme småtallsfelle som endringssporet: 3 mot 8 er +167 % og ren støy."""
    assert kjor({("1103", "m"): 3.0, ("0", "m"): 8.0}) is None


def test_sterkeste_avvik_vinner_og_bare_ett_funn_per_tabell():
    """Fem varianter av samme funn er støy, ikke fem leads."""
    sak = kjor({
        ("1103", "svak"): 130.0, ("0", "svak"): 100.0,
        ("1103", "sterk"): 300.0, ("0", "sterk"): 100.0,
    })
    assert sak is not None and "200 %" in sak.title


def test_lavere_enn_landet_beholdes_naar_det_er_et_snitt():
    """«Lavere enn landet» er ofte den sterkeste saken — så lenge landstallet
    åpenbart er et snitt og ikke en sum."""
    sak = kjor({("1103", "m"): 60.0, ("0", "m"): 100.0})
    assert sak is not None and "lavere" in sak.title
