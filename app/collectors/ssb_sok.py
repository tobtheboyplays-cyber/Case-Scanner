"""Soekesystem: finner STATISTIKK vi ikke har sett paa foer.

De andre SSB-kollektorene er kuraterte - de spoer de samme tabellene hver gang.
Denne gjor det motsatte: den leter i hele SSBs katalog (7700+ tabeller) etter noe
NYTT, og husker hva den har provd slik at neste soek leter et annet sted.

To spor, som utfyller hverandre:

1. **Ferskhet** - `?pastDays=N` gir tabellene SSB faktisk har oppdatert de siste
   dagene. Dette er bokstavelig talt «ny statistikk»: tall som ikke fantes forrige
   gang journalisten trykket soek.
2. **Tema-rotasjon** - `?query=<ord>` mot en roterende liste med tema som betyr noe
   for lesere i 20-40-aarene. Markoeren lagres i databasen, saa skann nr. 2 leter i
   et annet hjoerne av katalogen enn skann nr. 1.

For hver kandidat sjekker vi metadata: har tabellen kommunetall for Stavanger eller
Sandnes? Kan de ovrige dimensjonene elimineres (summeres bort)? Er tidsserien lang
nok til aa sammenligne med samme periode i fjor? Foerst da bruker vi et datakall.
Utfallet skrives til `ssb_tabeller` - permanente avslag probes aldri igjen,
midlertidige bare naar SSB har publisert nye tall.

Kilde: https://data.ssb.no/api/pxwebapi/v2 - aapent, ingen noekkel, CC BY 4.0.
Verifisert live 25.07.2026.

Driftshensyn (SSBs brukerveiledning): 30 spoerringer per minutt per IP. Denne
kollektoren bruker maks 2 katalogkall + 2 kall per kandidat, med MAKS_KANDIDATER
som tak - i praksis under 10 kall per skann.
"""

from __future__ import annotations

import re
import time
from datetime import UTC, datetime

from app.collectors.base import http_get
from app.config import DEMOGRAPHIC_TOPICS
from app.models import Case
from app.storage import (
    bor_probes,
    marker_ssb_tabell,
    meta_get,
    meta_set,
    neste_i_rotasjon,
    ssb_utforsket,
)

KATALOG = "https://data.ssb.no/api/pxwebapi/v2/tables"

# Kommunene vi krever tall for. En tabell uten disse er ikke en lokal sak.
KOMMUNER: dict[str, str] = {"1103": "Stavanger", "1108": "Sandnes"}

# Tabeller andre kollektorer allerede dekker - ingen grunn til aa duplisere dem.
ALLEREDE_DEKKET: frozenset[str] = frozenset({"07459", "01222"})

# Tema vi roterer gjennom. Rekkefolgen er bevisst blandet slik at to paafolgende
# skann faar ulike deler av katalogen, ikke to naboer i samme emne.
TEMA: list[str] = [
    "leie av bolig",
    "arbeidsledige",
    "konkurs",
    "studenter",
    "fodte",
    "inntekt",
    "sykefravaer",
    "barnehage",
    "lovbrudd",
    "boligpriser",
    "utdanning",
    "flytting",
    "husholdninger",
    "sysselsetting",
    "kollektivtransport",
    "elbil",
    "gjeld",
    "aleneboende",
]

FERSK_DAGER = 10          # hvor langt tilbake «nylig oppdatert» rekker
TEMA_PER_SKANN = 2        # hvor mange soekeord vi bruker per skann
MAKS_KANDIDATER = 8       # hvor mange tabeller vi faktisk prober per skann
KATALOG_SIDE = 30         # treff per katalogkall
MAKS_METRIKKER = 5        # statistikkvariabler vi sjekker per tabell (ett datakall)

# Ord i variabellista som antyder at tabellen har geografi i det hele tatt.
GEO_ORD = ("region", "kommune", "fylke", "bydel")

# SSB merker tabellnavn med geografisk nivaa: (K) = kommune, (B) = bydel,
# (F) = fylke. En ren (F)-tabell har aldri Stavanger-tall, saa vi sparer to
# API-kall ved aa se paa navnet i stedet for aa hente metadata og bli skuffet.
# Dette alene halverte bomkallene i test: 17 av 28 prober var fylkestabeller.
NIVAA_KOMMUNE = ("(K)", "(B)")
NIVAA_FYLKE = "(F)"

