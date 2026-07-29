# Forskningsfunn og hva som ble endret (25.07.2026)

Kilde: deep research, 108 agenter, påstander adversarielt verifisert (forsøkt
motbevist) før de fikk stå. Under er bare det som overlevde, og hva jeg gjorde med det.

## Funn som endret koden

### 1. Sourcing er den dominerende feilmodusen — ikke språk
EBU/BBC «News Integrity in AI Assistants» (okt. 2025): 22 kringkastere, 18 land,
n=2 709 vurderte KI-svar. 45 % hadde minst ett signifikant problem, og **sourcing var
største enkeltkategori (31 %)** — manglende, misvisende eller feil attribusjon.

*Forbehold fra verifiseringen:* tallet er kraftig dratt av én modell (Gemini 72 % vs.
ChatGPT 24 %). Uten den faller sourcing til ~18 %, altså på linje med accuracy. Studien
måler dessuten konsument-assistenter med åpen web, ikke et lukket SSB-grunnlag som
vårt. **Bruk det som evidens for hvilken feilmodus som dominerer — ikke som en feilrate
for dette verktøyet.**

→ **Implementert:** `verify.usporbare_tall()` sporer hvert tall i utkastet mekanisk
tilbake til kildegrunnlaget. Tall som ikke finnes der flagges synlig i UI. Årstall og
små heltall filtreres bort (datoer og mengdeord, ikke påstander).

### 2. Washington Post-havariet
Reuters Institute Trends & Predictions 2026 §8: WaPo lanserte en KI-generert podkast
**tross interne tester** som viste feilattribuerte sitater og feiltolkede fakta.
Bekreftet uavhengig av Semafor via intern korrespondanse.

→ **Lærdom, ikke kode:** kjente feilmoduser skal gate output *før* publisering. Det er
derfor tallsporingen blokkerer/flagger i stedet for å bare logge.

### 3. Vinkeltypologi finnes og er promptbar
Motta, Daga, Opdahl & Tessem, «Analysis and Design of Computational News Angles»,
IEEE Access 8 (2020) s. 120613–120626, tabell 1: **11 navngitte vinkler anvendt på én
og samme hendelse**, hver med en «headline fact» som viser hva vinkelen løfter fram.

*Forbehold:* forfatterne kaller det selv et startsett, ikke en validert lukket
typologi. Ikke siter det som «DEN» typologien.

→ **Implementert:** `prompts.VINKLER` — de 8 av settet som faktisk lar seg drive av en
kommunestatistikk (nærhet, konsekvens, ytterpunkt, milepæl, menneske, uventet,
motsetning, handling). Journalisten **må** velge tre forskjellige nøkler og oppgi en
**headline fact** per vinkel. Det er headline fact-en som skiller vinklene — ikke
tittelen. Modellen må også si hvilke data den mangler.

### 4. Modeller avstår ikke selv når grunnlaget er tynt
Frontier-modeller velger systematisk et selvsikkert feilsvar framfor «vet ikke» når
konteksten er utilstrekkelig. Abstention må håndheves **utenfra**.

→ **Implementert:** `verify.nok_grunnlag()` — en deterministisk gate som kjøres FØR
journalisten bruker tid. Mangler tallet, kilde-URL, kildenavn eller dekningssjekk, dør
saken der, med begrunnelse vist i UI.

### 5. KI-merking koster tillit — men kildelisten nøytraliserer det
Toff & Simon, *International Journal of Press/Politics* 30(4) 2025: KI-etikett senker
tilliten (5,9 → 5,5 på 11-punktsskala, p<0,001), men effekten nøytraliseres i stor grad
av en **synlig kildeliste med URL-er**. 81–84 % vil ha åpenhet, og **78 % av dem ber om
et forklarende prosessnotat** — ikke en ettordsetikett.

→ **Implementert:** `verify.prosessnotat()` genererer en kort, konkret linje på hver
godkjent sak: hvilken kilde med lenke, hva KI-en gjorde, hvem som godkjente, og at
teksten er et utkast som må faktasjekkes. Kildene vises som klikkbare lenker sammen
med den.

## Funn jeg IKKE implementerte (ennå)

**Chain-of-Verification (CoVe)** med faktorerte verifikasjonsspørsmål i isolerte kall.
Dokumentert virksomt, men koster ett LLM-kall per påstand. Den deterministiske
tallsporingen dekker den viktigste delen gratis. Vurderes hvis kvoten tillater det.

