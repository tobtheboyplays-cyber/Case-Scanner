# Lenka og oppdateringer — hvordan noe du pusher havner hos journalisten

Én side. Alt om hvordan koden kommer fra GitHub til telefonen hans, og hvorfor
lenka ser ut som den gjør.

## Kort versjon

```bash
cd ~/case-radar && bash oppdater.sh
```

Den henter ny kode, viser deg hva som kommer, bygger, og sjekker til slutt at
lenka faktisk svarer **utenfra**. Lenka endrer seg ikke.

Er noe rart:

```bash
bash sjekk-server.sh     # hva kjører egentlig? leser, endrer ingenting
```

## Fella som gjorde dette nødvendig

`deploy.sh` henter **ingen** kode. Den bygger det som allerede ligger på disken.

Kjører du bare `bash deploy.sh` etter at noe er pushet, bygger du den gamle
koden om igjen — og alt ser vellykket ut. Grønne haker, fungerende lenke, ingen
feilmelding. Det eneste som mangler, er endringen.

`oppdater.sh` finnes for å stenge den fella: den henter først, viser deg
commit-ene, og bygger etterpå.

## De tre lenketypene

Serveren har IPv4 (185.117.250.65), så `deploy.sh` ville normalt gitt en
IP-lenke. At det likevel ble brukt tunnel, forteller noe: **one.com har sin egen
skybrannmur i web-panelet**, og `ufw allow` på serveren er ikke nok. Det er den
klart vanligste grunnen til at en lenke timer ut på mobil.

| Type | Adresse | Overlever reboot? | Krever |
|---|---|---|---|
| IP | `http://185.117.250.65:8000` | ja | at one.coms brannmur slipper port 8000 gjennom |
| **Quick tunnel** | `https://<tilfeldig>.trycloudflare.com` | **NEI** | ingenting |
| **Navngitt tunnel** | `https://radar.dittdomene.no` | ja | et domene i Cloudflare |

### Hvorfor quick tunnel er en bombe med ukjent klokke

Cloudflare trekker et **nytt tilfeldig navn hver gang cloudflared-prosessen
starter**. Containeren kjører med `--restart unless-stopped`, så ved en
server-reboot starter den igjen — med ny adresse. Journalistens bokmerke er da
dødt, uten at noen har gjort noe galt.

Det er ikke en feil i oppsettet. Det er slik quick tunnels virker.

### Fast lenke

```bash
bash fast-lenke.sh
```

Skriptet forklarer de fire klikkene i Cloudflare Zero Trust, tar imot tokenet,
starter tunnelen og **sier seg ikke ferdig før lenka faktisk svarer**.

En navngitt tunnel binder adressen til DNS i stedet for til prosessen. Da
overlever den reboot, redeploy og at cloudflared restartes.

**Krever et domene i Cloudflare.** Det finnes ingen gratis fast adresse uten:
`*.cfargotunnel.com` er ikke offentlig rutbar, og `trycloudflare.com` er alltid
tilfeldig. Har du et domene hos one.com, flytter du navneserverne til Cloudflare
gratis. Har du ingen, selger Cloudflare til kostpris (~100 kr/år).

*Vil du unngå domene helt:* Tailscale Funnel gir en fast
`https://<vert>.<tailnet>.ts.net` gratis. Styggere adresse og enda en konto, men
den virker og krever ingenting av one.com.

## Hva som IKKE endrer adressen

Når `~/.case-radar-tunnel-token` finnes, er den navngitte tunnelen fasit, og
`deploy.sh` lar tunnel-containeren være i fred:

- `bash oppdater.sh` — trygt
- `bash deploy.sh` — trygt
- `bash deploy.sh --tunnel` — **flagget ignoreres**, med en advarsel

App-containeren rives og bygges på nytt hver deploy. Det er trygt: tunnelen
peker på `localhost:8000` og kobler seg på den nye containeren selv.

Den eneste måten å bytte lenke på, er å kjøre `fast-lenke.sh` bevisst.

## Hvor koden kommer fra

To repo, med hver sin jobb. Det er ikke rot — det er begrunnet:

| Repo | Rolle |
|---|---|
| `Trading-bot` (**privat**) | arbeidsrepo. Her ligger `brain/` og trading-koden. |
| `Case-Scanner` (**offentlig**) | **deploy-kilde.** Det serveren henter fra. |

Serveren henter fra det **offentlige** repoet, og grunnen er praktisk: en server
skal kunne hente kode uten tilsyn, for alltid. Et privat repo krever et
GitHub-token som må limes inn på serveren og som **utløper etter 90 dager**.
Da står deployen stille en dag du ikke har tid til å feilsøke.

```
github.com/tobtheboyplays-cyber/Case-Scanner   branch: main
katalog på serveren: ~/case-radar
```

Prøver du å klone `Trading-bot` uten token, sier GitHub **«Repository not
found»** — ikke «feil passord». Private repo skjules helt for uautentiserte kall.
Ser du den meldingen, er det fordi du peker på feil repo.

**For den som utvikler:** hver case-radar-endring må til *begge* repoene.
Push kun til Trading-bot, og serveren ser den aldri.

Førstegangsoppsett: se `BOOTSTRAP.md`.

## Vil du slippe å kjøre noe i det hele tatt

`autodeploy.sh` sjekker hvert 5. minutt om noe er pushet, og deployer det selv:

```bash
(crontab -l 2>/dev/null | grep -v case-radar/autodeploy; \
 echo "*/5 * * * * bash $HOME/case-radar/autodeploy.sh") | crontab -
```

Ærlig om hva det koster: **serveren deployer da ting du ikke har sett på først.**
Med `oppdater.sh` ser du commit-ene og godkjenner før noe rulles ut. Velg selv.

Skru av igjen: `crontab -l | grep -v case-radar/autodeploy | crontab -`
Se hva den har gjort: `tail -f ~/.case-radar-autodeploy.log`

## Nøkler

`~/.case-radar-key` (KI) og `~/.case-radar-tunnel-token` (tunnel) ligger på
serveren med `chmod 600`. Ingen skript skriver dem noen gang ut — verken til
skjerm, logg eller feilmelding. `sjekk-server.sh` sier bare *om* de finnes.

Skal en nøkkel byttes: `bash deploy.sh --ask` leser den nye trygt.