# Terskler for aa kalle en endring en sak. 4 % er normal svingning, og BEGGE
# tallene maa vaere store nok: «3 mot 8» er +167 % og likevel ren stoy. Kravet om
# nivaa paa fjoraarstallet OGSAA er det som hindrer den klassiske
# smaatallsfellen der en enkelt hendelse blir en prosentoverskrift.
MIN_ENDRING_PST = 15.0
MIN_NIVAA = 20.0

# Dimensjonsnavn som betyr TID. Har tabellen en slik dimensjon i tillegg til
# tidsvariabelen, og vi eliminerer (summerer) den bort, sammenligner vi et
# halvferdig aar med et helt aar. Tabell 12983 er akkurat den fellen: aarstall
# utenpaa, maaned inni - «Døde ned 50 %» var bare aaret som ikke er ferdig.
TIDSORD_EKSAKT: frozenset[str] = frozenset(
    {"år", "aar", "kalenderår", "årgang", "periode", "dato", "tid"}
)
TIDSORD_DEL: tuple[str, ...] = ("måned", "maaned", "kvartal", "uke", "halvår", "tertial")

# Hvor mange perioder tilbake «samme periode i fjor» ligger, per tidsenhet.
STEG_TILBAKE: dict[str, int] = {
    "Annual": 1,
    "Quarterly": 4,
    "Monthly": 12,
    "Weekly": 52,
    "Halfyear": 2,
    "Tertiary": 3,
}


def _rydd_tittel(raa: str) -> str:
    """«07165: Opna konkursar ... (K) 2006K1-2026K2» -> «Opna konkursar ... (K)»."""
    uten_id = re.sub(r"^\d+:\s*", "", raa).strip()
    # Perioden bakerst er stoy i en overskrift.
    return re.sub(r"\s+\d{4}[A-ZKMU]?\d*\s*-\s*\d{4}[A-ZKMU]?\d*$", "", uten_id).strip()


def _hent_katalog(params: dict) -> tuple[list[dict], int]:
    """(tabeller, antall sider totalt) fra et katalogkall."""
    from urllib.parse import urlencode

    url = f"{KATALOG}?{urlencode({'lang': 'no', 'pageSize': KATALOG_SIDE, **params})}"
    svar = http_get(url, timeout=25).json()
    sider = int((svar.get("page") or {}).get("totalPages") or 1)
    return svar.get("tables", []), sider


def _metadata(tabell_id: str) -> dict:
    url = f"{KATALOG}/{tabell_id}/metadata?lang=no&outputFormat=json-stat2"
    return http_get(url, timeout=25).json()


def _data(tabell_id: str, *, geo: str, geo_koder: str, tid: str, n: int,
          metric: str, metric_kode: str) -> dict:
    url = (
        f"{KATALOG}/{tabell_id}/data?lang=no&format=json-stat2"
        f"&valueCodes%5B{geo}%5D={geo_koder}"
        f"&valueCodes%5B{metric}%5D={metric_kode}"
        f"&valueCodes%5B{tid}%5D=top({n})"
    )
    return http_get(url, timeout=25).json()


def _roller(meta: dict) -> tuple[str, str, str] | None:
    """(geo-dim, tid-dim, metric-dim) fra json-stat2-rollene. None om noe mangler."""
    rolle = meta.get("role") or {}
    geo = (rolle.get("geo") or [None])[0]
    tid = (rolle.get("time") or [None])[0]
    metric = (rolle.get("metric") or [None])[0]
    if not (geo and tid and metric):
        return None
    return geo, tid, metric


def _er_tidsdimensjon(etikett: str) -> bool:
    lav = (etikett or "").strip().lower()
    return lav in TIDSORD_EKSAKT or any(o in lav for o in TIDSORD_DEL)


def _vurder(meta: dict) -> tuple[str, tuple[str, str, str] | None]:
    """Kan vi bruke denne tabellen? Returnerer (verdikt, roller)."""
    roller = _roller(meta)
    if roller is None:
        return "ingen-kommune" if not (meta.get("role") or {}).get("geo") else "ingen-tid", None
    geo, tid, metric = roller

    kommune_koder = set(meta["dimension"][geo]["category"]["index"])
    if not (set(KOMMUNER) & kommune_koder):
        return "ingen-kommune", None

    # Alle ovrige dimensjoner maa kunne elimineres, ellers blir uttrekket
    # tvetydig (hvilken naering? hvilken aldersgruppe?) og tallet ubrukelig.
    for navn in meta["id"]:
        if navn in (geo, tid, metric):
            continue
        dimensjon = meta["dimension"][navn]
        if _er_tidsdimensjon(dimensjon.get("label", "")):
            # Aa summere bort maanedene i et paagaaende aar gir et halvt aar mot
            # et helt. Vi lager heller ingen sak enn en feil sak.
            return "delvis-periode", None
        if not dimensjon.get("extension", {}).get("elimination"):
            return "ikke-eliminerbar", None
    return "ok", roller


