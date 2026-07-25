"""Konfigurasjon: kilder, geografi- og demografi-nokkelord.

Alt som er lett a tilpasse for Mathias samles her, slik at man kan justere
kilder og tema uten a rore selve logikken.
"""

from __future__ import annotations

import os

# --- Nyhets-RSS (gratis, stabilt) -------------------------------------------
# geo="lokal" -> teller som Stavanger/Rogaland-relevant uansett innhold.
NEWS_FEEDS: list[dict[str, str]] = [
    {"name": "Stavanger Aftenblad", "url": "https://www.aftenbladet.no/rss", "geo": "lokal"},
    {"name": "NRK Rogaland", "url": "https://www.nrk.no/rogaland/toppsaker.rss", "geo": "lokal"},
    {"name": "NRK Siste nytt", "url": "https://www.nrk.no/nyheter/siste.rss", "geo": "nasjonal"},
    {"name": "NRK Norge", "url": "https://www.nrk.no/norge/toppsaker.rss", "geo": "nasjonal"},
    {"name": "VG", "url": "https://www.vg.no/rss/feed/", "geo": "nasjonal"},
    {"name": "E24 (okonomi)", "url": "https://e24.no/rss", "geo": "nasjonal"},
]

# --- Reddit (offentlig JSON, gratis) ----------------------------------------
# geo="lokal" for stavanger-subredditen.
SUBREDDITS: list[dict[str, str]] = [
    {"name": "r/stavanger", "sub": "stavanger", "geo": "lokal"},
    {"name": "r/norge", "sub": "norge", "geo": "nasjonal"},
    {"name": "r/Norway", "sub": "Norway", "geo": "nasjonal"},
]

# --- Geografi: hva teller som Stavanger/Rogaland-lokalt ----------------------
# Kun entydige stedsnavn. Korte/tvetydige ord (ha, time, viking, lyse) er bevisst
# utelatt fordi de gir falske lokal-treff. Geografi avgjores av INNHOLD, ikke
# hvilken avis saken kom fra (lokalaviser dekker ogsaa nasjonale nyheter).
STAVANGER_TERMS: set[str] = {
    "stavanger", "sandnes", "randaberg", "hafrsfjord", "hundvag",
    "storhaug", "hillevag", "madla", "eiganes",
    "jaeren", "bryne", "klepp", "gjesdal", "hommersaak",
    "rogaland", "haugesund", "egersund", "dalane", "ryfylke", "nord-jaeren",
    "universitetet i stavanger", "sviland", "forus", "sokndal",
    "hjelmeland", "strand", "finnoy", "rennesoy", "kvernevik",
}

# Entydige lokale forkortelser/egennavn (matches som hele ord, store bokstaver ok).
STAVANGER_TERMS_EXACT: set[str] = {"uis", "sr-bank"}

# --- Demografi 18-34: tema og nokkelord med vekt ----------------------------
# Hvert tema har nokkelord; treff gir demografi-poeng og en tema-tag.
DEMOGRAPHIC_TOPICS: dict[str, list[str]] = {
    "bolig og leie": [
        "leie", "leiemarked", "husleie", "bolig", "boligpris", "hybel",
        "utleie", "depositum", "borettslag", "forstegangskjoper",
    ],
    "studentliv": [
        "student", "studenter", "uis", "universitet", "hogskole", "eksamen",
        "fadderuke", "studentby", "sit", "campus", "kollektiv",
    ],
    "jobb og okonomi": [
        "jobb", "arbeidsledig", "permittert", "lonn", "rente", "strompris",
        "inflasjon", "matpriser", "dyrtid", "sparing", "gjeld",
    ],
    "uteliv og kultur": [
        "utested", "bar", "konsert", "festival", "nattklubb", "utelivet",
        "kultur", "scene", "dj", "byfest", "gladmat", "maijazz",
    ],
    "psykisk helse": [
        "psykisk", "ensomhet", "utenforskap", "angst", "depresjon",
        "helsekø", "fastlege", "ventetid", "rusmiddel", "selvmord",
    ],
    "klima og miljo": [
        "klima", "miljo", "utslipp", "elbil", "kollektiv", "sykkel",
        "baerekraft", "gjenbruk", "natur", "vindkraft",
    ],
    "trygghet og kriminalitet": [
        "vold", "ran", "narkotika", "gjeng", "politi", "knivstikking",
        "trygghet", "hærverk", "innbrudd", "voldtekt",
    ],
    "gaming og digitalt": [
        "gaming", "e-sport", "esport", "twitch", "tiktok", "influenser",
        "streaming", "kunstig intelligens",
    ],
    "trening og livsstil": [
        "trening", "treningssenter", "lopeklubb", "kosthold", "protein",
        "livsstil", "helse", "søvn", "løping",
    ],
    "dating og relasjoner": [
        "dating", "tinder", "kjæreste", "singel", "forhold",
    ],
}

