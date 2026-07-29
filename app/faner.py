"""Faner for «Kommer snart» — ett tema per fane, med egen farge og nytt-prikk.

Eieren 26.07.2026, med skjermbilde: «Rotete, hva skjer. Ha det slik det er med et
sånn fanesystem med forskjellige farger med ulike temaer som kan komme inn. Så kan
det komme en liten notifikasjon-ikon over den fanen der det har kommet noe nytt.»

Panelet blandet to helt ulike ting under én overskrift:

  · KONKURSER, som allerede har skjedd, og som han kan ringe på i dag
  · SSB-TALL, som IKKE er sluppet, og som han kan forberede seg på

Begge er nyttige. Sammen er de en liste på 52 elementer der man må lese hver rad
for å vite hva slags sak det er. Fanene gjør det til ett blikk.

Hvorfor dette ligger i Python og ikke i malen: grupperingen, sorteringen,
tellingen og nytt-prikken er logikk. Gjort i Jinja blir det tre nøstede løkker
med `selectattr` og en `namespace()` for å telle — uleselig, og umulig å teste.
Her er det en liste med dicts og en tabell med tester.
"""

from __future__ import annotations

# Rekkefølgen her ER rekkefølgen på fanene, og den er journalistisk:
# det man kan ringe på i dag først, det som kommer etterpå.
#
# Fargene er ikke dekor. Hver fane har sin egen, og den går igjen på
# fanen, kanten og merket inni — så «hvilken slags sak er dette?» besvares
# av øyekroken før man har lest et ord. Fargen står ALDRI alene: hver fane
# har også ikon og navn (se style.css).
KONKURS = {"navn": "Konkurser", "ikon": "💥", "farge": "rod"}
NYTT = {"navn": "Nyåpninger", "ikon": "✨", "farge": "gronn"}

# SSBs egne emnekoder → fanen de havner i. Emner som ikke står her, samles i
# «Annet» i stedet for å lage hver sin fane av seg selv.
SSB_FANER: dict[str, dict] = {
    "arbeid-og-lonn": {"navn": "Jobb og lønn", "ikon": "💼", "farge": "blaa"},
    "inntekt-og-forbruk": {"navn": "Jobb og lønn", "ikon": "💼", "farge": "blaa"},
    "priser-og-prisindekser": {"navn": "Priser", "ikon": "💰", "farge": "gul"},
    "bygg-bolig-og-eiendom": {"navn": "Bolig og bygg", "ikon": "🏠", "farge": "lilla"},
    "befolkning": {"navn": "Befolkning", "ikon": "👥", "farge": "turkis"},
    "utdanning": {"navn": "Skole", "ikon": "🎓", "farge": "turkis"},
    "helse": {"navn": "Helse", "ikon": "🏥", "farge": "rosa"},
    "sosiale-forhold-og-kriminalitet": {"navn": "Kriminalitet", "ikon": "🚔", "farge": "rosa"},
    "energi-og-industri": {"navn": "Energi", "ikon": "⚡", "farge": "oransje"},
    "transport-og-reiseliv": {"navn": "Transport", "ikon": "🚌", "farge": "oransje"},
}
ANNET = {"navn": "Annet", "ikon": "📊", "farge": "grå"}

# Hvor mange elementer hver fane viser. Uten et tak var konkursfanen 40 rader
# lang, og da har vi flyttet rotet i stedet for å fjerne det.
MAKS_PER_FANE = 12


def _tom(mal: dict, slug: str) -> dict:
    return {**mal, "slug": slug, "elementer": [], "nytt": 0}


IDEER = {"navn": "Ideer til Tobias", "ikon": "💡", "farge": "gul"}


def bygg(
    hendelser: list[dict] | None,
    kommende: list[dict] | None,
    ideer: list[dict] | None = None,
) -> list[dict]:
    """[{slug, navn, ikon, farge, elementer, nytt}] — tomme faner utelates.

    `elementer` er dicts med `slag` («hendelse» eller «ssb») slik at malen vet
    hvilken rad den skal tegne, og `id` som nettleseren bruker til å huske hva
    han allerede har sett.
    """
    grupper: dict[str, dict] = {}

    def fane(slug: str, mal: dict) -> dict:
        if slug not in grupper:
            grupper[slug] = _tom(mal, slug)
        return grupper[slug]

    for h in hendelser or []:
        er_nytt = h.get("type") == "nytt"
        slug = "nyapninger" if er_nytt else "konkurser"
        f = fane(slug, NYTT if er_nytt else KONKURS)
        f["elementer"].append({
            **h,
            "slag": "hendelse",
            # orgnr er stabil; navn kan skrives om i registeret.
            "id": f"h:{h.get('orgnr') or h.get('navn', '')}",
            # Ferskt = noe som skjedde denne uka. Det er dette prikken teller.
            "fersk": (h.get("dager_siden") or 99) <= 7,
        })

    for v in kommende or []:
        mal = SSB_FANER.get(v.get("emne", ""), ANNET)
        slug = mal["navn"].lower().replace(" ", "-").replace("ø", "o").replace("å", "a")
        f = fane(slug, mal)
        f["elementer"].append({
            **v,
            "slag": "ssb",
            "id": f"s:{v.get('lenke') or v.get('tittel', '')}",
            # For et varsel er «ferskt» det samme som «nært»: det som slippes
            # innen tre dager er det han må rekke å forberede.
            "fersk": (v.get("dager_til") or 99) <= 3,
        })

    ut = []
    for f in grupper.values():
        # Hendelser: ferskest først. Varsler: det som kommer først, først.
        f["elementer"].sort(
            key=lambda e: (e.get("dager_siden") if e["slag"] == "hendelse"
                           else e.get("dager_til") or 0)
        )
        f["antall"] = len(f["elementer"])
        f["nytt"] = sum(1 for e in f["elementer"] if e["fersk"])
        f["elementer"] = f["elementer"][:MAKS_PER_FANE]
        ut.append(f)

    # Konkurser og nyåpninger først — det er det man kan ringe på i dag.
    # Deretter SSB-varslene, med den mest innholdsrike fanen først.
    rang = {"konkurser": 0, "nyapninger": 1}
    ut.sort(key=lambda f: (rang.get(f["slug"], 2), -f["antall"]))

    # Ideene sist, og alltid til slutt uansett hvor mange det er. Eieren
    # 26.07.2026: «den blir lagret paa en av fanene der det staar ideer til
    # Tobias.» Dette er den korteste veien fra «Mathias faar en idé mens han
    # bruker verktoyet» til «Tobias ser den» - uten den gaar ideen via
    # hukommelsen hans til en melding han kanskje sender.
    if ideer:
        ut.append({
            **IDEER,
            "slug": "ideer",
            "antall": len(ideer),
            # «Nytt» er det som ikke er lest. Da staar prikken der til Tobias
            # faktisk har sett den, i stedet for aa forsvinne av seg selv.
            "nytt": sum(1 for i in ideer if not i.get("lest")),
            "elementer": [
                # `id` blir en tekstnoekkel som resten av fanene bruker; det
                # numeriske rad-id-et maa derfor tas vare paa under et eget navn,
                # ellers har sletteknappen ingenting aa peke paa.
                {**i, "slag": "ide", "id": f"i:{i.get('id')}",
                 "ide_id": i.get("id"), "fersk": not i.get("lest")}
                for i in ideer
            ],
        })
    return ut
