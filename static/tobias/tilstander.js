/* Tilstandsmaskinen: hva Tobias gjor, og hvordan det ser ut.
 *
 * Eieren 26.07.2026 beskrev ni tilstander og seks oppfoersler. De ligger her,
 * én metode per tilstand, med samme form: `startX()` setter opp, `X(dt)`
 * animerer og returnerer `true` naar den er ferdig.
 *
 * ## Regelen som styrer alt
 *
 * Eieren: «Ikke kjor tilfeldig animasjon hvert sekund. Han skal vaere rolig
 * mesteparten av tiden.» Derfor gjor `idle` lite, pausene mellom hendelser er
 * lange (se `K.hendelsePause`), og de morsomme tingene har lav vekt.
 *
 * ## Sekundaerbevegelse
 *
 * Antenna og armene bruker `Etterslep` og foelger kroppen med treghet. Det er
 * det som gjor at han stopper som en figur og ikke som en variabel: kroppen
 * staar, antenna svinger videre et halvt sekund til.
 */

import { K, tilfeldig, tilfeldigFra } from "./konfig.js";
import {
  Etterslep, Forloep, bland, easeMedTilloep, easeOverskudd, easeUt,
  easeUtInn, jevn, klem, strekk,
} from "./bevegelse.js";
import { UTTRYKK } from "./ansikt.js";

export const HUMOER = {
  HAPPY: "happy", CURIOUS: "curious", SLEEPY: "sleepy", ANNOYED: "annoyed",
};

export class Oppforsel {
  constructor(robot, stol, verden) {
    this.r = robot;
    this.stol = stol;
    this.v = verden;              // { bredde, hoyde, mobil, rolig }

    this.tilstand = "hidden";
    this.humoer = HUMOER.HAPPY;

    /* Posisjon i piksler, av lerretets senter. Styres av `tobias.js`. */
    this.x = 0;
    this.y = 0;
    this.retning = 1;             // 1 = mot hoyre, -1 = mot venstre

    this.tid = 0;                 // sekunder siden montering, til pust og vugging
    this.gangfase = 0;

    /* Sekundaerbevegelse. Stivhet og demping er valgt slik at antenna svinger
     * synlig men ikke vibrerer. */
    this.antenneEtter = new Etterslep(0, 55, 6.5);
    this.kroppRull = new Etterslep(0, 70, 9);
    this.hodeVri = new Etterslep(0, 90, 11);

    /* Maalverdier tilstandene setter, og som kroppen joger mot. */
    this.maal = {
      vri: 0,          // kroppens rotasjon om y
      nikk: 0,         // hodets rotasjon om x
      skrå: 0,         // hodets rotasjon om z
      hodeVri: 0,
      hoyde: 0,        // hvor lavt han staar (sitting)
      armV: 0, armH: 0,
      beinV: 0, beinH: 0,
      strekk: 0,
    };

    this._blunkOm = tilfeldig(2, 5);
    this._blunker = null;
    this.forloep = null;
    this.uttrykk = UTTRYKK.NORMAL;
  }

  /* ── Felles per frame ───────────────────────────────────────────────────── */

  oppdater(dt) {
    this.tid += dt;
    this._blunk(dt);

    let ferdig = false;
    const f = this["_" + this.tilstand];
    if (f) ferdig = f.call(this, dt);

    this._legem(dt);
    return ferdig;
  }

  /* Blunking gaar uavhengig av tilstand - det er det som gjor at han virker
   * levende ogsaa naar han staar helt stille. */
  _blunk(dt) {
    if (this.uttrykk === UTTRYKK.SLEEP || this.uttrykk === UTTRYKK.PANIC) return;
    if (this._blunker) {
      this._blunker += dt;
      const t = this._blunker / 0.17;
      if (t >= 1) {
        this._blunker = null;
        this.r.ansikt.settBlunk(0);
      } else {
        /* Ned og opp igjen. */
        this.r.ansikt.settBlunk(Math.sin(t * Math.PI));
      }
      return;
    }
    this._blunkOm -= dt;
    if (this._blunkOm <= 0) {
      this._blunker = 0;
      /* Soevnige blunker sjeldnere og tyngre; nysgjerrige oftere. */
      const base = this.humoer === HUMOER.SLEEPY ? [4, 8]
        : this.humoer === HUMOER.CURIOUS ? [1.4, 3.2] : [2.4, 6];
      this._blunkOm = tilfeldig(base[0], base[1]);
    }
  }

