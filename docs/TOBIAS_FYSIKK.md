# Aktiv ragdoll — oppskriften

Slik bygger du en figur som **oppfører seg** i stedet for å spille av animasjoner.
Skrevet 27.07.2026 etter at Tobias var ferdig, for at neste gang skal koste dager
og ikke uker.

Alt her er målt, ikke husket. Der det står et tall, står det fordi noe annet ble
prøvd først og ga et dårligere tall.

**Kildene:** `static/tobias/fysikk/` (fysikken), `static/tobias/ansikt.js` (fjes),
`static/tobias/fysikk/testbenk.html` (målebenken).

---

## 1. Hva «aktiv ragdoll» betyr, og hvorfor det er verdt det

En vanlig ragdoll er en slapp dukke: ledd og masse, ingen vilje. En *aktiv*
ragdoll har i tillegg en regulator som hele tiden drar kroppen mot en ønsket
stilling — men som kan tape mot fysikken.

Hele gevinsten ligger i én setning fra eieren:

> «Hvis jeg gjør noe utvikleren ikke eksplisitt har programmert en animasjon for,
> skal han fortsatt reagere troverdig fordi fysikksystemet håndterer situasjonen.»

Det er derfor det ikke finnes en `fallFromChair`, en `throwAnimation` eller en
`getUpFromBack` noe sted. Det finnes **positurer** (hva han prøver på) og
**krefter** (hva som faktisk skjer). Alt annet følger.

Prisen er ærlig: fysikk kan ikke debugges ved å se på skjermen. Du må måle.
Se § 6.

---

## 2. De fem lovene

Disse er ikke råd. Hver av dem ble brutt, målt, og rettet.

### Lov 1 — Enhver fjær trenger tre ting: treghetsskalering, demping og tak

Formelen er:

```
moment = I · (kp · feil − kd · vinkelfart)     // I = treghetsmoment
tak    = absolutte newtonmeter                 // IKKE skalert med I
```

- **Uten `I`** betyr `kp` forskjellige ting for en hånd og en torso, og
  dempingen blir ustabil på de lette delene. Målt: `kd·dt/I ≈ 50` på et lem, og
  da *skyter dempeleddet forbi null hvert steg* — den pumper energi inn i stedet
  for å ta den ut.
- **Uten demping** sparker fjæra lemmet forbi målet og gjør det igjen.
- **Uten tak** kan én stor feil ganget med stivheten sende lemmet i bane.

Taket skal være absolutt (hvor sterkt leddet *er*), ikke ganget med `I`.

**Denne loven ble brutt to ganger i samme prosjekt.** Først i PD-regulatoren.
Så, tre dager senere, i de myke leddgrensene — som var en helt egen fjær ingen
hadde tenkt på som en fjær. Målt: begge hendene snurret vedvarende i
**1000–3100 rad/s** mens figuren bare sto der. Etter fiksen: 0,52.

> **Let etter alle fjærene i systemet.** Alt som dytter mot et mål er en fjær:
> PD-regulatoren, leddgrensene, grepet, balansen. Hver eneste trenger alle tre.

### Lov 2 — Stabilitetskravet bestemmer fysikkfrekvensen, ikke omvendt

```
kd ≈ 2·√kp        (kritisk demping)
kd · dt < 1       (ellers pumper dempeleddet)
```

Beina trenger `kp ≈ 2800` for å bære kroppen ⇒ `kd ≈ 105` ⇒ `dt < 1/105`.
Derfor kjører Tobias **120 Hz**, ikke 60. Halvert steg gir dobbelt tillatt
demping og dermed **fire ganger** tillatt stivhet.

Dette er også grunnen til at man **ikke** kan spare kraft på mobil ved å
halvere frekvensen. Kutt heller solveriterasjoner og piksler.

### Lov 3 — Skriv ett punkt, aldri to

Et ledd forbinder to kropper. Fristelsen er å skrive et anker i hver kropps
lokale rom. Da kommer de i utakt.

