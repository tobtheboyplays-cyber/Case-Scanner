# UI-notater fra designforslagene (25.07.2026)

Utvalgte ideer verdt å ta inn. Ikke alt — bare det som faktisk gjør verktøyet bedre.

## 1. «Be om utkast» — ikke generer alt på forhånd ⭐ VIKTIGST

Forslag 2 har en **«Be om utkast»**-knapp: brukeren velger vinkel FØRST, og
artikkelen skrives på forespørsel.

Dette er ikke bare UI — det er en arkitekturforbedring:

- I dag skriver journalist-agenten **tre fulle artikler for hver godkjente sak**, ved
  hvert skann. Det er tregt og brenner kvote på saker journalisten aldri åpner.
- Bedre: journalisten leverer først tre **vinkel-overskrifter** (tittel + én setning +
  hvem som må ringes). Full artikkel skrives kun for den vinkelen han faktisk ber om.
- Gevinst: raskere skann, mye lavere forbruk, og modellen kan bruke flere tokens på
  den ene artikkelen som faktisk skal brukes.

**Konsekvens for koden:** del `journalist_angles()` i to steg — `angles_short()` ved
skann, `write_draft(angle)` på knappetrykk.

## 2. Dekningsstatus som ikon + TEKST, ikke bare farge

Forslagene bruker et skjold-ikon pluss ordene «INGEN HAR SKREVET DET» / «DELVIS
DEKKET» / «GODT DEKKET». Mye bedre enn fargeprikkene mine:

- lesbart for fargeblinde (form + tekst + farge, ikke farge alene)
- sier hva det BETYR, ikke bare at det er grønt

Dette er den enkleste og mest verdifulle endringen å gjøre nå.

## 3. Tallet med sammenligningen rett under

`+1,9 %` stort, og «mot +0,4 % i landet» i mindre tekst umiddelbart under. Avviket ER
nyheten — da må sammenligningen stå der tallet står, ikke i en egen boks ved siden av.

## 4. Kildehenvisning alltid synlig på kortet

«SSB tabell 07459» oppe til høyre på hvert kort. Proveniens er ikke en detalj man
graver fram — den skal være synlig hele tiden. Passer perfekt med ankeret vi allerede
bygget.

## 5. Vinklene som ikonknapper med undertekst

I stedet for «1 / 2 / 3»:

- 👤 **Menneske** — «Slik påvirker det studentene»
- 📈 **Konsekvens** — «Hva betyr det for leiemarkedet?»
- 🔍 **Årsak** — «Hvorfor skjer dette akkurat nå?»

Undertekstene gjør valget informert uten å måtte åpne noe.

## 6. Kalender: saker som BÅND over dager, ikke prikker

Forslag 4 tegner hver sak som et horisontalt bånd fra start til deadline, med tittel
oppå. Langt bedre enn prikkene mine — man ser lengde og overlapp umiddelbart.
Under rutenettet: **«Kommende deadlines»** som enkel liste, og stadiene med antall
(«Research · 2 saker»).

## 7. Dagsoversikt som landingsside (forslag 5)

«God morgen» + dagens viktigste lead + dagens oppgaver. Verdt å vurdere som startside
senere, men ikke prioritet nå — radaren og kalenderen først.

---

## Retning

Designerens anbefaling — **forslag 2 (én sak av gangen) for dypdykk + forslag 4
(kalender først) for planlegging** — sammenfaller med min egen vurdering. To flater
for to helt ulike oppgaver.

## Rekkefølge for implementering

1. Dekningsstatus med ikon + tekst (raskest, størst effekt)
2. Tallet + sammenligning samlet, kildehenvisning på kortet
3. Vinkler som ikonknapper med undertekst
4. «Be om utkast» — lat generering (arkitekturendring, størst gevinst)
5. Kalenderbånd + kommende deadlines