**Maskinsjekk mot selve SSB-cellen** (P1 i anbefalingen): slå hvert tall opp på nytt mot
data.ssb.no og sammenlign programmatisk. Riktig neste steg, men krever at hver påstand
bærer tabell-ID + dimensjonskoder. Tallsporingen mot kildegrunnlaget er et billigere
førstetrinn som fanger det meste.

## Ærlig hull i researchen

Delspørsmålene om **andre norske datakilder** og **UX/hvorfor redaksjonelle verktøy
blir forlatt** ble IKKE dekket av noen verifisert påstand i denne runden. De er
ubesvart, ikke besvart svakt. Kilde-spørsmålet dekkes av den andre research-runden som
fortsatt kjører.

## Bekreftet nyttig

SSBs API-er er åpne, gratis og krever **ingen nøkkel**. PxWebApi v2 gir hele
Statistikkbanken inkludert kommunenivå, CC BY 4.0. Verktøyet trenger altså ingen
credential-håndtering for datakilden — bare for KI-en.

---

# Research nr. 2: kilder som gir forsprang (25.07.2026)

110 agenter, samme adversarielle verifisering.

## Implementert: SSBs publiseringskalender ⭐

**Dette er den eneste kilden i verktøyet som varsler om noe som ikke har skjedd enda.**

`https://www.ssb.no/rss/statkal` — åpen, gratis, ingen nøkkel. 31 dagers horisont.
Verifisert live av meg selv: HTTP 200, 54 framtidsdaterte publiseringer.

Feeden har en egen namespace (`http://www.ssb.no/ns/ssbrss`) som bærer planlagt dato,
kortnavn, emne — **og navn, telefon og e-post til statistikeren som eier tallet**.
Ofte flere per publisering.

Journalisten får ikke tallet tidlig (embargo til kl. 08.00 hverdager), men han får tid
til å forberede saken og ringe kilden. Det er der forspranget ligger.

→ **Implementert:** `collectors/ssb_kalender.py` + «⏳ Kommer snart»-panel øverst på
radaren, vektet etter emne (arbeid/priser/bolig høyest), lokale nøkkelord og hvor nært
slippet er. Telefonnumre er klikkbare på mobil.

*Merk:* researchen oppga feil namespace-URI og en flat kontaktstruktur. Begge deler var
gale — jeg fant det ved å teste mot den ekte feeden. Det er derfor jeg verifiserer selv
i stedet for å kode etter en oppsummering.

## Verifisert, men ikke implementert ennå

**SSB StatBank API v2** (`https://data.ssb.no/api/pxwebapi/v2/`) — nøkkelfritt,
verifisert HTTP 200 uten autentisering. 7 747 tabeller (3 786 aktive), kommunenivå for
Stavanger (1103) og Sandnes (1108), CC BY 4.0.
Driftsgrenser å designe rundt: **30 spørringer/min per IP** (deles av hele
redaksjonen), 800 000 celler per uttrekk, ~2 100 tegn URL-grense på GET (bruk POST),
metadata-nedetid 05.00 og 11.30, og unngå 07.55–08.15 rundt frigivelsen.
Fallgruve: `includeDiscontinued=false` er default — en naiv crawler ser bare halve
katalogen.

**Postjournaler.** Ikke ett nasjonalt API, men en oppstykket virkelighet:
- `norske-postlister.no` aggregerer 176 mill. journalposter fra 722 myndigheter.
  Stavanger, Sandnes og Rogaland fylkeskommune alle merket «Ferske data».
- eInnsyn har et udokumentert, men åpent søke-API: `POST https://einnsyn.no/api/result`,
  OpenAPI på `/api/v3/api-docs`. Dekker Stavanger, men **ikke** Sandnes (verifisert:
  null journalposter, `skjult=true`). Sandnes ligger på egne 360Online-endepunkter.

**Størst strukturell nyhetsverdi:** 52 kommuner — inkludert Stavanger, Sola, Randaberg,
Strand og Karmøy — skjuler politikeres forslag i digitale møteportaler **før** møtet.
Presseforbundet har et ferdig, rettslig forankret innsynskrav-templat som kan sendes
rutinemessig per møtedato. Dette er ikke et API-problem, men et arbeidsflyt-problem —
og potensielt den mest verdifulle enkeltkilden.

## Ærlig hull

Delspørsmålene om **sektor-API-er** (NVE, Vegvesen, NAV, FHI, Udir …), **statistisk
metodikk for små kommunetall** (sesongjustering, anomalideteksjon, multippel testing)
og **hvordan andre redaksjoner gjør dette** ble IKKE dekket av verifiserte påstander.
De er ubesvart, ikke besvart svakt. Ikke bygg på antakelser om dem.
