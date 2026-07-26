#!/usr/bin/env bash
# Case-radar — bytt engangslenka mot en fast adresse som overlever alt.
#
#   bash fast-lenke.sh
#
# Problemet den loser:
#
#   Dagens lenke er en «quick tunnel» - https://<tilfeldig>.trycloudflare.com.
#   Cloudflare trekker et NYTT tilfeldig navn hver gang cloudflared-prosessen
#   starter. Containeren har --restart unless-stopped, saa en server-reboot gir
#   ny adresse og et dodt bokmerke hos journalisten. Ingen har gjort noe galt;
#   det er bare slik quick tunnels virker.
#
#   En NAVNGITT tunnel binder adressen til DNS i stedet for til prosessen. Da
#   overlever lenka reboot, redeploy og at cloudflared restartes.
#
# Hvorfor token og ikke `cloudflared tunnel login`: innloggingen krever en
# nettleser midt i en SSH-okt. Tokenet limes inn EN gang og lagres - noyaktig
# samme monster som KI-nokkelen i ~/.case-radar-key, saa det er ett monster aa
# huske, ikke to.
set -u

say()  { printf '\n\033[1m%s\033[0m\n' "$*"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }
bad()  { printf '  \033[31m✗\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }
info() { printf '    %s\n' "$*"; }

TOKENFIL="$HOME/.case-radar-tunnel-token"
VERTFIL="$HOME/.case-radar-tunnel-vert"

DOCKER="docker"
docker info >/dev/null 2>&1 || DOCKER="sudo docker"
$DOCKER info >/dev/null 2>&1 || { bad "Docker kjorer ikke. Prov: sudo systemctl start docker"; exit 1; }

# ── 0. Appen maa kjore ───────────────────────────────────────────────────────
say "0/4  Appen"
HEALTH=$(curl -s -m 3 http://localhost:8000/health 2>/dev/null || true)
case "${HEALTH:-}" in
  *'"ok"'*) ok "Appen svarer paa localhost:8000" ;;
  *) bad "Appen svarer ikke. Start den forst:  bash deploy.sh"
     exit 1 ;;
esac

# ── 1. Forutsetningen, sagt rett ut ──────────────────────────────────────────
say "1/4  Dette trenger du forst"
cat <<'TEKST'
    En fast Cloudflare-adresse KREVER et domene i Cloudflare. Det finnes ingen
    gratis fast adresse uten: *.cfargotunnel.com er ikke offentlig rutbar, og
    trycloudflare.com er alltid tilfeldig. Bedre aa vite det naa enn etter ti
    minutter med klikking.

    Har du et domene (f.eks. hos one.com):
      Flytt navneserverne til Cloudflare - gratis, tar en halvtime aa forplante.

    Har du ingen:
      Cloudflare selger domener til kostpris, rundt 100 kr/aar.

    Vil du ikke ha domene i det hele tatt:
      Tailscale Funnel gir en fast https-adresse gratis uten domene. Styggere
      adresse (<vert>.<tailnet>.ts.net), ny konto - men den virker. Se
      docs/LENKA.md.

    NAAR du har domenet, gjor dette i Cloudflare Zero Trust (one.dash.cloudflare.com):

      1. Networks -> Tunnels -> Create a tunnel -> Cloudflared
      2. Navn: case-radar
      3. Kopier tokenet den viser (lang streng som begynner med «eyJ»)
      4. Under Public Hostname -> Add a public hostname:
           Subdomain: radar          (eller det du vil)
           Domain:    <ditt domene>
           Type:      HTTP
           URL:       localhost:8000
TEKST

printf '\n  Har du gjort de fire stegene? [j/N] '
IFS= read -r SVAR
case "$SVAR" in
  j|J|ja|JA|y|Y|yes) ;;
  *) echo "  Greit - kjor skriptet igjen naar du er klar."; exit 0 ;;
esac

