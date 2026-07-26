# Kilderegelen

> **Kilder som kan LAGE artikler — ikke artikler for å lage artikler.**
> Og de skal være først.
>
> — eieren, 26.07.2026

Dette er den viktigste regelen for hva Case-radar henter. Den står i egen fil
fordi den allerede har blitt brutt én gang, og fordi bruddet så fornuftig ut da
det ble gjort.

## Hva som er lov

| Kilde | Hvorfor den er lov |
|---|---|
| SSB (tabeller, søk, flytting) | Tall ingen har skrevet ut ennå |
| Brønnøysundregistrene | Konkursvedtak og nyregistreringer — hendelser man kan ringe på i dag |
| SSBs publiseringskalender | Forsprang: hva som slippes de neste ukene |
| Google Trends | Svakeste tier. Et signal om hva folk søker på, ikke en sak i seg selv |

## Hva som ikke er lov

**Avisartikler som råstoff.** Aftenposten, Bergens Tidende og E24 lå inne som
lead-kilder gjennom `app/collectors/schibsted.py`. Ideen var idé-gjenbruk: en
sak fra en søsteravis kunne kanskje gjøres lokalt. Den er slettet 26.07.2026.

Tre grunner, i rekkefølge etter hvor mye de betyr:

1. **En publisert artikkel er noen andres ferdige jobb.** Verktøyets forsprang er
   å finne det ingen har skrevet. Å foreslå en Aftenposten-sak er å foreslå at
   journalisten skriver den om igjen.
2. **Det kostet KI-kvota.** Redaktør og journalist rekker fire saker per skann
   (Groqs minuttak, se `docs/KI_BUDSJETT.md`). Hver gjenbrukt avissak som nådde
   redaktøren, stjal én av de fire plassene fra et ekte funn.
3. **RSS-churn tok over forsiden.** Nøkkelen ble laget av overskriften, og feeder
   bytter overskrifter hele tiden — så hver avissak var teknisk «aldri sett før»
   ved hvert eneste skann og la seg øverst.

## Den ene lovlige bruken av artikler

`app/collectors/coverage.py` — dekningssjekken, som svarer «har noen allerede
skrevet om dette?». Det er å bruke artikler som **fasit**, ikke som råstoff, og
den skal stå. Den er selve grunnen til at grønne funn betyr noe.

`AFTENBLADET_NAME` i `app/config.py` hører til denne bruken.

## Hvordan regelen er voktet

Ikke av et flagg. Et flagg satt til `false` blir slått på igjen av en framtidig
økt som ikke kjenner grunnen — derfor er kollektoren **slettet**, ikke avslått.

I tillegg vokter `tests/test_kilder.py` mekanisk at:

- `app/collectors/schibsted.py` ikke finnes
- ingen fil under `app/` nevner `SCHIBSTED`
- ingen avis-RSS-URL ligger i `config.py`
- bare `kind in ("data", "hendelse")` når redaktøren
- Brønnøysund-hendelsene hentes **før** KI-flyten (ellers får de ingen vinkler)

Faller noen av dem, er regelen brutt — uansett hvor rimelig endringen så ut.