  /* Kroppen joger mot maalverdiene. ALL demping skjer her, ett sted, saa ingen
   * tilstand kan sette en rotasjon direkte og lage et hopp. */
  _legem(dt) {
    const r = this.r;
    const m = this.maal;

    /* Pust: en liten, langsom skalering. Uten den ser han doed ut naar han
     * staar stille. */
    const pust = Math.sin(this.tid * 1.5) * 0.012;
    strekk(r.torso, m.strekk + pust);

    r.rot.rotation.y = jevn(r.rot.rotation.y, m.vri, K.snufart, dt);
    r.rot.position.y = jevn(r.rot.position.y, -m.hoyde, 9, dt);

    r.hode.rotation.x = jevn(r.hode.rotation.x, m.nikk, 8, dt);
    r.hode.rotation.z = jevn(r.hode.rotation.z, m.skrå, 8, dt);
    r.hode.rotation.y = this.hodeVri.mot(m.hodeVri, dt);

    r.armV.rotation.x = jevn(r.armV.rotation.x, m.armV, 10, dt);
    r.armH.rotation.x = jevn(r.armH.rotation.x, m.armH, 10, dt);
    r.beinV.rotation.x = jevn(r.beinV.rotation.x, m.beinV, 12, dt);
    r.beinH.rotation.x = jevn(r.beinH.rotation.x, m.beinH, 12, dt);

    /* Sekundaerbevegelse: antenna peker mot kroppens rotasjon, men henger
     * etter. Eieren: «kroppen stopper foerst, antennen beveger seg litt
     * videre.» */
    const ant = this.antenneEtter.mot(r.rot.rotation.y * 0.5 + m.nikk * 0.4, dt);
    r.antenne.rotation.z = -ant * 0.8;
    r.antenne.rotation.x = Math.sin(this.tid * 2.1) * 0.05;

    /* Kulen paa antenna lyser svakt av og til - et blunk i maskinen. */
    r.antenneKule.material.emissiveIntensity =
      1.2 + Math.sin(this.tid * 2.6) * 0.35;
  }

  settUttrykk(u) {
    this.uttrykk = u;
    this.r.ansikt.sett(u);
  }

  settHumoer(h) {
    this.humoer = h;
  }

  /* Uttrykket humoeret gir naar ingenting spesielt skjer. */
  hvileUttrykk() {
    return {
      [HUMOER.HAPPY]: UTTRYKK.NORMAL,
      [HUMOER.CURIOUS]: UTTRYKK.CURIOUS,
      [HUMOER.SLEEPY]: UTTRYKK.SLEEP,
      [HUMOER.ANNOYED]: UTTRYKK.SMUG,
    }[this.humoer] || UTTRYKK.NORMAL;
  }

  nullstillLemmer() {
    Object.assign(this.maal, {
      nikk: 0, skrå: 0, hodeVri: 0, hoyde: 0,
      armV: 0, armH: 0, beinV: 0, beinH: 0, strekk: 0,
    });
  }

  /* ── hidden ─────────────────────────────────────────────────────────────── */

  startHidden() {
    this.tilstand = "hidden";
    this.r.rot.visible = false;
  }

  _hidden() {
    return false;
  }

  /* ── Inngang: han GAAR inn fra kanten ───────────────────────────────────── */

