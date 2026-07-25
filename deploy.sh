#!/usr/bin/env bash
# Case-radar — ett skript som deployer, diagnostiserer og gir deg lenka.
#
#   bash deploy.sh                    # deploy + finn lenke (demo-modus hvis ingen nøkkel)
#   bash deploy.sh AIzaSy...          # deploy med gratis Gemini-nøkkel (ekte KI)
#   bash deploy.sh --tunnel           # tving gratis https-tunnel (funker uten IPv4/brannmur)
#   bash deploy.sh AIzaSy... --tunnel # begge
#
# Skriptet gjetter aldri: hvert steg sjekkes, og du får enten en fungerende lenke
# eller nøyaktig hva som er galt.
set -u

KEY=""
FORCE_TUNNEL=0
for arg in "$@"; do
  case "$arg" in
    --tunnel) FORCE_TUNNEL=1 ;;
    -*) echo "Ukjent flagg: $arg"; exit 2 ;;
    *) KEY="$arg" ;;
  esac
done

say()  { printf '\n\033[1m%s\033[0m\n' "$*"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }
bad()  { printf '  \033[31m✗\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }

# ── 0. Riktig mappe ──────────────────────────────────────────────────────────
if [ ! -f Dockerfile ] || [ ! -d app ]; then
  bad "Du står i feil mappe (fant ingen Dockerfile + app/)."
  echo "     Kjør:  cd ~/Trading-bot/case-radar && bash deploy.sh $*"
  exit 1
fi
ok "Riktig mappe: $(pwd)"

# ── 1. Docker ────────────────────────────────────────────────────────────────
say "1/6  Docker"
if ! command -v docker >/dev/null 2>&1; then
  warn "Docker mangler — installerer (dette tar et par minutter)…"
  curl -fsSL https://get.docker.com | sudo sh || { bad "Docker-installasjon feilet."; exit 1; }
fi
sudo docker info >/dev/null 2>&1 || { bad "Docker kjører ikke. Prøv: sudo systemctl start docker"; exit 1; }
ok "Docker kjører"

# ── 2. Nøkkelsjekk (før vi bygger, så du slipper å vente på en feil) ─────────
say "2/6  KI-nøkkel"
KEY_ARGS=""
if [ -z "$KEY" ]; then
  warn "Ingen nøkkel oppgitt → appen kjører i DEMO-modus (maler, ikke ekte KI)."
  warn "Vil du ha ekte KI gratis: hent nøkkel på https://aistudio.google.com/app/apikey"
  warn "og kjør:  bash deploy.sh AIzaSy…"
elif [ "${KEY#sk-ant-}" != "$KEY" ]; then
  ok "Claude-nøkkel (betalt API-kreditt)"
  KEY_ARGS="-e ANTHROPIC_API_KEY=$KEY"
else
  # Ingen prefiks-gjetting: Google har flere nøkkelformater (AIza…, AQ.…, ya29.…).
  # Vi TESTER nøkkelen mot ekte API og lar svaret avgjøre.
  echo "  Tester nøkkelen mot Gemini…"
  GM=${CASE_RADAR_GEMINI_MODEL:-gemini-2.0-flash}
  GURL="https://generativelanguage.googleapis.com/v1beta/models/$GM:generateContent"
  BODY='{"contents":[{"role":"user","parts":[{"text":"ping"}]}],"generationConfig":{"maxOutputTokens":4}}'
  # Googles dokumenterte maate er x-goog-api-key; ?key= er eldre; Bearer for
  # OAuth-/ephemeral-tokens. Prøv alle tre — formatet skal ikke avgjøre.
  R1=$(curl -s -o /tmp/cr_key.json -w '%{http_code}' -m 20 -X POST \
        -H 'Content-Type: application/json' -H "x-goog-api-key: $KEY" \
        -d "$BODY" "$GURL" 2>/dev/null || echo 000)
  R2=000; R3=000
  if [ "$R1" != "200" ]; then
    R2=$(curl -s -o /tmp/cr_key.json -w '%{http_code}' -m 20 -X POST \
          -H 'Content-Type: application/json' -d "$BODY" "$GURL?key=$KEY" 2>/dev/null || echo 000)
  fi
  if [ "$R1" != "200" ] && [ "$R2" != "200" ]; then
    R3=$(curl -s -o /tmp/cr_key.json -w '%{http_code}' -m 20 -X POST \
          -H 'Content-Type: application/json' -H "Authorization: Bearer $KEY" \
          -d "$BODY" "$GURL" 2>/dev/null || echo 000)
  fi
  if [ "$R1" = "200" ] || [ "$R2" = "200" ] || [ "$R3" = "200" ]; then
    ok "Nøkkelen VIRKER mot Gemini (gratis-nivå)"
    KEY_ARGS="-e GEMINI_API_KEY=$KEY"
  else
    bad "Nøkkelen ble avvist (header $R1 / key= $R2 / Bearer $R3). Googles egen melding:"
    head -c 400 /tmp/cr_key.json 2>/dev/null; echo
    echo
    echo "     Vanligste årsaker:"
    echo "       • Tokenet er et kortlevd/ephemeral token — de utløper etter minutter."
    echo "         Du trenger en varig API-nøkkel: https://aistudio.google.com/app/apikey"
    echo "         (Create API key → kopier hele strengen)"
    echo "       • Generative Language API ikke aktivert for prosjektet."
    echo "       • Feil kopiert (mellomrom eller manglende tegn)."
    echo
    echo "     Deployer i DEMO-modus nå så du får en fungerende lenke uansett."
    echo "     Legg på nøkkel senere:  bash deploy.sh <nøkkel>"
    KEY_ARGS=""
  fi
  rm -f /tmp/cr_key.json
fi

# ── 3. Bygg ──────────────────────────────────────────────────────────────────
say "3/6  Bygger image"
sudo docker build -q -t case-radar . >/dev/null || { bad "Bygging feilet. Se feilen over."; exit 1; }
ok "Image bygget"

# ── 4. Start ─────────────────────────────────────────────────────────────────
say "4/6  Starter container"
sudo docker rm -f case-radar >/dev/null 2>&1
# shellcheck disable=SC2086
sudo docker run -d --name case-radar --restart unless-stopped \
  -p 8000:8000 $KEY_ARGS -v /opt/case-radar-data:/tmp case-radar >/dev/null \
  || { bad "Start feilet."; exit 1; }

for i in $(seq 1 30); do
  HEALTH=$(curl -s -m 2 http://localhost:8000/health 2>/dev/null || true)
  case "$HEALTH" in *'"ok"'*) break ;; esac
  sleep 1
done
case "${HEALTH:-}" in
  *'"ok"'*) ok "Appen svarer: $HEALTH" ;;
  *) bad "Appen svarer ikke på /health etter 30 sek. Logg:"
     sudo docker logs --tail 20 case-radar; exit 1 ;;
