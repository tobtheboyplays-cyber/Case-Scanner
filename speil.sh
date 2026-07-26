#!/usr/bin/env bash
# Case-radar — speil arbeidsrepoet til det OFFENTLIGE repoet serveren henter fra.
#
#   bash speil.sh              # vis hva som mangler, spor, speil og push
#   bash speil.sh --ja         # ikke spor (til skript)
#   bash speil.sh --sjekk      # bare SI om speilet henger etter, endre ingenting
#
# ## Hvorfor dette skriptet finnes
#
# 26.07.2026 skrev eieren: «Pushen faar det aldri igjennom med en gang. Ingen pil
# og ingen Tobias.» Koden var pushet, testene var groenne, og deployen paa
# serveren virket. Feilen var likevel enkel og total:
#
#   Serveren henter fra `Case-Scanner` (offentlig). Arbeidet ble pushet til
#   `Trading-bot` (privat). Serveren saa det aldri.
#
# `oppdater.sh` sa da helt korrekt «Ingenting nytt - serveren kjorer allerede
# siste versjon», fordi den bare kan se det offentlige repoet. Alt saa riktig ut
# fra hver enkelt vinkel, og likevel naadde ingenting fram til journalisten.
#
# Det stod i `docs/LENKA.md` at hver endring maatte til begge repoene. En setning
# i et dokument er ikke en sperre - den er en paaminnelse man kan gaa glipp av.
# Dette skriptet er sperren.
#
# ## Hva det gjor, og hva det IKKE gjor
#
# Bare filer som er SPORET av git i arbeidsrepoet kopieres. Det er med vilje:
# da kan ingen ignorert fil (`.env`, `data/`, `BUILD.txt`, noekler) sive over i et
# offentlig repo ved et uhell. `brain/` og trading-koden ligger utenfor
# `case-radar/` og er derfor aldri i naerheten av dette.
set -u

# Git setter GIT_DIR/GIT_WORK_TREE naar den kjorer en hook. Arver vi dem, peker
# ALLE git-kall her paa repo-rota uansett hvilken katalog vi ber om - og
# `git ls-files` i case-radar/ svarte med hele Trading-bot, trading-testene
# inkludert. Maalt 26.07.2026: 191 filer «skilte seg», hvorav de fleste ikke
# hoerer til case-radar i det hele tatt.
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_PREFIX GIT_COMMON_DIR \
      GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES 2>/dev/null || true

JA=0; BARE_SJEKK=0
for arg in "$@"; do
  case "$arg" in
    --ja|-y)   JA=1 ;;
    --sjekk|-n) BARE_SJEKK=1 ;;
    *) echo "Ukjent flagg: $arg"; exit 2 ;;
  esac
done

