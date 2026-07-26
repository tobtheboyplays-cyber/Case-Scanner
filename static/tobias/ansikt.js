/* Ansiktet til Tobias: cyan oyne og munn paa et svart, blankt display.
 *
 * Eieren 26.07.2026 ba om sju uttrykk (NORMAL, BLINK, CURIOUS, SLEEP, PANIC,
 * SMUG, HAPPY) og skrev: «Ikke bruk bokstavelig tekst dersom det ser daarlig ut.
 * Lag oyne og munn som mesh/SVG/plane shapes.»
 *
 * ## Hvorfor lerret og ikke geometri
 *
 * Foerste tanke var en mesh per oye og en per munn, og saa skalere dem. Det gir
 * fine blunk, men et daarlig `^_^` - vinkler og buer blir en haug med
 * smaageometrier som maa holdes i sync.
 *
 * Her tegnes ansiktet i stedet én gang paa et 2D-lerret, som legges paa
 * displayet som tekstur. Da er hvert uttrykk noen linjer med `arc` og
 * `quadraticCurveTo`, og vi faar glod paa kjoepet med `shadowBlur`.
 *
 * ## Og hvorfor det ikke koster noe
 *
 * Eieren: «ikke skap nye Three.js-materialer hvert frame.» Lerretet tegnes
 * bare naar uttrykket FAKTISK endrer seg, eller mens et blunk paagaar - ikke
 * per frame. Teksturen og materialet lages én gang og gjenbrukes.
 */

const B = 256;              // lerretsstoerrelse, kvadratisk

export const UTTRYKK = {
  NORMAL: "NORMAL",
  BLINK: "BLINK",
  CURIOUS: "CURIOUS",
  SLEEP: "SLEEP",
  PANIC: "PANIC",
  SMUG: "SMUG",
  HAPPY: "HAPPY",
};

export class Ansikt {
  constructor(THREE, farge) {
    this.THREE = THREE;
    this.farge = farge;
    this.lerret = document.createElement("canvas");
    this.lerret.width = this.lerret.height = B;
    this.ctx = this.lerret.getContext("2d");

    this.tekstur = new THREE.CanvasTexture(this.lerret);
    this.tekstur.colorSpace = THREE.SRGBColorSpace;
    this.tekstur.anisotropy = 4;

    this.uttrykk = UTTRYKK.NORMAL;
    this._blunk = 0;          // 0 = aapne oyne, 1 = helt lukket
    this._skrev = null;       // siste tegnede tilstand, for aa slippe aa gjenta
    this.tegn();
  }

  /* Sett uttrykk. Er det samme som foer, gjor vi ingenting. */
  sett(uttrykk) {
    if (this.uttrykk === uttrykk) return;
    this.uttrykk = uttrykk;
    this.tegn();
  }

  /* 0..1. Kalles fra blunkelogikken i tilstandsmaskinen. */
  settBlunk(v) {
    const rundet = Math.round(v * 8) / 8;   // kvantiser: faerre tegninger
    if (rundet === this._blunk) return;
    this._blunk = rundet;
    this.tegn();
  }

  /* ── Selve tegningen ──────────────────────────────────────────────────── */

  tegn() {
    const noekkel = `${this.uttrykk}:${this._blunk}`;
    if (noekkel === this._skrev) return;
    this._skrev = noekkel;

    const c = this.ctx;
    c.clearRect(0, 0, B, B);

    const lys = "#" + this.farge.lys.toString(16).padStart(6, "0");
    c.strokeStyle = lys;
    c.fillStyle = lys;
    c.lineCap = "round";
    c.lineJoin = "round";
    /* Gloden er det som gjor at det ser ut som et display og ikke som maling. */
    c.shadowColor = lys;
    c.shadowBlur = 18;

    const u = this.uttrykk;
    /* Et paagaaende blunk overstyrer alt annet enn SLEEP, som allerede er
     * lukkede oyne. */
    const lukket = u === UTTRYKK.SLEEP ? 1 : this._blunk;

    if (u === UTTRYKK.PANIC) this._panikk(c);
    else if (u === UTTRYKK.SLEEP) this._sover(c);
    else if (u === UTTRYKK.SMUG) this._lurt(c, lukket);
    else if (u === UTTRYKK.HAPPY) this._glad(c, lukket);
    else if (u === UTTRYKK.CURIOUS) this._nysgjerrig(c, lukket);
    else this._normal(c, lukket);

    this.tekstur.needsUpdate = true;
  }

