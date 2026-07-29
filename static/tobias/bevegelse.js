/* Smaa matematiske hjelpere for animasjon.
 *
 * Eieren 26.07.2026: «Robotens bevegelser maa bruke easing, anticipation,
 * squash/stretch subtilt, overshoot, secondary motion. Dette skal ikke se ut
 * som en emoji-widget.»
 *
 * Det som skiller en levende figur fra en som bare flytter seg, er at delene
 * ikke stopper samtidig. Antenna henger etter kroppen, armene henger etter
 * torsoen. `Etterslep` under er hele det trikset: en verdi som joger mot en
 * maalverdi med treghet, i stedet for aa hoppe dit.
 */

export const klem = (v, lav, hoy) => Math.min(hoy, Math.max(lav, v));

export const bland = (a, b, t) => a + (b - a) * t;

/* Rammeuavhengig utjevning. `bland(a, b, 0.1)` per frame gir ulik fart paa 60
 * og 120 Hz; dette gir samme fart uansett. */
export const jevn = (a, b, fart, dt) => bland(a, b, 1 - Math.exp(-fart * dt));

/* ── Easing ───────────────────────────────────────────────────────────────── */

export const easeUtInn = (t) =>
  t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;

export const easeUt = (t) => 1 - Math.pow(1 - t, 3);

export const easeInn = (t) => t * t * t;

/* Skyter litt forbi og faller tilbake. Brukes naar han reiser seg og naar
 * armene kommer opp i dansen - en bevegelse som stopper helt eksakt paa
 * maalet ser mekanisk ut. */
export function easeOverskudd(t, styrke = 1.7) {
  const c = styrke + 1;
  return 1 + c * Math.pow(t - 1, 3) + styrke * Math.pow(t - 1, 2);
}

/* Anticipation: gaar LITT motsatt vei foerst. Uten dette ser et hopp ut som om
 * figuren blir dyttet, ikke som om den hopper selv. */
export function easeMedTilloep(t, tilloep = 0.12) {
  if (t < 0.25) return -tilloep * Math.sin((t / 0.25) * Math.PI);
  const u = (t - 0.25) / 0.75;
  return easeOverskudd(u, 1.2);
}

/* ── Etterslep: sekundaerbevegelse ────────────────────────────────────────── */

/* En verdi som foelger etter en annen med fjaerkraft og demping.
 *
 * Eieren: «Naar han stopper: kroppen stopper foerst, antennen beveger seg litt
 * videre.» Det er nettopp dette. Antenna faar en `Etterslep` som peker paa
 * kroppens rotasjon, med lav stivhet - saa svinger den videre av seg selv.
 */
export class Etterslep {
  constructor(verdi = 0, stivhet = 90, demping = 12) {
    this.verdi = verdi;
    this.fart = 0;
    this.stivhet = stivhet;
    this.demping = demping;
  }

  mot(maal, dt) {
    /* Halv-implisitt Euler. Stabil nok for de kreftene vi bruker, og billig. */
    const kraft = (maal - this.verdi) * this.stivhet - this.fart * this.demping;
    this.fart += kraft * dt;
    this.verdi += this.fart * dt;
    return this.verdi;
  }

  sett(verdi) {
    this.verdi = verdi;
    this.fart = 0;
  }
}

/* ── Squash & stretch ─────────────────────────────────────────────────────── */

/* Volumbevarende: strekker han seg oppover, blir han smalere. Gjor det gjor
 * uten dette ser han ut som en ballong som blaases opp. */
export function strekk(objekt, mengde) {
  const y = 1 + mengde;
  const xz = 1 / Math.sqrt(y);
  objekt.scale.set(xz, y, xz);
}

/* ── Tidsstyrt forloep ────────────────────────────────────────────────────── */

/* Et forloep som gaar fra 0 til 1 over en gitt tid, og sier fra naar det er
 * ferdig. Brukes av hver enkelt oppfoersel i stedet for at hver av dem holder
 * styr paa egne tellere. */
export class Forloep {
  constructor(lengde, easing = easeUtInn) {
    this.lengde = Math.max(1, lengde);
    this.easing = easing;
    this.gaatt = 0;
  }

  /* Returnerer eased 0..1. `ferdig` er sann fra og med det siste steget. */
  steg(dt) {
    this.gaatt = Math.min(this.lengde, this.gaatt + dt * 1000);
    return this.easing(this.gaatt / this.lengde);
  }

  get raa() {
    return this.gaatt / this.lengde;
  }

  get ferdig() {
    return this.gaatt >= this.lengde;
  }
}