say()  { printf '\n\033[1m%s\033[0m\n' "$*"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }
bad()  { printf '  \033[31m✗\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }
info() { printf '    %s\n' "$*"; }

KILDE=$(cd "$(dirname "$0")" && pwd)
[ -d "$KILDE/app" ] || { bad "Fant ingen app/ i $KILDE"; exit 1; }

# Klonen av det offentlige repoet. Kan overstyres naar den ligger et annet sted.
MAAL="${CASE_SCANNER_DIR:-}"
if [ -z "$MAAL" ]; then
  for kandidat in /workspace/case-scanner "$HOME/case-scanner" "$HOME/Case-Scanner"; do
    [ -d "$kandidat/.git" ] && { MAAL="$kandidat"; break; }
  done
fi
if [ -z "$MAAL" ] || [ ! -d "$MAAL/.git" ]; then
  bad "Finner ingen klone av det offentlige repoet."
  info "Klon det:  git clone https://github.com/tobtheboyplays-cyber/Case-Scanner"
  info "Eller pek paa den:  CASE_SCANNER_DIR=/sti/til/klonen bash speil.sh"
  exit 1
fi
ok "Speiler $KILDE  ->  $MAAL"

# ── 1. Kopier det git sporer, og bare det ────────────────────────────────────
say "1/4  Sammenligner"
ENDRINGER=$(KILDE="$KILDE" MAAL="$MAAL" TORR="$BARE_SJEKK" python3 - <<'PY'
import os, shutil, subprocess, sys
from pathlib import Path

kilde, maal = Path(os.environ["KILDE"]), Path(os.environ["MAAL"])
torr = os.environ["TORR"] == "1"

def sporet(rot):
    ut = subprocess.run(["git", "ls-files"], cwd=rot, capture_output=True, text=True)
    return [r for r in ut.stdout.split("\n") if r]

nye, endret = [], []
for rel in sporet(kilde):
    s, m = kilde / rel, maal / rel
    if not m.exists():
        nye.append(rel)
    elif s.read_bytes() != m.read_bytes():
        endret.append(rel)
    else:
        continue
    if not torr:
        m.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(s, m)

# Slettet hos kilden skal ogsaa slettes i speilet, ellers vokser det offentlige
# repoet med filer som ikke lenger finnes noe sted.
har = set(sporet(kilde))
borte = [r for r in sporet(maal) if r not in har]
if not torr:
    for r in borte:
        (maal / r).unlink(missing_ok=True)

for merke, liste in (("ny", nye), ("endret", endret), ("slettet", borte)):
    for r in liste:
        print(f"      {merke:8} {r}", file=sys.stderr)
print(len(nye) + len(endret) + len(borte))
PY
) || { bad "Sammenligningen feilet."; exit 1; }

if [ "$ENDRINGER" = "0" ]; then
  ok "Speilet er allerede likt - serveren ser alt som er gjort."
  exit 0
fi
echo "  $ENDRINGER filer skiller seg."

if [ "$BARE_SJEKK" = "1" ]; then
  warn "SPEILET HENGER ETTER. Serveren vil IKKE se disse endringene."
  info "Fiks:  bash speil.sh"
  exit 1
fi

# ── 2. Bevis at speilet faktisk ble likt ─────────────────────────────────────
# Uten dette kunne en kopieringsfeil gitt gronne haker og et halvt speil.
say "2/4  Sjekker at speilet er identisk"
IGJEN=$(KILDE="$KILDE" MAAL="$MAAL" TORR=1 python3 - <<'PY'
import os, subprocess
from pathlib import Path
kilde, maal = Path(os.environ["KILDE"]), Path(os.environ["MAAL"])
def sporet(rot):
    u = subprocess.run(["git","ls-files"], cwd=rot, capture_output=True, text=True)
    return [r for r in u.stdout.split("\n") if r]
avvik = [r for r in sporet(kilde)
         if not (maal/r).exists() or (kilde/r).read_bytes() != (maal/r).read_bytes()]
print(len(avvik))
PY
)
if [ "$IGJEN" != "0" ]; then
  bad "$IGJEN filer er fortsatt ulike etter kopiering. Speilet er IKKE komplett."
  exit 1
fi
ok "Alle sporede filer er byte-identiske"

# ── 3. Hemmeligheter skal aldri naa et offentlig repo ────────────────────────
say "3/4  Leter etter hemmeligheter i det som skal ut"
cd "$MAAL" || exit 1
git add -A
# Formene vi faktisk bruker: Groq (gsk_), OpenAI-lignende (sk-), Alpaca (PK/AK).
#
# ## Hvorfor vendor/ holdes utenfor MOENSTERsoeket - og hva som gjores i stedet
#
# `static/tobias/vendor/rapier.js` er 2 MB minifisert tredjepartskode med en
# innbakt WASM-modul. Der finnes det garantert bokstavsekvenser som ser ut som
# `AK` + 16 tegn; 26.07.2026 stoppet det hele speilingen paa en tilfeldig
# variabelrekke inne i wasm-bindgen-limet. Et moenstersoek har ingen sjanse mot
# slik kode, og en sperre som alltid slaar ut er en sperre folk laerer seg aa
# overstyre - da er den verre enn ingen.
#
# Filene slippes likevel ikke inn ubesett: de maa staa i lista under. Legger
# noen en NY fil i vendor/, stopper speilingen like fullt - men da paa noe som
# faktisk betyr noe, i stedet for paa tilfeldig base64.
# Rapier er Apache 2.0 (ikke MIT - lisensfila ligger ved siden av, slik Apache
# 2.0 krever). Three.js, som ligger over i static/tobias/, er MIT.
VENDOR_GODKJENT="static/tobias/vendor/rapier.js static/tobias/vendor/RAPIER-LICENSE.txt"
for f in $(git diff --cached --name-only -- 'static/tobias/vendor/' || true); do
  case " $VENDOR_GODKJENT " in
    *" $f "*) ;;
    *) bad "Ny fil i vendor/ som ikke er godkjent: $f"
       say "    Legg den i VENDOR_GODKJENT i speil.sh naar du VET hva den er."
       git reset >/dev/null; exit 1 ;;
  esac
done
MISTENKT=$(git diff --cached -- . ':(exclude)static/tobias/vendor/' \
  | grep -nE '^\+.*(gsk_[A-Za-z0-9]{20}|sk-[A-Za-z0-9]{20}|(PK|AK)[A-Z0-9]{16})' \
  | head -5 || true)
if [ -n "$MISTENKT" ]; then
  bad "Fant noe som ligner en noekkel. INGENTING pushes."
  printf '%s\n' "$MISTENKT" | sed 's/^/    /'
  git reset >/dev/null
  exit 1
fi
ok "Ingen noekkelformer i diffen"

# ── 4. Push ──────────────────────────────────────────────────────────────────
say "4/4  Pusher til det offentlige repoet"
git -C "$KILDE" log --format='%h %s' -1 | sed 's/^/    arbeidsrepo: /'
if [ "$JA" != "1" ]; then
  printf '\n  Push til Case-Scanner/main? [j/N] '
  IFS= read -r SVAR
  case "$SVAR" in
    j|J|ja|JA|y|Y|yes) ;;
    *) echo "  Avbrutt - filene er kopiert, men ingenting er pushet."; exit 0 ;;
  esac
fi

EMNE=$(git -C "$KILDE" log --format=%s -1)
KILDE_SHA=$(git -C "$KILDE" rev-parse --short HEAD)
git commit -q -m "$EMNE" -m "Speiling av $KILDE_SHA i Trading-bot. Serveren henter herfra." || {
  warn "Ingenting aa committe."; exit 0; }

for forsok in 1 2 3 4; do
  if git push -u origin main; then
    ok "Pushet. Serveren henter dette ved neste autodeploy (hvert 5. min),"
    info "eller med én gang hvis du kjorer:  cd ~/case-radar && bash oppdater.sh"
    exit 0
  fi
  VENT=$((2 ** forsok))
  warn "Push feilet - proever igjen om ${VENT}s"
  sleep "$VENT"
done
bad "Push feilet fire ganger. Speilet er committet lokalt i $MAAL."
exit 1
