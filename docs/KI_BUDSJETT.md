# KI-budsjettet og køen — hvorfor skannet gjør *mindre* enn det kunne

**Problemet, fra journalistens telefon 26.07.2026 kl. 00:48:**

    Groq (gratis): HTTPStatusError: Client error '429 Too Many Requests'

Nøkkelen var riktig. Feilen var strukturell, ikke uflaks: ett skann fyrte av
inntil 15 KI-kall uten pause. Groqs gratis-nivå tåler **12 000 tokens i minuttet**
(`llama-3.3-70b-versatile`, console.groq.com/docs/rate-limits, hentet 26.07.2026),
og et fullt skann brukte grovt **37 000**. Skannet var *garantert* å sprenge taket.

## Løsningen (eierens egen)

> «Så kan han heller trykke søk flere ganger slik den holder seg under limit.»

Det er den riktige løsningen, og den er bedre enn å vente lenge inne i ett skann:
gjør mindre KI-arbeid per trykk, og la journalisten trykke igjen for resten.

**Men den holder bare hvis neste skann tar de NESTE sakene.** Gjør den ikke det,
brenner hvert trykk kvoten på nøyaktig de samme topp-sakene, og køen tømmes aldri.
Derfor er dette to mekanismer, ikke én:

### 1. Budsjettet (`agents.Budsjett`)

`KI_BUDSJETT_TOKENS` (standard **9 000**) er taket for ett skann. Før hvert kall
anslås tokenbruken (samme anslag som kvotestyringen bruker, `llm.anslaa_tokens`).
Er det ikke plass, gjøres kallet ikke — saken merkes `ko` og telles.

9 000 og ikke 12 000: marginen gjør at to skann rett etter hverandre fortsatt
holder seg under taket, siden minuttvinduet ruller.

Ett unntak: **det første kallet slipper alltid gjennom**, uansett hvor lavt
budsjettet er satt. Et tall i en miljøvariabel skal ikke kunne slå av KI-en stille.

### 2. Hurtiglageret (`storage.ki_hent` / `ki_lagre`)

Ekte KI-svar lagres per sakskey og gjenbrukes gratis ved neste skann. Da går hele
budsjettet til saker som *ikke* har fått KI ennå, og køen krymper for hvert trykk.

To regler som ikke må mykes opp:

- **Bare ekte KI-svar lagres.** Maler og mislykte kall skal prøves på nytt, ikke
  fryses fast som om modellen hadde svart.
- **Delvis lagring er lov.** Fikk saken redaktørdom, men gikk tom for budsjett før
  vinklene, overlever dommen — neste skann betaler ikke for den på nytt.

Lageret er begrenset til `KI_CACHE_MAKS` (400) rader.

## «mal» og «kø» er ikke det samme

Dette er den viktigste distinksjonen i hele mekanismen, og den er en ærlighetsregel:

| Merking | Betyr | Hva journalisten skal gjøre |
|---|---|---|
| `llm` | ekte KI-vinkler | ingenting — dette er varen |
| `mal` | **dette er alt du får** (ingen nøkkel, eller kallet feilet) | ikke stol på vinkelen |
| `ko` | ikke forsøkt ennå, budsjettet var brukt opp | **trykk «Skann igjen»** |

Blandes `ko` inn i `mal`, ser verktøyet ødelagt ut akkurat når det gjør jobben
sin. Blandes `mal` inn i `llm`, lyver det. Begge deler er regressionstestet i
`tests/test_ki_budsjett.py`.

## Målt

`test_skannet_stopper_for_kvotetaket`: 12 saker på 9 000 tokens gir maks 8 kall —
langt under de 15 som utløste 429-en.

`test_koen_tommes_til_slutt`: gjentatte skann tømmer køen. Et system der køen
aldri blir tom er verre enn ingen kø.

## Det som ikke er verifisert

Pacing, 429-retry og budsjett er testet mot **mockede** svar. Tallene over er
anslag mot Groqs dokumenterte tak, ikke målinger mot eierens ekte nøkkel. Første
ekte skann med nøkkel er det som avgjør om anslaget stemmer — står det «KI: på»
og ingen 429 i statuslinjene, holder det.

## Justering

`CASE_RADAR_KI_BUDSJETT` (tokens per skann), `CASE_RADAR_EDITOR_CAP`,
`CASE_RADAR_JOURNALIST_CAP`. Bytter du til en betalt leverandør med høyere tak,
er det budsjettet som skal opp — ikke capene først.