def _hovedtall(metric_dim: dict, antall: int = MAKS_METRIKKER) -> list[str]:
    """Velg de mest lesbare statistikkvariablene i en tabell.

    Heuristikk: korteste etikett foerst. SSB navngir hovedtallet enkelt
    («Konkursar», «Døde») og avledede noekkeltall langt («Brutto driftsutgifter
    til styrket tilbud til førskolebarn (f 211) per barn ...»). Korteste er
    derfor nesten alltid det tallet en leser forstaar uten forklaring.

    Vi tar flere enn én fordi de faar plass i SAMME datakall: en tabell med ti
    variabler koster like mye aa sjekke bredt som smalt, og bredden er forskjellen
    paa «fant ingenting» og «fant en sak».
    """
    koder = list(metric_dim["category"]["index"])
    etiketter = metric_dim["category"].get("label", {})
    rangert = sorted(koder, key=lambda k: (len(etiketter.get(k, k)), koder.index(k)))
    return rangert[:antall]


def _kort(tekst: str, maks: int = 65) -> str:
    """Kutt paa ordgrense - en overskrift paa 120 tegn er ikke en overskrift."""
    tekst = tekst.strip()
    if len(tekst) <= maks:
        return tekst
    kuttet = tekst[:maks].rsplit(" ", 1)[0].rstrip(" ,;(-")
    return f"{kuttet} …"


def _tidssteg(katalog_rad: dict) -> int:
    return STEG_TILBAKE.get(str(katalog_rad.get("timeUnit") or ""), 1)


def _tema_fra(tekst: str) -> list[str]:
    lav = tekst.lower()
    treff = [t for t, ord_ in DEMOGRAPHIC_TOPICS.items() if any(o in lav for o in ord_)]
    return treff[:3] or ["jobb og okonomi"]


def _pst(naa: float, fjor: float) -> float | None:
    if not fjor:
        return None
    return (naa - fjor) / abs(fjor) * 100.0


def _tall(v: float) -> str:
    """1234.0 -> «1 234», 3.75 -> «3,75». Norsk lesbarhet uten locale-avhengighet."""
    if float(v).is_integer():
        return f"{int(v):,}".replace(",", " ")
    return f"{v:,.2f}".replace(",", " ").replace(".", ",")


def _side(nokkel: str) -> int:
    """Les en sidemarkoer fra databasen. Soppel i feltet skal aldri velte et skann."""
    try:
        return max(1, int(meta_get(nokkel, "1")))
    except ValueError:
        return 1


