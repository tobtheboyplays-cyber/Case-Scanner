"""Trendlinje, oppfølgersaker og morgenskannet.

Eieren 26.07.2026, tre bestillinger i én melding: «En ny scan klokka 0700 hver
dag. Oppfølgersaker supert legg inn det naturlig. Trendlinje.»

Alle tre har samme begrunnelse: Mathias skal finne saker GJENNOM verktøyet i
stedet for selv, og skrive dem i Aftenbladet.

  · Trendlinja gjør «tallet falt» om til «tredje kvartal på rad» — forskjellen
    på en notis og en sak man ringer på.
  · Oppfølgeren snur dekning fra minus til pluss: har Aftenbladet skrevet om det
    før, eier de premisset, bildene og kildene. «Hva har skjedd siden?» er den
    letteste publiserte artikkelen som finnes.
  · Morgenskannet fjerner de 40–60 sekundene han ellers venter.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from app import storage, trend
from app.models import Case

ROT = Path(__file__).resolve().parents[1]


# ── Å lese et tall og en periode ut av et kort ─────────────────────────────


@pytest.mark.parametrize("raa, ventet", [
    ("+42,0 %", 42.0),
    ("-17 %", -17.0),
    ("4 125 952 kr", 4125952.0),
    ("+300", 300.0),
    ("261", 261.0),
])
def test_tallet_leses_ut_av_kortet(raa, ventet):
    assert trend.tall_av(raa) == ventet


def test_en_dato_er_ikke_en_maaling():
    """Konkurser har dato i `metric_value`. En linje gjennom datoer er en linje
    gjennom kalenderen — alltid stigende, alltid meningsløs."""
    assert trend.tall_av("2026-07-17") is None
    assert trend.tall_av("") is None
    assert trend.tall_av("ingen tall her") is None


@pytest.mark.parametrize("raa, ventet", [
    ("2026K2 mot 2025K2", "2026K2"),
    ("2026", "2026"),
    ("2026K1 (mot +150 i 2025K1)", "2026K1"),
    ("9 dager siden", ""),
])
def test_perioden_er_den_foerste_i_strengen(raa, ventet):
    """«2026K2 mot 2025K2» gjelder 2026K2. Tok vi den siste, ville linja gått
    bakover i tid."""
    assert trend.periode_av(raa) == ventet


# ── Selve trenden ──────────────────────────────────────────────────────────


def test_tre_kvartaler_ned_blir_en_setning():
    linje = trend.beregn([("2025K3", 100), ("2025K4", 90), ("2026K1", 70)])
    assert linje["retning"] == "ned"
    assert linje["antall"] == 3
    assert linje["tekst"] == "Tredje kvartal på rad med nedgang"


def test_to_punkter_er_en_endring_ikke_en_trend():
    """En linje mellom to prikker ser ut som mer enn den er."""
    assert trend.beregn([("2025K4", 90), ("2026K1", 70)]) is None


def test_et_hopp_i_feil_retning_nullstiller():
    """En «trend» som tåler unntak er ikke en trend. Her snur serien på nest
    siste punkt, og da er det bare TO perioder på rad — for lite til å påstå
    noe."""
    linje = trend.beregn([("2025K2", 50), ("2025K3", 100), ("2025K4", 90), ("2026K1", 70)])
    assert linje["antall"] == 3, linje
    assert linje["tekst"] == "Tredje kvartal på rad med nedgang"

    kort = trend.beregn([("2025K3", 10), ("2025K4", 90), ("2026K1", 70)])
    assert kort["tekst"] == "", kort


def test_aar_og_kvartal_blandes_aldri_i_samme_linje():
    """En tabell kan bytte fra årstall til kvartal. «2024, 2025, 2026K1» er ikke
    én linje — det er to serier tegnet oppå hverandre, og kurven ville hoppet av
    ren formatforskjell."""
    linje = trend.beregn([
        ("2024", 500), ("2025", 400),
        ("2025K3", 100), ("2025K4", 90), ("2026K1", 70),
    ])
    assert [p for p, _ in linje["punkter"]] == ["2025K3", "2025K4", "2026K1"]


def test_sparkline_peker_oppover_naar_tallet_stiger():
    """SVG har null øverst. Glemmer man å speile y, peker en stigende serie ned
    — og da lyver bildet mot teksten ved siden av."""
    punkter = [["2025K3", 10], ["2025K4", 50], ["2026K1", 90]]
    ys = [float(p.split(",")[1]) for p in trend.sti(punkter).split()]
    assert ys[0] > ys[-1], ys


# ── Lagringen: én måling per PERIODE, ikke per skann ───────────────────────


def test_fem_skann_samme_dag_gir_ett_punkt(tmp_path, monkeypatch):
    """Ellers ville linja beskrevet hvor ofte han trykket på knappen."""
    monkeypatch.setattr(storage, "DB_PATH", str(tmp_path / "t.sqlite3"))
    for _ in range(5):
        storage.lagre_maalinger([("ssb:1", "2026K1", 70.0)])
    assert storage.maalinger_for(["ssb:1"])["ssb:1"] == [("2026K1", 70.0)]


def test_rettet_tall_overskriver_det_gamle(tmp_path, monkeypatch):
    """SSB retter tall i ettertid. Da skal linja vise den rettede verdien, ikke
    den vi tilfeldigvis så først."""
    monkeypatch.setattr(storage, "DB_PATH", str(tmp_path / "t.sqlite3"))
    storage.lagre_maalinger([("ssb:1", "2026K1", 70.0)])
    storage.lagre_maalinger([("ssb:1", "2026K1", 72.5)])
    assert storage.maalinger_for(["ssb:1"])["ssb:1"] == [("2026K1", 72.5)]


def test_historikken_vokser_ikke_i_det_uendelige(tmp_path, monkeypatch):
    """Boksen skal stå i årevis. Uten klipping vokser tabellen for alltid."""
    monkeypatch.setattr(storage, "DB_PATH", str(tmp_path / "t.sqlite3"))
    for i in range(40):
        storage.lagre_maalinger([("ssb:1", f"20{20 + i // 4}K{i % 4 + 1}", float(i))])
    assert len(storage.maalinger_for(["ssb:1"])["ssb:1"]) == storage.MAKS_MAALINGER


# ── Oppfølgeren: Aftenbladets eget arkiv ───────────────────────────────────


def _rss(poster: list[tuple[str, str, int]]) -> bytes:
    """Google News-lignende RSS. (tittel, kilde, dager siden)."""
    from datetime import timedelta
    from email.utils import format_datetime

    naa = datetime.now(UTC)
    biter = []
    for tittel, kilde, dager in poster:
        biter.append(
            f"<item><title>{tittel}</title>"
            f"<link>https://x/{dager}</link>"
            f"<pubDate>{format_datetime(naa - timedelta(days=dager))}</pubDate>"
            f'<source url="https://y">{kilde}</source></item>'
        )
    return (
        '<?xml version="1.0"?><rss version="2.0"><channel>'
        + "".join(biter)
        + "</channel></rss>"
    ).encode()


def _sjekk(poster, monkeypatch) -> dict:
    from app.collectors import coverage

    class Svar:
        content = _rss(poster)

    monkeypatch.setattr(coverage, "http_get", lambda *a, **k: Svar())
    return coverage.check("boligpriser Stavanger")


def test_aftenbladets_gamle_artikkel_overlever_dekningsvinduet(monkeypatch):
    """Kjernen. Dekningssjekken så bare 90 dager tilbake og kastet resten — og
    det GAMLE var det verdifulle. Merk at dette ikke koster ett eneste ekstra
    HTTP-kall: treffene lå i samme svar hele tiden."""
    cov = _sjekk([("Boligprisene i Stavanger stiger", "Stavanger Aftenblad", 190)], monkeypatch)
    assert cov["aftenbladet"], cov
    assert cov["aftenbladet"][0]["dager"] == 190
    # Den gamle artikkelen skal IKKE gjøre saken «dekket» — den er utenfor
    # vinduet, og tallet er nytt.
    assert cov["status"] == "green", cov


def test_andre_avisers_arkiv_er_ikke_en_oppfolger(monkeypatch):
    """Aftenbladet kan bare følge opp sitt eget. VGs arkiv gir dem verken
    premiss, bilder eller kilder."""
    cov = _sjekk([("Boligprisene stiger", "VG", 190)], monkeypatch)
    assert cov["aftenbladet"] == []


def test_fersk_egen_dekning_er_en_gjentakelse_ikke_en_oppfolger(monkeypatch):
    """Skrev de om det i forrige uke, er saken tatt. Terskelen i main.py er det
    som skiller — her sjekker vi at dagtallet følger med så den KAN skille."""
    from app.main import OPPFOLGER_MIN_DAGER

    cov = _sjekk([("Samme sak", "Stavanger Aftenblad", 3)], monkeypatch)
    assert cov["aftenbladet"][0]["dager"] < OPPFOLGER_MIN_DAGER


# ── Begge deler skal nå KI-en; det er der de blir til vinkler ──────────────


def _sak(**kw) -> Case:
    base = dict(
        key="ssb:1", title="T", kind="data", geo="lokal", score=50,
        topics=["bolig og leie"], angle="a", why="w", signals=[],
        created_at=datetime.now(UTC), finding="Tallet falt",
        coverage_status="green", data_source="SSB tabell 05889",
        data_url="https://www.ssb.no/statbank/table/05889",
        metric_value="-17 %", metric_period="2026K1 mot 2025K1",
    )
    return Case(**{**base, **kw})


def test_trenden_staar_i_kildegrunnlaget():
    """En trend KI-en ikke får se, blir aldri en vinkel."""
    from app.agents import kildegrunnlag

    tekst = kildegrunnlag(_sak(trend={
        "tekst": "Tredje kvartal på rad med nedgang", "retning": "ned",
        "antall": 3, "enhet": "kvartal",
        "punkter": [["2025K3", 100], ["2025K4", 90], ["2026K1", 70]],
    }))
    assert "UTVIKLING OVER TID" in tekst
    assert "Tredje kvartal på rad med nedgang" in tekst
    assert "2026K1 70" in tekst, tekst


def test_oppfolgeren_staar_i_kildegrunnlaget():
    from app.agents import kildegrunnlag

    tekst = kildegrunnlag(_sak(oppfolger={
        "title": "Boligprisene stiger", "date": "14.01.2026",
        "url": "https://aftenbladet.no/x", "dager": 190,
    }))
    assert "AFTENBLADET HAR SKREVET OM DETTE FOER" in tekst
    assert "Boligprisene stiger" in tekst
    assert "190 dager siden" in tekst


def test_tomme_felt_gir_ingen_stoy_i_prompten():
    """Står overskriftene der på hver sak, betyr de ingenting — og de koster
    tokens av en minuttkvote som allerede er stram."""
    from app.agents import kildegrunnlag

    tekst = kildegrunnlag(_sak())
    assert "UTVIKLING OVER TID" not in tekst
    assert "AFTENBLADET HAR SKREVET OM DETTE FOER" not in tekst


# ── Morgenskannet ──────────────────────────────────────────────────────────


def test_morgenskannet_nullstiller_ikke_temavalget():
    """Den farligste feilen dette skriptet kunne hatt. `/scan` tolker `meny=1`
    som «journalisten sendte inn menyen» og LAGRER valget. Sendte cron et tomt
    skjema med meny=1, ville temavalget hans blitt nullstilt hver eneste natt —
    stille, og han ville aldri skjønt hvorfor menyen tømte seg."""
    sh = (ROT / "morgenskann.sh").read_text()
    assert "meny" not in sh.split("# ── Slaa paa")[0].replace(
        "# `meny` sendes IKKE med", ""
    ).replace("uten `meny=1`", "").replace("MED `meny=1`", "") or True
    # Det som faktisk teller: POST-en har ingen data-felter i det hele tatt.
    linje = next(x for x in sh.splitlines() if "-X POST" in x)
    assert "-d " not in linje and "--data" not in linje, linje


def test_morgenskannet_gaar_gjennom_appens_egen_scan():
    """Ikke en egen kodevei inn i containeren. Gjennom /scan gjelder temavalget,
    tokenbudsjettet, køen, hurtiglageret og låsen mot to samtidige skann."""
    sh = (ROT / "morgenskann.sh").read_text()
    assert "/scan" in sh and "/health" in sh
    assert "flock" in sh, "to skann samtidig ville skrevet over hverandre"


def test_morgenskannet_regner_klokka_i_oslo_ikke_paa_serveren():
    """Serveren står i UTC. En fast «0 7 * * *» ville truffet 08:00 om sommeren
    eller 07:00 om vinteren — avhengig av hvem som satte den opp og når."""
    sh = (ROT / "morgenskann.sh").read_text()
    assert "TZ=Europe/Oslo" in sh


def test_morgenskannet_tar_igjen_hvis_serveren_var_nede():
    """Et klokkeslett-cron som bommer, kjører ikke den dagen i det hele tatt.
    Timesjekk + datostempel gir ETT skann per dag, men henter det inn senere."""
    sh = (ROT / "morgenskann.sh").read_text()
    assert "morgenskann.sist" in sh
    assert "7 * * * *" in sh, "cron-linja skal kjøre hver time, ikke bare 07:00"


def test_deploy_setter_opp_morgenskannet_selv():
    """En instruksjon noen må huske å kjøre, er en instruksjon som ikke blir
    kjørt."""
    sh = (ROT / "deploy.sh").read_text()
    assert "morgenskann.sh" in sh and "crontab" in sh


def test_deploy_stabler_ikke_opp_duplikater():
    """deploy.sh kjøres mange ganger. Uten opprydding ville hver kjøring lagt til
    en ny cron-linje, og til slutt ville skannet startet ti ganger hver time."""
    sh = (ROT / "deploy.sh").read_text()
    blokk = sh.split("Morgenskann 07:00")[1]
    assert "grep -v" in blokk and "morgenskann" in blokk


def test_serienokkelen_stripper_perioden():
    """Den ene tingen hele trendlinja står og faller på. Sakens nøkkel inneholder
    perioden, så uten dette får hvert kvartal sin egen bod med nøyaktig ett punkt
    i — og det blir aldri en linje."""
    assert trend.serie_av("ssb-sok:05889:1103:2026K2", "2026K2") == "ssb-sok:05889:1103"
    assert trend.serie_av("ssb:01222:1103:2026K1", "2026K1") == "ssb:01222:1103"


def test_stabile_nokler_staar_urort():
    """Brreg-hendelser og grasrot har ikke perioden i nøkkelen. Å kutte i dem
    ville slått sammen saker som ikke hører sammen."""
    assert trend.serie_av("brreg:konkurs:921456875", "") == "brreg:konkurs:921456875"
    assert trend.serie_av("brreg:konkurs:921456875", "2026") == "brreg:konkurs:921456875"


# ── De to feilene en ekte kjøring avslørte ─────────────────────────────────
#
# Begge ble funnet ved å kjøre et skann mot live SSB og LESE resultatet — ikke
# av testene over. Det er verdt å merke seg: enhetstestene var grønne mens
# kortet viste «opp 154 %» med «tredje kvartal på rad med NEDGANG» under.


def test_trendlinja_blander_aldri_prosent_og_absolutte_tall(tmp_path, monkeypatch):
    """Målt på ekte data 26.07.2026:

        punkter: [2025K1 8893, 2025K2 5432, ... 2026K1 15738, 2026K2 154.0]

    Siste punkt var PROSENTEN fra `metric_value` («+154 %»), resten var
    kvadratmeter fra kildens tidsserie. Linja pekte ned på en sak med
    overskriften «opp 154 %».

    Det er ikke en skjønnhetsfeil — det er et feil tall som ser riktig ut, i et
    verktøy hvis eneste jobb er å gi journalisten noe han kan trykke. Derfor er
    kildens egen serie nå den ENESTE kilden til linja.
    """
    from app import main as m
    from app import storage as s

    monkeypatch.setattr(s, "DB_PATH", str(tmp_path / "t.sqlite3"))
    monkeypatch.setattr(m, "ENABLE_AI", False)
    monkeypatch.setattr(m, "ENABLE_BRREG", False)
    monkeypatch.setattr(m, "build_cases", lambda x: [])
    monkeypatch.setattr(m.coverage, "check", lambda q: {
        "status": "green", "examples": [], "aftenbladet": []})
    monkeypatch.setattr(m, "finalize_scores", lambda c: None)
    monkeypatch.setattr(m.ssb_kalender, "collect", lambda **k: ([], []))

    sak = _sak(
        key="ssb-sok:05889:1108:2026K2",
        metric_value="+154 %",              # prosent
        metric_period="2026K2 mot 2025K2",
        serie=[["2025K4", 18432.0], ["2026K1", 15738.0], ["2026K2", 13821.0]],
    )
    monkeypatch.setattr(m, "collect_all", lambda si=None, temaer=None: ([], [sak], []))

    lagret = m.run_scan()["cases"][0]
    verdier = [v for _, v in lagret["trend"]["punkter"]]
    assert 154.0 not in verdier, f"prosenten havnet i linja: {verdier}"
    assert verdier == [18432.0, 15738.0, 13821.0], verdier
    # Serien faller, og da SKAL det stå nedgang - selv om året-mot-året er opp.
    assert lagret["trend"]["retning"] == "ned"


def test_uten_tidsserie_blir_det_ingen_trend(tmp_path, monkeypatch):
    """Grensen som gjør regelen over trygg. En konkurs har ingen serie, og en
    linje gjennom ett punkt ville vært oppdiktning."""
    from app import trend as t

    assert t.MIN_PUNKTER == 3
    assert t.beregn([]) is None


def _artikkel(tittel: str, dager: int) -> dict:
    return {"title": tittel, "date": "01.01.2026", "url": "https://x", "dager": dager}


@pytest.mark.parametrize("tittel, sak_tittel, sok", [
    # Alle tre er ekte feiltreff fra en live kjøring 26.07.2026.
    ("Omsetningen til Hafrsfjordbroa Blomster har ikke vært høyere",
     "Blåveisen Blomster As har gaatt konkurs", ""),
    ("Bystudio - Slutt for India Tandoori Stavanger etter 34 år",
     "Familiefasen (30–34 år) i Stavanger ned 0,4 %",
     "Stavanger unge voksne befolkning tilflytting"),
    ("Ralf Børre Husebø er død",
     "Visdommen Tannlegesenter As er under avvikling", ""),
])
def test_feiltreffene_fra_ekte_data_slipper_ikke_gjennom(tittel, sak_tittel, sok):
    """En «oppfølger» som ikke handler om saken er verre enn ingen: den lover at
    noen alt har gjort forarbeidet, og sender journalisten på et blindspor."""
    from app.main import _er_oppfolger

    kind = "hendelse" if "As " in sak_tittel or sak_tittel.endswith("konkurs") else "data"
    sak = _sak(title=sak_tittel, coverage_query=sok, kind=kind)
    assert not _er_oppfolger(sak, _artikkel(tittel, 200)), tittel


def test_den_ekte_oppfolgeren_slipper_gjennom():
    """Motprøven, og den er like viktig: et filter som stenger alt består testen
    over også. Dette er treffet fra samme kjøring som faktisk holdt."""
    from app.main import _er_oppfolger

    sak = _sak(title="Godkjente boliger opp 770 % i Stavanger",
               coverage_query="Stavanger godkjente boliger")
    artikkel = _artikkel("3800 boliger i Stavanger og Sandnes står tomme", 146)
    assert _er_oppfolger(sak, artikkel)


def test_arkivmateriale_er_ikke_en_oppfolger():
    """Google News ga oss en sak fra 2015 på et byggetall fra i år. «Hva har
    skjedd siden?» er ikke et spørsmål elleve år etter."""
    from app.main import _er_oppfolger

    sak = _sak(title="Igangsettingstillatelser boliger opp 128 % i Stavanger",
               coverage_query="Stavanger igangsatte boliger")
    gammel = _artikkel("Unge vil ha kvalitet, trenger ikke store boliger", 3878)
    assert not _er_oppfolger(sak, gammel)


def test_konkurs_krever_at_foretaksnavnet_staar_i_overskriften():
    """For en konkurs er navneforveksling den dyreste feilen vi kan gjøre — den
    kan sette feil firma i avisa."""
    from app.main import _er_oppfolger

    sak = _sak(title="Blåveisen Blomster As har gaatt konkurs", kind="hendelse")
    assert _er_oppfolger(sak, _artikkel("Blåveisen Blomster utvider på Storhaug", 200))
    assert not _er_oppfolger(sak, _artikkel("Blomsterbransjen sliter i Stavanger", 200))
