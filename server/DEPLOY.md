# Deploy av proxyen på din egen server

Utvidelsen må nå serveren over **HTTPS**. Under er tre veier – velg den som
passer din server. Alle bruker de samme filene i denne mappen.

Felles forberedelse (på serveren):

```bash
cd server
npm install
cp .env.example .env        # fyll inn ANTHROPIC_API_KEY + JWT_SECRET
node hash-passord.js "velg-passord"   # kopier hashen inn i users.json
```

`users.json`:
```json
[{ "brukernavn": "mathias", "passordHash": "$2a$10$..." }]
```

---

## Vei A – Linux VPS med Caddy (enklest, automatisk HTTPS) ✅ anbefalt

Krever et domene som peker (A-record) til serverens IP.

1. Start proxyen (helst via systemd, se Vei B) på `localhost:8787`.
2. Installer Caddy, legg `Caddyfile.example` som `/etc/caddy/Caddyfile` (bytt domenet):
   ```
   redaktor.dittdomene.no {
       reverse_proxy localhost:8787
   }
   ```
3. `sudo systemctl reload caddy` – Caddy henter HTTPS-sertifikat automatisk.
4. Server-adressen i utvidelsen blir: `https://redaktor.dittdomene.no`

## Vei B – systemd (hold proxyen kjørende)

1. Legg prosjektet i `/opt/redaktor-assistent`.
2. Kopier `redaktor.service` til `/etc/systemd/system/redaktor.service`.
3. ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now redaktor
   sudo systemctl status redaktor      # skal være "active (running)"
   ```
4. Sett HTTPS foran med Caddy (Vei A) eller nginx (under).

### nginx i stedet for Caddy
```nginx
server {
    server_name redaktor.dittdomene.no;
    location / {
        proxy_pass http://localhost:8787;
        proxy_set_header Host $host;
    }
}
```
Kjør deretter `certbot --nginx -d redaktor.dittdomene.no` for HTTPS.

## Vei C – Docker

```bash
cd server
docker build -t redaktor-assistent .
docker run -d --name redaktor -p 8787:8787 \
  -e ANTHROPIC_API_KEY=sk-ant-... \
  -e JWT_SECRET=lang-tilfeldig-streng \
  -e USERS='[{"brukernavn":"mathias","passordHash":"$2a$10$..."}]' \
  redaktor-assistent
```
Sett HTTPS foran med Caddy/nginx som over.

## Vei D – Plattform (Render / Railway / Fly.io o.l.)

Disse gir HTTPS automatisk. Sett `server/` som rot, start-kommando `npm start`,
og legg inn miljøvariablene `ANTHROPIC_API_KEY`, `JWT_SECRET` og `USERS` i
plattformens «Environment»-panel. Bruk URL-en de gir deg i utvidelsen.

---

## Til slutt: koble utvidelsen til

1. Last inn `extension/` i Chrome (`chrome://extensions` → Utviklermodus → Last inn upakket).
2. Åpne innstillinger → skriv inn server-adressen (f.eks. `https://redaktor.dittdomene.no`).
3. Logg inn, åpne en artikkel, trykk **Sjekk artikkel**.

Test at serveren lever: åpne `https://<din-adresse>/` → du skal få JSON med `"modell"`.
