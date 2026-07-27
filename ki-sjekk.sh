#!/usr/bin/env bash
# Case-radar — hva er det EGENTLIG som feiler med KI-en?
#
#   bash ki-sjekk.sh
#
# ## Hvorfor dette skriptet finnes
#
# 27.07.2026 sto det «KI-en er AV» paa kortet i to timer. Varselet sa
# «Groq (gratis): kvotetak (429)», og rett under sto raadet «sett noekkelen paa
# serveren» — som var gjort for lengst. Eieren maatte gjette.
#
# Dette skriptet gjetter ikke. Det gjoer ett bittelite ekte kall per leverandoer
# og sier hva som skjedde, med tall: hvilke noekler som finnes, hvem som svarer,
# og ved 429 om kvota aapner om sekunder (minuttak) eller timer (doegntak).
# De to krever helt ulike ting av deg, og det er hele poenget.
#
# Noekler skrives ALDRI ut - bare om de finnes og hvor mange tegn de er.
set -u
cd "$(dirname "$0")"
PY=.venv/bin/python
[ -x "$PY" ] || PY=python3

# Serveren legger noekkelen i ~/.case-radar-key. Uten dette leser skriptet
# ingenting og melder feilaktig «ingen noekkel».
[ -f "$HOME/.case-radar-key" ] && set -a && . "$HOME/.case-radar-key" && set +a

"$PY" - <<'PYEOF'
import os
from app import llm

def linje(t, s=""):
    print(f"  {t:<28} {s}")

print("\n\033[1mNØKLER I MILJØET\033[0m")
for n in ("GROQ_API_KEY", "OPENROUTER_API_KEY", "ANTHROPIC_API_KEY",
          "GEMINI_API_KEY", "CASE_RADAR_OLLAMA"):
    v = os.getenv(n, "")
    linje(n, f"\033[32m✓\033[0m {len(v)} tegn" if v else "\033[90m–\033[0m")

kjede = llm.leverandorkjede()
print("\n\033[1mKJEDEN\033[0m")
linje("rekkefølge", " → ".join(kjede) if kjede else "\033[31mtom\033[0m")
linje("Groq hovedmodell", llm.GROQ_MODEL)
linje("Groq reservemodell", llm.GROQ_MODEL_RESERVE)

print("\n\033[1mETT EKTE KALL PER LEVERANDØR\033[0m")
if not kjede:
    linje("resultat", "\033[31mingen nøkkel — appen kjører på maler\033[0m")
    print("\n  Fiks:  cd ~/case-radar && bash deploy.sh --ask\n")
    raise SystemExit(1)

for navn in kjede:
    llm._sett_feil(None)
    try:
        if navn == "anthropic":
            llm._anthropic_text("", "ping", model=llm.MODEL_JOURNALIST, max_tokens=4)
        elif navn == "gemini":
            llm._gemini_text("", "ping", max_tokens=4)
        else:
            llm._openai_chat(navn, "Svar med JSON.", "ping", max_tokens=8)
    except llm.KvoteSprengt as exc:
        v = llm.kvote_vent() or getattr(exc, "sekunder", 0) or 0
        if v >= llm.DOGNTAK_GRENSE:
            linje(llm.provider_label(navn),
                  f"\033[31mDØGNKVOTA ER BRUKT OPP\033[0m — åpner om "
                  f"{v/3600:.1f} t")
        else:
            linje(llm.provider_label(navn),
                  f"\033[33mminuttkvota er full\033[0m — åpner om {v:.0f} s")
        continue
    except Exception as exc:  # noqa: BLE001
        linje(llm.provider_label(navn),
              f"\033[31m{type(exc).__name__}\033[0m: {str(exc)[:70]}")
        continue
    linje(llm.provider_label(navn), "\033[32m✓ svarer\033[0m")
    print("\n  \033[32mKI-en virker.\033[0m Trykk «Skann nå» — vinklene blir ekte.\n")
    raise SystemExit(0)

print("""
  \033[1mHva nå?\033[0m
    · Sto det «minuttkvota er full»: vent ett minutt og prøv igjen. Appen
      henter dessuten vinklene selv i bakgrunnen.
    · Sto det «DØGNKVOTA ER BRUKT OPP»: ingen venting hjelper i dag. Legg inn
      en reservenøkkel — OpenRouter er gratis og uten kort:
          cd ~/case-radar && bash deploy.sh --ask
    · Sto det noe annet: da er det ikke kvota. Meldingen over er grunnen.
""")
raise SystemExit(1)
PYEOF
