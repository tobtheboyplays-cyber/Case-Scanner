/* Dra og kast Tobias ut av skjermen.
 *
 * Eieren 26.07.2026: «Jeg vil ha en skjult interaksjon hvor brukeren kan kaste
 * Tobias ut av skjermen ... Hvis brukeren slipper Tobias med nok velocity skal
 * Tobias fysisk fly ut av skjermen.»
 *
 * ## Hvorfor farten maales over flere punkter
 *
 * Foerste tanke var aa bruke avstanden mellom de to siste `pointermove`-ene.
 * Det gir helt feil tall: nettleseren leverer bevegelser i klumper, og en pause
 * paa 4 ms rett foer slipp ville gjort en rolig bevegelse til et rakettkast.
 *
 * Her holdes en kort historikk (`SPOR_MS`), og farten regnes over hele vinduet.
 * Da er «kast» faktisk et kast, og «slipp» faktisk et slipp.
 */

import { K } from "./konfig.js";

const SPOR_MS = 90;          // hvor langt tilbake vi maaler farten
const MAKS_SPOR = 12;

export class Kastefysikk {
  constructor() {
    this.spor = [];          // [{t, x, y}]
    this.fartX = 0;
    this.fartY = 0;
    this.rotasjon = 0;
    this.vinkelfart = 0;
  }

  nullstill() {
    this.spor.length = 0;
    this.fartX = this.fartY = 0;
    this.rotasjon = this.vinkelfart = 0;
  }

  /* Kalles paa hver pointermove mens han dras. */
  spor_punkt(x, y, naa) {
    this.spor.push({ t: naa, x, y });
    while (this.spor.length > MAKS_SPOR
           || (this.spor.length > 2 && naa - this.spor[0].t > SPOR_MS)) {
      this.spor.shift();
    }
  }

  /* Fart i px/s over sporingsvinduet. */
  fart() {
    if (this.spor.length < 2) return { x: 0, y: 0 };
    const a = this.spor[0];
    const b = this.spor[this.spor.length - 1];
    const dt = (b.t - a.t) / 1000;
    if (dt < 0.008) return { x: 0, y: 0 };   // for kort til aa si noe
    return { x: (b.x - a.x) / dt, y: (b.y - a.y) / dt };
  }

  /* Er dette et kast, eller bare et slipp? */
  erKast() {
    const f = this.fart();
    return Math.hypot(f.x, f.y) > K.kastGrense;
  }

  /* Start flukten. Vinkelfarten kommer av den vannrette farten, saa han
   * snurrer i den retningen han faktisk ble kastet. */
  start() {
    const f = this.fart();
    this.fartX = f.x;
    this.fartY = f.y;
    this.rotasjon = 0;
    this.vinkelfart = (f.x / 260) + (Math.random() - 0.5) * 4;
  }

  /* Ett steg. Returnerer ny posisjon; kalleren flytter beholderen. */
  steg(dt, x, y) {
    this.fartY += K.tyngde * dt;
    this.fartX *= Math.pow(K.luftmotstand, dt * 60);
    this.fartY *= Math.pow(K.luftmotstand, dt * 60);
    this.rotasjon += this.vinkelfart * dt;
    return { x: x + this.fartX * dt, y: y + this.fartY * dt };
  }

  /* Ute av syne? Marginen er robotens egen stoerrelse, saa han er HELT ute
   * foer vi despawner - ikke halvveis synlig i kanten. */
  utenfor(x, y, bredde, hoyde, margin) {
    return x < -margin || x > bredde + margin
      || y < -margin || y > hoyde + margin;
  }
}