# ── 2. Token ─────────────────────────────────────────────────────────────────
say "2/4  Tunnel-token"
# Leses uten echo og skrives aldri ut. Et tunnel-token gir tilgang til aa
# eksponere tjenester paa domenet ditt - det er en hemmelighet paa linje med
# API-nokkelen, og hores ikke hjemme i terminalhistorikk eller en logg.
printf '  Lim inn tokenet (det vises ikke) og trykk enter: '
if ! IFS= read -rs TOKEN 2>/dev/null; then IFS= read -r TOKEN; fi
printf '\n'

[ -n "${TOKEN:-}" ] || { bad "Tomt token."; exit 1; }
case "$TOKEN" in
  eyJ*) ok "Ser ut som et tunnel-token (${#TOKEN} tegn)" ;;
  *) warn "Tokenet begynner ikke med «eyJ». Vanligste feil: du kopierte hele"
     info "docker-kommandoen i stedet for bare tokenet. Provner likevel." ;;
esac

printf '  Vertsnavnet du satte opp (f.eks. radar.dittdomene.no): '
IFS= read -r VERT
[ -n "${VERT:-}" ] || { bad "Uten vertsnavn kan jeg ikke verifisere at lenka virker."; exit 1; }
VERT=${VERT#http://}; VERT=${VERT#https://}; VERT=${VERT%%/*}

# ── 3. Start den navngitte tunnelen ──────────────────────────────────────────
say "3/4  Starter fast tunnel"
$DOCKER rm -f case-radar-tunnel >/dev/null 2>&1 && ok "Fjernet den gamle engangstunnelen" || true
pkill -f "cloudflared.*8000" 2>/dev/null || true

if ! $DOCKER run -d --name case-radar-tunnel --restart unless-stopped --network host \
     cloudflare/cloudflared:latest tunnel --no-autoupdate run --token "$TOKEN" >/dev/null 2>&1; then
  bad "Klarte ikke starte tunnel-containeren."
  info "Se hva som skjedde:  $DOCKER logs case-radar-tunnel"
  exit 1
fi
ok "Tunnel-container startet (--restart unless-stopped)"

# Lagres FORST etter at containeren startet, saa en halvferdig kjoring ikke
# etterlater en fil som lyver om at alt er satt opp.
printf '%s' "$TOKEN" > "$TOKENFIL" && chmod 600 "$TOKENFIL"
printf '%s' "$VERT"  > "$VERTFIL"  && chmod 600 "$VERTFIL"
ok "Token lagret i $TOKENFIL (chmod 600, vises aldri)"

# ── 4. Beviset ───────────────────────────────────────────────────────────────
say "4/4  Virker den?"
echo "  Venter paa at tunnelen kobler seg opp og DNS forplanter seg…"
SVAR=""
for _ in $(seq 1 20); do
  SVAR=$(curl -s -m 8 "https://$VERT/health" 2>/dev/null || true)
  case "$SVAR" in *'"ok"'*) break ;; esac
  sleep 3
done

case "${SVAR:-}" in
  *'"ok"'*)
    ok "Lenka svarer: $SVAR"
    printf '\n\033[1;32m  FAST LENKE:  https://%s\033[0m\n\n' "$VERT"
    echo "  Denne endrer seg ALDRI - ikke ved reboot, ikke ved deploy."
    echo "  Send den til journalisten og be ham bytte bokmerke."
    echo "  Fra naa av: legg inn oppdateringer med  bash oppdater.sh"
    ;;
  *)
    bad "Lenka svarer ikke enda."
    info "Det trenger ikke vaere feil - DNS kan bruke noen minutter forste gang."
    info "Sjekk om noen minutter:  curl https://$VERT/health"
    info "Tunnelens egen logg:      $DOCKER logs case-radar-tunnel"
    info "Vanligste aarsak: Public Hostname i Cloudflare peker ikke paa"
    info "localhost:8000, eller vertsnavnet er skrevet feil her."
    exit 1
    ;;
esac