  startEntre(fraVenstre) {
    this.tilstand = "entre";
    this.r.rot.visible = true;
    this.retning = fraVenstre ? 1 : -1;
    this.maal.vri = this.retning * Math.PI * 0.5;
    this.r.rot.rotation.y = this.maal.vri;
    this.settUttrykk(UTTRYKK.NORMAL);
    this.nullstillLemmer();
    this.forloep = new Forloep(2600, easeUt);
    this._mål = null;
  }

  _entre(dt) {
    this.forloep.steg(dt);
    this._gangbein(dt, 0.75);
    this.x += this.retning * this._fart() * 0.8 * dt;
    return this.forloep.ferdig;
  }

  /* ── idle ───────────────────────────────────────────────────────────────── */

  startIdle(lengde) {
    this.tilstand = "idle";
    this.nullstillLemmer();
    this.settUttrykk(this.hvileUttrykk());
    this.forloep = new Forloep(lengde ?? tilfeldig(4000, 9000));
    /* Én liten ting per idle - ikke en loop man ser gjentakelsen av. */
    this._smaating = ["seg", "fot", "klø", "ingenting", "ingenting"][
      Math.floor(Math.random() * 5)];
    this._gjort = false;

    /* Ansiktet skifter ogsaa naar han bare staar. Eieren 26.07.2026: «Vil ogsaa
     * at fjeset endrer seg.» Foer dette byttet uttrykket bare ved hendelser, og
     * i en lang idle sto det samme fjeset i et halvt minutt.
     *
     * Uttrykkene er valgt slik at de passer til aa staa stille: ingen PANIC,
     * ingen SLEEP med mindre han faktisk er soevnig. */
    this._miner = [];
    const n = 1 + Math.floor(Math.random() * 2);
    for (let i = 0; i < n; i++) {
      const naar = 0.25 + Math.random() * 0.5;
      const hva = this.humoer === HUMOER.ANNOYED
        ? UTTRYKK.SMUG
        : [UTTRYKK.HAPPY, UTTRYKK.CURIOUS, UTTRYKK.NORMAL][
          Math.floor(Math.random() * 3)];
      this._miner.push({ naar, hva, gjort: false });
    }
  }

  _idle(dt) {
    const t = this.forloep.steg(dt);
    const raa = this.forloep.raa;

    /* Miner: korte uttrykksskift underveis. Hver varer ~1,6 s og gaar tilbake
     * til hvileuttrykket - ellers ville han staatt og glist resten av dagen. */
    for (const m of this._miner || []) {
      if (!m.gjort && raa >= m.naar) {
        m.gjort = true;
        m.til = this.tid + 1.6;
        this.settUttrykk(m.hva);
        if (m.hva === UTTRYKK.CURIOUS) this._blunkOm = 0.4;
      }
      if (m.gjort && m.til && this.tid > m.til) {
        m.til = 0;
        this.settUttrykk(this.hvileUttrykk());
      }
    }

    /* Vekten flyttes sakte fra fot til fot. */
    this.maal.vri = Math.sin(this.tid * 0.7) * 0.10;

    if (this._smaating === "seg" && raa > 0.3 && raa < 0.62) {
      /* Ser til siden og tilbake. */
      const u = (raa - 0.3) / 0.32;
      this.maal.hodeVri = Math.sin(u * Math.PI) * 0.55 * this.retning;
    } else if (this._smaating === "fot" && raa > 0.4 && raa < 0.62) {
      const u = (raa - 0.4) / 0.22;
      this.maal.beinH = -Math.sin(u * Math.PI) * 0.45;
    } else if (this._smaating === "klø" && raa > 0.35 && raa < 0.70) {
      /* Klor seg paa hodet: armen opp, hodet litt paa skrå. */
      const u = (raa - 0.35) / 0.35;
      const s = Math.sin(u * Math.PI);
      this.maal.armH = -s * 2.5;
      this.maal.skrå = -s * 0.16;
      if (!this._gjort && s > 0.5) {
        this.settUttrykk(UTTRYKK.CURIOUS);
        this._gjort = true;
      }
    } else {
      this.maal.hodeVri = 0;
      this.maal.armH = 0;
      this.maal.skrå = 0;
      if (this._gjort) {
        this.settUttrykk(this.hvileUttrykk());
        this._gjort = false;
      }
    }
    void t;
    return this.forloep.ferdig;
  }

