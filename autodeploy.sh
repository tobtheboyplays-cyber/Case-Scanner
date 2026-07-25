#!/usr/bin/env bash
# Case-radar — henter nye endringer og deployer dem automatisk.
#
# Settes opp ÉN gang (se nederst), deretter ruller nye versjoner ut av seg selv.
# Gjor ingenting naar det ikke er noe nytt, saa den kan kjore ofte og billig.
#
# Kjorer aldri uten en fungerende noekkel: deploy.sh henter den fra
# ~/.case-radar-key, som ble lagret forste gang du deployet med noekkel.
set -u

REPO_DIR="${CASE_RADAR_DIR:-$HOME/case-radar}"
LOG="$HOME/.case-radar-autodeploy.log"
LOCK="/tmp/case-radar-autodeploy.lock"

log() { printf '%s  %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >> "$LOG"; }

# Én om gangen. En henger ikke skal stable opp nye.
exec 9>"$LOCK" || exit 0
flock -n 9 || { log "hopper over: en deploy kjorer allerede"; exit 0; }

cd "$REPO_DIR" 2>/dev/null || { log "FEIL: finner ikke $REPO_DIR"; exit 1; }

# Hent uten aa endre noe enda, saa vi kan se om det faktisk er nytt.
if ! git fetch --quiet origin 2>>"$LOG"; then
  log "fetch feilet (nett?) - proever igjen neste gang"
  exit 0
fi

LOCAL=$(git rev-parse HEAD 2>/dev/null)
REMOTE=$(git rev-parse '@{u}' 2>/dev/null)

if [ "$LOCAL" = "$REMOTE" ]; then
  exit 0   # ingenting nytt - helt stille
fi

SUBJECT=$(git log --format=%s -1 "$REMOTE" 2>/dev/null)
log "ny versjon: ${LOCAL:0:7} -> ${REMOTE:0:7}  ($SUBJECT)"

if ! git merge --ff-only "$REMOTE" >>"$LOG" 2>&1; then
  log "FEIL: kunne ikke fast-forwarde (lokale endringer?) - hopper over"
  exit 1
fi

# deploy.sh henter lagret noekkel selv og bygger + restarter containeren.
if bash deploy.sh >>"$LOG" 2>&1; then
  log "deploy OK  ($SUBJECT)"
else
  log "DEPLOY FEILET - forrige container kjorer fortsatt. Se logg over."
  exit 1
fi

# ─────────────────────────────────────────────────────────────────────────────
# ENGANGS-OPPSETT (kjor denne ene linja paa serveren):
#
#   (crontab -l 2>/dev/null | grep -v case-radar/autodeploy; \
#    echo "*/5 * * * * bash $HOME/case-radar/autodeploy.sh") | crontab -
#
# Da sjekker serveren hvert 5. minutt om det er noe nytt, og deployer det selv.
# Se hva som har skjedd:   tail -f ~/.case-radar-autodeploy.log
# Skru av igjen:           crontab -l | grep -v case-radar/autodeploy | crontab -
# ─────────────────────────────────────────────────────────────────────────────
