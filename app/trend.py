"""Trendlinje: «tredje kvartal paa rad at tallet faller».

Eieren 26.07.2026. Og forskjellen er ikke kosmetisk - den er journalistisk:

    «Godkjente boliger falt 17 %»            -> en notis
    «Tredje kvartal paa rad at de faller»    -> en sak man ringer paa

Vi hadde allerede tallene. De ble bare kastet mellom hvert skann: `seen.verdi`
husket SISTE avtrykk, fordi den skal svare paa «er dette nytt eller det samme?».
Her lagres selve TALLET per PERIODE i stedet (app.storage.lagre_maalinger), og
denne modulen leser historikken tilbake.

Tre regler, og alle tre er der for aa hindre at linja lyver:

1. **Perioden er noekkelen, ikke skanntidspunktet.** Skanner journalisten fem
   ganger paa en tirsdag, er det fortsatt ETT punkt for 2026K1. Ellers ville
   linja beskrevet hvor ofte han trykket paa knappen.
2. **Bare sammenlignbare perioder.** 2026K1 og 2026 er ikke punkter paa samme
   linje. Blandes de, gaar linja opp og ned av ren formatforskjell.
3. **«Paa rad» krever at det faktisk er paa rad.** Ett hopp i feil retning
   nullstiller telleren. En «trend» som taaler unntak er ikke en trend.
"""

from __future__ import annotations

import re

# Minst tre punkter for aa i det hele tatt tegne noe. To punkter er en endring,
# ikke en utvikling - og en linje mellom to prikker ser ut som mer enn den er.
MIN_PUNKTER = 3

_PERIODE = re.compile(r"\b(\d{4})(?:\s*([KkQq])\s*([1-4])|\s*[Mm]\s*(0?[1-9]|1[0-2]))?\b")

ORDENSTALL = {
    2: "Andre", 3: "Tredje", 4: "Fjerde", 5: "Femte", 6: "Sjette",
    7: "Sjuende", 8: "Aattende", 9: "Niende", 10: "Tiende",
}


def periode_av(tekst: str) -> str:
    """«2026K2 mot 2025K2» -> «2026K2». Tom streng naar det ikke finnes noen.

    Vi tar den FOERSTE perioden i strengen, som er den maalingen gjelder -
    resten er sammenligningsgrunnlaget. Uten dette ville «2026K2 mot 2025K2»
    like gjerne blitt lagret som 2025K2, og linja hadde gaatt bakover i tid.
    """
    m = _PERIODE.search(tekst or "")
    if not m:
        return ""
    aar, _, kvartal, maaned = m.groups()
    if kvartal:
        return f"{aar}K{kvartal}"
    if maaned:
        return f"{aar}M{int(maaned):02d}"
    return aar


def serie_av(key: str, periode: str) -> str:
    """Noekkelen til SERIEN, ikke til denne ene maalingen.

    Dette er den ene tingen hele trendlinja staar og faller paa, og den er lett
    aa gaa glipp av: sakens noekkel inneholder perioden.

        ssb-sok:05889:1103:2026K1     <- foerste kvartal
        ssb-sok:05889:1103:2026K2     <- neste kvartal, NY noekkel

    Lagrer vi historikken under sakens noekkel, faar hver periode sin egen bod
    med noeyaktig ett punkt i, og det blir aldri en linje. Serien er det som er
    igjen naar perioden er strippet bort - tabell + region.

    Fant vi ingen periode i noekkelen, staar den urort: brreg-hendelser og
    grasrot har stabile noekler fra foer.
    """
    hale = f":{periode}"
    return key[: -len(hale)] if periode and key.endswith(hale) else key