Målt da de var håndskrevet: hofta hadde forelderankeret på verdenshøyde 0,265 og
barneankeret på 0,280. Solveren dro dem mot hverandre fra første frame, beina
foldet seg sammen, og figuren sank ned i en haug — lår på 0,057 m der de skulle
stått i 0,21, med føttene *over* lårene.

Skriv **ett verdenspunkt**, og regn begge lokale ankre ut av det. Da kan de ikke
komme i utakt, og endrer noen en kroppsdel følger leddet automatisk med.

### Lov 4 — Et lem henger riktig bare hvis leddet sitter i toppen av lemmet

Sitter skulderleddet midt inne i torsoen, på høyde med armens midte, henger armen
fra *sida* si. Tyngdekraften drar senteret ned under leddet, regulatoren drar mot
loddrett, og likevekten blir kompromisset mellom dem.

Målt: overarmen sto **25° ut**, underarmen kom inn igjen, hånden endte 0,09 m
innenfor albuen. På skjermen leste det som kyllingvinger. **Ingen vinkel i
posituren kunne fikset det** — feilen var geometrisk.

Med leddet i toppen av lemmet peker tyngdekraften og posituren samme vei, og
armen står loddrett uten å bli holdt der med makt. Bonusen er stor: armstivheten
kunne settes ned fra 2200 til 800, og da svinger armene naturlig når figuren går.

> Et lem som må *tvinges* til å se avslappet ut, har feil geometri.

### Lov 5 — Ingen tilstand som svekker figuren får kunne nås fra hvile

Tilstandsmaskinen skrudde kreftene ned til 45 % i `FALLER`. Det er riktig mens
man faller. Men `FALLER` ble satt hver gang ingen fot rørte bakken — og da
oppsto denne løkka:

```
ingen fot på gulvet  →  FALLER  →  45 % kraft
      ↑                                ↓
   føttene når aldri gulvet  ←  beina klarer ikke rette seg ut
```

Målt: fem sekunder «i fritt fall» mens figuren satt bom stille på knærne, med
torsoen dirrende mellom 0,226 og 0,271 m.

Feilen lå i **ordet**. «Ingen fot på bakken» betyr bare at han hviler på noe
annet enn føttene. Å falle er å *bevege seg nedover*.

> Test hver tilstand som svekker figuren: kan den nås mens alt står stille? Da er
> den en felle.

---

## 3. Byggerekkefølge

Bygg i denne rekkefølgen. Den er valgt slik at hver feil blir synlig alene, i
stedet for at fem feil maskerer hverandre.

| # | Steg | Ferdig når |
|---|---|---|
| 1 | Skjelett: kropper, kollidere, ledd fra **ett** punkt (lov 3) | delene står der de skal ved frame 0 |
| 2 | Gulv + vegger, ingen regulator | figuren faller sammen i en haug, uten NaN |
| 3 | PD-regulator (lov 1 + 2) | figuren står, `balansefeil ≈ 0` |
| 4 | Leddgrenser — **husk lov 1 her også** | ingen del snurrer vedvarende |
| 5 | Balanse: hoftedytt → skritt → snuble → fall | et lite dytt gir vingling, et stort gir fall |
| 6 | Griping og kast | figuren henger under det du holder i |
| 7 | Gange (§ 5) | han flytter seg faktisk, med fotløft |
| 8 | Fjes og «liv» | han gjør noe når ingen ser på |

Ikke gå videre før steget er **målt** ferdig. Steg 3 så «nesten riktig» ut i tre
runder på rad mens det egentlig var tre forskjellige feil.

---

## 4. Tallene, og hvorfor

Alle i `fysikk/konfig.js`. De viktigste, med begrunnelse:

| Verdi | Tall | Hvorfor akkurat dette |
|---|---|---|
| `steg` | 1/120 | lov 2: beina trenger kd=105 |
| `tyngde` | −14,0 | ekte 9,81 får en liten figur til å se ut som den sveiver |
| Massefordeling | **tunge bein, lett overkropp** | urealistisk med vilje — se under |
| `positur.bein` | 2800 / 105 / tak 60 Nm | må bære hele kroppen |
| `positur.arm` | 800 / 57 / tak 2 Nm | skal *henge*, ikke holdes (lov 4) |
| `demping.vinkelArm` | 9,0 (resten 4,0) | armene svinger fritt, men roer seg fortere |
| `grep.maksAkse` | 95 m/s² | **akselerasjon**, ikke kraft — se § 4.2 |
| `maksSpinn` | 34 rad/s | over det er det visuell suppe, se § 4.3 |