  /* ── walking ────────────────────────────────────────────────────────────── */

  startWalk(maalX) {
    this.tilstand = "walking";
    this.nullstillLemmer();
    this.settUttrykk(this.hvileUttrykk() === UTTRYKK.SLEEP
      ? UTTRYKK.NORMAL : this.hvileUttrykk());
    this._mål = maalX;
    this.retning = maalX > this.x ? 1 : -1;
    this.maal.vri = this.retning * Math.PI * 0.5;
  }

  _fart() {
    return this.v.mobil ? K.gangfartMobil : K.gangfart;
  }

  /* Selve gangsyklusen. Motsatt arm av bein, kroppen bobber, hodet nesten
   * ikke - eieren var presis paa akkurat den rekkefolgen. */
  _gangbein(dt, styrke = 1) {
    this.gangfase += dt * 6.2;
    const s = Math.sin(this.gangfase);
    const c = Math.cos(this.gangfase);
    this.maal.beinV = s * 0.55 * styrke;
    this.maal.beinH = -s * 0.55 * styrke;
    this.maal.armV = -s * 0.40 * styrke;
    this.maal.armH = s * 0.40 * styrke;
    /* Kroppen loefter seg to ganger per skritt - derfor abs(cos). */
    this.maal.hoyde = -Math.abs(c) * 0.022 * styrke * 100 * 0.01;
    this.maal.nikk = -Math.abs(c) * 0.03 * styrke;
  }

  _walking(dt) {
    const igjen = this._mål - this.x;
    if (Math.abs(igjen) < 4) {
      /* Stopper: beina samles, og antenna svinger videre av seg selv. */
      this.maal.beinV = this.maal.beinH = 0;
      this.maal.armV = this.maal.armH = 0;
      this.maal.hoyde = 0;
      return true;
    }
    this.retning = Math.sign(igjen);
    this.maal.vri = this.retning * Math.PI * 0.5;
    this._gangbein(dt);
    this.x += this.retning * this._fart() * dt;
    return false;
  }

  /* ── looking: ser ut av skjermen ────────────────────────────────────────── */

  startLook() {
    this.tilstand = "looking";
    this.nullstillLemmer();
    this.forloep = new Forloep(tilfeldigFra(K.seLengde));
    this._fase = 0;
  }

  _looking(dt) {
    const raa = this.forloep.raa;
    this.forloep.steg(dt);

    if (raa < 0.22) {
      /* 1-3: snur kroppen mot kamera og loefter hodet. */
      this.maal.vri = 0;
      this.maal.nikk = -0.16;
    } else if (raa < 0.6) {
      /* 4-5: ser rett ut, blunker (blunkingen gaar av seg selv). */
      this.maal.vri = 0;
      this.maal.nikk = -0.10;
      if (this._fase === 0) {
        this._fase = 1;
        this._blunkOm = 0.35;         // fremskynd ett blunk
      }
    } else {
      /* 6: legger hodet paa skrå. */
      this.maal.skrå = 0.22;
      this.maal.hodeVri = 0.12;
      if (this._fase === 1) {
        this._fase = 2;
        this.settUttrykk(UTTRYKK.CURIOUS);
      }
    }
    if (this.forloep.ferdig) {
      this.settUttrykk(this.hvileUttrykk());
      this.nullstillLemmer();
      return true;
    }
    return false;
  }

  /* ── sitting: stol-eventet ──────────────────────────────────────────────── */

  startSit() {
    this.tilstand = "sitting";
    this.nullstillLemmer();
    this.forloep = new Forloep(1400 + tilfeldigFra(K.sitteLengde) + 1500);
    this._sitteLengde = tilfeldigFra(K.sitteLengde);
    this._fase = "ser";
    this._t = 0;
    this.stol.rot.visible = false;
  }