def _kandidater(status: list[str]) -> list[dict]:
    """Katalogtreff fra begge sporene, uten duplikater, ferskeste foerst."""
    funnet: dict[str, dict] = {}

    # Spor 1: ferskhet. Det SSB nettopp har oppdatert er per definisjon ny
    # statistikk - tall som ikke fantes forrige gang journalisten trykket soek.
    # Ogsaa dette sporet blar: uten sidemarkoer fikk vi de samme 30 tabellene
    # hvert skann, og skann nr. 2 hadde allerede provd dem alle.
    fersk_side = _side("ssb_fersk_side")
    try:
        rader, sider = _hent_katalog({"pastDays": FERSK_DAGER, "pageNumber": fersk_side})
        if not rader and fersk_side > 1:
            fersk_side = 1
            rader, sider = _hent_katalog({"pastDays": FERSK_DAGER, "pageNumber": 1})
        for rad in rader:
            funnet[rad["id"]] = {**rad, "_spor": f"oppdatert siste {FERSK_DAGER} dager"}
    except Exception as exc:  # noqa: BLE001 - fail-soft, de andre sporene staar
        status.append(f"[FEIL] SSB-soek (ferskhet): {exc}")
    else:
        meta_set("ssb_fersk_side", str(fersk_side % max(sider, 1) + 1))
        status.append(
            f"SSB-soek: {len(rader)} nylig oppdaterte tabeller "
            f"(side {fersk_side} av {sider}, siste {FERSK_DAGER} dager)"
        )

    # Spor 2: tema-rotasjon. Hvert soekeord har sin egen sidemarkoer - andre gang
    # vi leter etter «konkurs» henter vi side 2. Uten dette ville vi tygget paa de
    # samme 30 tabellene hver runde og aldri kommet dypere i katalogen.
    for ord_ in neste_i_rotasjon("ssb_tema_markor", TEMA, TEMA_PER_SKANN):
        side = _side(f"ssb_side:{ord_}")
        try:
            rader, _ = _hent_katalog({"query": ord_, "pageNumber": side})
            if not rader and side > 1:
                side = 1
                rader, _ = _hent_katalog({"query": ord_, "pageNumber": 1})
            for rad in rader:
                funnet.setdefault(rad["id"], {**rad, "_spor": f"soekeord «{ord_}»"})
        except Exception as exc:  # noqa: BLE001
            status.append(f"[FEIL] SSB-soek «{ord_}»: {exc}")
        else:
            meta_set(f"ssb_side:{ord_}", str(side + 1))
            status.append(f"SSB-soek: lette etter «{ord_}» (side {side}, {len(rader)} treff)")

    # Spor 3: systematisk gjennomgang av HELE katalogen, én side per skann.
    # Dette er garantien mot at koen gaar tom: 7700+ tabeller delt paa 30 er
    # rundt 260 sider, og markoeren staar i databasen. Uansett hvor mange ganger
    # journalisten trykker soek, finnes det en side han ikke har vaert paa enda.
    side = _side("ssb_katalog_side")
    try:
        rader, sider = _hent_katalog({"pageNumber": side})
        for rad in rader:
            funnet.setdefault(rad["id"], {**rad, "_spor": f"katalogen, side {side}"})
    except Exception as exc:  # noqa: BLE001
        status.append(f"[FEIL] SSB-soek (katalog): {exc}")
    else:
        meta_set("ssb_katalog_side", str(side % max(sider, 1) + 1))
        status.append(f"SSB-soek: gikk gjennom katalogside {side} av {sider}")

    ut: list[dict] = []
    for rad in funnet.values():
        if rad["id"] in ALLEREDE_DEKKET:
            continue
        if not any(g in n.lower() for n in rad.get("variableNames", []) for g in GEO_ORD):
            continue
        etikett = rad.get("label", "")
        kommunenivaa = any(m in etikett for m in NIVAA_KOMMUNE)
        if NIVAA_FYLKE in etikett and not kommunenivaa:
            continue
        ut.append({**rad, "_kommunenivaa": kommunenivaa})

    # Merkede kommunetabeller foerst, deretter ferskeste. Da treffer de dyreste
    # kallene (metadata + data) de kandidatene som faktisk kan gi en lokal sak.
    ut.sort(key=lambda r: (not r["_kommunenivaa"], _synkende(str(r.get("updated") or ""))))
    return ut


def _synkende(tekst: str) -> tuple[int, ...]:
    """Sorteringsnokkel som gir nyeste dato foerst innenfor en stigende sortering."""
    return tuple(-ord(c) for c in tekst)


