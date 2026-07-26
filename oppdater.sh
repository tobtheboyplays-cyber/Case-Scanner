#!/usr/bin/env bash
# Case-radar — hent ny kode og rull den ut. EN kommando, hele veien.
#
#   bash oppdater.sh          # vis hva som er nytt, spor, og deploy
#   bash oppdater.sh --ja     # ikke spor, bare kjor (til cron/skript)
#
# Hvorfor dette skriptet finnes:
#
#   `deploy.sh` henter INGEN kode. Den bygger det som allerede ligger paa disken.
#   Kjorer du bare `bash deploy.sh` etter at noe er pushet, bygger du den gamle
#   koden om igjen - og alt ser vellykket ut. Ingen feilmelding, ingen anelse.
#   Det er den fella dette skriptet stenger.
#
# Kjeden er bare saa sterk som det svakeste leddet, saa hvert ledd sjekkes:
# hent -> vis hva som kommer -> flytt -> bygg -> og til slutt: virker lenka
# journalisten bruker, utenfra? Det siste er det eneste beviset som teller.
set -u

JA=0
for arg in "$@"; do
  case "$arg" in
    --ja|-y) JA=1 ;;
    *) echo "Ukjent flagg: $arg"; exit 2 ;;
  esac
done

say()  { printf '\n\033[1m%s\033[0m\n' "$*"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }
bad()  { printf '  \033[31m✗\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }
info() { printf '    %s\n' "$*"; }

if [ ! -f Dockerfile ] || [ ! -d app ]; then
  bad "Du staar i feil mappe (fant ingen Dockerfile + app/)."
  info "Prov:  cd ~/Trading-bot/case-radar && bash oppdater.sh"
  exit 1
fi

# ── 1. Hent ──────────────────────────────────────────────────────────────────
say "1/5  Henter fra GitHub"
git rev-parse --git-dir >/dev/null 2>&1 || { bad "Dette er ingen git-klone."; exit 1; }

if ! git fetch --quiet origin 2>&1; then
  bad "Fikk ikke kontakt med GitHub."
  info "Vanligst: tokenet i .git/config er utlopt. Lag nytt paa"
  info "https://github.com/settings/tokens (scope: repo) - se BOOTSTRAP.md."
  exit 1
fi

UPSTREAM=$(git rev-parse --abbrev-ref '@{u}' 2>/dev/null || true)
if [ -z "$UPSTREAM" ]; then
  bad "Branchen folger ingen upstream - vet ikke hvor den skal hente fra."
  info "Fiks:  git branch --set-upstream-to=origin/\$(git rev-parse --abbrev-ref HEAD)"
  exit 1
fi
ok "Henter fra $UPSTREAM"

# ── 2. Hva er nytt? ──────────────────────────────────────────────────────────
say "2/5  Hva som er nytt"
ANTALL=$(git rev-list --count "HEAD..@{u}" 2>/dev/null || echo 0)
if [ "$ANTALL" = "0" ]; then
  ok "Ingenting nytt - serveren kjorer allerede siste versjon."
  info "$(git log --format='%h %s' -1)"
  # Ikke bygg om for ingenting. En deploy uten endringer er 2 minutter og en
  # unodvendig nedetid paa appen.
  exit 0
fi
echo "  $ANTALL nye commits skal rulles ut:"
git log --format='      %h  %s' "HEAD..@{u}"

if [ "$JA" != "1" ]; then
  printf '\n  Rull ut? [j/N] '
  IFS= read -r SVAR
  case "$SVAR" in
    j|J|ja|JA|y|Y|yes) ;;
    *) echo "  Avbrutt - ingenting er endret."; exit 0 ;;
  esac
fi

# ── 3. Flytt ─────────────────────────────────────────────────────────────────
say "3/5  Flytter koden"
FOR=$(git rev-parse --short HEAD)
if ! git merge --ff-only '@{u}' >/dev/null 2>&1; then
  bad "Kunne ikke fast-forwarde. Det ligger lokale endringer i veien:"
  git status --short | head -10
  info "Serveren skal ikke ha lokale endringer. Kast dem med:"
  info "  git stash    (tar vare paa dem)   eller   git reset --hard @{u}  (kaster dem)"
  exit 1
