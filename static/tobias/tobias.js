/* Tobias — hovedmodulen. Scene, sloyfe, hendelser, peker og opprydding.
 *
 * Eieren 26.07.2026: «Implementer en komplett, produksjonsklar Easter
 * Egg-feature ... en liten 3D robotassistent som heter Tobias.»
 *
 * ## Hvordan han beveger seg
 *
 * Roboten staar stille i sitt eget lille lerret; det er LERRETET som flyttes
 * rundt paa skjermen med `transform: translate3d`. Eieren ba om nettopp det
 * («et lite transparent canvas som beveges rundt skjermen»), og det er ogsaa
 * det raskeste: ingen relayout, ingen scrollbars, og et 3D-kamera som aldri
 * trenger aa flytte seg.
 *
 * ## Hva som er gjort for at han ikke skal koste noe
 *
 *   · Three.js importeres foerst naar spawn-timeren loeper ut - ikke ved
 *     sidelast. Er flagget av eller `prefers-reduced-motion` paa, lastes den
 *     aldri.
 *   · `requestAnimationFrame` stoppes HELT naar han er skjult, og naar fanen
 *     ikke er synlig (Page Visibility API).
 *   · Materialer og teksturer lages én gang. Ansiktet tegnes bare naar
 *     uttrykket faktisk endrer seg.
 *   · `dispose()` river alt: geometri, materialer, teksturer, WebGL-konteksten,
 *     timere og lyttere.
 */

import {
  K, TOBIAS_DEBUG, TOBIAS_ENABLED, erMobil, hastSpawn, roligBevegelse,
  tilfeldig, tilfeldigFra, velgVektet,
} from "./konfig.js";
import { jevn, klem } from "./bevegelse.js";
import { Kastefysikk } from "./fysikk.js";
import { HUMOER, Oppforsel } from "./tilstander.js";
import { UTTRYKK } from "./ansikt.js";

let instans = null;

class Tobias {
  constructor(THREE) {
    this.THREE = THREE;
    this.mobil = erMobil();
    this.rolig = roligBevegelse();
    this.lever = true;
    this.kjorer = false;
    this.timere = new Set();
    this.opprydd = [];

    this._byggDom();
    this._byggScene();
    this._koblePeker();
    this._kobleVindu();

    this.fysikk = new Kastefysikk();
    this.sisteKlikk = 0;
    this.sisteMus = 0;
    this.forrigeTid = 0;
    this.koe = null;

  }

  /* Modellene lastes etter konstruktoeren, fordi importen er asynkron.
   * Foerste utkast kalte `_byggScene()` to ganger og bygde `Oppforsel` paa
   * nytt i `monterTobias` - en halvferdig konstruktoer som saa ut til aa virke.
   * Her er skillet eksplisitt: `new` setter opp alt synkront, `init()` henter
   * modellene og starter klokka. */
  async init() {
    const { byggRobot, byggStol } = await import("./modell.js");
    this.robot = byggRobot(this.THREE, K.farge);
    this.stol = byggStol(this.THREE, K.farge);
    this.scene.add(this.robot.rot);
    this.scene.add(this.stol.rot);
    this.robot.rot.visible = false;

    this.oppf = new Oppforsel(this.robot, this.stol, {
      bredde: innerWidth, hoyde: innerHeight,
      mobil: this.mobil, rolig: this.rolig, robotBredde: this.bredde,
    });
    this.oppf.startHidden();

    if (TOBIAS_DEBUG) this._byggDebug();
    this._planlegg(hastSpawn() ? 300 : tilfeldigFra(K.forsteSpawn),
                   () => this._entre());
    return this;
  }

  /* ── DOM ────────────────────────────────────────────────────────────────── */

  _byggDom() {
    const h = this.mobil ? K.hoyde.mobil : K.hoyde.desktop;
    this.hoydePx = h;
    this.bredde = Math.round(h * K.lerret.bredde);
    this.hoyde = Math.round(h * K.lerret.hoyde);

    const boks = document.createElement("div");
    boks.className = "tobias";
    boks.setAttribute("aria-hidden", "true");   // ren pynt; ingen skal hoere den
    boks.style.width = this.bredde + "px";
    boks.style.height = this.hoyde + "px";
    boks.hidden = true;

    const merke = document.createElement("span");
    merke.className = "tobias-merke";
    merke.textContent = "Botias";
    boks.appendChild(merke);

    const boble = document.createElement("span");
    boble.className = "tobias-boble";
    boble.hidden = true;
    boks.appendChild(boble);

    document.body.appendChild(boks);
    this.boks = boks;
    this.merke = merke;
    this.boble = boble;
    this.opprydd.push(() => boks.remove());
  }

