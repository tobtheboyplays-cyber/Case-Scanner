# Clumsy-fysikken — status 26.07.2026

**Ikke i bruk enda.** `tobias.js` importerer ingenting herfra, saa den Tobias som
kjorer hos journalisten er den forrige, fungerende versjonen. Det er med vilje:
grunnlaget er bygget og verifisert, men han **staar ikke** enda, og et Easter Egg
som ligger i en haug paa gulvet er verre enn ingen.

## Verifisert at det virker

| Del | Maalt |
|---|---|
| Rapier kjorer i nettleseren | kule falt fra 4,0 m, la seg paa 0,399 (radius + gulv) |
| 14 rigid bodies, 13 ledd | bygges uten feil |
| Grip en kroppsdel og loeft | haand 0,62 → torso 0,21 → fot 0,09: **han hang under haanden** |
| Kast ut av skjermen | hele ragdollen forsvant, `heltUtenfor` slo inn |
| Fysiske tilstander | leses av maalinger, ikke av hvilken animasjon som spiller |

## Virker IKKE enda

**Han staar ikke.** Torsoen skal staa i 0,42 m; den ender paa 0,19-0,28. I siste
runde begynte lemmene i tillegg aa drive oppover (haand paa 0,59, over skulderen)
— det er PD-regulatoren som pumper energi inn i systemet.

To feil er allerede funnet og rettet paa veien, og de staar dokumentert i koden:

1. **Haandskrevne leddankre stemte ikke.** Hofta hadde forelderankeret paa
   verdenshoyde 0,265 og barneankeret paa 0,280; kneet 0,135 mot 0,170. Solveren
   dro dem mot hverandre fra foerste frame. Ankrene regnes naa UT av delenes
   posisjoner (`ankre()` i `skjelett.js`), saa de ikke kan komme i utakt igjen.
2. **Momenttaket var skalert med lemmets egen masse.** Et legg paa 0,35 kg skal
   baere fire kilo kropp; med massefaktoren fikk det et tak paa 4,9 Nm der det
   trengte det dobbelte. Styrke hoerer til LEDDET, ikke til lemmet.

## Neste steg, i rekkefolge

1. **Stabiliser PD-regulatoren.** Den pumper energi. Mistanken er at
   `applyTorqueImpulse` med hoy stivhet og fast `dt` overskyter; proev
   implisitt demping (`w` etter steget, ikke foer) eller lavere stivhet med
   hoyere demping. Dette er den ENE tingen som blokkerer alt annet.
2. Naar han staar: balanse og recovery-steg (`_balanser` finnes, uproevd).
3. Deretter gange (`_gaa` finnes, uproevd), stolen, og kobling til `tobias.js`.

## Testbenken

`testbenk.html` kjorer aatte maalinger uten grafikk — den er raskere og mer
paalitelig enn aa se paa en skjerm. Kjor den mot en lokal server:

    /static/tobias/fysikk/testbenk.html
