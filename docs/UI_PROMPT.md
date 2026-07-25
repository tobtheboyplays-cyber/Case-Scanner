# Prompt: 5 UI-forslag til Case-radar (mobil)

Lim hele blokka under inn i en ny chat (ChatGPT, Claude, v0.dev eller Figma Make).

---

Du er en senior produktdesigner som lager mobil-UI for redaksjonelle verktøy.
Lag 5 ULIKE designforslag for appen «Case-radar», som skjermbilder til iPhone
(390×844 px, portrett). Ett bilde per forslag.

**HVA APPEN ER**
Case-radar er et verktøy for én journalist i Stavanger Aftenblad. Den henter ferske
tall fra SSB og andre åpne offentlige kilder, oppdager statistiske avvik som kan bli
saker, sjekker mot Google News om noen allerede har skrevet om det, og lar en KI
foreslå tre ulike vinkler med ferdige artikkelutkast. Journalisten godkjenner én
vinkel, setter startdag og deadline, og saken havner i en kalender.

MÅLET MED APPEN: finne saken FØR konkurrentene publiserer den.

**BRUKEREN**
En travel lokaljournalist. Bruker den på mobil, ofte stående, ofte i felt, ofte med
én hånd. Han skal på 30 sekunder se: er det noe her i dag som er verdt tiden min?

**INNHOLD SOM MÅ VÆRE MED** (bruk disse ekte eksemplene)
- Toppnivå: «14 leads · 9 uskrevet»
- En sak: «Studentalder opp 1,9 % — presser leiemarkedet»
  - Tallet: +1,9 % mot +0,4 % i landet
  - Kilde: SSB tabell 07459
  - Originalitetsmerke: grønn = ingen har skrevet dette, gul = delvis dekket,
    rød = godt dekket
  - Tre vinkler å velge mellom: Menneske / Konsekvens / Årsak
- En annen sak: «Arbeidsledigheten faller raskere i Rogaland» (gul, delvis dekket)
- Kalender: månedsrutenett der en sak fyller alle dagene fra startdag til deadline,
  med stadier Idé → Research → Skriving → Publisert
- Bunnmeny med tre faner: Radar · Kalender · Godkjent

**DE 5 FORSLAGENE SKAL VÆRE REELT FORSKJELLIGE**
Ikke fem fargevarianter av samme layout. Utforsk fem ulike måter å løse
informasjonshierarkiet på — for eksempel tett listeoversikt, én sak av gangen,
avis-/redaksjonspreg, kalender som hovedflate, eller noe du mener er bedre.
Begrunn kort hvorfor hver retning passer denne brukeren.

**KRAV**
- Alt på norsk (bokmål)
- Tallet i saken skal være det mest iøynefallende elementet — det er nyheten
- Originalitetsfargen må være lesbar for fargeblinde: bruk form/ikon/tekst i tillegg
  til farge, aldri farge alene
- Trykkflater minst 44 px
- Ekte tekstlengder, ikke «Lorem ipsum» og ikke kunstig korte titler
- Realistisk statuslinje øverst og hjemindikator nederst
- Ingen falske grafer uten forklaring; er det en graf, skal det stå hva den viser

**UNNGÅ**
Generisk «AI-dashboard»-stil med lilla gradienter og glødende linjer. Dette er et
arbeidsverktøy for en journalist, ikke en fintech-forside. Rolig, tett, lesbart.

**LEVER**
5 bilder + én kort setning per forslag om hva som er styrken, og til slutt din
anbefaling om hvilket som passer best til daglig bruk.

---

## Merknad om verktøyvalg

ChatGPT og Claude lager sjelden pikselpresise UI-bilder — de er sterkere på
beskrivelser og på å bygge ekte HTML. Vil du ha noe som faktisk ser ut som en app:

- **v0.dev / Figma Make** — bygger ekte, klikkbar UI av samme prompt
- **Midjourney / DALL·E** — legg til «UI design mockup, iPhone screenshot,
  flat vector, high fidelity» på slutten