# Ord som ALDRI skal bli en "entitet" a klynge saker rundt (for generelle).
ENTITY_STOPWORDS: set[str] = {
    "norge", "noreg", "norway", "nordmann", "dette", "slik", "dermed",
    "mann", "kvinne", "gutt", "jente", "politiet", "video", "direkte",
    "live", "mener", "mandag", "tirsdag", "onsdag", "torsdag", "fredag",
    "loerdag", "soendag", "januar", "februar", "mars", "april", "juni",
    "juli", "august", "september", "oktober", "november", "desember",
    "regjeringen", "eksperten", "sjefen", "kommentar", "meninger",
}

# --- Norske stoppord (for nokkelord-uttrekk) --------------------------------
STOPWORDS: set[str] = {
    "og", "i", "jeg", "det", "at", "en", "et", "den", "til", "er", "som",
    "pa", "de", "med", "han", "av", "ikke", "der", "sa", "var", "meg",
    "seg", "men", "et", "har", "om", "vi", "min", "mitt", "ha", "hadde",
    "for", "du", "na", "far", "kan", "vil", "skal", "ma", "blir", "ble",
    "etter", "over", "under", "mot", "fra", "ved", "eller", "nar", "hvor",
    "hva", "hvem", "hvordan", "her", "dette", "disse", "denne", "noen",
    "ingen", "alle", "flere", "mange", "mer", "mest", "andre", "samme",
    "svært", "helt", "bare", "ogsa", "enn", "opp", "ut", "inn", "ned",
    "far", "gar", "kommer", "sier", "fikk", "gjor", "vart", "vare",
    "the", "a", "of", "to", "and", "is", "in", "it", "you", "that",
    "nye", "ny", "nytt", "far", "million", "millioner", "prosent",
}

# --- Innstillinger (kan overstyres via miljovariabler) ----------------------
DB_PATH = os.getenv("CASE_RADAR_DB", "data/case_radar.sqlite3")
ENABLE_TRENDS = os.getenv("CASE_RADAR_ENABLE_TRENDS", "true").lower() == "true"

# Reddit er AV som standard. Reddit strammet det anonyme API-et, og alle tre
# subredditene svarer nå med HTTP-feil. Maalt 25.07.2026: 0 signaler, 3 mislykte
# kall og 3 rode [FEIL]-linjer i statuspanelet ved hvert eneste skann. Koden
# staar igjen - aapner Reddit igjen, er det ett miljovariabel-bytte unna.
ENABLE_REDDIT = os.getenv("CASE_RADAR_ENABLE_REDDIT", "false").lower() == "true"
GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
GOOGLE_TOKEN_FILE = os.getenv("GOOGLE_TOKEN_FILE", "token.json")

# HTTP User-Agent - noen kilder (NRK, Reddit) krever en realistisk UA.
USER_AGENT = (
    "Mozilla/5.0 (compatible; CaseRadar/0.2; journalist trend scanner; "
    "+https://github.com/tobtheboyplays-cyber/stavanger-case-radar)"
)

# === SSB (Statistisk sentralbyra) - primaerkilde for ORIGINALE datadrevne leads ===
# Gratis apent API, ingen nokkel. Region: Hele landet=0, Rogaland=11, Stavanger=1103.
SSB_API = "https://data.ssb.no/api/v0/no/table"
SSB_REGIONS = {"0": "Hele landet", "11": "Rogaland", "1103": "Stavanger"}

