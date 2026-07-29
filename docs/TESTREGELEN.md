# Testregelen: ikke bytt ut det du skal måle

**Eieren 26.07.2026:** «Synes testene dine ikke er gode nok siden vi alltid må
dobbeltsjekke. Jeg vil at du har grundigere tester.»

Han hadde rett, og det er verdt å skrive ned nøyaktig *hvorfor* — ellers kommer
det tilbake.

## Hva som skjedde

To feil nådde ham samtidig:

1. Menyvalget nådde bare én av tre SSB-kilder. `collect_all` sendte `temaer`
   videre til søkesystemet, men kalte `ssb.collect()` og `ssb_flytting.collect()`
   uten argument.
2. Et skann kunne komme tilbake helt tomt, fordi KI-en brukte budsjettet på saker
   som filteret rett etterpå skjulte.

**236 tester var grønne.** Ingen av dem merket noe.

Grunnen er presis, ikke tilfeldig: testene erstattet `collect_all`,
`run_workflow` og `coverage.check` med attrapper. Feilen lå i koblingen mellom
`run_scan` og kollektorene — altså *nøyaktig* det leddet attrappen hadde tatt
plassen til. Testene målte at resten av koden oppførte seg pent rundt et hull.

Det er den farligste testtypen som finnes: den er rask, grønn og gir falsk
trygghet. En manglende test vet man om. En løgnaktig test tror man på.

## Regelen

> **Attrappen skal ligge på ytterkanten av systemet — ikke inne i det du påstår
> noe om.**

For case-radar betyr det: bytt ut **nettverket** (`http_get`, `httpx.post`), og
la alt annet være ekte kode. Se `tests/nett.py` og `tests/test_ende_til_ende.py`.

En ende-til-ende-test skal påstå **to** ting, og begge trengs:

| Påstand | Fanger |
|---|---|
| **Hva ble spurt om** (`nett.spurte_om("07459")`) | døde koblinger — valget som aldri nådde kilden |
| **Hva står på sida** (tekst i HTML-en) | riktig data som likevel ikke når malen |

Bare den første ville godtatt at kortet aldri ble tegnet. Bare den andre ville
godtatt at menyen var pynt så lenge noe dukket opp.

## Prøven som avgjør om en test er verdt noe

**Gjeninnfør feilen og se om testen blir rød.** En test som ikke kan feile er
dekorasjon.

Begge feilene over ble gjeninnført med vilje etter fiksen:

```
FEIL 1 (temavalget droppes)     → 2 røde
FEIL 2 (blank side ved tomt skann) → 2 røde
```

Gjør dette hver gang en test skrives for en feil som *faktisk skjedde*. Det tar
ett minutt og er den eneste harde beviset på at testen måler noe.

## To feller som allerede har bitt oss

**`pytest.fail` arver fra `BaseException`.** Conftest setter `http_get` til en
`pytest.fail` for å hindre ekte nettkall. Den går rett forbi alle
`except Exception` i fail-soft-kollektorene, ut av `run_scan`, forbi feilfangsten
i `jobs.start`, og etterlater bakgrunnsjobben i «kjorer» for alltid — et skann
hang i 240 sekunder. Skal en test bruke ekte svar, må `http_get` byttes i
*kollektorens egen modul* (siste tilordning vinner).

**TestClient koder ikke «ø» som en nettleser.** `klient.post(..., data=[("tema",
"natur og miljø")])` sendte et forvansket navn, `sett_temaer` forkastet det
stille som ukjent, og **et temasøk i testen ble et bredt søk**. Da hadde
temafiltrene sett grønne ut uansett hva de gjorde. Bygg kroppen selv med
`urlencode(par, encoding="utf-8")` og send den som
`application/x-www-form-urlencoded` — da måles appens egen dekoding også.