  _sitting(dt) {
    this._t += dt * 1000;
    const s = this.stol.rot;

    if (this._fase === "ser") {
      /* 1-2: stopper og ser seg rundt. */
      this.maal.vri = 0;
      this.maal.hodeVri = Math.sin(this._t / 260) * 0.5;
      if (this._t > 900) {
        this._fase = "hent";
        this._t = 0;
        s.visible = true;
        s.scale.setScalar(0.01);
        s.position.set(this.retning * 0.75, 0, -0.12);
      }
      return false;
    }

    if (this._fase === "hent") {
      /* 3-4: stolen kommer fram og dras inn. */
      const u = Math.min(1, this._t / 900);
      s.scale.setScalar(easeOverskudd(u, 1.4) * 0.9 + 0.1);
      s.position.x = bland(this.retning * 0.75, this.retning * 0.30, easeUtInn(u));
      this.maal.hodeVri = this.retning * 0.3;
      this.maal.armH = -0.8 * u;
      if (u >= 1) { this._fase = "ned"; this._t = 0; }
      return false;
    }

    if (this._fase === "ned") {
      /* 5: setter seg. Eieren: «han boeyer beina foer kroppen gaar ned.» */
      const u = Math.min(1, this._t / 800);
      const bein = easeUtInn(Math.min(1, u * 1.6));
      const kropp = easeUtInn(Math.max(0, (u - 0.22) / 0.78));
      this.maal.beinV = this.maal.beinH = -bein * 1.35;
      this.maal.hoyde = kropp * 0.26;
      this.maal.armH = -0.8 * (1 - kropp);
      this.maal.vri = this.retning * 0.55;
      s.position.x = this.retning * 0.30;
      if (u >= 1) {
        this._fase = "sitter";
        this._t = 0;
        this.settUttrykk(UTTRYKK.NORMAL);
      }
      return false;
    }

    if (this._fase === "sitter") {
      /* 6-7: lener seg tilbake, beina litt fram, ser ut av skjermen. */
      this.maal.hoyde = 0.26;
      this.maal.beinV = -1.15;
      this.maal.beinH = -1.30;
      this.maal.armV = 0.30;
      this.maal.armH = 0.36;
      this.maal.nikk = -0.20;
      this.maal.vri = this.retning * 0.28;
      this.maal.skrå = Math.sin(this._t / 1400) * 0.06;
      if (this._t > this._sitteLengde) { this._fase = "opp"; this._t = 0; }
      return false;
    }

    /* Reiser seg, skyver stolen vekk, stolen fades ut. */
    const u = Math.min(1, this._t / 1100);
    this.maal.hoyde = 0.26 * (1 - easeOverskudd(u, 1.1));
    this.maal.beinV = this.maal.beinH = -1.2 * (1 - easeUtInn(u));
    this.maal.armV = this.maal.armH = 0;
    this.maal.nikk = 0;
    s.position.x = bland(this.retning * 0.30, this.retning * 0.95, easeInnUt(u));
    s.scale.setScalar(Math.max(0.001, (1 - easeInnUt(u)) * 0.9 + 0.1 * (1 - u)));
    if (u >= 1) {
      s.visible = false;
      this.nullstillLemmer();
      return true;
    }
    return false;
  }

  /* ── edgeLook: henger seg paa skjermkanten ──────────────────────────────── */

  startEdge(hoyreSide) {
    this.tilstand = "edge";
    this.nullstillLemmer();
    this._hoyre = hoyreSide;
    this.retning = hoyreSide ? 1 : -1;
    this.forloep = new Forloep(tilfeldigFra(K.kantLengde));
    this._fase = "gaar";
  }