# Alderskoder i tabell 07459 er "000".."105". Hjelper for aldersintervall.
def _ages(lo: int, hi: int) -> list[str]:
    return [f"{a:03d}" for a in range(lo, hi + 1)]


# Kuraterte "prober": hver gir ett eller flere datadrevne funn. Utvid med flere
# tabeller ved behov (hver SSB-tabell har egne dimensjonskoder).
# Fokus-aldersgruppe: 20-39 aar. Hvert probe er ett aldersspenn -> ett funn.
def _probe(pid, label, lo, hi, topics, cq):
    return {
        "id": pid, "table": "07459", "label": label,
        "query": {"Region": ["1103", "11", "0"], "Alder": _ages(lo, hi),
                  "ContentsCode": ["Personer1"], "Tid": {"top": 5}},
        "recipe": "sum_age_trend", "unit": "personer",
        "topics": topics, "coverage_query": cq,
    }


SSB_PROBES: list[dict] = [
    _probe("unge-voksne-20-39", "Unge voksne (20–39 år)", 20, 39,
           ["bolig og leie", "jobb og okonomi"], "Stavanger unge voksne befolkning tilflytting"),
    _probe("studenter-19-24", "Studentalder (19–24 år)", 19, 24,
           ["studentliv", "uteliv og kultur", "bolig og leie"],
           "Stavanger studenter UiS tilflytting studieby"),
    _probe("etablerere-25-29", "Etablererfasen (25–29 år)", 25, 29,
           ["bolig og leie", "jobb og okonomi", "dating og relasjoner"],
           "Stavanger unge voksne etablering bolig jobb"),
    _probe("familiefasen-30-34", "Familiefasen (30–34 år)", 30, 34,
           ["bolig og leie", "jobb og okonomi", "psykisk helse"],
           "Stavanger 30-åringer barnefamilier bolig"),
    _probe("35-39", "Aldersgruppen 35–39 år", 35, 39,
           ["jobb og okonomi", "bolig og leie"],
           "Stavanger 35-39 år arbeidsliv familie"),
]

# === Dekningssjekk (Google News RSS) - "er dette allerede skrevet om?" ===
GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"
COVERAGE_LOOKBACK_DAYS = 90      # ~3 maaneder: "har noen skrevet dette nylig?"
COVERAGE_YELLOW_MIN = 1          # 1-3 ferske treff => delvis dekket (gul)
COVERAGE_RED_MIN = 4             # >=4 ferske treff => allerede dekket (rod)

# === Schibsted-soesteraviser: idé-tyveri + sjekk at Aftenbladet ikke har skrevet ===
# Aftenbladet er Schibsted. Vi henter saker fra soesteraviser (ikke Stavanger) og
# ser om temaet kan gjenbrukes lokalt - forutsatt at Aftenbladet ikke har dekket det.
ENABLE_SCHIBSTED = os.getenv("CASE_RADAR_ENABLE_SCHIBSTED", "true").lower() == "true"
SCHIBSTED_FEEDS: list[dict] = [
    {"name": "Aftenposten", "url": "https://www.aftenposten.no/rss"},
    {"name": "Bergens Tidende", "url": "https://www.bt.no/rss"},
    {"name": "E24", "url": "https://e24.no/rss"},
]
AFTENBLADET_NAME = "Stavanger Aftenblad"
ENABLE_COVERAGE = os.getenv("CASE_RADAR_ENABLE_COVERAGE", "true").lower() == "true"
ENABLE_SSB = os.getenv("CASE_RADAR_ENABLE_SSB", "true").lower() == "true"

# === KI-arbeidsflyt (kostnadskontroll: cap antall KI-kall per skann) ===
ENABLE_AI = os.getenv("CASE_RADAR_ENABLE_AI", "true").lower() == "true"
EDITOR_CAP = int(os.getenv("CASE_RADAR_EDITOR_CAP", "8"))       # redaktor vurderer topp N
JOURNALIST_CAP = int(os.getenv("CASE_RADAR_JOURNALIST_CAP", "6"))  # utkast paa topp N godkjente
