/* Tobias — en liten robot som bor nederst paa sida. Konfigurasjon og tuning.
 *
 * Eieren 26.07.2026: «Implementer en komplett, produksjonsklar Easter
 * Egg-feature: en liten 3D robotassistent som heter Tobias.»
 *
 * ── To avvik fra spec-en, begge bevisste ────────────────────────────────────
 *
 * 1. INGEN REACT. Spec-en sier «bruk React Three Fiber DERSOM prosjektet
 *    allerede bruker React». Case-radar er FastAPI + Jinja2 + vanilla JS, uten
 *    npm og uten byggsteg. Samme arkitektur og oppfoersel er derfor bygget i
 *    rene ES-moduler mot Three.js direkte.
 *
 * 2. THREE.JS LASTES FOERST NAAR TOBIAS SKAL INN. Biblioteket er 670 kB, og
 *    Mathias bruker verktoyet paa 5G i felt. `import()` skjer derfor foerst
 *    naar spawn-timeren loeper ut - og aldri i det hele tatt ved
 *    `prefers-reduced-motion` eller naar flagget er av. Selve skannet er
 *    uberoert.
 *
 * Alt som kan trenge justering staar her, og bare her.
 */

/* Hovedbryteren. Én linje slaar hele greia av. */
export const TOBIAS_ENABLED = true;

/* Debugpanel med tilstand, humoer, posisjon og knapper. */
export const TOBIAS_DEBUG = false;

export const K = {
  /* ── Stoerrelse ──────────────────────────────────────────────────────── */
  hoyde: { desktop: 132, mobil: 92 },   // px, roboten selv
  /* Lerretet er bredere enn roboten fordi stolen skal faa plass ved siden av. */
  lerret: { bredde: 1.7, hoyde: 1.5 },  // multiplum av robothoyden

  /* ── Naar han kommer ─────────────────────────────────────────────────── */
  forsteSpawn: [20000, 60000],          // ms, tilfeldig i intervallet
  respawnEtterKast: [30000, 120000],

  /* ── Gulvet ──────────────────────────────────────────────────────────── */
  /* Eieren 26.07.2026: «Vi sier at det er gulvet ... saa kan den gaa over hele
   * skjermen paa en tenkt linje som er gulvet.»
   *
   * ÉN linje, ikke et baand. Foer dette fikk han en tilfeldig y i intervallet
   * 0.80-0.94 hver gang han kom inn, og da saa det ut som om han svevde i ulike
   * hoyder - ikke som om han gikk paa noe. Linja er usynlig, men den er den
   * samme hele tiden, og det er nok til at oyet leser den som et gulv. */
  gulv: 0.90,

  /* Hvor naer kantene han faar gaa. Liten margin: eieren ba om at han skal gaa
   * over HELE skjermen. */
  gaaMargin: 0.22,          // andel av lerretsbredden

  /* ── Landing ─────────────────────────────────────────────────────────── */
  /* Kastes han opp, skal han falle ned igjen og lande - ikke forsvinne.
   * Eieren: «saa er det physics saa du ser fallet og slik, ikke bare at han
   * teleporterer tilbake.» */
  /* Eieren 26.07.2026: «Vil ha Clumsy ninja physics.»
   *
   * Det betyr tre ting, og alle tre staar her: han SPRETTER flere ganger i
   * stedet for aa stoppe doedt, han TUMLER videre mens han spretter, og
   * lemmene henger etter kroppen i stedet for aa foelge den.
   *
   * Foerste utkast hadde sprett 0.42 og friksjon 0.68 - da stoppet han etter
   * ett halvhjertet hopp. Naa beholder han over halve farten, og gulvfriksjonen
   * er lav nok til at han sklir og ruller et stykke. */
  sprett: 0.56,             // hvor mye fart han beholder i et sprett
  friksjon: 0.82,           // vannrett fart som overlever et sprett
  spinnBrems: 0.90,         // hvor mye av rotasjonen som overlever
  landeGrense: 120,         // px/s - under dette blir han endelig liggende

  /* ── Fart ────────────────────────────────────────────────────────────── */
  gangfart: 46,                         // px/s, rolig
  gangfartMobil: 34,
  snufart: 7,                           // rad/s naar han snur seg

  /* ── Kast ────────────────────────────────────────────────────────────── */
  kastGrense: 820,                      // px/s - over dette slipper han taket
  tyngde: 2600,                         // px/s^2
  luftmotstand: 0.999,

  /* ── Timing ──────────────────────────────────────────────────────────── */
  seLengde: [2000, 4000],               // «ser ut av skjermen»
  sitteLengde: [5000, 15000],
  kantLengde: [3000, 6000],
  dansLengde: [3000, 5000],
  hendelsePause: [6000, 16000],         // ro mellom hendelser
  klikkPause: 4000,                     // cooldown paa klikkreaksjon

  /* ── Vekter for tilfeldige hendelser ─────────────────────────────────── */
  /* Maalet, med eierens ord: «brukeren glemmer nesten at Tobias finnes, og saa
   * gjor han plutselig noe morsomt.» Derfor er `idle` og `walk` tunge. */
  vekter: [
    { type: "walk", vekt: 40 },
    { type: "look", vekt: 20 },
    { type: "idle", vekt: 17 },
    { type: "sit", vekt: 10 },
    { type: "edge", vekt: 10 },
    { type: "dance", vekt: 3 },
  ],

  /* ── Farger ──────────────────────────────────────────────────────────── */
  farge: {
    kropp: 0xf2f1ee,        // off-white
    kroppSkygge: 0xd8d6d1,
    ledd: 0x9aa0a6,
    skjerm: 0x0d1014,       // svart, blankt ansiktsdisplay
    lys: 0x4fd6ff,          // cyan oyne og munn
    stol: 0x24272c,
    stolMetall: 0x8b9096,
  },
};

/* Mobil = smal skjerm ELLER grovt pekeverktoy. Begge deler betyr «mindre og
 * roligere», og de opptrer ikke alltid sammen (nettbrett). */
export function erMobil() {
  return window.matchMedia("(max-width: 620px), (pointer: coarse)").matches;
}

/* Respekteres uten unntak: ingen gange, ingen fysikk, ingen kast. */
export function roligBevegelse() {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/* `?tobias=naa` hopper over ventetiden. Uten den ville hver nettlesertest
 * brukt et minutt paa aa komme i gang, og da blir den ikke kjort. Den er ogsaa
 * den eneste maaten aa se ham paa naar man jobber med koden.
 *
 * Ikke en bakdoer: den forkorter bare en timer, og gjor ingenting annet. */
export function hastSpawn() {
  try {
    const v = new URLSearchParams(location.search).get("tobias");
    return v === "naa" || v === "nå" || v === "now";
  } catch {
    return false;
  }
}

export function tilfeldig(fra, til) {
  return fra + Math.random() * (til - fra);
}

export function tilfeldigFra(par) {
  return tilfeldig(par[0], par[1]);
}

export function velgVektet(liste) {
  const sum = liste.reduce((a, x) => a + x.vekt, 0);
  let n = Math.random() * sum;
  for (const x of liste) {
    n -= x.vekt;
    if (n <= 0) return x.type;
  }
  return liste[liste.length - 1].type;
}
