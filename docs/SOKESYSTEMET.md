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

## Temavalget styrer søket

Journalisten huker av temaer i menyen ved «Skann nå». Det er **25 temaer i seks
grupper** (Folk, Penger, Arbeid, Hverdag, Miljø, Annet), og de dekker
**alle 23 hovedemner i SSBs katalog** — ingen del av statistikken er utilgjengelig.
Valget lagres i `meta`-tabellen og oversettes i `app/config.py` (`TEMAER`) til
tre forskjellige vokabularer. **Tomt valg = alle temaer** — en tom meny skal aldri
gi et tomt skann.

Temaet biter tre steder:

| Felt | Hvor det virker |
|---|---|
| `sok` | søkeord mot katalogen — **fire per skann** når han har valgt noe, to ellers |
| `koder` | SSBs egne emnekoder; løfter treff fra ferskhets- og katalogsporet |
| `ssb_emner` | vekting av publiseringskalenderen (et *helt annet* SSB-vokabular) |

### To feller i SSBs emnekoder

1. **`?subjectCode=` ignoreres av API-et.** Verifisert 26.07.2026: kallet
   returnerte alle 3 786 tabellene uansett. Filtreringen må gjøres på vår side.
2. **En tabell ligger under flere stier, og riktig kode er ikke den første.**
   Tabell 09413 (siktede personer) har stiene `in > …`, `sk > …` og `sv > …`.
   Leste vi bare `paths[0]`, ville alle kriminalitetstabellene sett ut som
   innvandringsstatistikk. `_hovedemner()` leser første ledd i *hver* sti.
   Kodene er heller ikke til å gjette: `in` er **Innvandring**, inntekt er `if`,
   og jord/skog/fiske er `js`.

**Treffene fra temasporet legges FØRST i køen når han har valgt noe.** Det er
ikke kosmetikk: målt 26.07.2026 ga «helse+kriminalitet» og «næringsliv» nøyaktig
samme åtte tabeller uten den prioriteringen — søkeordene endret seg, men
ferskhets- og katalogsporet fylte kvoten uansett.

Målt etter fiksen (26.07.2026, ekte kall): «næringsliv» gir **6 av 8** probede
tabeller fra temaet, og de åtte er helt andre enn dem «helse+kriminalitet» gir.
Ferskhetssporet slipper fortsatt gjennom uansett tema — det er meningen.

## Justering

Alt står øverst i `app/collectors/ssb_sok.py`: `KOMMUNER`, `FERSK_DAGER`,
`MAKS_KANDIDATER`, `MIN_ENDRING_PST`, `MIN_NIVAA`. Søkeordene per tema står i
`app/config.py` under `TEMAER`.

---

# Gjennomgang 26.07.2026 — hva som faktisk kom ut

Eieren: *«ta en full sjekk av søke systemet og tester iherdig og ser litt over
hva som kommer og hva som kan eventuelt forbedres»*.

Metode: tre ekte skann mot SSB med **tom database**, så rotasjonen startet på
null. Alt under er målt, ikke antatt.

**Resultat:** 24 tabeller probet, **7 leads** (~29 % treffrate). Rotasjonen
virker — runde 1 lette på folkemengde/flytting/fødte/døde, runde 2 på
barnehage/grunnskole/elever, runde 3 på barnevern/eldre/sykehjem, og hver runde
tok en ny katalogside. De beste funnene var ekte saker: *«Ulykker i Sandnes: 65 i
2025, mot 39 i 2024»* og *«Godkjent bruksareal til annet enn boliger opp 154 %»*.

## Tre problemer, alle rettet

### 1. Overskriftene var rå SSB-variabelnavn

| Før | Etter |
|---|---|
| `Antall menn i kvalifiseringsprogram (antall) opp 23 %` | `Kvalifiseringsstønad opp 17 %` |
| `Kommunens totale kostnader til krisesentertilbud (NOK) … opp 96 %` | `Kommunens totale kostnader til krisesentertilbud opp 96 %` |
| `Årstimer til morsmålsopplæring, kommunale og private … opp 20 %` | `Årstimer til morsmålsopplæring opp 20 %` |

Tallene var riktige hele tiden. Men ingen leser en overskrift som begynner med
«Korrigerte brutto driftsutgifter», og et lead som ikke blir lest er et lead som
ikke finnes. `_overskrift()` fjerner enhetsparenteser (`(antall)`, `(kr)`,
`(NOK)`), etatskoder (`(f221)`) og et stumt innledende «Antall ».

**Det fulle variabelnavnet står uendret i `finding`** — der er presisjon
viktigere enn rytme, og journalisten må kunne finne igjen variabelen hos SSB.

### 2. Fem av sju leads var Sandnes — i en Stavanger-avis

Systemet valgte kommunen med størst prosentutslag. Sandnes er mindre, så
prosentene svinger mer der, og Sandnes vant nesten alltid.

`SANDNES_MARGIN = 1.4`: Sandnes må slå Stavanger med margin, ikke med en desimal.
**Vektlegging, ikke filter** — en kraftig Sandnes-sak går fortsatt gjennom, og
har Stavanger ingen sak i den tabellen, er Sandnes riktig svar. Etter endringen
er fordelingen fortsatt Sandnes-tung, og det er ærlig: i de tabellene lå
Stavanger-utslaget under terskelen.

### 3. Småtall konkurrerte med ekte signaler

`Antall menn i kvalifiseringsprogram: 128 mot 104` er +23 % og 24 personer — det
kan være ett kull. Det lå og konkurrerte med `Ulykker: 65 mot 39`.

Under `SMAATALL = 300` kreves nå 30 % endring i stedet for 15 %. Etter endringen
plukket systemet en annen variabel i samme tabell: kvalifiseringsstønad, 40,8 mot
34,9 millioner kroner. Samme tabell, større tall, bedre sak.

## Det som IKKE ble endret, og hvorfor

- **Treffraten på 29 % er ikke et problem.** De 71 prosentene er tabeller uten
  kommunetall, uten eliminerbare dimensjoner, eller under terskelen — og utfallet
  skrives til `ssb_tabeller`, så de aldri probes igjen.
- **Åtte kandidater per skann** (`MAKS_KANDIDATER`) ligger godt under SSBs tak på
  30 kall i minuttet. Å øke det ville gitt flere leads, men også lengre skann — og
  redaktøren rekker uansett bare fire saker per skann på Groqs kvote.

## Testene

`tests/test_ssb_sok.py` har nå 38 tester. De ni nye vokter nøyaktig funnene over:
at Stavanger vinner ved likt utslag, at en klart større Sandnes-sak likevel går
gjennom, at småtall krever mer, at store tall beholder den lave terskelen, og at
overskriften ryddes mens funnet forblir presist.