### 4.1 Massefordelingen er snudd, og det er hele poenget

Første utkast var realistisk: tung torso (2,6 kg), lette bein (0,35 kg legg). Da
klarte ikke beina å bære kroppen — PD-momentet er proporsjonalt med lemmets
*treghetsmoment*, og et legg på 0,35 kg har I ≈ 0,0005. Det ga 0,31 Nm der det
trengte 4. Målt: beina foldet seg sammen og torsoen sank fra 0,42 til 0,18 m.

Nå er det motsatt: **tunge bein (0,95 kg lår), lett overkropp (1,1 kg torso)**.
Det er urealistisk og helt med vilje. En leke med tyngdepunktet lavt lander på
føttene og ser klønete ut i stedet for ustabil.

Nedsiden, ærlig: et lite dytt i brystet flytter ham mindre enn det ville gjort en
menneskefigur.

### 4.2 Grep: taket må være i akselerasjon

Griper man en hånd på 0,08 kg og taket er `maksKraft · massen til den grepne
delen`, blir taket 7,2 N — mot en kropp på 7 kg som drar 98 N nedover. Hånden
kan altså **aldri** løfte figuren, mens torsoen så vidt klarer det. Det leses som
at det er tilfeldig hva som lar seg løfte.

Å sette taket til hele kroppsmassen er verre: 627 N på 80 gram = 7800 m/s².
Målt spinn 1843. Ragdollen eksploderte.

**Riktig størrelse er akselerasjon.** Et tak i m/s² betyr det samme for en hånd
og for en torso, og ingen del kan skytes av gårde.

Men da mangler løftet: leddene rekker ikke å føre 98 N gjennom en kjede på fire
ledd med solverbudsjettet vårt. Resten av kroppen får derfor **bære-hjelp, ikke
løft** — 90 % av sin egen vekt kansellert, pluss en drag mot hånda si fart.

> To krav som trekker mot hverandre gjennom samme tall, må skilles.
> «Løft ham over hele skjermen» og «han skal henge under hånda» kunne ikke begge
> løses med `bæreAndel`: 0,86 ga fint heng men halv skjerm, 0,99 ga full skjerm
> men han red *oppå* hånda. De skilte lag først da det ble to tall: hvor mye han
> **siger** (bæreAndel) og hvor godt han **følger** (kroppDemping).

### 4.3 Spinnklemme

Under de hardeste kastene ble det målt **308 rad/s** — 49 omdreininger i
sekundet. Det er ikke fysikk lenger, det er en grå sky. Verre: en tynn kapsel som
snurrer så fort kan gå tvers gjennom gulvet mellom to steg selv med CCD på.

En klemme (ikke en demping) på 34 rad/s gjør ingenting så lenge man er innenfor,
og fjerner bare det som uansett ikke kunne vises.

---

## 5. Gange som faktisk går

Gange er der de fleste ragdoller ser falske ut, og der vår «bestod» en test i to
økter uten å virke.

**Tre feil, i rekkefølge:**

1. **Retningen.** Kne og albue er hengsler om sin *egen* x-akse — de bøyer i
   dybden. Vender figuren mot kameraet, kan han ikke ta et skritt langs skjermen
   uten at kneet knekker sidelengs. Løsningen: han **snur seg** mot
   gangretningen, og hele positurbiblioteket ganges med vendingen. Da gjelder alt
   som er skrevet, uendret.

2. **Kreftene.** Første utgave dyttet foten med 2,6 N. Foten veier 0,60 kg = 8,4 N
   i vekt, og med friksjon 1,1 under begge føttene var 0,55 N på torsoen ikke i
   nærheten av å flytte 7 kg. **Hofte og kne må dreies av PD-regulatoren** (som
   har 60 Nm å ta av), og det er friksjonen under standfoten som skyver ham fram.
   Ingen impuls flytter figuren direkte.

