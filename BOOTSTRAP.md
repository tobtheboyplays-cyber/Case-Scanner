# Case-radar — start fra null på serveren

Én blokk. Kopier alt, lim inn i SSH. **Ingen innlogging, ingen token** —
serveren henter fra det offentlige repoet. Fungerer enten klonen finnes fra før
eller ikke.

```bash
cd ~ && \
if [ -d case-radar/.git ]; then
  cd case-radar && git pull
else
  git clone https://github.com/tobtheboyplays-cyber/Case-Scanner case-radar \
    && cd case-radar
fi && \
bash deploy.sh
```

Første gang, med KI-nøkkel: `bash deploy.sh --ask` i stedet — den leser nøkkelen
trygt og lagrer den i `~/.case-radar-key`. Senere deployer gjenbruker den selv.

## Ikke prøv å klone `Trading-bot`

`Trading-bot` er **privat**. Kloner du den uten token, svarer GitHub
**«Repository not found»** — ikke «feil passord». Private repo skjules helt for
uautentiserte kall, så feilmeldingen peker deg i feil retning.

Serveren skal ikke bruke det repoet i det hele tatt. Den henter fra
**`Case-Scanner`**, som er offentlig — da trengs ingen token, og ingenting
utløper etter 90 dager. Se [`docs/LENKA.md`](docs/LENKA.md) for hvorfor rollene
er delt slik.

## Hva som skjer

`deploy.sh` gjør resten og printer lenka til slutt:
bygger imaget → starter containeren → venter på `{"status":"ok"}` → åpner porten →
sjekker om serveren har IPv4 → hvis ikke, starter en gratis https-tunnel som funker
på hvilken som helst mobil.

## Etterpå: hvordan du legger inn oppdateringer

**Ikke bruk `deploy.sh` til dette.** Den henter *ingen* kode — den bygger det som
allerede ligger på disken. Kjører du bare `deploy.sh` etter at noe er pushet,
bygger du den gamle koden om igjen, og alt ser vellykket ut. Ingen feilmelding.

Bruk denne i stedet:

```bash
cd ~/case-radar && bash oppdater.sh
```

Den henter, viser deg hvilke commits som kommer, spør før den ruller ut, bygger,
og sjekker til slutt at lenka svarer **utenfra**. Lenka endrer seg ikke.

| Kommando | Hva den gjør |
|---|---|
| `bash oppdater.sh` | hent ny kode og rull den ut — den normale flyten |
| `bash sjekk-server.sh` | hva kjører egentlig? leser, endrer ingenting |
| `bash fast-lenke.sh` | bytt engangslenka mot en fast adresse |
| `bash deploy.sh` | bygg om det som ligger her nå (henter ingenting) |

Full forklaring på lenketyper, tunnel og autodeploy: [`docs/LENKA.md`](docs/LENKA.md).

## Hvor koden kommer fra

Serveren henter fra **`Case-Scanner`, branch `main`** — det offentlige repoet.
Derfor trengs ingen innlogging, og ingenting utløper.

`Trading-bot` er arbeidsrepoet der utviklingen skjer. Det er privat, og serveren
skal aldri peke dit. Hver case-radar-endring må derfor speiles til `Case-Scanner`
— pushes den bare til `Trading-bot`, ser serveren den aldri.

Full begrunnelse: [`docs/LENKA.md`](docs/LENKA.md).

## Nøkkelen

- **Gratis, ekte KI: Groq** — <https://console.groq.com/keys>. Starter med `gsk_…`,
  ingen kort. Dette er valget, og det virker fra denne serveren.
- **Gemini virker IKKE herfra.** Google blokkerer datasenter-IP-en og svarer HTML
  403 før kallet når API-et. Ikke feilsøk det på nytt — det er ikke nøkkelen.
- Legg den inn med `bash deploy.sh --ask`. Den leses uten å vises, testes mot
  leverandøren, og lagres i `~/.case-radar-key` (chmod 600) så senere deployer
  gjenbruker den.
- **Uten nøkkel:** `bash deploy.sh` alene — da kjører appen i demo-modus (maler),
  og skriptet sier tydelig ifra at det er demo.
- Nøkkelen skal **kun** limes inn her på serveren — aldri i kode, chat eller repo.

## Hvis noe feiler

Skriptet sier hva som er galt. Vanligste:

| Melding | Fiks |
|---|---|
| `Du står i feil mappe` | Kjør blokka over på nytt — den finner mappa selv |
| `remote: Repository not found` | Du kloner `Trading-bot`, som er privat. Bruk blokka øverst — den henter `Case-Scanner` |
| `No such file or directory` på `cd` | Klonen ligger i `~/case-radar`, ikke `~/Trading-bot/case-radar` |
| Groq avviste nøkkelen | Sjekk de fire siste tegnene mot console.groq.com. Skriptet viser dem |
| `Serveren har INGEN IPv4` | Ingenting — skriptet starter tunnelen automatisk |
| Lenka timer ut på mobil | `bash deploy.sh "$KEY" --tunnel` — one.coms skybrannmur er nesten alltid grunnen, ikke serveren |
| Lenka har byttet adresse | Du hadde en quick tunnel; de er engangsadresser. `bash fast-lenke.sh` |
| Oppdateringen kom ikke fram | Du kjørte `deploy.sh` i stedet for `oppdater.sh` — se over |

Logg: `sudo docker logs -f case-radar` · Stopp: `sudo docker rm -f case-radar case-radar-tunnel`
