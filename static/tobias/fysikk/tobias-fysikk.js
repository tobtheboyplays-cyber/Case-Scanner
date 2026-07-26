/* Inngangen til fysikk-Tobias: lerretet, loopen, pekeren og oppryddingen.
 *
 * Dette er laget som ERSTATTER `tobias.js` naar fysikkvarianten er paa. De to
 * kan ikke kjore samtidig - de ville tegnet hver sin robot.
 *
 * ## Forskjellen fra den gamle verten
 *
 * Den gamle Tobias bodde i en liten boks nede i hjornet med sitt eget kamera.
 * Denne dekker hele viewporten, fordi gulvet ER bunnen av vinduet (eieren §17)
 * og fordi han skal kunne kastes tvers over skjermen. Lerretet er
 * `pointer-events: none`, saa sida under er uberoert; det slaas bare paa i det
 * oyeblikket en straale faktisk treffer en kroppsdel.
 *
 * ## Om vekten, sagt rett ut
 *
 * Rapier er 2,0 MB og Three 0,67 MB. Det er mye for en paaskeegg-robot, og
 * derfor lastes ingenting av det for spawn-timeren har loept ut - er fanen
 * lukket eller brukeren gaatt videre, ble det aldri hentet. Paa mobil og ved
 * `prefers-reduced-motion` starter den ikke i det hele tatt; da er det den
 * lette animasjonsversjonen som gjelder. Se `boerFysikk()`.
 */

import {
  K, TOBIAS_ENABLED, erMobil, hastSpawn, roligBevegelse, tilfeldigFra,
} from "../konfig.js";
import { FYS } from "./konfig.js";

let instans = null;

/* Fysikkvarianten er for tung og for stor for en telefon: 2,7 MB nedlasting og
 * fjorten rigid bodies paa 120 Hz. Den er en desktop-godbit, og det er et
 * bevisst valg - ikke en glemt sak. */
export function boerFysikk() {
  return TOBIAS_ENABLED && !erMobil() && !roligBevegelse();
}

class FysikkTobias {
  constructor() {
    this.opprydd = [];
    this.kjorer = false;
    this.feil = 0;
    this.pekerNede = false;
    this.pekerId = null;
  }

