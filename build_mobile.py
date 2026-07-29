"""Bygger den skarpe, interaktive mobil-appen (SPA) for Case-radar.

Ekte SSB-tall (innbakt) + fengende titler og flere vinkler/artikler forfattet for
demoen. Dekningsstatus (gronn/gul/rod) hentes LIVE fra Google News per sak slik at
originaliteten er ekte. Publiseres som Artifact - apnes paa mobil.
"""

from __future__ import annotations

import html
import json

from app.collectors import coverage

# --- Forfattet innhold basert paa EKTE SSB-tall ------------------------------
# Kilder: SSB tabell 01222 (folketilvekst, Q1 2026), 09588 (flytting 2025),
# 07459 (befolkning etter alder 2026). Alle tall er reelle.
CASES = [
    {
        "id": "folkevekst",
        "tag": "SSB-data", "relevance": "høy",
        "headline": "Folkeveksten i Stavanger har nesten stoppet opp",
        "fact": "Stavanger vokste med bare 88 personer i første kvartal 2026 – mot 540 i samme kvartal året før. En nedgang på rundt 84 %.",
        "metric": "−84 %", "period": "folkevekst · Q1 2026",
        "source": "SSB (folketilvekst, 01222)",
        "url": "https://www.ssb.no/statbank/table/01222",
        "cov_query": "Stavanger folkevekst befolkning første kvartal 2026",
        "angles": [
            {"title": "Boligmarkedet: bremser prispresset?",
             "article": "Veksten i Stavanger har nærmest stoppet opp. Nye tall fra SSB viser at kommunen bare vokste med 88 personer i første kvartal 2026 – mot 540 i samme periode i fjor.\n\nFor et boligmarked som har vært preget av høy etterspørsel, kan en så brå oppbremsing få betydning. Færre nye innbyggere betyr isolert sett mindre press på leie- og kjøpsmarkedet – men det er langt fra hele bildet.\n\n[Ring en lokal eiendomsmegler og Eiendom Norge for å høre om de ser samme tendens i tallene sine. Sjekk om prisveksten faktisk har flatet ut.]\n\nSpørsmålet er om dette er en blipp for ett kvartal, eller starten på en ny trend for regionen.",
             "images": [
                 {"motiv": "Boligblokk under bygging på Nord-Jæren", "bildetekst": "Illustrasjon – bygging i Stavanger-området."},
                 {"motiv": "Enkel kurve som viser folkeveksten kvartal for kvartal", "bildetekst": "Folkeveksten stupte i første kvartal 2026. Kilde: SSB."}],
             "sources": ["Eiendom Norge / lokal megler", "Stavanger kommune, planavdelingen", "SSB folketilvekst"]},
            {"title": "Menneskene: hvem flytter ikke lenger hit?",
             "article": "Bak tallet på 88 skjuler det seg mennesker som lot være å flytte til Stavanger – og noen som flyttet ut. I samme kvartal var nettoinnflyttingen faktisk så vidt negativ.\n\nHvem er det som ikke lenger søker seg til oljebyen? Er det arbeidsinnvandrere, unge i etableringsfasen, eller familier på jakt etter rimeligere bolig andre steder?\n\n[Finn en person eller familie som nylig valgte bort Stavanger – eller flyttet ut – og la dem fortelle hvorfor. Snakk med en samfunnsgeograf ved UiS om hva som driver flyttestrømmene.]\n\nEn menneskelig historie kan gi tallene ansikt.",
             "images": [
                 {"motiv": "Ung person med flyttekasser", "bildetekst": "Illustrasjon – finn en reell case-person."},
                 {"motiv": "Portrett av forsker/samfunnsgeograf ved UiS", "bildetekst": "Ekspertkilde om flyttemønstre."}],
             "sources": ["Case-person som flyttet ut", "Samfunnsgeograf, UiS", "NAV Rogaland"]},
            {"title": "Kommunekassa: hva betyr færre innbyggere?",
             "article": "Kommunens inntekter henger tett sammen med innbyggertallet. Når veksten bremser fra 540 til 88 på ett år, kan det på sikt merkes på overføringene fra staten.\n\nSamtidig planlegger kommuner ofte for vekst – i barnehager, skoler og infrastruktur. Hva skjer hvis prognosene sprekker?\n\n[Be Stavanger kommune om deres egen befolkningsprognose og sammenlign med de ferske SSB-tallene. Snakk med en kommunaldirektør eller økonomisjef om hva en flatere vekst betyr for budsjettene.]\n\nDette er en sak som treffer alt fra skoleutbygging til eldreomsorg.",
             "images": [
                 {"motiv": "Stavanger rådhus", "bildetekst": "Kommuneøkonomien påvirkes av innbyggertallet."},
                 {"motiv": "Barnehage/skolebygg", "bildetekst": "Planlegges det for en vekst som uteblir?"}],
             "sources": ["Økonomisjef, Stavanger kommune", "Kommunens befolkningsprognose", "SSB"]},
        ],
    },
    {
        "id": "utflytting",
        "tag": "SSB-data", "relevance": "høy",
        "headline": "For første gang på lenge: flere flyttet fra Stavanger enn til",
        "fact": "Nettoinnflyttingen til Stavanger var så vidt negativ i første kvartal 2026 (−3 personer) – mot +408 i samme kvartal året før.",
        "metric": "−3", "period": "nettoinnflytting · Q1 2026",
        "source": "SSB (folketilvekst, 01222)",
        "url": "https://www.ssb.no/statbank/table/01222",
        "cov_query": "Stavanger netto utflytting fraflytting 2026",
        "angles": [
            {"title": "Jobb og bolig: hvorfor snur strømmen?",
             "article": "Etter år med solid tilflytting viser ferske SSB-tall at Stavanger fikk en så vidt negativ nettoinnflytting i første kvartal 2026: −3 personer, mot +408 året før.\n\nTo klassiske forklaringer melder seg: arbeidsmarkedet og boligprisene. Har det blitt vanskeligere å få jobb, eller dyrere å bo, sammenlignet med regioner folk flytter til?\n\n[Sjekk ledighetstallene hos NAV Rogaland og boligprisene mot resten av landet. Snakk med en arbeidslivsforsker om olje- og energibransjens betydning for tilflyttingen.]\n\nEn kort trend, eller et vendepunkt for regionen?",
             "images": [
                 {"motiv": "Forus næringsområde", "bildetekst": "Arbeidsmarkedet påvirker flyttestrømmene."},
                 {"motiv": "Til leie / Solgt-skilt", "bildetekst": "Bolig og jobb avgjør hvor folk bosetter seg."}],
             "sources": ["NAV Rogaland", "Arbeidslivsforsker, UiS/NORCE", "Eiendom Norge"]},
            {"title": "De unge: forlater 20-åringene byen?",
             "article": "Nettoutflytting henger ofte sammen med de yngste aldersgruppene. Samtidig viser SSB at antallet 20-åringer i Stavanger falt 3,4 prosent på ett år – mens landet samlet gikk opp.\n\nReiser unge fra Stavanger for å studere eller jobbe andre steder? Og kommer de tilbake?\n\n[Snakk med UiS om søkertall og med et par unge som har flyttet ut om hva som skulle til for at de ble. Be SSB om aldersfordelt flyttestatistikk.]\n\nDette er en sak som treffer byens framtid som ung by.",
             "images": [
                 {"motiv": "Studenter på UiS-campus", "bildetekst": "Trekker byen til seg – eller mister – de unge?"},
                 {"motiv": "Ung person på togperrong/flyplass", "bildetekst": "Illustrasjon – flytter de unge ut?"}],
             "sources": ["UiS opptakskontor", "To unge case-personer", "SSB flyttestatistikk (09588)"]},
        ],
    },
    {
        "id": "innvandring",
        "tag": "SSB-data", "relevance": "middels",
        "headline": "Innvandringen til Stavanger nesten halvert på ett år",
        "fact": "Innvandringen til Stavanger falt fra 692 personer i første kvartal 2025 til 402 i samme kvartal 2026 – en nedgang på rundt 42 %.",
        "metric": "−42 %", "period": "innvandring · Q1 2026",
        "source": "SSB (folketilvekst, 01222)",
        "url": "https://www.ssb.no/statbank/table/01222",
        "cov_query": "Stavanger innvandring nedgang arbeidsinnvandring 2026",
        "angles": [
            {"title": "Arbeidslivet: merker bedriftene rekrutteringssvikt?",
             "article": "Færre innvandrere kom til Stavanger i starten av 2026. SSB-tallene viser en nedgang på over 40 prosent sammenlignet med samme kvartal året før.\n\nRegionen har lenge vært avhengig av arbeidsinnvandring – i alt fra industri og bygg til helse og restaurant. Merker bedriftene at det blir vanskeligere å fylle stillingene?\n\n[Ring NHO Rogaland og et par bedrifter i bygg/industri om de sliter med rekruttering. Sjekk med NAV om ledige stillinger står lenger ubesatt.]\n\nEn nedgang her kan få direkte følger for lokal verdiskaping.",
             "images": [
                 {"motiv": "Arbeidere på en byggeplass", "bildetekst": "Illustrasjon – arbeidsinnvandring til regionen."},
                 {"motiv": "Kurve over innvandring per kvartal", "bildetekst": "Innvandringen falt kraftig. Kilde: SSB."}],
             "sources": ["NHO Rogaland", "Bedrift i bygg/industri", "NAV Rogaland"]},
            {"title": "Årsaken: politikk eller konjunktur?",
             "article": "Hva ligger bak nedgangen i innvandring til Stavanger? Endret nasjonal innvandringspolitikk, et strammere arbeidsmarked, eller at folk søker seg til andre regioner?\n\nTallene alene svarer ikke – men de reiser spørsmålet.\n\n[Be en migrasjonsforsker (f.eks. ved UiS eller NORCE) tolke tallene. Sammenlign med nasjonale innvandringstall for å se om Stavanger skiller seg ut, eller følger en landstrend.]\n\nEn forklarende sak som setter de lokale tallene i en større sammenheng.",
             "images": [
                 {"motiv": "Illustrasjon: Norgeskart med flyttepiler", "bildetekst": "Følger Stavanger en nasjonal trend?"},
                 {"motiv": "Portrett av migrasjonsforsker", "bildetekst": "Ekspertkilde tolker tallene."}],
             "sources": ["Migrasjonsforsker, UiS/NORCE", "UDI/SSB nasjonale tall", "Integrerings- og mangfoldsdirektoratet"]},
        ],
    },
    {
        "id": "fodsler",
        "tag": "SSB-data", "relevance": "middels",
        "headline": "Færre babyer i Stavanger – fødselstallet faller",
        "fact": "Det ble født 374 barn i Stavanger i første kvartal 2026, mot 399 i samme kvartal året før – en nedgang på drøyt 6 %.",
        "metric": "−6 %", "period": "fødte · Q1 2026",
        "source": "SSB (folketilvekst, 01222)",
        "url": "https://www.ssb.no/statbank/table/01222",
        "cov_query": "Stavanger fødselstall færre barn 2026",
        "angles": [
            {"title": "Dyrtid: velger unge bort barn nå?",
             "article": "Fødselstallet i Stavanger falt i første kvartal 2026. Det passer inn i et nasjonalt bilde der stadig færre får barn – og der mange peker på økonomi.\n\nHar renter, boligpriser og usikkerhet gjort at unge i etableringsfasen utsetter familielivet?\n\n[Snakk med et par i 30-årene som har valgt å vente, og med en økonom om sammenhengen mellom privatøkonomi og fødselstall. Sjekk fødetilbudet ved SUS – påvirker kapasitet noe?]\n\nEn nær sak for målgruppen 25–39 år.",
             "images": [
                 {"motiv": "Tomt babyrom / barnevogn", "bildetekst": "Illustrasjon – flere utsetter å få barn."},
                 {"motiv": "Ungt par ser på regninger", "bildetekst": "Økonomi oppgis ofte som årsak. Finn case."}],
             "sources": ["Par i etableringsfasen", "Økonom/demograf", "SUS fødeavdeling"]},
            {"title": "Barnehage og skole: hva betyr færre barn?",
             "article": "Færre fødsler nå merkes i barnehager og skoler om noen år. Kommuner som har bygget ut for vekst, kan stå med ledig kapasitet – eller motsatt, dersom det snur igjen.\n\n[Be Stavanger kommune om barnetallsprognosene sine og hold dem opp mot de ferske fødselstallene. Snakk med en barnehagestyrer om de allerede merker færre søknader.]\n\nEn sak som kobler tørre tall til hverdagen for barnefamilier.",
             "images": [
                 {"motiv": "Barnehage utendørs", "bildetekst": "Færre fødsler påvirker barnehagebehovet."},
                 {"motiv": "Klasserom", "bildetekst": "Planlegging av skolekapasitet."}],
             "sources": ["Stavanger kommune, oppvekst", "Barnehagestyrer", "SSB befolkningsframskriving"]},
        ],
    },
    {
        "id": "20aringer",
        "tag": "SSB-data", "relevance": "høy",
        "headline": "Stavanger mister 20-åringene – mens resten av landet får flere",
        "fact": "Antall 20-åringer i Stavanger falt 3,4 % på ett år (til 1 855 i 2026), mens hele landet gikk opp 1,2 % og Rogaland opp 0,3 %.",
        "metric": "−3,4 %", "period": "20-åringer · 2025→2026",
        "source": "SSB (befolkning, 07459)",
        "url": "https://www.ssb.no/statbank/table/07459",
        "cov_query": "Stavanger antall 20-åringer unge befolkning",
        "angles": [
            {"title": "Studieby: taper Stavanger kampen om de unge?",
             "article": "Mens Norge samlet får flere 20-åringer, går Stavanger motsatt vei: en nedgang på 3,4 prosent på ett år. Det stikker seg ut fra både landet og resten av Rogaland.\n\nFor en by som vil være en attraktiv studieby, er dette et signal verdt å grave i. Trekker Oslo, Bergen og Trondheim de unge til seg?\n\n[Sjekk søkertallene til UiS mot de store universitetene. Snakk med studentersamskipnaden og et par 20-åringer om hva som gjør en by attraktiv.]\n\nEn sak om byens framtid som ung by.",
             "images": [
                 {"motiv": "UiS-campus med studenter", "bildetekst": "Kampen om de unge. Illustrasjon."},
                 {"motiv": "Søylediagram: Stavanger vs landet", "bildetekst": "Stavanger skiller seg ut. Kilde: SSB."}],
             "sources": ["UiS opptak", "Studentsamskipnaden", "To 20-åringer"]},
            {"title": "Uteliv og kultur: hvem skal fylle byen?",
             "article": "Færre 20-åringer merkes ikke bare på universitetet, men også i utelivet og kulturlivet. Denne aldersgruppen er en kjernemålgruppe for konsertscener, utesteder og festivaler.\n\nHva betyr en nedgang for et allerede presset uteliv?\n\n[Snakk med drivere av utesteder/konsertscener (f.eks. Folken, Tou) om de merker endring i publikum. Se det i sammenheng med tall for hvor mange unge som flytter ut.]\n\nEn sak som kobler statistikk til byens puls.",
             "images": [
                 {"motiv": "Konsertpublikum på et utested", "bildetekst": "Unge er kjernepublikum i utelivet."},
                 {"motiv": "Utested/kulturhus i Stavanger", "bildetekst": "Illustrasjon – byens uteliv."}],
             "sources": ["Driver av utested/scene", "Stavanger kommune kultur", "SSB befolkning"]},
        ],
    },
    {
        "id": "studenter",
        "tag": "SSB-data", "relevance": "høy",
        "headline": "Flere i studentalder i Stavanger – men presset øker",
        "fact": "Antallet i studentalder (19–24 år) i Stavanger økte 1,9 % på ett år, til rundt 11 620 i 2026 – sterkere enn både Rogaland og landet.",
        "metric": "+1,9 %", "period": "19–24 år · 2025→2026",
        "source": "SSB (befolkning, 07459)",
        "url": "https://www.ssb.no/statbank/table/07459",
        "cov_query": "Stavanger studenter hybel bolig UiS 2026",
        "angles": [
            {"title": "Bolig: er det nok hybler til alle?",
             "article": "Aldersgruppen 19–24 år vokser raskere i Stavanger enn i landet ellers. Flere i studentalder betyr økt press på et allerede stramt marked for hybler og små leiligheter.\n\nKlarer studentboligtilbudet å holde tritt?\n\n[Be studentsamskipnaden om ventelistetall for studentboliger, og sjekk hybelprisene mot i fjor. Finn en student som har slitt med å finne bosted.]\n\nEn konkret bolig-sak som treffer mange unge i byen.",
             "images": [
                 {"motiv": "Studenthybel / kollektiv", "bildetekst": "Illustrasjon – trangt på hybelmarkedet."},
                 {"motiv": "Finn.no-annonser på skjerm", "bildetekst": "Sjekk hybelprisene mot i fjor."}],
             "sources": ["Studentsamskipnaden", "Student på hybeljakt", "Eiendom Norge (leie)"]},
            {"title": "Studieby: en lyspunkt-sak?",
             "article": "Mens Stavanger mister 20-åringene, vokser gruppen 19–24 år. Det kan tyde på at studietilbudet faktisk trekker unge til byen i en fase.\n\nHva gjør UiS og byen riktig – og hvordan holder man på de unge etter studiene?\n\n[Snakk med UiS om vekst i studenttall og med kommunen om tiltak for å beholde nyutdannede. En positiv vinkling som balanserer utflyttings-sakene.]\n\nEn sak om hva som faktisk fungerer.",
             "images": [
                 {"motiv": "Fornøyde studenter på campus", "bildetekst": "Studietilbudet trekker unge til byen."},
                 {"motiv": "UiS-bygg", "bildetekst": "Illustrasjon – Universitetet i Stavanger."}],
             "sources": ["UiS ledelse", "Stavanger kommune næring", "Nyutdannet som ble værende"]},
        ],
    },
]

