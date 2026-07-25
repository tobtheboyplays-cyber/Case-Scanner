# Søkesystemet — hvordan «trykk søk igjen» gir ny statistikk

**Problemet:** De opprinnelige SSB-probene spurte alle den **samme tabellen** (07459,
befolkning etter alder) med ulike aldersintervaller. Trykket journalisten søk to ganger
på rad, fikk han identiske funn. Verktøyet lette ikke — det gjentok seg.

**Løsningen:** `app/collectors/ssb_sok.py` leter i **hele SSBs katalog** (127 sider,
7 700+ tabeller) og **husker hvor den har vært**. Neste søk starter der forrige slapp.

## De tre sporene

Hvert skann henter kandidater fra tre uavhengige spor. De utfyller hverandre: ett er
raskt, ett er målrettet, ett er uttømmende.

| Spor | Kall | Hva det gir | Markør i databasen |
|---|---|---|---|
| **Ferskhet** | `?pastDays=10` | Tabeller SSB *faktisk har oppdatert* de siste 10 dagene — bokstavelig talt ny statistikk | `ssb_fersk_side` |
| **Tema-rotasjon** | `?query=<ord>` | Søkeordene til temaene journalisten har huket av, to per skann, hver med egen sidemarkør | `ssb_tema_markor`, `ssb_side:<ord>`, `temaer` |
| **Katalogen** | `?pageNumber=N` | Systematisk gjennomgang, én side per skann | `ssb_katalog_side` |

Katalogsporet er **garantien mot at køen går tom**. 127 sider betyr at det alltid finnes
en side journalisten ikke har vært på — uansett hvor mange ganger han trykker søk.

## Silen: fire kall spart per bomtabell

Kandidater vurderes billigst-først, slik at de dyre kallene (metadata + data) treffer
tabellene som faktisk kan gi en lokal sak.

1. **Navnet** — SSB merker tabeller `(K)` kommune, `(B)` bydel, `(F)` fylke. Rene
   `(F)`-tabeller forkastes uten et eneste ekstra kall. *Dette alene halverte bomkallene
   i test: 17 av 28 prober var fylkestabeller.*
2. **Variabellista** — må nevne region/kommune/fylke/bydel.
3. **Metadata** (1 kall) — har `Region` faktisk 1103 (Stavanger) eller 1108 (Sandnes)?
   Kan alle øvrige dimensjoner elimineres? Finnes det en skjult tidsdimensjon?
4. **Data** (1 kall) — nyeste periode mot **samme periode i fjor**, opptil fem
   statistikkvariabler i samme kall.

## To feller vi har gått i, og hvordan de er stengt

### «Døde ned 50 % i Sandnes» — den halvferdige perioden
Tabell 12983 har **år** som tidsvariabel og **måned** som egen dimensjon. Summerer man
bort månedene, sammenligner man et pågående 2026 (seks måneder) med hele 2025. Verktøyet
meldte «Døde ned 50 %». Det var ikke sant — bare halve året hadde gått.

→ Enhver tabell med en tidsdimensjon *i tillegg til* tidsvariabelen avvises som
`delvis-periode`, permanent. Regresjonstest: `test_avviser_tabell_med_maanedsdimensjon`.

### «+167 %» på tre hendelser — småtallsfellen
3 mot 8 er +167 % og likevel ren støy.

→ **Begge** sidene må være ≥ 20 (`MIN_NIVAA`), og endringen ≥ 15 % (`MIN_ENDRING_PST`).
Rå-tallene står alltid i funnet, så journalisten kan kontrollere prosenten selv.

### Sesong
Kvartal mot forrige kvartal er nesten alltid feil. Vi går alltid **ett år tilbake** —
antall perioder utledes av tabellens `timeUnit` (kvartalsvis = 4 tilbake, månedlig = 12).

## Hukommelsen

Tabellen `ssb_tabeller` lagrer utfallet av hvert forsøk:

| Verdikt | Permanent? | Hvorfor |
|---|---|---|
| `ingen-kommune` | ja | Strukturen blir ikke en annen av at tallene oppdateres |
| `ikke-eliminerbar` | ja | Vet ikke hvilken næring/gruppe tallet gjelder |
| `delvis-periode` | ja | Skjult tidsdimensjon |
| `for-kort` / `ingen-tid` | ja | For kort tidsserie |
| `under-terskel` | **nei** | Tallet lå under terskel *denne* gangen |
| `treff` | **nei** | Ga en sak — sjekk igjen ved nye tall |
| `feil` | **nei** | Nettverksfeil o.l. |

Midlertidige avslag prøves på nytt **kun når SSB har publisert nye tall** (feltet
`updated` fra katalogen har endret seg). Ellers går kallet til noe vi ikke har sett.

## Driftshensyn

SSB tillater **30 spørringer per minutt per IP**. Et skann bruker maks 4 katalogkall
+ 2 kall × 8 kandidater = 20, med 0,4 s mellom datakallene. Et helt skann tar 30–50
sekunder, så vi ligger godt under taket. Kollektoren er fail-soft: en død kilde gir en
statuslinje, ikke et krasj.

## Målt i praksis (25.07.2026, seks skann på rad)

- 35 tabeller utforsket, frontlinjen flyttet seg hvert eneste skann
- 5 nye leads (bl.a. «Godkjente boliger opp 770 % i Stavanger» — 30 → 261 på ett år)
- 3 av 6 skann ga null nye leads fra dette sporet

**Det siste er et ærlig resultat, ikke en feil.** De fleste SSB-tabeller beveger seg
ikke 15 % på et år. Søkesystemet er additivt: et fullt skann gir fortsatt 14–17 leads
fra de andre kildene, og dette sporet legger på det som er genuint nytt.

## Temavalget styrer sporet

Journalisten huker av temaer i menyen ved «Skann nå» (helse, lønn, fattigdom,
barn og unge, alderdom, idrett, kriminalitet, næringsliv). Valget oversettes i
`app/config.py` (`TEMAER`) til søkeord mot katalogen, og lagres i `meta`-tabellen.
**Tomt valg = alle temaer** — en tom meny skal aldri gi et tomt skann.

**Treffene fra temasporet legges FØRST i køen når han har valgt noe.** Det er
ikke kosmetikk: målt 26.07.2026 ga «helse+kriminalitet» og «næringsliv» nøyaktig
samme åtte tabeller uten den prioriteringen — søkeordene endret seg, men
ferskhets- og katalogsporet fylte kvoten uansett. Etter fiksen er 5 av 8 tabeller
forskjellige mellom de to valgene. De tre felles kommer fra ferskhetssporet, som
skal slippe gjennom uansett tema.

## Justering

Alt står øverst i `app/collectors/ssb_sok.py`: `KOMMUNER`, `FERSK_DAGER`,
`MAKS_KANDIDATER`, `MIN_ENDRING_PST`, `MIN_NIVAA`. Søkeordene per tema står i
`app/config.py` under `TEMAER`.
