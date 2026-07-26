"""Konfigurasjon: kilder, geografi- og demografi-nokkelord.

Alt som er lett a tilpasse for journalisten samles her, slik at man kan justere
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

# --- Temaer journalisten kan velge mellom -----------------------------------
# Dette er BRUKERENS vokabular, og det er noe annet enn DEMOGRAPHIC_TOPICS over.
# I koden betydde «tema» tidligere fire urelaterte ting: innholdstagging
# (DEMOGRAPHIC_TOPICS), SSB-soekeord (ssb_sok.TEMA), SSB-emneslugger
# (ssb_kalender.VIKTIGE_EMNER) og probe-etiketter. Ingen av dem var koblet.
# TEMAER er brua: ETT valg i menyen oversettes til alle tre vokabularene.
#
#   gruppe     -> overskrift i menyen, saa 22 temaer ikke blir en vegg av tekst.
#   sok        -> soekeord mot SSBs tabellkatalog. Sammen med `koder` er dette
#                 det som styrer HVILKE tabeller skannet finner - hovedeffekten.
#   koder      -> SSBs egne hovedemnekoder. Brukes til aa loefte katalogtreff
#                 presist, i stedet for aa stole paa at et soekeord tilfeldigvis
#                 traff. To ting maatte verifiseres mot det ekte API-et foer
#                 dette virket, og begge er felle:
#                   * API-et IGNORERER `subjectCode` som spoerreparameter -
#                     verifisert 26.07.2026, den returnerte alle 3 786
#                     tabellene - saa filtreringen maa gjoeres paa vaar side.
#                   * En tabell ligger under FLERE stier, og riktig kode er
#                     ikke noedvendigvis i den foerste. Se `_hovedemner()` i
#                     ssb_sok.py.
#                 Kodene under er hele settet, utledet ved aa gaa gjennom alle
#                 3 786 tabellene i katalogen 26.07.2026 - 23 hovedemner.
#                 Ikke gjett paa dem: «in» er Innvandring, ikke Inntekt (det er
#                 «if»), og jord/skog/fiske er «js».
#   ssb_emner  -> emneslugger i RSS-publiseringskalenderen. Et HELT annet
#                 vokabular enn `koder`, selv om begge kommer fra SSB.
#   demografi  -> hvilke DEMOGRAPHIC_TOPICS temaet dekker (til tagging/visning).
#
# Dekningen er bevisst komplett: alle 23 hovedemner i SSBs katalog er med, saa
# ingen del av statistikken er utilgjengelig for journalisten. Emner uten lokal
# relevans (Svalbard, utenriksoekonomi) ligger under «Annet» - de er sjelden
# aktuelle, men de skal finnes naar de er det.
TEMAER: dict[str, dict] = {
    # ── Folk ────────────────────────────────────────────────────────────────
    "befolkning": {
        "gruppe": "Folk", "ikon": "👥",
        "sok": ["folkemengde", "flytting", "fodte", "dode", "befolkningsframskriving"],
        "koder": ["be"], "ssb_emner": ["befolkning"],
        "demografi": ["bolig og leie"],
    },
    "barn og unge": {
        "gruppe": "Folk", "ikon": "🧒",
        "sok": ["barnehage", "grunnskole", "elever", "barnevern", "fodte"],
        "koder": ["ud", "be", "sk"], "ssb_emner": ["utdanning", "befolkning"],
        "demografi": ["studentliv"],
    },
    "alderdom": {
        "gruppe": "Folk", "ikon": "🧓",
        "sok": ["eldre", "pleie og omsorg", "sykehjem", "pensjon", "aleneboende"],
        "koder": ["he", "be", "os"], "ssb_emner": ["helse", "befolkning"],
        "demografi": ["psykisk helse"],
    },
    "innvandring": {
        "gruppe": "Folk", "ikon": "🌍",
        "sok": ["innvandrere", "innvandring", "flyktninger", "statsborgerskap"],
        "koder": ["in"], "ssb_emner": ["innvandring-og-innvandrere", "befolkning"],
        "demografi": [],
    },
    "familie og husholdning": {
        "gruppe": "Folk", "ikon": "🏡",
        "sok": ["husholdninger", "familier", "samboere", "skilsmisser", "aleneboende"],
        "koder": ["be"], "ssb_emner": ["befolkning"],
        "demografi": ["dating og relasjoner"],
    },

    # ── Penger ──────────────────────────────────────────────────────────────
    "lønn": {
        "gruppe": "Penger", "ikon": "💰",
        "sok": ["lonn", "inntekt", "arsloenn", "loennsforskjeller"],
        "koder": ["al", "if"], "ssb_emner": ["arbeid-og-lonn", "inntekt-og-forbruk"],
        "demografi": ["jobb og okonomi"],
    },
    "fattigdom": {
        "gruppe": "Penger", "ikon": "🏚",
        "sok": ["lavinntekt", "sosialhjelp", "bostotte", "barnefattigdom"],
        "koder": ["if", "sk"],
        "ssb_emner": ["inntekt-og-forbruk", "sosiale-forhold-og-kriminalitet"],
        "demografi": ["jobb og okonomi", "bolig og leie"],
    },
    "priser": {
        "gruppe": "Penger", "ikon": "🏷",
        "sok": ["konsumprisindeks", "matvarepriser", "byggekostnad", "drivstoff"],
        "koder": ["pp"], "ssb_emner": ["priser-og-prisindekser"],
        "demografi": ["jobb og okonomi"],
    },
    "gjeld og bank": {
        "gruppe": "Penger", "ikon": "🏦",
        "sok": ["gjeld", "utlaan", "renter", "husholdningenes gjeld", "betalingsanmerkninger"],
        "koder": ["bf"], "ssb_emner": ["bank-og-finansmarked"],
        "demografi": ["jobb og okonomi"],
    },
    "skatt og kommunekasse": {
        "gruppe": "Penger", "ikon": "🏛",
        "sok": ["skatt", "kommuneregnskap", "kostra", "offentlige utgifter"],
        "koder": ["os", "nk"],
        "ssb_emner": ["offentlig-sektor", "nasjonalregnskap-og-konjunkturer"],
        "demografi": ["jobb og okonomi"],
    },

    # ── Arbeid ──────────────────────────────────────────────────────────────
    "arbeid": {
        "gruppe": "Arbeid", "ikon": "🧰",
        "sok": ["sysselsetting", "arbeidsledige", "arbeidskraft", "sykefravaer", "deltid"],
        "koder": ["al"], "ssb_emner": ["arbeid-og-lonn"],
        "demografi": ["jobb og okonomi"],
    },
    "næringsliv": {
        "gruppe": "Arbeid", "ikon": "🏢",
        "sok": ["konkurs", "foretak", "etablerere", "omsetning", "naering"],
        "koder": ["vf"], "ssb_emner": ["virksomheter-foretak-og-regnskap"],
        "demografi": ["jobb og okonomi"],
    },
    "butikk og service": {
        "gruppe": "Arbeid", "ikon": "🛒",
        "sok": ["varehandel", "detaljhandel", "tjenesteyting", "overnatting", "servering"],
        "koder": ["vt"], "ssb_emner": ["varehandel-og-tjenesteyting"],
        "demografi": ["uteliv og kultur"],
    },
    "teknologi": {
        "gruppe": "Arbeid", "ikon": "💻",
        "sok": ["ikt", "internett", "digitalisering", "forskning og utvikling"],
        "koder": ["ti"], "ssb_emner": ["teknologi-og-innovasjon"],
        "demografi": ["gaming og digitalt"],
    },

    # ── Hverdag ─────────────────────────────────────────────────────────────
    "bolig og bygg": {
        "gruppe": "Hverdag", "ikon": "🏘",
        "sok": ["byggeareal", "boligpriser", "leiemarked", "boligmasse", "igangsatte boliger"],
        "koder": ["bb"], "ssb_emner": ["bygg-bolig-og-eiendom"],
        "demografi": ["bolig og leie"],
    },
    "helse": {
        "gruppe": "Hverdag", "ikon": "🩺",
        "sok": ["fastlege", "pasienter", "helsetjenester", "psykisk helse", "legemidler"],
        "koder": ["he"], "ssb_emner": ["helse"],
        "demografi": ["psykisk helse", "trening og livsstil"],
    },
    "utdanning": {
        "gruppe": "Hverdag", "ikon": "🎓",
        "sok": ["videregaende", "studenter", "hoyere utdanning", "frafall", "laererer"],
        "koder": ["ud"], "ssb_emner": ["utdanning"],
        "demografi": ["studentliv"],
    },
    "kriminalitet": {
        "gruppe": "Hverdag", "ikon": "🚓",
        "sok": ["lovbrudd", "anmeldte", "straffereaksjoner", "ofre", "fengsling"],
        "koder": ["sk"], "ssb_emner": ["sosiale-forhold-og-kriminalitet"],
        "demografi": ["trygghet og kriminalitet"],
    },
    "idrett og kultur": {
        "gruppe": "Hverdag", "ikon": "⚽",
        "sok": ["idrett", "kultur", "fritidsaktivitet", "bibliotek", "frivillighet"],
        "koder": ["kf"], "ssb_emner": ["kultur-og-fritid"],
        "demografi": ["trening og livsstil", "uteliv og kultur"],
    },

    # ── Miljø og transport ──────────────────────────────────────────────────
    "natur og miljø": {
        "gruppe": "Miljø", "ikon": "🌱",
        "sok": ["utslipp", "avfall", "klimagasser", "vann", "arealbruk"],
        "koder": ["nm"], "ssb_emner": ["natur-og-miljo"],
        "demografi": ["klima og miljo"],
    },
    "energi": {
        "gruppe": "Miljø", "ikon": "⚡",
        "sok": ["stromforbruk", "elektrisitet", "energibruk", "industri"],
        "koder": ["ei"], "ssb_emner": ["energi-og-industri"],
        "demografi": ["klima og miljo", "jobb og okonomi"],
    },
    "transport og reiseliv": {
        "gruppe": "Miljø", "ikon": "🚌",
        "sok": ["kollektivtransport", "bilpark", "elbil", "reiseliv", "trafikkulykker"],
        "koder": ["tr"], "ssb_emner": ["transport-og-reiseliv"],
        "demografi": ["klima og miljo"],
    },

    # ── Annet ───────────────────────────────────────────────────────────────
    "jord og fiske": {
        "gruppe": "Annet", "ikon": "🌾",
        "sok": ["jordbruk", "skogbruk", "fiskeri", "akvakultur", "landbruk"],
        "koder": ["js"], "ssb_emner": ["jord-skog-jakt-og-fiskeri"],
        "demografi": [],
    },
    "valg og politikk": {
        "gruppe": "Annet", "ikon": "🗳",
        "sok": ["valg", "stortingsvalg", "kommunestyrevalg", "valgdeltakelse"],
        "koder": ["va"], "ssb_emner": ["valg"],
        "demografi": [],
    },
    "utenriks og Svalbard": {
        "gruppe": "Annet", "ikon": "🧭",
        "sok": ["utenrikshandel", "eksport", "import", "svalbard"],
        "koder": ["ut", "sv"], "ssb_emner": ["utenriksokonomi", "svalbard"],
        "demografi": [],
    },
}


def sokeord_for(temaer: list[str] | None) -> list[str]:
    """Soekeordene for de valgte temaene. Tomt valg = ALLE temaer.

    Tomt valg betyr bevisst «alt», ikke «ingenting»: verktoyet skal virke som for
    helt til journalisten faktisk velger noe."""
    valgte = [t for t in (temaer or []) if t in TEMAER] or list(TEMAER)
    ut: list[str] = []
    for navn in valgte:
        for ord_ in TEMAER[navn]["sok"]:
            if ord_ not in ut:
                ut.append(ord_)
    return ut


def emnekoder_for(temaer: list[str] | None) -> set[str]:
    """SSBs hovedemnekoder for de valgte temaene (be, al, he, sk ...).

    Tomt valg gir en TOM mengde, ikke alle koder - kallerne tolker tomt som
    «ikke filtrer», og det er en annen ting enn «filtrer paa alt»."""
    valgte = [t for t in (temaer or []) if t in TEMAER]
    return {k for navn in valgte for k in TEMAER[navn]["koder"]}


def ssb_emner_for(temaer: list[str] | None) -> set[str]:
    """RSS-emneslugger for de valgte temaene - til vekting av publiseringskalenderen."""
    valgte = [t for t in (temaer or []) if t in TEMAER] or list(TEMAER)
    return {e for navn in valgte for e in TEMAER[navn]["ssb_emner"]}


def temagrupper() -> dict[str, list[str]]:
    """{gruppe: [temanavn]} i den rekkefolgen de er definert - til menyen."""
    ut: dict[str, list[str]] = {}
    for navn, t in TEMAER.items():
        ut.setdefault(t["gruppe"], []).append(navn)
    return ut


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
    "seg", "men", "har", "om", "vi", "min", "mitt", "ha", "hadde",
    "for", "du", "na", "far", "kan", "vil", "skal", "ma", "blir", "ble",
    "etter", "over", "under", "mot", "fra", "ved", "eller", "nar", "hvor",
    "hva", "hvem", "hvordan", "her", "dette", "disse", "denne", "noen",
    "ingen", "alle", "flere", "mange", "mer", "mest", "andre", "samme",
    "svært", "helt", "bare", "ogsa", "enn", "opp", "ut", "inn", "ned",
    "gar", "kommer", "sier", "fikk", "gjor", "vart", "vare",
    "the", "a", "of", "to", "and", "is", "in", "it", "you", "that",
    "nye", "ny", "nytt", "million", "millioner", "prosent",
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

# === Broennoeysundregistrene: hva som aapner og hva som gaar under ===========
# Aapent API, ingen noekkel, ingen kvote. Gir HENDELSER (konkurser, avviklinger,
# nyregistrerte foretak) i stedet for tall - saker journalisten kan ringe paa i
# dag. Fire kall per skann (to kommuner x to spoerringer). Se app/collectors/brreg.py.
ENABLE_BRREG = os.getenv("CASE_RADAR_ENABLE_BRREG", "true").lower() == "true"

# === KI-arbeidsflyt (kostnadskontroll: cap antall KI-kall per skann) ===
ENABLE_AI = os.getenv("CASE_RADAR_ENABLE_AI", "true").lower() == "true"
# Fire, ikke aatte (eierens beslutning 26.07.2026). Redaktoeren vurderer én sak
# per kall, saa dette tallet er DIREKTE antall KI-kall mot minuttkvoten. Med
# aatte traff skannet taket og journalisten fikk «4 av 4 kall feilet».
#
# Fire saker per trykk er ikke mindre verktoy - det er en annen rytme: han
# trykker «Skann naa» igjen, og fordi ekte KI-svar lagres per sak (storage.
# ki_lagre) bruker neste skann hele budsjettet paa de NESTE fire. Koen toemmer
# seg, og hver sak faar ordentlige vinkler i stedet for at alle blir halve.
EDITOR_CAP = int(os.getenv("CASE_RADAR_EDITOR_CAP", "4"))
# Vinklene lages i ETT samlet kall for alle godkjente saker, saa dette tallet
# koster ikke kall - bare tokens i det ene kallet. Det foelger EDITOR_CAP fordi
# en sak uten redaktoerdom uansett ikke kommer hit.
JOURNALIST_CAP = int(os.getenv("CASE_RADAR_JOURNALIST_CAP", "4"))

# Tokenbudsjett for ETT skann. Groqs gratis-nivaa gir 12 000 tokens i minuttet
# (llama-3.3-70b-versatile, console.groq.com/docs/rate-limits, hentet 26.07.2026),
# og et fullt skann ville brukt rundt 37 000 - det var derfor 429-en traff
# journalistens telefon. Naa stopper skannet naar budsjettet er brukt opp, og
# resten legges i kø: trykker han «Skann igjen» tar neste skann de neste sakene.
# Eierens egen loesning, og den er bedre enn aa vente lenge inne i ett skann.
#
# 9 000 og ikke 12 000: marginen gjor at to skann rett etter hverandre fortsatt
# holder seg under taket, siden minuttvinduet ruller.
KI_BUDSJETT_TOKENS = int(os.getenv("CASE_RADAR_KI_BUDSJETT", "9000"))
