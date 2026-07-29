#!/usr/bin/env bash
# Case-radar — ett skann hver morgen, saa lista staar ferdig naar han setter seg.
#
# Eieren 26.07.2026: «En ny scan klokka 0700 hver dag.»
#
# Poenget er rytmen, ikke automatikken: et skann tar 40-60 sekunder, og det er
# 40-60 sekunder journalisten ellers sitter og venter paa. Kjorer det 07:00, er
# saksforslagene der naar han aapner lenka.
#
# KJORES HVER TIME, ikke 07:00. Det ser bakvendt ut og er med vilje:
#
#   · Serveren staar i UTC, journalisten i Oslo. En fast «0 7 * * *» ville truffet
#     08:00 om sommeren og 07:00 om vinteren - eller motsatt, avhengig av hvem som
#     satte den opp og naar. Her spor skriptet selv hva klokka er i OSLO.
#   · Var maskinen nede, rebootet eller uten nett 07:00, kjorer et
#     klokkeslett-cron aldri den dagen. Dette tar igjen ved neste time.
#
# Datostempelet sorger for at det blir ETT skann per dag uansett hvor mange
# ganger cron kaller.
set -u

PORT="${CASE_RADAR_PORT:-8000}"
URL="http://localhost:${PORT}"
LOG="$HOME/.case-radar-morgenskann.log"
LOCK="/tmp/case-radar-morgenskann.lock"
STEMPEL="$HOME/.case-radar-morgenskann.sist"
TIME_FRA="${CASE_RADAR_MORGENTIME:-7}"

log() { printf '%s  %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >> "$LOG"; }

# Hva er klokka og datoen der journalisten er? Faller TZ-databasen bort i et
# slankt image, bruker vi serverens egen tid i stedet for aa stoppe helt.
NAA_TIME=$(TZ=Europe/Oslo date +%H 2>/dev/null || date +%H)
I_DAG=$(TZ=Europe/Oslo date +%F 2>/dev/null || date +%F)

# `--naa` hopper over baade klokkeslett og datostempel. Til testing paa serveren:
# «virker dette i det hele tatt?» skal kunne besvares uten aa vente til i morgen.
if [ "${1:-}" != "--naa" ]; then
  [ "$((10#$NAA_TIME))" -lt "$TIME_FRA" ] && exit 0
  [ "$(cat "$STEMPEL" 2>/dev/null)" = "$I_DAG" ] && exit 0
fi

# Én om gangen. Henger et skann, skal ikke neste time stable seg oppaa.
exec 9>"$LOCK" || exit 0
flock -n 9 || { log "hopper over: et skann kjorer allerede"; exit 0; }

# Er appen oppe? Uten denne ville en nede container gitt en kryptisk curl-feil i
# logga i stedet for det som faktisk er galt.
if ! curl -sf -m 5 "$URL/health" > /dev/null 2>&1; then
  log "FEIL: appen svarer ikke paa $URL/health - skannet ble ikke startet"
  exit 1
fi

# Skannet startes gjennom appens EGEN /scan, ikke ved aa kjore Python inne i
# containeren. Da gjelder alt som gjelder for et knappetrykk: temavalget hans,
# tokenbudsjettet, koen, KI-hurtiglageret og laasen mot to samtidige skann. En
# egen kodevei ville vaert en ny sjanse for at cron og knapp gjor ulike ting.
#
# `meny` sendes IKKE med, og det er hele forskjellen paa cron og et knappetrykk:
# uten `meny=1` lar /scan temavalget staa urort, saa morgenskannet bruker det
# journalisten sist valgte. Sendte vi et tomt skjema MED `meny=1`, ville cron
# stille nullstilt temavalget hans hver eneste natt.
START=$(date +%s)
SVAR=$(curl -s -m 300 -o /dev/null -w '%{http_code}' -X POST "$URL/scan" 2>/dev/null || echo "000")
BRUKT=$(( $(date +%s) - START ))

if [ "$SVAR" = "200" ] || [ "$SVAR" = "303" ]; then
  ANTALL=$(curl -s -m 10 "$URL/api/cases" 2>/dev/null | grep -o '"key"' | wc -l | tr -d ' ')
  printf '%s\n' "$I_DAG" > "$STEMPEL"
  log "ok: morgenskann ferdig paa ${BRUKT}s, ${ANTALL} saker i lista"
else
  # Stempelet settes IKKE ved feil - da proever neste time paa nytt, som er
  # nettopp det man vil naar nettet var nede i fem minutter.
  log "FEIL: /scan svarte $SVAR etter ${BRUKT}s - proever igjen neste time"
  exit 1
fi

# ── Slaa paa (én gang, paa serveren) ─────────────────────────────────────────
#
#   (crontab -l 2>/dev/null | grep -v case-radar/morgenskann; \
#    echo "7 * * * * bash $HOME/case-radar/morgenskann.sh") | crontab -
#
# Minutt 7 og ikke 0: da kraesjer den ikke med autodeploy.sh, som kjorer hvert
# femte minutt paa hele fem.
#
# Se at det virker med én gang:  bash morgenskann.sh --naa
# Les logga:                     tail ~/.case-radar-morgenskann.log
# Skru av igjen:                 crontab -l | grep -v case-radar/morgenskann | crontab -