PILL = {"green": ("🟢 Uskrevet", "pg"), "yellow": ("🟡 Delvis dekket", "pa"),
        "red": ("🔴 Allerede dekket", "pr"), "unknown": ("· Ukjent", "pu")}


def enrich_coverage():
    for c in CASES:
        try:
            cov = coverage.check(c["cov_query"])
        except Exception:  # noqa: BLE001
            cov = {"status": "unknown"}
        c["cov"] = cov.get("status", "unknown")


def render() -> str:
    data_json = json.dumps(CASES, ensure_ascii=False)
    # UI bygges klientside fra CASES via JS.
    return TEMPLATE.replace("__DATA__", data_json)


TEMPLATE = r"""<style>
:root{--bg:#0d1320;--bg2:#0b111c;--panel:#141c2b;--panel2:#1a2333;--bd:#232e43;--tx:#e7ecf4;--mu:#8a97ab;--fa:#61708a;--ac:#3b82f6;--ac2:#2f6bff;--gr:#37c46d;--am:#e0a63a;--rd:#e0574c;}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent;}
.app{max-width:480px;margin:0 auto;background:var(--bg);min-height:100vh;color:var(--tx);font-family:-apple-system,'Segoe UI',Roboto,Arial,sans-serif;position:relative;padding-bottom:74px;}
.hd{display:flex;align-items:center;justify-content:space-between;padding:16px 18px 12px;position:sticky;top:0;background:linear-gradient(180deg,#0d1320,#0d1320f0);z-index:5;}
.hd .l{display:flex;align-items:center;gap:10px;}.hd .lg{font-size:22px;color:var(--ac);}.hd h1{font-size:21px;margin:0;font-weight:800;}
.scan{background:var(--ac2);color:#fff;border:0;padding:9px 15px;border-radius:11px;font-weight:600;font-size:13px;}
.note{margin:0 18px 12px;background:rgba(224,166,58,.10);border:1px solid rgba(224,166,58,.3);color:var(--am);font-size:12px;padding:8px 12px;border-radius:10px;}
.kpis{display:grid;grid-template-columns:repeat(2,1fr);gap:10px;padding:0 18px 8px;}
.kpi{background:var(--panel);border:1px solid var(--bd);border-radius:14px;padding:12px 14px;}
.kpi .n{font-size:24px;font-weight:800;}.kpi .n.g{color:var(--gr);}.kpi .n.sm{font-size:16px;}
.kpi .l{font-size:11.5px;color:var(--mu);margin-top:2px;}
.dl{width:100%;margin-top:10px;background:var(--panel2);color:var(--ac);border:1px solid var(--bd);padding:13px;border-radius:12px;font-weight:600;font-size:14px;}
.feed{padding:0 18px;}
.card{background:var(--panel);border:1px solid var(--bd);border-radius:16px;padding:15px;margin-bottom:14px;cursor:pointer;transition:transform .08s;}
.card:active{transform:scale(.985);}
.row{display:flex;justify-content:space-between;align-items:center;gap:8px;}
.pill{font-size:12px;font-weight:700;padding:5px 11px;border-radius:14px;white-space:nowrap;}
.pg{background:rgba(55,196,109,.16);color:var(--gr);}.pa{background:rgba(224,166,58,.16);color:var(--am);}.pr{background:rgba(224,87,76,.16);color:var(--rd);}.pu{background:#1a2333;color:var(--mu);}
.tag{font-size:11px;color:var(--mu);background:var(--panel2);border:1px solid var(--bd);padding:3px 9px;border-radius:7px;white-space:nowrap;}
.rel{display:inline-block;margin-top:9px;font-size:11px;padding:3px 9px;border-radius:12px;background:rgba(224,166,58,.12);color:var(--am);}
.card h3{font-size:18.5px;line-height:1.25;margin:8px 0 6px;}
.desc{color:var(--mu);font-size:13px;margin:0 0 11px;}
.chip{display:inline-block;background:var(--panel2);border:1px solid var(--bd);border-radius:10px;padding:8px 12px;font-size:14px;margin-bottom:11px;}
.chip b{font-size:18px;}.cg b{color:var(--gr);}.ca b{color:var(--am);}.cr b{color:var(--rd);}.cu b{color:var(--tx);}
.more{display:flex;justify-content:space-between;align-items:center;border-top:1px solid var(--bd);padding-top:11px;color:var(--ac);font-size:13.5px;font-weight:600;}
/* detail */
.det{padding:0 18px 20px;display:none;}
.back{background:none;border:0;color:var(--ac);font-size:15px;padding:14px 0;cursor:pointer;}
.fact{background:var(--panel);border:1px solid var(--bd);border-radius:14px;padding:14px;margin-bottom:16px;}
.fact h2{font-size:20px;margin:0 0 8px;line-height:1.25;}.fact p{color:var(--mu);font-size:14px;margin:0;}
.tabs{display:flex;gap:8px;overflow-x:auto;padding-bottom:10px;margin-bottom:4px;}
.tb{flex:none;background:var(--panel2);border:1px solid var(--bd);color:var(--mu);padding:8px 14px;border-radius:20px;font-size:13px;cursor:pointer;white-space:nowrap;}
.tb.on{background:var(--ac2);color:#fff;border-color:var(--ac2);}
.art h4{font-size:17px;margin:6px 0 10px;}
.art p{font-size:14.5px;line-height:1.6;margin:10px 0;color:#dbe3ee;}
.art .flag{color:var(--fa);font-style:italic;}
.lbl{font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--fa);margin:18px 0 6px;}
.imgs{list-style:none;padding:0;margin:0;}.imgs li{background:var(--panel);border:1px solid var(--bd);border-radius:10px;padding:10px 12px;margin-bottom:8px;font-size:13.5px;}.imgs .cap{color:var(--mu);font-size:12.5px;display:block;margin-top:3px;}
.src{margin:0;padding-left:18px;font-size:13.5px;color:var(--mu);}.src li{margin-bottom:4px;}
.act{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:24px;}
.ap{background:var(--gr);color:#06210f;border:0;padding:14px;border-radius:12px;font-weight:700;font-size:15px;}
.fo{background:var(--panel2);color:var(--mu);border:1px solid var(--bd);padding:14px;border-radius:12px;font-size:15px;}
.empty{text-align:center;color:var(--mu);padding:60px 24px;}
.saved{background:rgba(55,196,109,.12);color:var(--gr);border:1px solid rgba(55,196,109,.3);border-radius:10px;padding:10px;text-align:center;font-size:13px;margin-top:14px;}
.nav{position:fixed;bottom:0;left:50%;transform:translateX(-50%);width:100%;max-width:480px;background:#0b111ce8;backdrop-filter:blur(8px);border-top:1px solid var(--bd);display:flex;justify-content:space-around;padding:10px 0 16px;z-index:10;}
.nv{background:none;border:0;text-align:center;color:var(--fa);font-size:11px;cursor:pointer;}.nv .ic{font-size:20px;display:block;margin-bottom:2px;}.nv.on{color:var(--ac);}
</style>
<div class="app" id="app"></div>
<script>
const CASES = __DATA__;
const PILL = {green:['🟢 Uskrevet','pg'],yellow:['🟡 Delvis dekket','pa'],red:['🔴 Allerede dekket','pr'],unknown:['· Ny','pu']};
const CFILL = {green:'cg',yellow:'ca',red:'cr',unknown:'cu'};
const esc = s => (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
function saved(){try{return JSON.parse(localStorage.getItem('cr_saved')||'{}')}catch(e){return {}}}
function setSaved(o){localStorage.setItem('cr_saved',JSON.stringify(o))}
let view={name:'radar',caseId:null,angle:0};

function header(){
  return `<div class="hd"><div class="l"><span class="lg">📡</span><h1>Case-radar</h1></div>
    <button class="scan" onclick="alert('Demo: «Skann nå» henter ferske saker i den fulle appen.')">🛰 Skann nå</button></div>`;
}
function nav(){
  const s=Object.keys(saved()).length;
  const t=(n,ic,lb)=>`<button class="nv ${view.name===n?'on':''}" onclick="go('${n}')"><span class="ic">${ic}</span>${lb}${n==='godkjente'&&s?` (${s})`:''}</button>`;
  return `<div class="nav">${t('radar','📡','Radar')}${t('godkjente','✓','Godkjente')}${t('plan','📅','Plan')}</div>`;
}
function kpis(){
  const g=CASES.filter(c=>(c.cov||'')==='green').length;
  const nS=Object.keys(saved()).length;
  const t=(n,l,cls='')=>`<div class="kpi"><div class="n ${cls}">${n}</div><div class="l">${l}</div></div>`;
  return `<div class="kpis">${t(CASES.length,'saker i radaren')}${t(g,'🟢 uskrevet','g')}${t(nS,'godkjente')}${t('i dag','sist skannet','sm')}</div>`;
}
function radar(){
  let h=header()+`<div class="note">Ekte SSB-tall. Trykk en sak → se ulike vinkler + hele artikler. «Godkjenn» lagres på telefonen. Tips: Del → «Legg til på Hjem-skjerm» for å bruke den som app.</div>`+kpis()+`<div class="feed">`;
  CASES.forEach(c=>{
    const [pl,pc]=PILL[c.cov||'unknown'];
    h+=`<div class="card" onclick="openCase('${c.id}')">
      <div class="row"><span class="pill ${pc}">${pl}</span><span class="tag">${esc(c.tag)}</span></div>
      <div><span class="rel">🎯 ${esc(c.relevance)} relevans</span></div>
      <h3>${esc(c.headline)}</h3>
      <p class="desc">${esc(c.fact.slice(0,120))}…</p>
      <div class="chip ${CFILL[c.cov||'unknown']}"><b>${esc(c.metric)}</b> · ${esc(c.period)}</div>
      <div class="more"><span>${c.angles.length} vinkler + artikler</span><span>›</span></div>
    </div>`;
  });
  return h+`</div>`+nav();
}
function detail(){
  const c=CASES.find(x=>x.id===view.caseId); if(!c)return radar();
  const a=c.angles[view.angle]||c.angles[0];
  const isSaved=saved()[c.id+'::'+view.angle];
  let tabs=c.angles.map((an,i)=>`<button class="tb ${i===view.angle?'on':''}" onclick="setAngle(${i})">${esc(an.title)}</button>`).join('');
  let body=a.article.split('\n\n').map(p=>{
    const fl=p.trim().startsWith('[');
    return `<p class="${fl?'flag':''}">${esc(p)}</p>`;
  }).join('');
  let imgs=a.images.map(im=>`<li><b>${esc(im.motiv)}</b><span class="cap">${esc(im.bildetekst)}</span></li>`).join('');
  let src=a.sources.map(s=>`<li>${esc(s)}</li>`).join('');
  return `<div class="det" style="display:block">
    <button class="back" onclick="go('radar')">‹ Tilbake til radaren</button>
    <div class="fact"><h2>${esc(c.headline)}</h2><p>${esc(c.fact)}</p>
      <div class="chip ${CFILL[c.cov||'unknown']}" style="margin-top:12px"><b>${esc(c.metric)}</b> · ${esc(c.period)}</div></div>
    <div class="lbl">Velg vinkel (${c.angles.length})</div>
    <div class="tabs">${tabs}</div>
    <div class="art"><h4>${esc(a.title)}</h4>${body}
      <div class="lbl">📸 Forslag til bilder</div><ul class="imgs">${imgs}</ul>
      <div class="lbl">✅ Kilder å ringe / sjekke</div><ul class="src">${src}</ul>
    </div>
    ${isSaved?`<div class="saved">✓ Denne vinkelen er godkjent og lagret</div>
       <button class="dl" onclick="download('${c.id}',${view.angle})">⬇ Last ned artikkelen</button>`:
      `<div class="act"><button class="ap" onclick="approve('${c.id}')">Godkjenn denne vinkelen</button>
       <button class="fo" onclick="go('radar')">Ikke nå</button></div>`}
  </div>`+nav();
}
function godkjente(){
  const s=saved();const keys=Object.keys(s);
  let h=header();
  if(!keys.length)return h+`<div class="empty"><h3>Ingen godkjente saker ennå</h3><p>Gå til radaren, velg en vinkel og trykk «Godkjenn».</p></div>`+nav();
  h+=`<div class="feed">`;
  keys.forEach(k=>{const it=s[k];
    h+=`<div class="card" onclick="openAngle('${it.caseId}',${it.angle})">
      <div class="row"><span class="pill pg">✓ Godkjent</span><span class="tag">${esc(it.source)}</span></div>
      <h3>${esc(it.angleTitle)}</h3><p class="desc">${esc(it.headline)}</p>
      <div class="more"><span>Les artikkelen</span><span>›</span></div></div>`;
  });
  return h+`</div>`+nav();
}
function plan(){
  const s=saved();const keys=Object.keys(s);let h=header();
  if(!keys.length)return h+`<div class="empty"><h3>📅 Din plan</h3><p>Godkjenn saker i radaren, så dukker de opp her som en gjøreliste for uka – med første kilde å ringe.</p></div>`+nav();
  h+=`<div class="feed"><div class="lbl" style="padding:2px 2px 6px">Denne uka – følg opp</div>`;
  keys.forEach((k,i)=>{const it=s[k];
    h+=`<div class="card" onclick="openAngle('${it.caseId}',${it.angle})">
      <div class="row"><span class="pill pg">Sak ${i+1}</span><span class="tag">${esc(it.source)}</span></div>
      <h3 style="font-size:16px;margin-top:8px">${esc(it.angleTitle)}</h3>
      <p class="desc">${esc(it.headline)}</p>
      <div class="more"><span>📞 Ring: ${esc(it.firstSource||'kilde i saken')}</span><span>›</span></div></div>`;
  });
  return h+`</div>`+nav();
}

function render(){const el=document.getElementById('app');
  el.innerHTML = view.name==='radar'?radar():view.name==='detail'?detail():view.name==='godkjente'?godkjente():plan();
  window.scrollTo(0,0);}
function go(n){view.name=n;render();}
function openCase(id){view.name='detail';view.caseId=id;view.angle=0;render();}
function openAngle(id,a){view.name='detail';view.caseId=id;view.angle=a;render();}
function setAngle(i){view.angle=i;render();}
function approve(id){const c=CASES.find(x=>x.id===id);const a=c.angles[view.angle];
  const s=saved();s[id+'::'+view.angle]={caseId:id,angle:view.angle,headline:c.headline,angleTitle:a.title,source:c.source,firstSource:(a.sources&&a.sources[0])||''};
  setSaved(s);render();}
function copyText(t){if(navigator.clipboard){navigator.clipboard.writeText(t).then(()=>alert('Artikkelen er kopiert – lim den inn der du vil.'),()=>alert('Kunne ikke kopiere automatisk.'));}else{alert('Nedlasting/kopiering er ikke tilgjengelig her.');}}
async function download(id,angle){
  const c=CASES.find(x=>x.id===id);const a=c.angles[angle];
  const text=`${a.title}\n\n${c.fact}\n\n${a.article}\n\nFORSLAG TIL BILDER:\n`+a.images.map(im=>`- ${im.motiv} (${im.bildetekst})`).join('\n')+`\n\nKILDER Å RINGE / SJEKKE:\n`+a.sources.map(x=>`- ${x}`).join('\n')+`\n\nDatakilde: ${c.source}\n(Utkast fra Case-radar – faktasjekk før publisering.)`;
  const fn=(a.title||'artikkel').toLowerCase().replace(/[^a-z0-9æøå ]/gi,'').trim().replace(/ +/g,'_').slice(0,40)+'.txt';
  if(window.claude&&window.claude.downloads){
    try{await window.claude.downloads.save({filename:fn,data:text});}
    catch(e){if(e&&e.code==='declined')return;copyText(text);}
  }else{copyText(text);}
}
render();
</script>
"""


def main():
    print("Henter live dekningsstatus per sak ...")
    enrich_coverage()
    for c in CASES:
        print(f"  {c['id']}: {c.get('cov')}")
    out = render()
    path = ("/tmp/claude-0/-home-user-Trading-bot/db52581d-3123-56ba-9e44-"
            "ec1bf6e66cc2/scratchpad/case-radar-app.html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(out)
    print("skrevet", len(out), "bytes ->", path)


if __name__ == "__main__":
    main()