  /* ── Three.js ───────────────────────────────────────────────────────────── */

  _byggScene() {
    const T = this.THREE;
    this.scene = new T.Scene();

    /* Kameraet ser roboten litt fra siden og litt ovenfra - nok til at formen
     * leses som 3D, lite nok til at ansiktet peker mot brukeren. */
    this.kamera = new T.PerspectiveCamera(
      30, this.bredde / this.hoyde, 0.1, 20);
    this.kamera.position.set(0.55, 0.85, 3.4);
    this.kamera.lookAt(0, 0.52, 0);

    this.scene.add(new T.HemisphereLight(0xdfe8ff, 0x2a2f3a, 1.55));
    const sol = new T.DirectionalLight(0xffffff, 1.5);
    sol.position.set(2.2, 3.4, 2.6);
    this.scene.add(sol);
    /* Kantlys i cyan: binder roboten til displayfargen sin. */
    const kant = new T.DirectionalLight(K.farge.lys, 0.55);
    kant.position.set(-2.4, 1.0, -1.4);
    this.scene.add(kant);

    this.renderer = new T.WebGLRenderer({
      alpha: true, antialias: !this.mobil, powerPreference: "low-power",
    });
    this.renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 2));
    this.renderer.setSize(this.bredde, this.hoyde, false);
    this.renderer.setClearColor(0x000000, 0);
    this.renderer.domElement.className = "tobias-lerret";
    this.boks.appendChild(this.renderer.domElement);
  }

  /* ── Peker: klikk, dra, kast ────────────────────────────────────────────── */

  _koblePeker() {
    /* Selve lerretet er `pointer-events: none` som standard, saa sida under er
     * uberoert. Naar han er synlig, slaas det midlertidig paa - eieren:
     * «Interaktive Tobias-elementer kan midlertidig faa pointer-events: auto.» */
    const ned = (e) => {
      if (!this.synlig() || this.rolig) return;
      this.drar = true;
      this.dragId = e.pointerId;
      this.boks.setPointerCapture?.(e.pointerId);
      this.fysikk.nullstill();
      this.fysikk.spor_punkt(e.clientX, e.clientY, performance.now());
      this._dragStart = performance.now();
      this._flyttet = 0;
      this.oppf.startDrag();
      this.boks.classList.add("tobias-dras");
      e.preventDefault();
    };

    const beveg = (e) => {
      if (!this.drar || e.pointerId !== this.dragId) return;
      const naa = performance.now();
      const forrige = this.fysikk.spor[this.fysikk.spor.length - 1];
      if (forrige) {
        this._flyttet += Math.hypot(e.clientX - forrige.x, e.clientY - forrige.y);
      }
      this.fysikk.spor_punkt(e.clientX, e.clientY, naa);
      this.x = e.clientX;
      this.y = e.clientY;
      e.preventDefault();
    };

    const opp = (e) => {
      if (!this.drar || e.pointerId !== this.dragId) return;
      this.drar = false;
      this.boks.releasePointerCapture?.(e.pointerId);
      this.boks.classList.remove("tobias-dras");

      /* Et KLIKK er kort og uten bevegelse. Alt annet er et slipp. */
      const kort = performance.now() - this._dragStart < 320;
      if (kort && this._flyttet < 10) {
        this._klikk();
        return;
      }
      if (this.fysikk.erKast()) {
        this._kast();
        return;
      }
      /* Sluppet uten fart: han faller ned i baandet sitt og gaar videre. */
      this.oppf.settUttrykk(this.oppf.hvileUttrykk());
      this._nesteHendelse(600);
    };

    this.boks.addEventListener("pointerdown", ned);
    addEventListener("pointermove", beveg, { passive: false });
    addEventListener("pointerup", opp);
    addEventListener("pointercancel", opp);
    this.opprydd.push(() => {
      this.boks.removeEventListener("pointerdown", ned);
      removeEventListener("pointermove", beveg);
      removeEventListener("pointerup", opp);
      removeEventListener("pointercancel", opp);
    });

    /* Mye musebevegelse naer Tobias -> nysgjerrig. */
    const naerhet = (e) => {
      if (!this.synlig() || this.drar) return;
      const d = Math.hypot(e.clientX - this.x, e.clientY - this.y);
      if (d < this.bredde * 0.9) {
        this.sisteMus = performance.now();
        if (this.oppf.humoer !== HUMOER.ANNOYED) {
          this.oppf.settHumoer(HUMOER.CURIOUS);
        }
      }
    };
    if (!this.mobil) {
      addEventListener("pointermove", naerhet, { passive: true });
      this.opprydd.push(() => removeEventListener("pointermove", naerhet));
    }
  }

  _kobleVindu() {
    const endret = () => {
      /* Eieren: «Clamp posisjon mot viewport. Haandter resize.» */
      if (this.oppf) {
        this.oppf.v.bredde = innerWidth;
        this.oppf.v.hoyde = innerHeight;
      }
      this._klem();
    };
    const synlighet = () => {
      /* Page Visibility: ingen frames i en fane ingen ser paa. */
      if (document.hidden) this._stopp();
      else if (this.synlig()) this._start();
    };
    addEventListener("resize", endret, { passive: true });
    document.addEventListener("visibilitychange", synlighet);
    this.opprydd.push(() => {
      removeEventListener("resize", endret);
      document.removeEventListener("visibilitychange", synlighet);
    });
  }

  /* ── Sloyfa ─────────────────────────────────────────────────────────────── */

  _start() {
    if (this.kjorer || !this.lever) return;
    this.kjorer = true;
    this.forrigeTid = performance.now();
    const steg = (naa) => {
      if (!this.kjorer) return;
      /* Klem dt: en fane som har ligget i bakgrunnen gir et enormt sprang, og
       * da ville fysikken sende ham i bane. */
      const dt = Math.min(0.05, (naa - this.forrigeTid) / 1000);
      this.forrigeTid = naa;
      /* Et Easter Egg skal aldri kunne velte sida - og en feil i én frame skal
       * heller ikke drepe ham for godt. Kastet `_frame` foer dette, stoppet
       * sloyfa umiddelbart og Tobias frøs midt i en bevegelse. Naa logges
       * feilen, og han rydder seg selv bort etter tre paa rad i stedet for aa
       * spinne paa en feil sekstig ganger i sekundet. */
      try {
        this._frame(dt);
        this._feil = 0;
      } catch (e) {
        this._feil = (this._feil || 0) + 1;
        console.warn("Tobias:", e);
        if (this._feil >= 3) { this.dispose(); return; }
      }
      this.ramme = requestAnimationFrame(steg);
    };
    this.ramme = requestAnimationFrame(steg);
  }

  _stopp() {
    this.kjorer = false;
    if (this.ramme) cancelAnimationFrame(this.ramme);
    this.ramme = 0;
  }

  _frame(dt) {
    const o = this.oppf;

    if (o.tilstand === "dragged") {
      const f = this.fysikk.fart();
      o.settDragfart(f.x, f.y);
      o.oppdater(dt);
    } else if (o.tilstand === "thrown") {
      const p = this.fysikk.steg(dt, this.x, this.y);
      this.x = p.x; this.y = p.y;
      /* Lemmene skal reagere paa kroppens FAKTISKE fart, ikke paa en klokke. */
      o.settKastfart(this.fysikk.fartX, this.fysikk.fartY, this.fysikk.vinkelfart);
      o.oppdater(dt);

      /* GULVET. Kastes han opp, faller han ned igjen og lander - han skal ikke
       * forsvinne bare fordi han passerte nederste skjermkant. */
      const gulv = this._gulvY();
      if (this.y >= gulv && this.fysikk.fartY > 0) {
        this.y = gulv;
        if (this.fysikk.land(K.sprett, K.friksjon, K.spinnBrems, K.landeGrense)) {
          this._landing();
          return;
        }
      }
      /* Ut til SIDEN er det eneste som teller som borte. */
      if (this.fysikk.utenfor(this.x, innerWidth, Math.max(this.bredde, this.hoyde))) {
        this._despawn();
        return;
      }
    } else if (o.tilstand === "landet") {
      /* Rotasjonen fra flukten roteres tilbake til rett opp mens han reiser
       * seg. Uten dette ble han staaende paa skakke resten av oekten. */
      this.fysikk.rotasjon = jevn(this.fysikk.rotasjon, 0, 6, dt);
      this.y = jevn(this.y, this._gulvY(), 12, dt);
      if (o.oppdater(dt)) {
        this.fysikk.rotasjon = 0;
        this._nesteHendelse(1200);
      }
    } else {
      const ferdig = o.oppdater(dt);
      this.x = o.x;
      this.y = o.y;
      if (ferdig) this._hendelseFerdig();
    }

    /* Soevnig etter lang ro; ikke lenger nysgjerrig naar musa har vaert borte. */
    if (o.humoer === HUMOER.CURIOUS && performance.now() - this.sisteMus > 6000) {
      o.settHumoer(HUMOER.HAPPY);
    }

    this._klem();
    this._tegn();
    this.renderer.render(this.scene, this.kamera);
    if (this.debug) this._debugTekst();
  }

  /* Posisjonen skrives ut med transform - aldri med top/left, som ville
   * tvunget layout og kunne laget scrollbars. */
  _tegn() {
    /* Rotasjonen gjelder ogsaa mens han reiser seg - da roteres den tilbake. */
    const snurrer = this.oppf.tilstand === "thrown"
      || this.oppf.tilstand === "landet";
    const rot = snurrer ? `rotate(${this.fysikk.rotasjon}rad)` : "";
    this.boks.style.transform =
      `translate3d(${Math.round(this.x - this.bredde / 2)}px,` +
      `${Math.round(this.y - this.hoyde / 2)}px,0) ${rot}`;
  }

  /* Holder ham innenfor skjermen og innenfor sitt eget baand. Under kast og
   * kantkikk faar han bevisst lov til aa gaa utenfor. */
  /* Gulvlinja. Én y-verdi for hele oekten, ikke et baand - eieren 26.07.2026:
   * «en tenkt linje som er gulvet». */
  _gulvY() {
    return innerHeight * K.gulv;
  }

  _klem() {
    if (!this.oppf) return;
    const fri = this.oppf.tilstand === "thrown"
      || this.oppf.tilstand === "landet"
      || this.oppf.tilstand === "edge" || this.drar;
    if (fri) return;
    const halv = this.bredde * K.gaaMargin;
    this.x = klem(this.x, halv, innerWidth - halv);
    /* Foettene blir paa gulvet. */
    this.y = this._gulvY();
    this.oppf.x = this.x;
    this.oppf.y = this.y;
  }

  /* Han landet og blir liggende et oyeblikk foer han reiser seg. */
  _landing() {
    this.y = this._gulvY();
    this.fysikk.fartX = this.fysikk.fartY = 0;
    this.fysikk.vinkelfart = 0;
    this.oppf.x = this.x;
    this.oppf.startLandet();
  }

  /* ── Hendelser ──────────────────────────────────────────────────────────── */

  _planlegg(ms, fn) {
    const id = setTimeout(() => { this.timere.delete(id); fn(); }, ms);
    this.timere.add(id);
    return id;
  }

  _entre() {
    if (!this.lever) return;
    const fraVenstre = Math.random() < 0.5;
    this.x = fraVenstre ? -this.bredde * 0.4 : innerWidth + this.bredde * 0.4;
    this.y = this._gulvY();
    this.oppf.x = this.x;
    this.oppf.y = this.y;
    this.boks.hidden = false;
    this.boks.classList.add("tobias-inne");
    this.oppf.startEntre(fraVenstre);
    this._start();
  }

  _despawn() {
    this._stopp();
    this.boks.hidden = true;
    this.boks.classList.remove("tobias-inne");
    this.oppf.startHidden();
    for (const t of this.timere) clearTimeout(t);
    this.timere.clear();
    /* Etter et kast er han fornaermet naar han kommer tilbake. */
    this.oppf.settHumoer(HUMOER.ANNOYED);
    this._planlegg(tilfeldigFra(K.respawnEtterKast), () => this._entreIgjen());
  }

  _entreIgjen() {
    this._entre();
    /* Eieren: «Naar han senere kommer tilbake kan han gaa sakte inn, se litt
     * irritert ut, ha smug face.» Og: «Ikke gjor dette hver gang.» */
    this.oppf.settUttrykk(UTTRYKK.SMUG);
    if (Math.random() < 0.25) {
      this._si(Math.random() < 0.5 ? "seriøst?" : "😐", 2600);
    }
  }

  _kast() {
    this.fysikk.start();
    this.oppf.startThrown();
  }

  _klikk() {
    const naa = performance.now();
    if (naa - this.sisteKlikk < K.klikkPause) return;
    this.sisteKlikk = naa;
    const hva = ["vink", "blink", "hopp", "haand", "dans", "smug"][
      Math.floor(Math.random() * 6)];
    if (hva === "dans") this.oppf.startDance();
    else this.oppf.startReaksjon(hva);
  }

  _hendelseFerdig() {
    this._nesteHendelse(tilfeldigFra(K.hendelsePause));
  }

  _nesteHendelse(pause) {
    /* Ro mellom hendelsene er hele poenget. Eieren: «brukeren glemmer nesten at
     * Tobias finnes, og saa gjor han plutselig noe morsomt.» */
    this.oppf.startIdle(pause);
    if (this.koe) clearTimeout(this.koe);
    this.koe = this._planlegg(pause, () => this._velgHendelse());
  }

  _velgHendelse() {
    if (!this.lever || !this.synlig()) return;
    if (this.rolig) { this.oppf.startIdle(20000); return; }

    /* Paa mobil: faerre og roligere hendelser. */
    const vekter = this.mobil
      ? K.vekter.filter((v) => v.type !== "edge" && v.type !== "dance")
      : K.vekter;
    const type = velgVektet(vekter);

    if (type === "walk") {
      /* Hele skjermen, ikke midtpartiet. Eieren: «saa kan den gaa over hele
       * skjermen». Marginen er liten med vilje. */
      const margin = this.bredde * K.gaaMargin;
      this.oppf.startWalk(tilfeldig(margin, innerWidth - margin));
    } else if (type === "look") {
      this.oppf.startLook();
      if (Math.random() < 0.12) this._si(Math.random() < 0.5 ? "..." : "👀", 2200);
    } else if (type === "sit") {
      this.oppf.startSit();
    } else if (type === "edge") {
      this.oppf.startEdge(this.x > innerWidth / 2);
    } else if (type === "dance") {
      this.oppf.startDance();
    } else {
      this.oppf.startIdle();
      if (Math.random() < 0.3) this.oppf.settHumoer(HUMOER.SLEEPY);
    }
  }

  _si(tekst, ms) {
    this.boble.textContent = tekst;
    this.boble.hidden = false;
    this._planlegg(ms, () => { this.boble.hidden = true; });
  }

  synlig() {
    return this.oppf && this.oppf.tilstand !== "hidden";
  }

  /* ── Debug ──────────────────────────────────────────────────────────────── */

  _byggDebug() {
    const p = document.createElement("div");
    p.className = "tobias-debug";
    p.innerHTML = '<pre></pre><div class="tobias-debug-knapper"></div>';
    document.body.appendChild(p);
    this.debug = p.querySelector("pre");
    const knapper = p.querySelector(".tobias-debug-knapper");
    const valg = {
      Walk: () => this.oppf.startWalk(tilfeldig(80, innerWidth - 80)),
      Sit: () => this.oppf.startSit(),
      Edge: () => this.oppf.startEdge(this.x > innerWidth / 2),
      Dance: () => this.oppf.startDance(),
      Throw: () => {
        this.fysikk.fartX = 1400; this.fysikk.fartY = -900;
        this.fysikk.vinkelfart = 6; this.oppf.startThrown();
      },
      Respawn: () => { this._despawn(); this._planlegg(400, () => this._entre()); },
    };
    for (const [navn, fn] of Object.entries(valg)) {
      const b = document.createElement("button");
      b.type = "button";
      b.textContent = navn;
      b.addEventListener("click", fn);
      knapper.appendChild(b);
    }
    this.opprydd.push(() => p.remove());
  }

  _debugTekst() {
    const f = this.fysikk.fart();
    this.debug.textContent =
      `tilstand : ${this.oppf.tilstand}\n` +
      `humoer   : ${this.oppf.humoer}\n` +
      `uttrykk  : ${this.oppf.uttrykk}\n` +
      `x,y      : ${this.x.toFixed(0)}, ${this.y.toFixed(0)}\n` +
      `fart     : ${f.x.toFixed(0)}, ${f.y.toFixed(0)}\n` +
      `timere   : ${this.timere.size}`;
  }

  /* ── Opprydding ─────────────────────────────────────────────────────────── */

  dispose() {
    this.lever = false;
    this._stopp();
    for (const t of this.timere) clearTimeout(t);
    this.timere.clear();
    for (const fn of this.opprydd) fn();
    this.opprydd.length = 0;

    /* Three.js rydder ikke etter seg selv. Uten dette lekker GPU-minne hver
     * gang modulen lastes paa nytt. */
    this.scene?.traverse((o) => {
      if (o.geometry) o.geometry.dispose();
      if (o.material) {
        for (const m of [].concat(o.material)) {
          m.map?.dispose();
          m.dispose();
        }
      }
    });
    this.robot?.ansikt.fjern();
    this.renderer?.dispose();
    this.renderer?.forceContextLoss?.();
    instans = null;
  }
}

/* ── Inngang ───────────────────────────────────────────────────────────────── */

export async function monterTobias() {
  if (!TOBIAS_ENABLED || instans) return null;
  /* Ved redusert bevegelse dukker han opp og blunker, men gaar ikke og kan
   * ikke kastes - se `_velgHendelse` og pekerlytterne. */
  const THREE = await import("./three.module.js");
  instans = new Tobias(THREE);
  return instans.init();
}

export function fjernTobias() {
  instans?.dispose();
}

export { instans as tobias };