  async init() {
    const lerret = document.createElement("canvas");
    lerret.className = "tobias-fysikk";
    document.body.appendChild(lerret);
    this.lerret = lerret;
    this.opprydd.push(() => lerret.remove());

    const THREE = await import("../three.module.js");
    const RAPIER = await import("../vendor/rapier.js");
    await RAPIER.init();
    const { Ragdoll } = await import("./ragdoll.js");
    const { Visning } = await import("./visning.js");
    const { Ansikt } = await import("../ansikt.js");
    const { Liv } = await import("./liv.js");

    this.bredde = innerWidth / FYS.pikslerPerMeter;
    this.rag = new Ragdoll(RAPIER, this.bredde);
    this.vis = new Visning(THREE, RAPIER, this.rag, Ansikt, K.farge);
    this.liv = new Liv(this.rag, this.bredde);

    this.renderer = new THREE.WebGLRenderer({
      alpha: true, antialias: true, powerPreference: "low-power",
    });
    this.renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 2));
    this.renderer.setSize(innerWidth, innerHeight, false);
    this.renderer.setClearColor(0x000000, 0);
    lerret.replaceWith(this.renderer.domElement);
    this.renderer.domElement.className = "tobias-fysikk";
    this.lerret = this.renderer.domElement;
    this.opprydd.push(() => this.lerret.remove());

    this._koblePeker();
    this._kobleVindu();

    /* Ett hektepunkt for nettlesertester og for eieren selv i konsollen. Det er
     * bare en referanse - ingen oppfoersel henger paa at den finnes. */
    window.__tobiasFysikk = this;
    this.opprydd.push(() => { delete window.__tobiasFysikk; });

    this.kjorer = true;
    this.forrige = performance.now();
    this._sloyfe = this._sloyfe.bind(this);
    requestAnimationFrame(this._sloyfe);
    return this;
  }

  /* ── Sloyfa ────────────────────────────────────────────────────────────── */

  _sloyfe(naa) {
    if (!this.kjorer) return;
    requestAnimationFrame(this._sloyfe);
    const dt = Math.min(0.05, (naa - this.forrige) / 1000);
    this.forrige = naa;

    try {
      this.liv.oppdater(dt);
      this.vis.ansikt.sett(this.liv.uttrykk);
      this.vis.ansikt.settBlunk(this.liv.blunk > 0 ? 1 : 0);

      /* Interpolasjon: fysikken gaar i faste 1/120-steg, skjermen tegner naar
       * den vil. `merkForrige` tas FOER stegene, saa `synk` har to punkter aa
       * legge meshene mellom. Uten det synes hvert steg som et lite rykk. */
      this.vis.merkForrige();
      this.rag.steg(dt);
      this.vis.synk();
      this.renderer.render(this.vis.scene, this.vis.kamera);
      this.feil = 0;

      /* Kastet helt ut av vinduet? Eieren §17: «Naar hele ragdollens bounding
       * box er utenfor: despawn.» Uten dette blir en robot som ble kastet for
       * hardt borte for godt, og journalisten sitter igjen med en tom side og
       * et lerret som simulerer fjorten kropper i det tomme rommet. */
      if (!this.pekerNede && this.rag.heltUtenfor(1.2)) this._komTilbake();
    } catch (e) {
      /* Tre paa rad, saa gir vi opp og rydder. En paaskeegg-robot skal aldri
       * kunne holde en journalist ute fra sidene sine ved aa kaste hver frame. */
      if (++this.feil >= 3) {
        console.warn("Tobias-fysikken stoppet:", e);
        this.dispose();
      }
    }
  }

  /* Han kommer tilbake etter en pause, et tilfeldig sted, og faller ned i
   * bildet. Ingen animasjon: kroppene flyttes til utgangsstillingen og
   * tyngdekraften gjor resten - derfor lander han ulikt hver gang. */
  _komTilbake() {
    if (this._venter) return;
    this._venter = true;
    this.rag.stoppGange();
    setTimeout(() => {
      this._venter = false;
      if (!this.kjorer) return;
      this.rag.plasser(0.6 + Math.random() * Math.max(0.2, this.bredde - 1.2), 0.9);
    }, 2200 + Math.random() * 3000);
  }

  /* ── Pekeren ───────────────────────────────────────────────────────────── */

  _koblePeker() {
    /* Staar han foran en knapp, vinner KNAPPEN. Uten denne sjekken kan et
     * museklikk paa «Godkjenn sak» ende med at journalisten griper en robot i
     * stedet for aa godkjenne saken sin - og en paaskeegg-robot som stjeler
     * arbeidsklikk er ikke morsom, den er i veien. */
    const KLIKKBART = "a, button, input, select, textarea, summary, label,"
      + " details, [role='button'], [tabindex]";
    const overKnapp = (x, y) => {
      const el = document.elementFromPoint(x, y);
      return !!(el && el.closest(KLIKKBART));
    };

    const ned = (e) => {
      if (!this.kjorer || this.pekerNede) return;
      if (overKnapp(e.clientX, e.clientY)) return;
      const del = this.vis.delUnder(e.clientX, e.clientY);
      if (!del) return;                       // ingen treff: sida faar klikket
      this.pekerNede = true;
      this.pekerId = e.pointerId;
      this.lerret.style.pointerEvents = "auto";
      this.lerret.setPointerCapture?.(e.pointerId);
      this.rag.stoppGange();
      this.rag.grip(del, this.vis.tilVerden(e.clientX, e.clientY));
      e.preventDefault();
    };

    const beveg = (e) => {
      if (!this.pekerNede || e.pointerId !== this.pekerId) return;
      this.rag.flyttGrep(this.vis.tilVerden(e.clientX, e.clientY), e.timeStamp);
      e.preventDefault();
    };

    const opp = (e) => {
      if (this.pekerNede && e.pointerId === this.pekerId) {
        this.pekerNede = false;
        this.lerret.releasePointerCapture?.(e.pointerId);
        this.lerret.style.pointerEvents = "none";
        this.rag.slipp();
      }
    };

    /* Hodet folger pekeren selv naar han ikke holdes. */
    const folg = (e) => {
      if (!this.kjorer) return;
      this.liv.seMot(this.vis.tilVerden(e.clientX, e.clientY));
    };

    /* `pointerdown` maa staa paa DOKUMENTET og ikke paa lerretet: lerretet er
     * `pointer-events: none` mens ingen holder ham, saa det ville aldri faatt
     * hendelsen i det hele tatt. Straalen avgjor om vi tar den. */
    document.addEventListener("pointerdown", ned, { passive: false });
    document.addEventListener("pointermove", beveg, { passive: false });
    document.addEventListener("pointermove", folg, { passive: true });
    document.addEventListener("pointerup", opp);
    document.addEventListener("pointercancel", opp);
    document.addEventListener("pointerleave", () => this.liv.seMot(null));
    this.opprydd.push(() => {
      document.removeEventListener("pointerdown", ned);
      document.removeEventListener("pointermove", beveg);
      document.removeEventListener("pointermove", folg);
      document.removeEventListener("pointerup", opp);
      document.removeEventListener("pointercancel", opp);
    });
  }

  _kobleVindu() {
    let timer = 0;
    const endret = () => {
      clearTimeout(timer);
      timer = setTimeout(() => {
        if (!this.kjorer) return;
        this.renderer.setSize(innerWidth, innerHeight, false);
        this.vis.settStorrelse(innerWidth, innerHeight);
        this.bredde = innerWidth / FYS.pikslerPerMeter;
        this.liv.bredde = this.bredde;
      }, 160);
    };
    addEventListener("resize", endret);
    /* Fanen i bakgrunnen: `requestAnimationFrame` stopper av seg selv, men
     * klokka gjor ikke det. Uten dette faar han ett kjempesteg naar man kommer
     * tilbake, og staar plutselig i motsatt ende av rommet. */
    const synlighet = () => { this.forrige = performance.now(); };
    document.addEventListener("visibilitychange", synlighet);
    this.opprydd.push(() => {
      removeEventListener("resize", endret);
      document.removeEventListener("visibilitychange", synlighet);
      clearTimeout(timer);
    });
  }

  dispose() {
    this.kjorer = false;
    for (const f of this.opprydd) { try { f(); } catch { /* rydder videre */ } }
    this.opprydd = [];
    this.vis?.fjern();
    this.rag?.fjern();
    this.renderer?.dispose();
    this.renderer?.forceContextLoss?.();
    instans = null;
  }
}

export async function monterFysikkTobias() {
  if (!boerFysikk() || instans) return null;
  /* Ingenting lastes for han faktisk skal komme. Er fanen lukket i mellomtida,
   * ble de 2,7 MB aldri hentet. */
  /* `?tobias=naa` henter ham med én gang. Samme luke som den lette varianten
   * bruker - uten den er hver eneste test 20-60 sekunder lang. */
  await new Promise((ok) =>
    setTimeout(ok, hastSpawn() ? 200 : tilfeldigFra(K.forsteSpawn)));
  if (instans) return null;
  instans = new FysikkTobias();
  return instans.init();
}

export function fjernFysikkTobias() {
  instans?.dispose();
}