3. **Løftet.** Andre utgave la 22 N under foten. Målt gjennom en hel syklus: foten
   lå på 0,032 m hele veien mens **lårets høyde sank** fra 0,204 til 0,182 — han
   huket seg ned. Et bein veier 32,9 N og må bæres **ovenfra**, slik en hofte
   gjør. Og foten som svinger må slippe friksjonen: en fot i svevfasen står ikke
   på noe.

Resultat: 3,00 → 4,07 m, med 8–9 cm fotklaring.

**Armene svinger i motfase med beina.** Det er den ene detaljen som mest av alt
får gange til å se ekte ut, og den koster to linjer.

---

## 6. Målebenken — det viktigste verktøyet

Fysikk kan ikke debugges ved å se på skjermen. Bygg dette **først**, ikke sist.

### 6.1 Regelen som koster mest å bryte

> **Benken må steppe med samme `dt` som appen.**

Benken vår hardkodet 1/60 mens konfigurasjonen sto på 1/120. Da målte den en
ustabil variant ingen bruker ser (`kd·dt<1` brytes ved 60 Hz når beina har
kd=105). Den meldte «balancing» og 0,8 m/s vingling der nettleseren viste at han
sto i ro — og **den skjulte at gangen ikke virket i det hele tatt**: den «virket»
bare fordi ristingen flyttet ham 0,40 m.

En testbenk som simulerer noe annet enn appen, måler ikke appen.

### 6.2 Åtte målinger som fanger alt

```
1 STÅR HAN?          høyde, balansefeil, tilstand, hver dels y
2 LITE DYTT          → vingler, men står
3 HARDT DYTT         → faller
4 REISER HAN SEG?    → tilbake til stable
5 LØFT ETTER HÅNDA   hånd > torso > fot  (henger han under?)
6 KAST               slippfart og hvor langt han fløy
7 HELT UT            forsvinner han, og kommer han tilbake?
8 GANGE              faktisk forflytning i meter
```

Kjør headless via Playwright og les tallene. Én kjøring tar sekunder; å se på
skjermen tar minutter og gir feil svar.

### 6.3 Torturtesten

Før noe slippes til en bruker:

| Prøve | Ser etter |
|---|---|
| 60 kast i alle retninger, 10 gripepunkter | NaN, eksplosjon |
| 20 løft opp/hold/ned/slipp | fastlåste tilstander |
| 10 kast helt ut av skjermen | kommer han tilbake? |
| 5 minutter uten input | hva gjør han når ingenting skjer? |

Siste rad avslørte at «sovner etter en stund» var død kode: telleren ble
nullstilt hver gang figuren fant på noe **selv**. At han går en tur er ikke at
det skjer noe — det som teller er om **noen rørte ham**.

### 6.4 Fallgruver i testene selv

Flere «app-feil» viste seg å være testfeil. Alle disse har skjedd:

- **Testen målte under gange.** Spinn 6,5 rad/s ble flagget som risting; det var
  lårsvingen. Mål bare mens figuren står, eller stub oppførselen.
- **Testen flyttet figuren til knappen i toppen av sida**, og han falt 650 px før
  klikket kom. Den målte tyngdekraften. Legg heller knappen oppå der han står.
- **Stubbet oppførsel ble ikke lagt tilbake**, så neste deltest målte en død
  figur.
- **`pytest.fail` arver `BaseException`** og slipper forbi hvert eneste
  `except Exception` — den drepte en bakgrunnstråd uten spor.

---

## 7. Utseende: små ting med stor virkning

- **Interpolér mellom fysikkstegene.** Fysikken går i faste 1/120-steg, skjermen
  tegner når den vil. Leser man rå tilstand hver frame får man to steg i én
  frame, så null, så to igjen — synlige mikrorykk selv når simuleringen er helt
  jevn. Lagre forrige tilstand før stegene, og lerp/slerp med `rest / steg`.
