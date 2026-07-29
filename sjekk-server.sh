#!/usr/bin/env bash
# Case-radar — hva som FAKTISK kjorer paa serveren. Leser, endrer ingenting.
#
#   bash sjekk-server.sh
#
# Kjor denne naar noe er rart, eller for du fikser noe. Poenget er aa slippe aa
# gjette: hvilken kode kjorer, hvilken lenke har journalisten, og er de to i takt?
#
# Hvorfor den finnes: en deploy kan se helt vellykket ut og likevel bygge gammel
# kode, fordi deploy.sh ikke henter noe selv. Da staar alle og tror det er
# oppdatert. Denne sier fra.
set -u

say()  { printf '\n\033[1m%s\033[0m\n' "$*"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }
bad()  { printf '  \033[31m✗\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }
info() { printf '    %s\n' "$*"; }

DOCKER="docker"
docker info >/dev/null 2>&1 || DOCKER="sudo docker"

# ── 1. Koden ─────────────────────────────────────────────────────────────────
say "1/4  Koden"
if [ ! -f Dockerfile ] || [ ! -d app ]; then
  bad "Du staar i feil mappe (fant ingen Dockerfile + app/)."
  info "Prov:  cd ~/Trading-bot/case-radar && bash sjekk-server.sh"
  exit 1
fi
ok "Mappe: $(pwd)"

if git rev-parse --git-dir >/dev/null 2>&1; then
  REMOTE_URL=$(git remote get-url origin 2>/dev/null || echo "(ingen origin)")
  BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "?")
  ok "Repo:   $REMOTE_URL"
  ok "Branch: $BRANCH"
  info "Kjorer: $(git log --format='%h %s' -1 2>/dev/null)"

  # Er vi bak? Dette er hele grunnen til at skriptet finnes.
  if git fetch --quiet origin 2>/dev/null; then
    if UPSTREAM=$(git rev-parse --abbrev-ref '@{u}' 2>/dev/null); then
      BAK=$(git rev-list --count "HEAD..@{u}" 2>/dev/null || echo 0)
      FORAN=$(git rev-list --count "@{u}..HEAD" 2>/dev/null || echo 0)
      if [ "$BAK" -gt 0 ]; then
        bad "$BAK nye commits ligger i $UPSTREAM og kjorer IKKE her:"
        git log --format='      %h %s' "HEAD..@{u}" 2>/dev/null | head -10
        info "Rull dem ut med:  bash oppdater.sh"
      else
        ok "Oppdatert mot $UPSTREAM"
      fi
      [ "$FORAN" -gt 0 ] && warn "$FORAN lokale commits er ikke pushet noe sted"
    else
      warn "Branchen folger ingen upstream - «git pull» vet ikke hvor den skal hente"
    fi
  else
    warn "Fikk ikke kontakt med GitHub (nett? token utlopt?) - kan ikke si om vi er bak"
  fi

  ENDRET=$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')
  [ "$ENDRET" != "0" ] && warn "$ENDRET lokalt endrede filer - de blokkerer en ff-oppdatering"
else
  bad "Dette er ingen git-klone. Da kan ingenting oppdateres herfra."
fi

# ── 2. Containerne ───────────────────────────────────────────────────────────
say "2/4  Containerne"
for navn in case-radar case-radar-tunnel; do
  STATUS=$($DOCKER inspect -f '{{.State.Status}} siden {{.State.StartedAt}}' "$navn" 2>/dev/null || true)
  if [ -n "$STATUS" ]; then
    ok "$navn: $STATUS"
  else
    [ "$navn" = "case-radar" ] && bad "$navn kjorer ikke - appen er nede" \
                              || warn "$navn kjorer ikke (ingen tunnel)"
  fi
done

HEALTH=$(curl -s -m 3 http://localhost:8000/health 2>/dev/null || true)
case "${HEALTH:-}" in
  *'"ok"'*) ok "Appen svarer lokalt: $HEALTH" ;;
  *) bad "Appen svarer ikke paa localhost:8000/health" ;;
esac

# ── 3. Lenka ─────────────────────────────────────────────────────────────────
say "3/4  Lenka journalisten bruker"
LOGG=$( { $DOCKER logs case-radar-tunnel 2>&1; cat /tmp/case-radar-tunnel.log 2>/dev/null; } | tail -400 )
QUICK=$(printf '%s' "$LOGG" | grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' | tail -1)

if [ -n "${QUICK:-}" ]; then
  warn "QUICK tunnel: $QUICK"
  info "Denne adressen er en ENGANGSADRESSE. Restarter serveren, far tunnelen et"
  info "nytt tilfeldig navn og journalistens bokmerke blir dodt."
  info "Fast lenke i stedet:  bash fast-lenke.sh"
elif [ -f "$HOME/.case-radar-tunnel-token" ]; then
  ok "Navngitt tunnel er satt opp (adressen staar i Cloudflare-panelet)"
  VERT=$(cat "$HOME/.case-radar-tunnel-vert" 2>/dev/null || true)
  if [ -n "$VERT" ]; then
    SVAR=$(curl -s -m 8 "https://$VERT/health" 2>/dev/null || true)
    case "$SVAR" in
      *'"ok"'*) ok "https://$VERT svarer: $SVAR" ;;
      *) bad "https://$VERT svarer IKKE - journalisten naar ikke appen" ;;
    esac
  fi
else
  IPV4=$(curl -4 -s -m 5 ifconfig.me 2>/dev/null || true)
  if [ -n "$IPV4" ]; then
    warn "Ingen tunnel. Lenka er da:  http://$IPV4:8000"
    info "Timer den ut paa mobil, er det one.coms skybrannmur - ikke serveren."
  else
    bad "Ingen tunnel og ingen IPv4 - det finnes ingen lenke som virker."
  fi
fi

# ── 4. Nokler ────────────────────────────────────────────────────────────────
# Kun OM de finnes. Innholdet skal aldri i terminalhistorikk eller logg.
say "4/4  Nokler (viser aldri innholdet)"
[ -r "$HOME/.case-radar-key" ] \
  && ok "KI-nokkel lagret ($(wc -c < "$HOME/.case-radar-key" | tr -d ' ') tegn)" \
  || warn "Ingen KI-nokkel - appen kjorer i demo-modus (maler, ikke ekte KI)"
[ -r "$HOME/.case-radar-tunnel-token" ] \
  && ok "Tunnel-token lagret" \
  || info "Ingen tunnel-token (bruker quick tunnel eller IP-lenke)"

say "Ferdig"
echo "  Oppdater:   bash oppdater.sh"
echo "  Fast lenke: bash fast-lenke.sh"
echo "  Applogg:    $DOCKER logs -f case-radar"