def _case(rad: dict, roller: tuple[str, str, str], data: dict, steg: int) -> Case | None:
    """Bygg et lead hvis tallet faktisk har flyttet seg nok. Ellers None."""
    geo, tid, metric = roller
    order, storrelser = data["id"], data["size"]
    dim = data["dimension"]
    idx = {k: list(dim[k]["category"]["index"]) for k in order}
    verdier = data["value"]
    perioder = idx[tid]
    if len(perioder) < steg + 1:
        return None

    def hent(region: str, periode: str, metrikk: str) -> float | None:
        pos = 0
        for k, n in zip(order, storrelser, strict=True):
            if k == geo:
                valg = region
            elif k == tid:
                valg = periode
            elif k == metric:
                valg = metrikk
            else:
                valg = idx[k][0]
            pos = pos * n + idx[k].index(valg)
        v = verdier[pos]
        return None if v is None else float(v)

    naa_p, fjor_p = perioder[-1], perioder[-1 - steg]
    etiketter = dim[metric]["category"].get("label", {})
    tabell_id = rad["id"]
    tittel_raa = _rydd_tittel(rad["label"])

    # Sterkeste utslag paa tvers av alle statistikkvariabler OG begge kommunene.
    # Bare ÉN sak per tabell: fem varianter av samme funn er stoy, ikke fem leads.
    beste: tuple[float, str, str, float, float, str] | None = None
    for metrikk in idx[metric]:
        for kode, kommune in KOMMUNER.items():
            if kode not in idx[geo]:
                continue
            try:
                naa, fjor = hent(kode, naa_p, metrikk), hent(kode, fjor_p, metrikk)
            except (ValueError, KeyError, IndexError):
                continue
            # BEGGE sidene maa vaere store nok - ellers er prosenten et kunstprodukt.
            if naa is None or fjor is None or min(abs(naa), abs(fjor)) < MIN_NIVAA:
                continue
            pst = _pst(naa, fjor)
            if pst is None or abs(pst) < MIN_ENDRING_PST:
                continue
            if beste is None or abs(pst) > abs(beste[0]):
                beste = (pst, kode, kommune, naa, fjor, etiketter.get(metrikk, metrikk))

    if beste is None:
        return None
    pst, _kode, kommune, naa, fjor, metric_navn = beste

    retning = "opp" if pst > 0 else "ned"
    funn = (
        f"{metric_navn} i {kommune}: {_tall(naa)} i {naa_p}, mot {_tall(fjor)} i "
        f"{fjor_p} - {retning} {abs(pst):.0f} prosent. Kilde: SSB tabell {tabell_id}."
    )
    return Case(
        key=f"ssb-sok:{tabell_id}:{_kode}:{naa_p}",
        title=f"{_kort(metric_navn, 55)} {retning} {abs(pst):.0f} % i {kommune}",
        score=min(10 + abs(pst) / 2, 45),
        geo="lokal",
        topics=_tema_fra(f"{tittel_raa} {metric_navn}"),
        angle=(
            f"Hva ligger bak endringen? Sammenlign Stavanger og Sandnes i samme "
            f"tabell, og be SSB eller kommunen forklare hoppet fra {fjor_p} til {naa_p}."
        ),
        why=(
            f"Nyoppdaget tabell ({rad['_spor']}). SSB oppdaterte den "
            f"{str(rad.get('updated') or '')[:10]} - tallet er ferskt."
        ),
        signals=[],
        created_at=datetime.now(tz=UTC),
        kind="data",
        finding=funn,
        metric_value=f"{pst:+.0f} %",
        metric_period=f"{naa_p} mot {fjor_p}",
        data_source=f"SSB tabell {tabell_id} ({tittel_raa})",
        data_url=f"https://www.ssb.no/statbank/table/{tabell_id}",
        coverage_query=f"{kommune} {metric_navn}",
    )


def collect() -> tuple[list[Case], list[str]]:
    """Let etter ny statistikk. Fail-soft som alle kollektorer."""
    status: list[str] = []
    try:
        kandidater = _kandidater(status)
    except Exception as exc:  # noqa: BLE001
        return [], [f"[FEIL] SSB-soek: {exc}"]

    utforsket = ssb_utforsket()
    kø = [r for r in kandidater if bor_probes(r["id"], str(r.get("updated") or ""), utforsket)]
    status.append(
        f"SSB-soek: {len(kandidater)} kandidater med geografi, "
        f"{len(kø)} ikke provd foer (prober {min(len(kø), MAKS_KANDIDATER)})"
    )

    cases: list[Case] = []
    for rad in kø[:MAKS_KANDIDATER]:
        tabell_id = rad["id"]
        oppdatert = str(rad.get("updated") or "")
        tittel = _rydd_tittel(rad["label"])
        try:
            meta = _metadata(tabell_id)
            verdikt, roller = _vurder(meta)
            if roller is None:
                marker_ssb_tabell(tabell_id, verdikt, oppdatert=oppdatert, notat=tittel)
                continue

            geo, tid, metric = roller
            steg = _tidssteg(rad)
            regioner = meta["dimension"][geo]["category"]["index"]
            koder = ",".join(k for k in KOMMUNER if k in regioner)
            metric_koder = ",".join(_hovedtall(meta["dimension"][metric]))
            time.sleep(0.4)  # 30 kall/min-taket hos SSB - vi ligger godt under
            data = _data(
                tabell_id, geo=geo, geo_koder=koder, tid=tid, n=steg + 2,
                metric=metric, metric_kode=metric_koder,
            )
            sak = _case(rad, roller, data, steg)
        except Exception as exc:  # noqa: BLE001 - én daarlig tabell skal ikke velte skannet
            marker_ssb_tabell(tabell_id, "feil", oppdatert=oppdatert, notat=str(exc)[:200])
            status.append(f"SSB-soek: tabell {tabell_id} feilet ({type(exc).__name__})")
            continue

        if sak is None:
            marker_ssb_tabell(tabell_id, "under-terskel", oppdatert=oppdatert, notat=tittel)
        else:
            marker_ssb_tabell(tabell_id, "treff", oppdatert=oppdatert, notat=tittel)
            cases.append(sak)

    status.append(f"SSB-soek: {len(cases)} nye leads fra tabeller vi ikke hadde sett foer")
    return cases, status