esac

# ── 5. Nettverk: kan mobilen faktisk nå den? ─────────────────────────────────
say "5/6  Nettverk"
sudo ufw allow 8000/tcp >/dev/null 2>&1 && ok "ufw: port 8000 åpnet" || warn "ufw ikke aktiv/tilgjengelig (ok)"
IPV4=$(curl -4 -s -m 5 ifconfig.me 2>/dev/null || true)
USE_TUNNEL=$FORCE_TUNNEL
if [ -n "$IPV4" ]; then
  ok "Serveren har IPv4: $IPV4"
else
  bad "Serveren har INGEN IPv4 (kun IPv6) — en http://[2001:…]-lenke funker sjelden på mobil."
  warn "Bruker gratis https-tunnel i stedet."
  USE_TUNNEL=1
fi

# ── 6. Lenka ─────────────────────────────────────────────────────────────────
say "6/6  Lenka di"
if [ "$USE_TUNNEL" = "1" ]; then
  if ! command -v cloudflared >/dev/null 2>&1; then
    warn "Installerer cloudflared (gratis tunnel)…"
    ARCH=$(dpkg --print-architecture 2>/dev/null || echo amd64)
    curl -fsSL -o /tmp/cf.deb "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${ARCH}.deb" \
      && sudo dpkg -i /tmp/cf.deb >/dev/null 2>&1 \
      || { bad "Klarte ikke installere cloudflared."
           echo "     Alternativ som alltid funker: deploy på Render (render.yaml ligger i repoet)."
           exit 1; }
  fi
  sudo docker rm -f case-radar-tunnel >/dev/null 2>&1
  sudo docker run -d --name case-radar-tunnel --restart unless-stopped --network host \
    cloudflare/cloudflared:latest tunnel --no-autoupdate --url http://localhost:8000 >/dev/null 2>&1 \
    || { pkill -f "cloudflared.*8000" 2>/dev/null
         nohup cloudflared tunnel --no-autoupdate --url http://localhost:8000 \
           > /tmp/case-radar-tunnel.log 2>&1 & }
  echo "  Venter på tunnel-adresse…"
  URL=""
  for i in $(seq 1 30); do
    URL=$( { sudo docker logs case-radar-tunnel 2>&1; cat /tmp/case-radar-tunnel.log 2>/dev/null; } \
           | grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' | head -1 )
    [ -n "$URL" ] && break
    sleep 2
  done
  if [ -n "$URL" ]; then
    ok "Tunnel oppe"
    printf '\n\033[1;32m  ÅPNE PÅ MOBIL:  %s\033[0m\n\n' "$URL"
    echo "  (https, funker på hvilken som helst mobil — ingen brannmur eller IP nødvendig)"
    echo "  Adressen endres hvis tunnelen restartes. Vil du ha en fast lenke: bruk Render."
  else
    bad "Fikk ikke tunnel-adresse. Sjekk: sudo docker logs case-radar-tunnel"
    exit 1
  fi
else
  printf '\n\033[1;32m  ÅPNE PÅ MOBIL:  http://%s:8000\033[0m\n\n' "$IPV4"
  echo "  Får du timeout på mobil: åpne port 8000 i one.com sitt kontrollpanel"
  echo "  (serverens ufw er ikke nok — skyleverandøren har sin egen brannmur)."
  echo "  Eller kjør:  bash deploy.sh ${KEY:+<nøkkel> }--tunnel   for gratis https-lenke."
fi

say "Status"
echo "  Live-modus vises i appen etter «Skann nå» — den sier ærlig om KI-en er ekte,"
echo "  og hvis den feiler får du grunnen (feil nøkkel / tom kvote / ukjent modell)."
echo "  Logg:   sudo docker logs -f case-radar"
echo "  Stopp:  sudo docker rm -f case-radar case-radar-tunnel"