  _edge(dt) {
    const kant = this._hoyre
      ? this.v.bredde - this.v.robotBredde * 0.18
      : this.v.robotBredde * 0.18;

    if (this._fase === "gaar") {
      /* 1-2: gaar helt ut i kanten, saa deler av kroppen er utenfor. */
      const igjen = kant - this.x;
      if (Math.abs(igjen) < 4) {
        this._fase = "henger";
        this.forloep = new Forloep(tilfeldigFra(K.kantLengde));
        return false;
      }
      this.retning = Math.sign(igjen);
      this.maal.vri = this.retning * Math.PI * 0.5;
      this._gangbein(dt, 0.8);
      this.x += this.retning * this._fart() * dt;
      return false;
    }

    const raa = this.forloep.raa;
    this.forloep.steg(dt);

    /* 3-5: holder seg fast, lener hodet utenfor, ser rundt.
     * Eieren: «gjor det som om det finnes en verden utenfor nettsiden.» */
    this.maal.vri = this._hoyre ? Math.PI * 0.5 : -Math.PI * 0.5;
    /* Den bakre armen strekkes bakover - det er den som «holder fast». */
    this.maal.armV = 1.9;
    this.maal.armH = 0.5;
    /* Kroppen lener seg ut. */
    this.maal.skrå = (this._hoyre ? -1 : 1) * 0.20;
    this.maal.hodeVri = Math.sin(raa * Math.PI * 3) * 0.45;
    this.maal.nikk = -0.12 + Math.sin(raa * Math.PI * 2) * 0.10;
    this.maal.beinV = 0.25;
    this.maal.beinH = -0.15;

    if (raa > 0.15 && raa < 0.25) this.settUttrykk(UTTRYKK.CURIOUS);

    if (this.forloep.ferdig) {
      this.settUttrykk(this.hvileUttrykk());
      this.nullstillLemmer();
      return true;
    }
    return false;
  }

  /* ── dancing ────────────────────────────────────────────────────────────── */

  startDance() {
    this.tilstand = "dancing";
    this.nullstillLemmer();
    this.settUttrykk(UTTRYKK.HAPPY);
    this.forloep = new Forloep(tilfeldigFra(K.dansLengde));
    this._hopp = 0;
  }

  _dancing(dt) {
    const raa = this.forloep.raa;
    this.forloep.steg(dt);
    const t = this.tid * 7;

    /* Armene opp med overskudd i starten. */
    const opp = easeOverskudd(Math.min(1, raa * 4), 2.0);
    this.maal.armV = -2.3 * opp + Math.sin(t) * 0.5;
    this.maal.armH = -2.3 * opp - Math.sin(t) * 0.5;
    /* Hopper fra side til side, og snurrer paa slutten. */
    this.maal.hoyde = -Math.abs(Math.sin(t * 0.75)) * 0.10;
    this.maal.vri = raa > 0.65
      ? (raa - 0.65) / 0.35 * Math.PI * 2
      : Math.sin(t * 0.75) * 0.55;
    this.maal.skrå = Math.sin(t * 0.75) * 0.14;
    this.maal.beinV = Math.sin(t * 0.75) * 0.35;
    this.maal.beinH = -Math.sin(t * 0.75) * 0.35;

    if (this.forloep.ferdig) {
      this.maal.vri = 0;
      this.nullstillLemmer();
      this.settHumoer(HUMOER.HAPPY);
      this.settUttrykk(this.hvileUttrykk());
      return true;
    }
    return false;
  }

  /* ── Smaa reaksjoner paa klikk ──────────────────────────────────────────── */

  startReaksjon(hva) {
    this.tilstand = "reaksjon";
    this.nullstillLemmer();
    /* IKKE `this._reaksjon`: tilstandsmetoden heter allerede `_reaksjon`, og
     * `oppdater()` slaar den opp med `this["_" + this.tilstand]`. En property
     * med samme navn skygger for metoden, og hele sloyfa doede med
     * «f.call is not a function» - maalt i nettleseren 26.07.2026. */
    this._reaksjonstype = hva;
    this.forloep = new Forloep(hva === "hopp" ? 700 : 1200);
    if (hva === "vink") this.settUttrykk(UTTRYKK.HAPPY);
    if (hva === "smug") this.settUttrykk(UTTRYKK.SMUG);
    if (hva === "haand") this.settUttrykk(UTTRYKK.CURIOUS);
  }