- **La delene overlappe.** Kapsler lagt tupp mot tupp er matematisk pent og ser
  ut som tre løse perler på en snor. En arm leses som **én** lem først når delene
  går et par cm inn i hverandre.
- **Ikke stripete materialer.** Mørk skulder → lys overarm → mørk underarm → lys
  hånd leser som fire ting, ikke som en arm. På beina leser det samme mønsteret
  som en støvel, og der er det riktig.
- **Navneskilt hører hjemme i DOM, ikke i 3D.** Ekte tekst, skalerer med
  systemfonten, koster ingenting å tegne. Husk `translateY(-100%)` — ellers
  legger det seg *nedover* og dekker hodet.
- **Fjes skal svare på noe målt.** Svimmel etter målt rotasjon, «au» ved målt
  anslagsfart, hjerter når noen slipper figuren forsiktig i stedet for å kaste.
  Et fjes som bare bytter bilde på en timer er pynt; et fjes som svarer på
  fysikken føles som en reaksjon.

---

## 8. Å bo på en ekte nettside

- **Lerretet dekker hele viewporten** og er `pointer-events: none`. Det slås på
  først i det øyeblikket en stråle faktisk treffer en kroppsdel. Uten det stjeler
  et fullskjermslerret hvert eneste klikk.
- **Hvem vinner, figuren eller knappen?** Vi bygde først knappen-vinner. Eieren
  overstyrte: *«Der er meninga han kommer litt i veien. Skal ikke være mulig å
  trykke igjennom han.»* Han har rett — slipper man klikket gjennom er figuren
  ikke en gjenstand lenger, den er en tegning. Det går an å leve med **fordi han
  kan flyttes**: en hindring man kan ta i og kaste vekk er noe annet enn en
  hindring man ikke kommer forbi.
- **Berøring må låse sida mens man holder.** Ellers tolker telefonen dragingen
  som scrolling: sida glir oppover og figuren blir stående. Låsen settes i det
  grepet tas og fjernes når man slipper — en side som *permanent* ikke lot seg
  scrolle ville vært en langt verre feil. `touch-action: none` alene holder ikke i
  iOS Safari; `touchmove` må avvises med `{ passive: false }`.
- **Vekten skal sies rett ut.** Three 0,67 MB + Rapier 2,0 MB. Last ingenting før
  figuren faktisk skal komme. Respekter `prefers-reduced-motion` og
  `navigator.connection.saveData` — det første er tilgjengelighet, det andre er en
  leser som har bedt om det motsatte.
- **Rydd opp for alvor.** Tre kastende frames på rad ⇒ riv alt ned. Et påskeegg
  skal aldri kunne holde en journalist ute fra sidene sine.

---

## 9. Rundt koden

- **To repoer.** Utvikling i det private, serveren henter fra det offentlige.
  `speil.sh` + en `pre-push`-hook er sperra; en setning i et dokument er ikke.
  Se `docs/LENKA.md`.
- **Vendorert minifisert kode utløser hemmelighetsskannere.** Rapier er 2 MB
  minifisert med innbakt WASM, og der finnes garantert `AK`+16 tegn. Ikke svekk
  søket — hold `vendor/` utenfor *mønstersøket* og krev i stedet at hver fil står
  på en godkjenningsliste. En sperre som alltid slår ut, blir en sperre folk
  lærer seg å overstyre.
- **Lisenser:** Three.js er MIT, **Rapier er Apache 2.0** (ikke MIT — lisensfila
  må følge med).

---

## 10. Hva som ikke er gjort

Ærlig liste, fra spesifikasjonen eieren skrev:

- Stolfysikk (§16) — han skal kunne sitte fysisk på en stol, ikke festes til den
- Antenne med sekundærbevegelse (§20)
- Håndinteraksjon: plukke opp ting (§22)
- Debug-overlegg og tuning-skyvere (§27–28) — `TUNING` finnes, panelet ikke
- Ettersving i armene topper på 15–18 rad/s rett etter et hardt kast. Det er en
  sving, ikke risting (faller under 1 rad/s på 1,33 s), men den er synlig.
