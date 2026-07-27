# 📡 Case-radar

Trend- og case-scanner for journalister. Skanner **Stavanger/Rogaland og Norge**
for hva som rører seg – med vekt på **18–34 år** – og foreslår konkrete saker med
vinkling og kildelenker. Bygget for en rask hverdag i felt.

> Prototype (v1). Bruk treffene som **tips/leads**, ikke som fasit. Alle kilder er
> offentlige. Ingen betalte API-er kreves.

## Hva den gjør (v2 – originalitets-pivot)

Poenget er **originale saker ingen har skrevet ennå** – ikke gjenbruk av andre
avisers oppslag.

- **Datadrevne leads:** henter ferske tall fra **SSB** (åpne data) og finner notable
  endringer for Stavanger/Rogaland vs. resten av landet – et «funn» journalisten selv
  vinkler.
- **Originalitetssjekk:** for hvert lead søker den i Google News (gratis) og merker det
  🟢 **uskrevet**, 🟡 delvis dekket eller 🔴 allerede dekket. Uskrevne saker rangeres øverst.
- **Grasrot (valgfritt):** Reddit + Google Trends gir tidlige signaler før mediene.
- **Planlegger:** «gjør dette i uka»-liste + valgfri Google Calendar.

## Kilder (gratis)

| Kilde | Rolle | Status |
|---|---|---|
| **SSB åpne API** (tabell 07459 m.fl.) | Primær: datadrevne funn | ✅ |
| **Google News RSS** | Originalitetssjekk («allerede skrevet?») | ✅ |
| Reddit (r/stavanger, r/norge) | Grasrot-signaler | ✅ (kan blokkeres av proxy) |
| Google Trends (Norge) | Stigende søk | ✅ (kan rate-limites) |
| Google Calendar | Planlegger | ⚙️ valgfritt (krever egen nøkkel) |
| Flere SSB-tabeller, politilogg, arrangement | — | 🔜 lett å utvide i `config.py` |

## Dokumentasjon

| Fil | Hva |
|---|---|
| `docs/KILDER.md`, `docs/KILDEREGELEN.md` | Hvilke kilder, og regelen for hva som slipper inn |
| `docs/SOKESYSTEMET.md` | Hvordan skannet fungerer |
| `docs/LENKA.md` | To repoer: hvorfor speilingen finnes |
| `docs/TESTREGELEN.md` | Hva som må være grønt |
| **`docs/TOBIAS_FYSIKK.md`** | **Aktiv ragdoll — oppskriften. Les den før du rører `static/tobias/fysikk/`** |

## Kom i gang

```bash
# 1. Installer (uv anbefalt)
uv sync

# 2a. Kjør et skann i terminalen (rask sjekk)
uv run python -m app.cli

# 2b. Eller start web-dashboardet
uv run uvicorn app.main:app --reload
# åpne http://localhost:8000  → trykk «Skann nå»
```

Uten `uv`:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[trends]"
uvicorn app.main:app --reload
```

## 📱 Kjør som app (hosting) — så «Skann nå» + KI virker live

For at journalisten skal kunne åpne én URL på mobilen og bruke det som et dashboard
(med ekte skanning og KI-skrevne artikler), må appen kjøre på en server. Enklest:

### Render (anbefalt – nettleser, ingen kommandolinje)
1. Opprett gratis konto på **render.com** og koble til GitHub.
2. **New → Web Service** → velg dette repoet.
3. **Root Directory:** `case-radar`  ·  **Runtime:** Docker (oppdages fra `Dockerfile`).
4. Under **Environment** legg til en secret:  `ANTHROPIC_API_KEY = sk-ant-...`
   (nøkkel fra console.anthropic.com – uten den kjører appen i demo-modus/maler).
5. **Create Web Service.** Etter et par minutter får du en URL – åpne den på mobilen,
   og legg den til på Hjem-skjermen for app-følelse.

### Fly.io (kommandolinje)
```bash
cd case-radar
fly launch --dockerfile Dockerfile        # følg promptene, ikke deploy ennå
fly secrets set ANTHROPIC_API_KEY=sk-ant-...
fly deploy
```

### Lokalt med Docker
```bash
cd case-radar
docker build -t case-radar .
docker run -p 8000:8000 -e ANTHROPIC_API_KEY=sk-ant-... case-radar
# åpne http://localhost:8000
```

> Merk: på gratis-hosting er disken flyktig – godkjente saker nullstilles ved ny
> deploy. For varig lagring, koble på en liten database/disk (neste steg).
> Nøkkelen legges **kun** som secret/miljøvariabel hos hosten – aldri i koden.

## Google Trends (valgfritt)

```bash
uv sync --extra trends      # eller: pip install ".[trends]"
```
Slå av med `CASE_RADAR_ENABLE_TRENDS=false` i `.env` hvis Google rate-limiter deg.

## Google Calendar (valgfritt)

Prototypen kjører fint **uten** kalender. For å koble til:

1. Opprett en OAuth-klient (type **Desktop app**) i Google Cloud Console og last ned
   `credentials.json` til prosjektmappen.
2. `uv sync --extra calendar`
3. Første kjøring åpner en innloggingsflyt; `token.json` lagres lokalt (read-only).

`credentials.json`, `token.json` og `.env` er i `.gitignore` – de committes aldri.

## Tilpasning

Alt av kilder og nøkkelord ligger i [`app/config.py`](app/config.py):
- `NEWS_FEEDS` / `SUBREDDITS` – legg til/fjern kilder
- `STAVANGER_TERMS` – hva som teller som lokalt
- `DEMOGRAPHIC_TOPICS` – tema og nøkkelord for 18–34

## Tester

```bash
uv run pytest        # kjører uten nettverk (syntetiske data)
```

## Prosjektstruktur

```
app/
  main.py            FastAPI: dashboard + /scan
  config.py          kilder, geo- og temaord
  collectors/        news_rss, reddit, google_trends (fail-soft)
  scoring.py         klynging + rangering + vinkling
  planner.py         ukeplan-forslag
  calendar_google.py valgfri Google Calendar (read-only)
  storage.py         SQLite (siste skann)
templates/ static/   dashboard-UI
tests/               scoring- og parsing-tester
```

## Veien videre

Politilogg + arrangement-kilder, SSB-tall som bakgrunn, smartere (LLM-baserte)
vinklinger, e-post-morgenrapport, deploy, og X/TikTok når budsjett finnes.
