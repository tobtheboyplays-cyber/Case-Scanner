# Case-radar — start fra null på serveren

Repoet er **public** — ingen innlogging, ingen token. Kopier blokka, bytt nøkkelen, lim inn i SSH.

```bash
KEY=AIzaSyDIN_EKTE_NØKKEL_HER

cd ~ && \
if [ -d case-radar/.git ]; then cd case-radar && git pull; \
else git clone https://github.com/tobtheboyplays-cyber/case-radar && cd case-radar; fi && \
bash deploy.sh "$KEY"
```

## Hva som skjer

`deploy.sh` gjør resten og printer lenka til slutt: bygger imaget → starter containeren →
venter på `{"status":"ok"}` → åpner porten → sjekker om serveren har IPv4 → hvis ikke,
starter en gratis https-tunnel som funker på hvilken som helst mobil.

## Nøkkelen

- **Gratis, ekte KI:** <https://aistudio.google.com/app/apikey> — starter med `AIzaSy…`, ingen kort.
- **Uten nøkkel:** kjør bare `bash deploy.sh` → demo-modus (maler). Skriptet sier tydelig ifra.
- Nøkkelen limes **kun** inn på serveren — aldri i kode, chat eller repo.

## Hvis noe feiler

| Melding | Fiks |
|---|---|
| `Du står i feil mappe` | Kjør blokka over på nytt |
| `Dette ser ikke ut som en gyldig nøkkel` | Må starte med `AIzaSy…` (Gemini) eller `sk-ant-…` (Claude) |
| `Serveren har INGEN IPv4` | Ingenting — tunnelen starter automatisk |
| Lenka timer ut på mobil | `bash deploy.sh "$KEY" --tunnel` |

Logg: `sudo docker logs -f case-radar` · Stopp: `sudo docker rm -f case-radar case-radar-tunnel`

## Fast lenke i stedet for tunnel

`render.yaml` ligger klar: render.com → New + → Blueprint → velg dette repoet → Apply.
Legg inn `GEMINI_API_KEY` når Render spør. Gir en permanent `https://…onrender.com`.
