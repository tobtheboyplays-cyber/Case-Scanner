# Kildene — hva som ble sjekket, hva som kom med, og hvorfor resten falt fra

Eieren 26.07.2026: «Finn flere kilder vi kan søke igjennom som er gratis og kan
gi noe.»

Regelen fra `docs/KILDEREGELEN.md` gjelder alt her: **kilder som kan LAGE
artikler, ikke artikler for å lage artikler.** En avissak er noen andres ferdige
jobb; et konkursvedtak, et SSB-tall og et representantforslag er råstoff ingen
har skrevet ut ennå.

Alt under er testet 26.07.2026 med et faktisk kall — ikke funnet i en liste og
antatt å virke. Statuskodene er de vi fikk.

## I bruk nå

| Kilde | Hva den gir | robots.txt |
|---|---|---|
| **SSB** (data.ssb.no) | Tall per kommune, faste prober + katalogsøk | åpen |
| **SSBs publiseringskalender** | Hva som slippes de neste ukene — det eneste ekte forspranget | åpen |
| **Brønnøysundregistrene** | Konkurser, avviklinger, nyregistreringer + regnskapstall | åpen, ingen nøkkel |
| **Stortinget** (data.stortinget.no) | Saker der en av Rogalands 14 representanter er saksordfører eller forslagsstiller | `Allow: /` |
| **Strømpris NO2** (hvakosterstrommen.no) | Timepriser i Stavangers eget prisområde, i dag og i morgen | ingen direktiver + eksplisitt fri bruk |
| **Sola lufthavn** (Avinor) | Kanselleringer og forsinkelser i sanntid | bare `Sitemap:`, ingen `Disallow` |
| **Vegvesenets tellepunkter** (trafikkdata.no) | Sykler og biler per døgn — 21 sykkelpunkter i storbyområdet | ingen robots.txt (404) |
| **Google News RSS** | Dekningssjekk + Aftenbladets eget arkiv (oppfølgere) | fasit, ikke råstoff |

### Vegvesenets tellepunkter — råstoffet ingen henter ut

Vegvesenet teller hver bil og hver sykkel som passerer 245 punkter i Rogaland,
døgn for døgn, og legger tallene åpent ut i et GraphQL-API. Ingen skriver om dem,
fordi de ligger bak et spørrespråk i stedet for i en pressemelding.

**Sykkel først, med vilje.** 21 av punktene i Stavanger/Sandnes/Sola/Randaberg
teller sykler — fire av dem på **Sykkelstamvegen**, som har kostet nær en
milliard og som det har stått strid om i ti år. «Hvor mange sykler faktisk der?»
er et spørsmål med et offentlig tall bak. Bilrekorder blir skrevet om uansett;
sykkeltallene er de få ingen henter ut.

**Terskel:** minst 15 % endring mot samme to ukers periode i fjor, på et punkt med
minst 80 passeringer i døgnet og minst 10 komplett målte døgn i *begge* år.

**Tre feller i dataene, og den tredje er den farligste:**

1. Døde punkter svarer med `volumeNumbers: null`, ikke med en feilkode.
   «Kannik (sykkel)» sto som `isOperational: true` og ga 14 tomme døgn på rad.
2. Tallene henger etter — de siste døgnene er ikke kvalitetssikret. Vinduet
   slutter fire dager tilbake.
3. **Et døgn kan være delvis målt.** Første ekte kjøring meldte «Sykkelstamvegen
   62 % opp mot i fjor» — men flere fjorårsdøgn var målt med 67 % dekning, så
   fjorårssnittet var kunstig lavt og hele endringen blåst opp. Nå teller bare
   døgn med minst 95 % dekning, og antall døgn oppgis for **begge** år i funnet.

Målt 26.07.2026 med komplette døgn: Sykkelstamvegen (Asser Jåtten bru sør)
1 039 sykler i døgnet 08.07–22.07, mot 639 i fjor — 63 prosent opp.

### Strømprisen — den mest personlige lokalnyheten som finnes

Stavanger ligger i **NO2**. Prisen for i morgen settes klokka 13 i dag, så fra
ettermiddagen har vi et tall ingen har skrevet om ennå, og som treffer hver eneste
husstand i byen. For et publikum på 20–39 år er det vanskelig å slå.

API-sida sier det rett ut: *«Fritt tilgjengelig for hvem som helst, til hva som
helst. Fordi vi mener strømprisen tilhører folket.»* robots.txt inneholder bare
den forklarende Cloudflare-blokka — ingen direktiver i det hele tatt.

**Terskel:** minst 25 % endring fra i dag til i morgen, ELLER minst 3× sprik
mellom billigste og dyreste time. Uten den ville strømprisen tatt en plass i lista
hver eneste morgen uansett hva den gjorde. Målt på ekte data 26.07.2026: 4,8 ×
sprik — 148,1 øre kl. 22 mot 30,9 øre kl. 10.

**Forbeholdet står i hvert funn:** prisene er uten nettleie, avgifter og
strømstøtte. En overskrift uten det er misvisende.

### Sola — saken man kan ringe på i løpet av minutter

Avinors XML-feed er åpen og oppdateres kontinuerlig. Terskel: minst én
kansellering, eller minst fire samtidige forsinkelser over 20 minutter — en
forsinket avgang er ikke en nyhet, det er en tirsdag.

To feller som kostet et forsøk hver:
- `TimeFrom` **må** være 0 eller større. Et negativt vindu gir `400`. Første
  utkast prøvde å se én time bakover for å fange ferske kanselleringer.