  /* Hjelper: et oye som lukker seg. `lukket` 0..1 klemmer hoyden. */
  _oye(c, x, y, r, lukket, bredde = 1) {
    const h = r * (1 - lukket);
    if (h < 1.5) {
      /* Helt lukket: en strek, ikke en flate. En sammenklemt ellipse ser ut
       * som en feil; en strek ser ut som et blunk. */
      c.lineWidth = 7;
      c.beginPath();
      c.moveTo(x - r * bredde, y);
      c.lineTo(x + r * bredde, y);
      c.stroke();
      return;
    }
    c.beginPath();
    c.ellipse(x, y, r * bredde, h, 0, 0, Math.PI * 2);
    c.fill();
  }

  /* ^_^ — normalt, vennlig. */
  _normal(c, lukket) {
    this._oye(c, 86, 106, 26, lukket);
    this._oye(c, 170, 106, 26, lukket);
    c.lineWidth = 9;
    c.beginPath();
    c.moveTo(104, 168);
    c.quadraticCurveTo(128, 190, 152, 168);
    c.stroke();
  }

  /* Store, glade oyne og bred munn. */
  _glad(c, lukket) {
    this._oye(c, 86, 104, 27, lukket, 1.05);
    this._oye(c, 170, 104, 27, lukket, 1.05);
    c.lineWidth = 11;
    c.beginPath();
    c.moveTo(94, 162);
    c.quadraticCurveTo(128, 200, 162, 162);
    c.stroke();
  }

  /* Ett oye stoerre. Hodet paa skraa gjores i modellen, ikke her. */
  _nysgjerrig(c, lukket) {
    this._oye(c, 86, 106, 18, lukket);
    this._oye(c, 170, 102, 27, lukket);
    c.lineWidth = 8;
    c.beginPath();
    c.arc(128, 172, 12, 0, Math.PI * 2);
    c.stroke();
  }

  /* -_- */
  _sover(c) {
    c.lineWidth = 8;
    for (const x of [88, 168]) {
      c.beginPath();
      c.moveTo(x - 22, 112);
      c.lineTo(x + 22, 112);
      c.stroke();
    }
    /* Liten «z» ved siden av. Diskret - ikke en emoji. */
    c.lineWidth = 6;
    c.beginPath();
    c.moveTo(196, 66); c.lineTo(216, 66); c.lineTo(196, 86); c.lineTo(216, 86);
    c.stroke();
    c.lineWidth = 9;
    c.beginPath();
    c.moveTo(112, 172);
    c.quadraticCurveTo(128, 166, 144, 172);
    c.stroke();
  }

  /* O_O — brukes naar han dras og naar han flyr. */
  _panikk(c) {
    c.lineWidth = 8;
    for (const x of [86, 170]) {
      c.beginPath();
      c.arc(x, 104, 25, 0, Math.PI * 2);
      c.stroke();
    }
    c.beginPath();
    c.ellipse(128, 176, 17, 22, 0, 0, Math.PI * 2);
    c.fill();
  }

  /* Skjevt lite smil. Han er ikke sint, bare litt fornaermet. */
  _lurt(c, lukket) {
    this._oye(c, 88, 110, 20, lukket, 1.15);
    /* Halvlukket hoyre oye: den skjeve delen av uttrykket. */
    this._oye(c, 168, 108, 20, Math.max(lukket, 0.45), 1.15);
    c.lineWidth = 9;
    c.beginPath();
    c.moveTo(102, 172);
    c.quadraticCurveTo(130, 186, 156, 164);
    c.stroke();
  }

  fjern() {
    this.tekstur.dispose();
  }
}
