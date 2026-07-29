# Redaktør-assistent

En **Chrome-utvidelse** + **server-proxy** som gir en journalist en full redaksjonell
kvalitetskontroll av en artikkel før publisering — etter Stavanger Aftenblads
standard. Drevet av Claude.

Journalisten trykker på én knapp i nettleseren og får:

- **Et sidepanel** med hele rapporten: LIX, dramaturgi, sjanger, Vær Varsom-plakaten,
  presseetikk, språk, fakta-sjekk, ingress, mellomtitler, 5 tittelforslag,
  omskrivinger, kritiske feil og delkarakterer med **Publiseringsklar: JA/NEI**.
- **Fargemarkeringer rett i teksten** for konkrete språk-, fakta- og VVP-funn,
  med et notat når man holder musepekeren over. Klikk på et funn i panelet for å
  hoppe til markeringen i teksten.

Innlogging (brukernavn/passord) gjør at kun godkjente brukere kan bruke serveren.

```
[Chrome-utvidelse]  --1) /login (brukernavn+passord)-->  [Din server (proxy)]
   (sidepanel)      <-- token ------------------------
                    --2) /review (tekst + token) ------>  --Claude API (nøkkel i env)--> [Anthropic]
                    <-------- strukturert vurdering (JSON) --------------------------------
```

Claude-nøkkelen ligger **kun** på serveren og forlater den aldri.

---

## Del 1 – Sett opp serveren

Serveren er en liten Node.js-proxy. Nøkkelen din ligger allerede på serveren.

### 1. Installer

```bash
cd server
npm install
```

### 2. Lag en `.env`

Kopier `.env.example` til `.env` og fyll inn:

```bash
cp .env.example .env
```

- `ANTHROPIC_API_KEY` – Claude-nøkkelen (ligger allerede på serveren din).
- `JWT_SECRET` – en lang, tilfeldig streng. Lag én slik:
  ```bash
  node -e "console.log(require('crypto').randomBytes(48).toString('hex'))"
  ```

### 3. Lag en bruker

Lag en passord-hash og legg brukeren i `server/users.json`
(eller i `USERS`-miljøvariabelen):

```bash
npm run hash-passord -- "det-hemmelige-passordet"
# -> $2a$10$....  (kopier hele linjen)
```

`server/users.json`:

```json
[{ "brukernavn": "mathias", "passordHash": "$2a$10$...." }]
```

(`.env` og `users.json` blir aldri committet – de står i `.gitignore`.)

### 4. Start

```bash
npm start
# Redaktør-assistent kjører på port 8787 (modell: claude-opus-4-8)
```

Test at den lever: åpne `http://localhost:8787/` – du skal få litt JSON.

> **Modell:** Standard er `claude-opus-4-8` (best kvalitet). Vil du ha en
> rimeligere modell, sett `MODEL=claude-sonnet-5` i `.env`.

> **Sett den offentlig:** Utvidelsen må nå serveren over HTTPS. Kjør proxyen bak
> HTTPS (din egen server / reverse proxy). Adressen du gir utvidelsen er
> roten, f.eks. `https://din-server.no` – den legger selv til `/login` og `/review`.

---

## Del 2 – Installer utvidelsen i Chrome

1. Gå til `chrome://extensions`.
2. Skru på **Utviklermodus** (øverst til høyre).
3. Klikk **Last inn upakket** og velg mappen `extension/`.
4. Klikk på verktøylinje-ikonet for å åpne **sidepanelet**.
5. Første gang: klikk **Åpne innstillinger** og skriv inn server-adressen
   (f.eks. `https://din-server.no`). Lagre.

---

## Del 3 – Slik bruker Mathias den

1. Åpne artikkelen i systemet der han skriver.
2. Klikk på **Redaktør-assistent**-ikonet → sidepanelet åpnes.
3. Logg inn (første gang) med brukernavn og passord.
4. Klikk **Sjekk artikkel**.
   - Utvidelsen henter teksten fra skrivefeltet automatisk. Vil han sjekke bare
     en del, kan han **markere** den delen først.
   - Finner den ikke teksten automatisk, dukker det opp et felt der han kan
     **lime inn** teksten.
5. Rapporten vises i panelet, og funn markeres i teksten. Klikk et funn i panelet
   for å hoppe til det i teksten.

---

## Tilpasse markering i den ekte editoren

Utvidelsen finner teksten robust (markering → største skrivefelt → `<article>`).
For at fargemarkeringene skal treffe **helt nøyaktig** inne i Aftenbladets editor,
kan det hende vi må justere hvordan teksten hentes. Send et skjermbilde eller
«Inspiser»-HTML av skrivefeltet, så finjusterer vi `hentTekst()` i
`extension/content.js`. Sidepanel-rapporten og «hopp til sitat» fungerer uansett.

---

## Personvern

Upubliserte artikler sendes til **din** server og videre til Anthropic (Claude)
med **din** nøkkel. Ingenting lagres av utvidelsen utover innloggings-token og
server-adressen, som ligger lokalt i nettleseren.

---

## Filoversikt

```
server/                 Node.js-proxy
  index.js              /login + /review
  prompt.js             redaktør-prompten + JSON-skjemaet
  hash-passord.js       lag passord-hash
extension/              Chrome MV3-utvidelse
  manifest.json
  background.js         åpner sidepanelet
  content.js            henter tekst + legger på markeringer
  panel/                sidepanelet (innlogging + rapport)
  options.html/js       innstillinger (server-adresse)
```