fi
ETTER=$(git rev-parse --short HEAD)
ok "$FOR -> $ETTER"

# ── 4. Bygg og start ─────────────────────────────────────────────────────────
say "4/5  Bygger og starter"
# deploy.sh henter KI-nokkelen fra ~/.case-radar-key selv, og lar en navngitt
# tunnel staa i fred. Ingen argumenter her: alt som kan endre lenka, skal skje
# bevisst i fast-lenke.sh - aldri som bivirkning av en oppdatering.
if ! bash deploy.sh; then
  bad "Deploy feilet. Koden er flyttet, men containeren er ikke byttet."
  info "Forrige versjon kjorer sannsynligvis fortsatt - sjekk:  bash sjekk-server.sh"
  info "Tilbake til forrige commit:  git reset --hard $FOR && bash deploy.sh"
  exit 1
fi

# ── 5. Beviset: naar den fram til journalisten? ──────────────────────────────
# `deploy.sh` sjekker localhost. Det beviser at appen lever, ikke at noen
# UTENFRA kan naa den. Det er to forskjellige ting, og bare den siste betyr noe
# for journalisten.
say "5/5  Sjekker lenka utenfra"
VERT=$(cat "$HOME/.case-radar-tunnel-vert" 2>/dev/null || true)
LENKE=""
if [ -n "$VERT" ]; then
  LENKE="https://$VERT"
else
  DOCKER="docker"; docker info >/dev/null 2>&1 || DOCKER="sudo docker"
  QUICK=$( { $DOCKER logs case-radar-tunnel 2>&1; cat /tmp/case-radar-tunnel.log 2>/dev/null; } \
           | grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' | tail -1 )
  [ -n "${QUICK:-}" ] && LENKE="$QUICK"
fi

if [ -z "$LENKE" ]; then
  warn "Fant ingen offentlig lenke aa teste (ingen tunnel satt opp)."
  info "Kjor:  bash sjekk-server.sh"
else
  SVAR=$(curl -s -m 15 "$LENKE/health" 2>/dev/null || true)
  case "$SVAR" in
    *'"ok"'*) ok "Lenka svarer utenfra: $SVAR" ;;
    *) bad "Lenka svarer IKKE utenfra. Appen kjorer, men journalisten naar den ikke."
       info "Kjor:  bash sjekk-server.sh" ;;
  esac

  # At appen lever beviser ikke at NETTLESEREN faar ny CSS. Det gjorde den ikke
  # 26.07.2026: hele fiksen som gjorde sveipen synlig laa i style.css, fila ble
  # cachet av tunnelen, og en pull-to-refresh henter bare HTML. Deployen saa
  # vellykket ut mens eieren satt med gammel stil.
  #
  # Naa har lenka en innholdshash (?v=...). Vi henter forsiden, plukker ut den
  # hashen deployen faktisk serverer, og laster ned selve fila.
  CSSURL=$(curl -s -m 15 "$LENKE/" 2>/dev/null \
           | grep -oE '/static/style\.css\?v=[a-f0-9]+' | head -1)
  if [ -z "${CSSURL:-}" ]; then
    warn "Fant ingen versjonert CSS-lenke paa forsiden."
    info "Da kan nettleseren fortsatt sitte paa en gammel stilfil."
  else
    BITER=$(curl -s -m 15 "$LENKE$CSSURL" 2>/dev/null | wc -c)
    if [ "$BITER" -gt 1000 ]; then
      ok "Ny CSS serveres (${CSSURL#*v=}, $BITER bytes)"
    else
      bad "CSS-lenka svarte med $BITER bytes - noe cacher seg fast."
    fi
  fi
fi

say "Ferdig"
echo "  Kjorer naa:  $(git log --format='%h %s' -1)"
[ -n "$LENKE" ] && printf '\n\033[1;32m  LENKA:  %s\033[0m\n' "$LENKE"
echo
echo "  Si til journalisten at han drar ned for aa laste siden paa nytt - lenka er den samme."