  _reaksjon(dt) {
    const raa = this.forloep.raa;
    this.forloep.steg(dt);
    const s = Math.sin(raa * Math.PI);

    if (this._reaksjonstype === "vink") {
      this.maal.vri = 0;
      this.maal.armH = -2.4 * s;
      /* Selve vinket: haanden gaar fram og tilbake mens armen er oppe. */
      this.r.armH.rotation.z = Math.sin(raa * Math.PI * 8) * 0.45 * s;
    } else if (this._reaksjonstype === "hopp") {
      /* Anticipation: han synker litt foer han hopper. */
      const h = easeMedTilloep(raa);
      this.maal.hoyde = -h * 0.30;
      this.maal.beinV = this.maal.beinH = -Math.max(0, h) * 0.5;
      this.maal.strekk = h > 0 ? h * 0.10 : h * 0.25;   // strekk opp, klem ned
    } else if (this._reaksjonstype === "haand") {
      this.maal.vri = 0;
      this.maal.nikk = 0.30 * s;         // ser ned mot pekeren
      this.maal.skrå = 0.18 * s;
    } else if (this._reaksjonstype === "smug") {
      this.maal.vri = 0.25 * s;
      this.maal.skrå = -0.20 * s;
    } else {
      this._blunkOm = 0;                  // «blink»
    }

    if (this.forloep.ferdig) {
      this.r.armH.rotation.z = 0;
      this.nullstillLemmer();
      this.settUttrykk(this.hvileUttrykk());
      return true;
    }
    return false;
  }

  /* ── dragged / thrown ───────────────────────────────────────────────────── */

  startDrag() {
    this.tilstand = "dragged";
    this.nullstillLemmer();
    this.settUttrykk(UTTRYKK.PANIC);
    this.stol.rot.visible = false;
  }

  /* Pekerens fart, satt utenfra hver frame. Ligger paa objektet og sendes
   * IKKE som argument: `oppdater()` kaller tilstandsmetoden med bare `dt`, saa
   * et argument her ville blitt `undefined` og nullstilt alt hvert frame. */
  settDragfart(x, y) {
    this._dragFartX = x;
    this._dragFartY = y;
  }

  /* Armer og bein henger etter kroppen mens han dras. */
  _dragged(dt) {
    const fartX = this._dragFartX || 0;
    const fartY = this._dragFartY || 0;
    const f = klem(fartX / 900, -1, 1);
    this.maal.vri = -f * 0.5;
    this.maal.armV = klem(-fartY / 700, -1.4, 1.4) - f * 0.6;
    this.maal.armH = klem(-fartY / 700, -1.4, 1.4) + f * 0.6;
    this.maal.beinV = klem(fartY / 900, -0.9, 0.9) - f * 0.3;
    this.maal.beinH = klem(fartY / 900, -0.9, 0.9) + f * 0.3;
    this.maal.skrå = f * 0.35;
    void dt;
    return false;
  }

  startThrown() {
    this.tilstand = "thrown";
    this.settUttrykk(UTTRYKK.PANIC);
    this.stol.rot.visible = false;
  }

  /* Mens han flyr: armer og bein spriker, kroppen roterer. */
  _thrown(dt) {
    const t = this.tid * 9;
    this.maal.armV = -2.0 + Math.sin(t) * 0.5;
    this.maal.armH = -2.0 - Math.sin(t) * 0.5;
    this.maal.beinV = 0.9 + Math.cos(t) * 0.3;
    this.maal.beinH = 0.9 - Math.cos(t) * 0.3;
    void dt;
    return false;
  }
}

/* Liten easing som brukes to steder i stol-sekvensen. Ligger her og ikke i
 * bevegelse.js fordi den bare gir mening sammen med den. */
function easeInnUt(t) {
  return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
}