def tall_av(tekst: str) -> float | None:
    """«+42,0 %» -> 42.0. «4 125 952 kr» -> 4125952.0. «2026-07-17» -> None.

    En dato er ikke en maaling. Konkurser har dato i `metric_value`, og en linje
    gjennom datoer ville vaert en linje gjennom kalenderen - alltid stigende, og
    alltid meningsloes.
    """
    raa = (tekst or "").strip()
    if not raa or re.match(r"^\d{4}-\d{2}-\d{2}", raa):
        return None
    # Norske tall: mellomrom (ogsaa hardt) som tusenskille, komma som desimal.
    ryddet = raa.replace(" ", "").replace(" ", "").replace(",", ".")
    m = re.search(r"[-+]?\d+(?:\.\d+)?", ryddet)
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:
        return None


def _enhet(perioder: list[str]) -> str:
    if all("K" in p for p in perioder):
        return "kvartal"
    if all("M" in p for p in perioder):
        return "maaned"
    return "aar"


def _sammenlignbare(punkter: list[tuple[str, float]]) -> list[tuple[str, float]]:
    """Behold bare perioder av SAMME type, og bare de nyeste av dem.

    En tabell kan bytte fra aarstall til kvartal. Da er ikke «2024, 2025, 2026K1»
    en linje - det er to serier tegnet oppaa hverandre."""
    if not punkter:
        return []
    form = "K" if "K" in punkter[-1][0] else ("M" if "M" in punkter[-1][0] else "aar")

    def passer(p: str) -> bool:
        return ("K" in p) if form == "K" else ("M" in p) if form == "M" else (
            "K" not in p and "M" not in p
        )

    return [(p, v) for p, v in punkter if passer(p)]


def beregn(punkter: list[tuple[str, float]]) -> dict | None:
    """{punkter, retning, antall, tekst, enhet} - eller None naar det ikke er nok.

    `antall` teller PERIODER i samme retning, ikke endringer: tre punkter som
    stiger er «tredje kvartal paa rad», slik en journalist ville sagt det.
    """
    rene = _sammenlignbare(sorted(punkter))
    if len(rene) < MIN_PUNKTER:
        return None

    verdier = [v for _, v in rene]
    # Tell bakover fra siste punkt saa lenge retningen holder seg.
    retning = 0
    lengde = 1
    for i in range(len(verdier) - 1, 0, -1):
        steg = verdier[i] - verdier[i - 1]
        if steg == 0:
            break
        naa = 1 if steg > 0 else -1
        if retning == 0:
            retning = naa
        elif naa != retning:
            break
        lengde += 1

    enhet = _enhet([p for p, _ in rene])
    ut = {
        "punkter": [[p, v] for p, v in rene],
        "retning": "opp" if retning > 0 else "ned" if retning < 0 else "flat",
        "antall": lengde,
        "enhet": enhet,
        "tekst": "",
    }
    # «Paa rad» sies bare naar det er noe aa si. To perioder er en endring, og
    # aa kalle den en trend ville vaert aa selge inn en sak som ikke finnes.
    if lengde >= MIN_PUNKTER and retning != 0:
        ord_ = ORDENSTALL.get(lengde, f"{lengde}.")
        vei = "oppgang" if retning > 0 else "nedgang"
        ut["tekst"] = f"{ord_} {enhet} på rad med {vei}"
    return ut


def sti(punkter: list[list], bredde: int = 96, hoyde: int = 24) -> str:
    """SVG-punktliste for en sparkline. Tom streng naar den ikke kan tegnes.

    Ingen akser, ingen tall, ingen rutenett: linja er et FORM-signal ved siden
    av tallet som allerede staar der med full presisjon. Tegner vi et diagram,
    later vi som om tre punkter er en analyse."""
    verdier = [float(v) for _, v in punkter]
    if len(verdier) < 2:
        return ""
    lav, hoy = min(verdier), max(verdier)
    spenn = (hoy - lav) or 1.0
    steg = bredde / (len(verdier) - 1)
    # y speiles: SVG har null oeverst, og en stigende serie skal peke oppover.
    return " ".join(
        f"{i * steg:.1f},{hoyde - (v - lav) / spenn * hoyde:.1f}"
        for i, v in enumerate(verdier)
    )