- Statuskoden `E` betyr bare at det er satt en forventet tid, ikke at flyet er
  forsinket. Uten minuttgrensen ble hver avgang med et estimat «forsinket».

### Hvorfor Stortinget er verdt plassen

Fjorten av 169 representanter er valgt fra Rogaland. Står én av dem som
saksordfører, er en riksdekkende sak også en **lokal** sak — med en navngitt
kilde som har telefonnummer og plikt til å svare. Det er en annen slags lead enn
et SSB-tall: der må journalisten først finne noen som merker tallet.

Målt: 650 saker i sesjonen, 99 med en lokal krok, tak på 8 per skann.

**Sommerferien var en felle.** Stortinget har fri fra juni til oktober. Nyeste
oppdaterte sak 26. juli var 31 dager gammel, medianen 89. Et vindu på 30 dager ga
derfor null treff hele sommeren — altså nettopp når journalisten har minst annet
å skrive om. Vinduet er 120 dager, og scoren faller med alderen.

## Sjekket og forkastet

| Kandidat | Hva som skjedde |
|---|---|
| norske-postlister.no | `Disallow: /` for ClaudeBot. Ikke lov. |
| eInnsyn | `Disallow: /api/`. Ikke lov. |
| politiet.no (politiloggen) | `Disallow: /api/`. Ikke lov. |
| stavanger.kommune.no | `Disallow: /api`. Ikke lov. |
| **NILU** (luftkvalitet) | `410 Gone` — «This endpoint has been discontinued». |
| **Mattilsynet smilefjes** | `data.mattilsynet.no/robots.txt` sier `Disallow: /` (sjekket 26.07.2026). Det er et nei, ikke en teknisk feil. Skulle vært den beste av alle — restauranthygiene er lokalt, konkret og ringbart. Ikke prøv igjen uten at robots endrer seg. |
| **NAV arbeidsplassen** | 404 på det åpne feed-endepunktet. |
| ~~**Vegvesenet trafikkdata**~~ | **Denne raden var feil.** Den sa «POST mot den nye adressen svarer med HTML» — det var feil vertsnavn. `https://trafikkdata-api.atlas.vegvesen.no/` svarer med ren JSON. Kilden er **i bruk nå**, se over. Lærdommen: «svarer med HTML» betyr som regel feil adresse, ikke stengt dør. |
| **NVE hydrologi** | `401` — krever gratis nøkkel. Mulig senere. |
| **MET Frost** (vær) | `400` uten nøkkel. Gratis nøkkel finnes. |
| **data.norge.no** | `Disallow: /api/`. Katalogen er lesbar, API-et ikke. |

## Kandidater som svarte, men som ikke ble tatt inn

| Kandidat | Status | Hvorfor ikke ennå |
|---|---|---|
| **Barnehagefakta** (Udir) | `200`, 128 barnehager i Stavanger, med feltet `oppfyllerPedagognorm` («Oppfyller pedagognormen med disp.») | Sterkeste ubrukte kandidat. Krever ett detaljkall per barnehage — 128 er for mange per skann, så den må rotere slik SSB-søket gjør. |
| **Geonorge** (adresser, stedsnavn, kommuneinfo) | `200` | Referansedata. Presist, men ingen sak i seg selv. |
| **Entur** (geocoder) | `200` | Samme — nyttig til oppslag, ikke til leads. |
| **Sokkeldirektoratet** (factpages) | `200`, månedlig produksjon per felt som CSV. Verifisert 26.07.2026 | Fungerer, og er unikt Stavanger. Men månedstall per oljefelt dekkes allerede tett av E24 og Aftenbladets oljedesk, og «Johan Sverdrup produserte X» er ikke en personlig sak for 20–39-åringer. Verdt å ta inn hvis vinkelen blir *arbeidsplasser* (felt som nærmer seg avvikling), ikke produksjon. |
| **Entur** (sanntid, Kolumbus) | `200`, ekte avgangstider med `cancellation`-flagg. Verifisert 26.07.2026 | Kan bli «bussen din er innstilt», som Sola er for fly. Krever at man plukker ut holdeplasser først — en innstilt buss er en tirsdag, akkurat som en forsinket avgang. Neste kandidat inn. |
| **MET MetAlerts** (farevarsel) | `200` for Rogaland, tom liste (ingen varsel i juli) | Nesten null støy — den fyrer bare når det ER et varsel. Men ekstremvær er det ene hver eneste redaksjon allerede får dyttet på seg, så forspranget er null. Bevisst utelatt. |
| **HKDIR/DBH** (studenttall UiS) | API-et svarer og gir en presis feilmelding på gale variabelnavn | Lovende for et 20–39-publikum (søkertall, frafall ved UiS), men krever at man kartlegger tabell- og variabelnavn først. |

## Regelen for neste gang

1. **Les robots.txt først.** Er den stengt, er den stengt — uansett hvor god
   dataen er.
2. **Gjør et ekte kall.** Halvparten av kandidatene her sto i en liste over
   «åpne norske API-er» og var avviklet, flyttet eller bak en nøkkel.
3. **Krev en lokal krok.** En nasjonal kilde uten et filter for Rogaland er 650
   saker som drukner de fem lokale.
4. **Skriv ned hvorfor den falt fra.** Ellers blir den sjekket på nytt om tre
   måneder av noen som ikke vet at den ble sjekket.
