/* Ragdollen: verden, positurer, balanse, griping, kast og fysiske tilstander.
 *
 * Eieren 26.07.2026: «Han skal foeles som en fysisk liten robot som eksisterer
 * paa nettsiden ... 60 % kontrollert karakter + 40 % ragdoll.»
 *
 * ## Den viktigste testen, med eierens ord
 *
 * «Hvis jeg gjor noe utvikleren ikke eksplisitt har programmert en animasjon
 * for, skal Tobias fortsatt reagere troverdig fordi fysikksystemet haandterer
 * situasjonen.»
 *
 * Det er derfor det ikke finnes en `fallFromChair`, en `throwAnimation` eller
 * en `getUpFromBack` her. Det finnes POSITURER (hva han proever aa gjore) og
 * KREFTER (hva som faktisk skjer med ham). Alt annet foelger av de to.
 *
 * ## Hvordan tilstanden bestemmes
 *
 * Eieren §25: «State bestemmes primaert fra fysikken. Ikke bestem falling bare
 * fordi en animation spiller.» `_lesTilstand()` ser bare paa maalinger:
 * fotkontakt, hoyde over gulvet, torsoens opprettstaaende retning, farten.
 */

import { FYS } from "./konfig.js";
import { byggSkjelett, byggVerden, FOETTER, GRIPBARE } from "./skjelett.js";
import {
  draModPositur, fraEuler, gang as ganger, holdLeddgrenser,
} from "./positur.js";
import { POSITURER, blandPositur } from "./positurer.js";

export const FYSISK = {
  STABIL: "stable", BALANSERER: "balancing", GAAR: "walking",
  SNUBLER: "stumbling", FALLER: "falling", NEDE: "grounded",
  GREPET: "grabbed", I_LUFTA: "airborne", REISER: "recovering", SITTER: "sitting",
};

export class Ragdoll {
  constructor(RAPIER, bredde) {
    this.R = RAPIER;
    this.bredde = bredde;                 // verdensbredde i meter
    this.verden = new RAPIER.World({ x: 0, y: FYS.tyngde, z: 0 });
    this.verden.timestep = FYS.steg;
    /* Flere solveriterasjoner. Med standardverdien (4) ble hofteleddet brutt
     * med 10 cm - torsoen og laaret laa 0,10 m for tett, og hele beinkjeden
     * foldet seg sammen selv om PD-regulatoren var stabil. En kjede paa fire
     * ledd med stor massekontrast trenger flere passeringer for aa konvergere.
     * Maalt 26.07.2026: torso paa 0,178 m der den skulle staatt i 0,42. */
    const ip = this.verden.integrationParameters;
    if (ip) {
      if ("numSolverIterations" in ip) ip.numSolverIterations = FYS.solver.iter;
      if ("numInternalPgsIterations" in ip) {
        ip.numInternalPgsIterations = FYS.solver.pgs;
      }
      if ("numAdditionalFrictionIterations" in ip) {
        ip.numAdditionalFrictionIterations = FYS.solver.friksjon;
      }
    }

    byggVerden(RAPIER, this.verden, bredde);
    const s = byggSkjelett(RAPIER, this.verden, bredde / 2, 0.02);
    this.kropper = s.kropper;
    this.kollidere = s.kollidere;
    this.ledd = s.ledd;

    this.hendelser = new RAPIER.EventQueue(true);

    this.tilstand = FYSISK.STABIL;
    this.positur = "staa";
    this.positurTid = 0;
    this.styrke = 1;                      // hvor mye kontroll han har (0..1)
    this.rest = 0;                        // opphopet tid til faste fysikksteg
    this.grep = null;
    this.sisteSmell = 0;
    this.nedeTid = 0;
    this.stegTid = 0;
    this.stegFot = null;
    this.gaarMot = null;
    this.hodeMaal = null;                 // {x,y,z} i verdensrom, eller null

    /* Hvilken vei han VENDER, i radianer om y-aksen. 0 = rett mot kameraet.
     *
     * ## Hvorfor han maa kunne snu seg i det hele tatt
     *
     * Han gaar langs skjermens x-akse, men kneet og albuen er hengsler om sin
     * EGEN x-akse - de boyer altsaa i dybden. Vender han rett mot kameraet, kan
     * han derfor ikke ta et steg sidelengs uten at kneet knekker sidelengs, og
     * det ser oedelagt ut, ikke kloenete.
     *
     * Loesningen er den samme som i den godkjente `modell.js`: han snur seg mot
     * gangretningen. Da faller hans egen «framover» sammen med reiseretningen,
     * hengslene boyer riktig vei, og hele positurbiblioteket - som er skrevet
     * som om han staar rett fram - gjelder uendret. `_byggMaalpositur` ganger
     * bare hver maalrotasjon med gjeldende vending. */
    this.retning = 0;
    this.retningMaal = 0;
    this.gangFase = 0;                    // 0..1 over ett helt skrittpar
  }

  /* ── Maalinger. Alt som styrer oppfoerselen leses her, fra fysikken. ────── */

  massesenter() {
    let m = 0, x = 0, y = 0, z = 0;
    for (const rb of Object.values(this.kropper)) {
      const p = rb.translation();
      const w = rb.mass();
      m += w; x += p.x * w; y += p.y * w; z += p.z * w;
    }
    return { x: x / m, y: y / m, z: z / m, masse: m };
  }

  /* Hvor foettene staar, og om de i det hele tatt roerer bakken. */
  stoette() {
    const p = [];
    for (const f of FOETTER) {
      const t = this.kropper[f].translation();
      /* Foten er 0.035 hoy; under 0.075 regnes den som paa gulvet. */
      if (t.y < 0.075) p.push({ navn: f, x: t.x, z: t.z });
    }
    if (!p.length) return null;
    const x = p.reduce((a, b) => a + b.x, 0) / p.length;
    return { x, antall: p.length, foetter: p };
  }

  /* Hvor opprett torsoen staar: 1 = rett opp, -1 = opp ned. */
  opprett() {
    const q = this.kropper.torso.rotation();
    /* Y-aksen til torsoen, rotert. */
    return 1 - 2 * (q.x * q.x + q.z * q.z);
  }

  fart() {
    const v = this.kropper.torso.linvel();
    return Math.hypot(v.x, v.y, v.z);
  }

  spinn() {
    const w = this.kropper.torso.angvel();
    return Math.hypot(w.x, w.y, w.z);
  }

  /* Balansefeilen: hvor langt massesenteret ligger fra midt mellom foettene. */
  balansefeil() {
    const s = this.stoette();
    if (!s) return null;
    return this.massesenter().x - s.x;
  }

  /* ── Tilstand, lest av fysikken og ingenting annet ──────────────────────── */

  _lesTilstand() {
    if (this.grep) return FYSISK.GREPET;
    if (this.positur === "sitte") return FYSISK.SITTER;

    const s = this.stoette();
    const opp = this.opprett();
    const com = this.massesenter();

    if (!s && com.y > 0.30) return FYSISK.I_LUFTA;

    if (opp < 0.35) {
      /* Ligger, uansett hva han proever paa. */
      return this.nedeTid > 0.9 ? FYSISK.REISER : FYSISK.NEDE;
    }

    const feil = this.balansefeil();
    if (feil === null) return FYSISK.FALLER;
    const a = Math.abs(feil);
    if (a > FYS.balanse.fall) return FYSISK.FALLER;
    if (a > FYS.balanse.snuble) return FYSISK.SNUBLER;
    if (this.gaarMot !== null) return FYSISK.GAAR;
    if (a > FYS.balanse.vingle) return FYSISK.BALANSERER;
    return FYSISK.STABIL;
  }

  /* ── Balansekontrolleren ────────────────────────────────────────────────
   *
   * Eieren §5-6. Fire nivaaer, med stigende alvor. Ingen av dem er en
   * animasjon - alle er krefter og fot-maal.
   */
  _balanser(dt) {
    const feil = this.balansefeil();
    if (feil === null) return;
    const a = Math.abs(feil);
    const retn = Math.sign(feil);

    if (a <= FYS.balanse.vingle) {
      this.stegTid = 0;
      return;
    }

    /* Smaa forstyrrelser: hofta dytter tilbake, og armene brukes som motvekt.
     * Det siste er billig og selger hele bevegelsen. */
    const torso = this.kropper.torso;
    torso.applyImpulse(
      { x: -retn * Math.min(a, 0.3) * FYS.balanse.styrke * dt, y: 0, z: 0 }, true);

    /* Gaar han, styrer skrittfasen beina. Uten denne linja kjemper balansens
     * gjenvinningsskritt mot gangens skritt om de samme foettene, og han staar
     * og stamper. Hoftedyttet over blir staaende - det er balanse, ikke skritt. */
    if (this.gaarMot !== null) return;

    if (a > FYS.balanse.steg && this.stegTid <= 0) {
      /* Stoerre: ta et steg. Eieren §6: «Ikke bruk en ferdig walk animation til
       * recovery. Flytt fot-target og la kroppen fysisk proeve aa folge.» */
      const s = this.stoette();
      if (s && s.foetter.length) {
        /* Den bakerste foten i fallretningen flyttes fram. */
        const fot = s.foetter.reduce((b, f) =>
          (retn > 0 ? f.x < b.x : f.x > b.x) ? f : b, s.foetter[0]);
        this.stegFot = fot.navn;
        this.stegTid = FYS.balanse.stegTid;
      }
    }

    if (this.stegTid > 0) {
      this.stegTid -= dt;
      const rb = this.kropper[this.stegFot];
      if (rb) {
        /* Foten loeftes og kastes framover mot der massesenteret er paa vei. */
        const u = 1 - this.stegTid / FYS.balanse.stegTid;
        rb.applyImpulse({
          x: retn * FYS.balanse.stegLengde * 5.5 * dt,
          y: Math.sin(u * Math.PI) * 2.2 * dt,
          z: 0,
        }, true);
      }
    }
  }

  /* ── Griping ────────────────────────────────────────────────────────────
   *
   * Eieren §7: «IKKE flytt hele Tobias. Opprett en temporary physics joint
   * mellom pointer target og Tobias.handRigidBody.»
   *
   * Vi bruker ikke et ekte Rapier-ledd, men en fjaer mot et punkt - det gir
   * samme oppfoersel og lar oss klippe kraften, saa fingeren ikke kan rive ham
   * i stykker.
   */
  grip(delnavn, punkt) {
    if (!GRIPBARE.includes(delnavn)) return false;
    const rb = this.kropper[delnavn];
    const p = rb.translation();
    this.grep = {
      del: delnavn, rb,
      /* Offset i kroppens eget rom, saa han ikke snapper til pekeren. */
      dx: p.x - punkt.x, dy: p.y - punkt.y, dz: p.z - punkt.z,
      maal: { ...punkt },
      spor: [],
    };
    for (const b of Object.values(this.kropper)) b.wakeUp();
    return true;
  }

  flyttGrep(punkt, naa) {
    if (!this.grep) return;
    this.grep.maal = { ...punkt };
    this.grep.spor.push({ t: naa, x: punkt.x, y: punkt.y, z: punkt.z });
    while (this.grep.spor.length > 2
           && naa - this.grep.spor[0].t > FYS.kast.sporMs) {
      this.grep.spor.shift();
    }
  }

  /* Slipp. Returnerer farten han ble sluppet med, i m/s. */
  slipp() {
    if (!this.grep) return { x: 0, y: 0, z: 0 };
    const s = this.grep.spor;
    let v = { x: 0, y: 0, z: 0 };
    if (s.length >= 2) {
      const a = s[0], b = s[s.length - 1];
      const dt = (b.t - a.t) / 1000;
      if (dt > 0.008) {
        v = { x: (b.x - a.x) / dt, y: (b.y - a.y) / dt, z: 0 };
      }
    }
    const l = Math.hypot(v.x, v.y);
    if (l > FYS.kast.maksFart) {
      v.x *= FYS.kast.maksFart / l;
      v.y *= FYS.kast.maksFart / l;
    }
    /* Eieren §10: «Paafor velocity/impulse paa bodyparten. Resten av kroppen
     * folger gjennom ragdoll joints.» Impulsen gaar paa DEN delen som ble
     * grepet - ikke paa torsoen. Det er forskjellen paa aa kaste ham og aa
     * flytte ham. */
    const rb = this.grep.rb;
    const m = rb.mass();
    rb.applyImpulse({
      x: v.x * m * FYS.kast.faktor,
      y: v.y * m * FYS.kast.faktor,
      z: 0,
    }, true);
    /* ... og en andel til RESTEN av kroppen. Uten den flyr bare den grepne
     * delen av gaarde, og leddene drar den tilbake igjen. */
    for (const [navn, b] of Object.entries(this.kropper)) {
      if (navn === this.grep.del) continue;
      const bm = b.mass();
      b.applyImpulse({
        x: v.x * bm * FYS.kast.kroppAndel,
        y: v.y * bm * FYS.kast.kroppAndel,
        z: 0,
      }, true);
    }
    /* Litt spinn av kastet, saa han tumler i stedet for aa fly rett. */
    this.kropper.torso.applyTorqueImpulse(
      { x: 0, y: 0, z: -v.x * 0.05 }, true);
    this.grep = null;
    return v;
  }

  _dragIGrep(dt) {
    const g = this.grep;
    if (!g) return;
    const p = g.rb.translation();
    const v = g.rb.linvel();
    const maalX = g.maal.x + g.dx;
    const maalY = g.maal.y + g.dy;
    const m = g.rb.mass();
    let fx = ((maalX - p.x) * FYS.grep.stivhet - v.x * FYS.grep.demping) * m;
    let fy = ((maalY - p.y) * FYS.grep.stivhet - v.y * FYS.grep.demping) * m;
    const l = Math.hypot(fx, fy);
    const tak = FYS.grep.maksKraft * m;
    if (l > tak) { fx *= tak / l; fy *= tak / l; }
    g.rb.applyImpulse({ x: fx * dt, y: fy * dt, z: 0 }, true);
  }

  /* ── Dytt: brukt av debugpanelet og av klikk ────────────────────────────── */

  dytt(kraft) {
    const t = this.kropper.torso;
    t.wakeUp();
    t.applyImpulse({ x: kraft, y: 0, z: 0 }, true);
  }

  /* ── Sett ham et sted ────────────────────────────────────────────────────
   *
   * Brukt naar han skal komme tilbake etter aa ha blitt kastet ut av vinduet.
   * Hver kropp settes til utgangsstillingen sin forskjovet til (x, y), med all
   * fart nullstilt - ellers tar han med seg kastefarten inn i det nye livet.
   *
   * Det er ingen «spawn-animasjon» her, og det er med vilje: han slippes i
   * lufta og faller ned. Derfor lander han litt forskjellig hver gang, uten at
   * noen har skrevet variantene. */
  plasser(x, y) {
    for (const [navn, rb] of Object.entries(this.kropper)) {
      const d = FYS.deler[navn];
      rb.setTranslation({ x: x + (d.x || 0), y: y + d.y, z: d.z || 0 }, true);
      rb.setRotation({ x: 0, y: 0, z: 0, w: 1 }, true);
      rb.setLinvel({ x: 0, y: 0, z: 0 }, true);
      rb.setAngvel({ x: 0, y: 0, z: 0 }, true);
      rb.wakeUp();
    }
    this.grep = null;
    this.gaarMot = null;
    this.retning = 0;
    this.retningMaal = 0;
    this.nedeTid = 0;
    this.sisteSmell = 0;
    this._nullstillFotfriksjon();
    this.settPositur("staa");
  }

  /* ── Stegets hovedloop ──────────────────────────────────────────────────── */

  /* `dt` i sekunder. Faste fysikksteg med akkumulator, saa oppfoerselen er den
   * samme paa 30 og 144 Hz - og saa en treg frame ikke sender ham i bane. */
  steg(dt) {
    this.rest += Math.min(dt, 0.1);
    let n = 0;
    while (this.rest >= FYS.steg && n < FYS.maksSteg) {
      this._ettSteg(FYS.steg);
      this.rest -= FYS.steg;
      n++;
    }
    if (n === FYS.maksSteg) this.rest = 0;   // gi opp aa ta igjen
    this.tilstand = this._lesTilstand();
    return n;
  }

  _ettSteg(h) {
    this.positurTid += h;

    /* Kontrollstyrken faller naar fysikken tar over. Eieren: «Han proever hele
     * tiden aa kontrollere kroppen sin, men fysikken kan vinne.» */
    const maalStyrke = {
      [FYSISK.NEDE]: 0.25, [FYSISK.FALLER]: 0.45, [FYSISK.SNUBLER]: 0.7,
      [FYSISK.I_LUFTA]: 0.35, [FYSISK.GREPET]: 0.5, [FYSISK.REISER]: 0.9,
    }[this.tilstand] ?? 1.0;
    this.styrke += (maalStyrke - this.styrke) * Math.min(1, h * 4);

    const maal = this._byggMaalpositur();
    draModPositur(this.kropper, maal, this.styrke, h);
    holdLeddgrenser(this.ledd, this.kropper, h);

    if (this.grep) this._dragIGrep(h);
    else if (this.tilstand === FYSISK.STABIL
             || this.tilstand === FYSISK.BALANSERER
             || this.tilstand === FYSISK.GAAR) {
      this._balanser(h);
    }

    if (this.tilstand === FYSISK.NEDE) this.nedeTid += h;
    else if (this.tilstand !== FYSISK.REISER) this.nedeTid = 0;

    if (this.gaarMot !== null) this._gaa(h);
    else this.retningMaal = 0;            // staar han stille, vender han fram

    /* Vendingen glir mot maalet. Eksponentiell utjevning, ikke et sprang: den
     * gaar ogsaa inn i posituren, saa et sprang her ville rykket hele kroppen. */
    this.retning += (this.retningMaal - this.retning)
      * Math.min(1, h / FYS.gange.snuTid);

    this.verden.step(this.hendelser);
    this._lesSmell();
  }

  /* Eieren §12: «Maal collision impulse.» Vi leser kontakthendelsene og tar
   * vare paa den kraftigste, saa ansiktet kan reagere paa den. */
  _lesSmell() {
    let maks = 0;
    this.hendelser.drainCollisionEvents((h1, h2, startet) => {
      if (!startet) return;
      void h1; void h2;
      const v = this.fart();
      if (v > maks) maks = v;
    });
    if (maks > this.sisteSmell) this.sisteSmell = maks;
    this.sisteSmell *= 0.92;
  }

  /* ── Gange, fysisk ──────────────────────────────────────────────────────
   *
   * Eieren §14: «Walking skal bruke physics. Ikke bare position.x += speed.»
   * Foettene faar maal etter tur, og kroppen dras etter av balansen.
   */
  gaaMot(x) { this.gaarMot = x; }
  stoppGange() {
    this.gaarMot = null;
    this.stegTid = 0;
    this._nullstillFotfriksjon();
  }

  /* ## Hvorfor gangen ble skrevet om
   *
   * Foerste utgave dyttet foten med smaa impulser: 2.6 N framover og 2.6 N opp.
   * Foten veier 0.60 kg og har 8.4 N i vekt, saa den forlot aldri bakken - og
   * med friksjon 1.1 under begge foettene var 0.55 N paa torsoen ikke i
   * naerheten av aa flytte 7 kg. Han stod stille og lente seg.
   *
   * Grunnen til at det likevel «bestod» testen, var at testbenken steppet 1/60
   * mot en konfigurasjon paa 1/120. Da var dempingen ustabil, og ristingen
   * flyttet ham 0.40 m. Da benken ble rettet, ble fasiten 3.00 -> 3.00 m.
   *
   * Naa gaar han slik man faktisk gaar: hofta og kneet dreies av PD-regulatoren
   * (som har 60 Nm aa ta av, mot impulsenes 2.6 N), foten settes ned foran,
   * og det er FRIKSJONEN under standbeinet som skyver kroppen fram. Ingen
   * impuls flytter ham direkte - eieren §14: «Walking skal bruke physics. Ikke
   * bare position.x += speed.»
   */
  _gaa(dt) {
    const com = this.massesenter();
    const igjen = this.gaarMot - com.x;
    if (Math.abs(igjen) < 0.14) { this.stoppGange(); return; }
    const retn = Math.sign(igjen);

    /* Snu deg mot der du skal. Vendingen glir paa plass over ca. 0.3 s, saa han
     * ikke snapper rundt naar han skifter retning. */
    this.retningMaal = retn > 0 ? Math.PI / 2 : -Math.PI / 2;

    /* Skrittfasen gaar rundt én gang per skrittPAR. */
    this.gangFase = (this.gangFase + dt / (2 * FYS.balanse.stegTid)) % 1;

    /* Han lener seg svakt framover. Lenen alene flytter ham ikke - den gjor at
     * massesenteret havner foran standfoten, saa han MAA sette den andre foten
     * fram for ikke aa falle. Det er den mekanismen som gaar. */
    const framover = { x: Math.sin(this.retning), y: 0, z: Math.cos(this.retning) };
    this.kropper.torso.applyImpulse({
      x: framover.x * FYS.gange.len * dt,
      y: 0,
      z: framover.z * FYS.gange.len * dt,
    }, true);

    /* ## Foten som svinger, skal slippe taket
     *
     * Foerste forsok lot begge foettene beholde friksjon 1.10 hele veien. Da
     * loeftet venstre fot 3.8 cm og hoyre ALDRI - maalt over seks sekunder.
     * Foten veier 0.60 kg (den snudde massefordelingen som gjor ham stoedig aa
     * staa paa) og laa limt til gulvet mens hofta dro i beinet.
     *
     * En fot som er i svevfasen staar ikke paa noe, saa den skal heller ikke
     * gripe i noe. Friksjonen settes ned mens den svinger og tilbake naar den
     * lander - og den faar et loeft som er stort nok til aa baere sin egen vekt
     * (0.60 kg * 14 m/s² = 8.4 N), ellers klarer ikke hofta aa faa den klar av
     * bakken i det hele tatt. */
    const g = FYS.gange;
    const f = this.gangFase * Math.PI * 2;
    const svingV = Math.cos(f) > 0;        // venstre bein paa vei fram
    /* Hvor langt inn i svevet vi er, 0 -> 1 -> 0. Loeftet er sterkest paa
     * midten og null i endene, saa han ikke sparker foten opp i det den skal
     * lande, og ikke river den los i det den nettopp har landet. */
    const u = Math.sin(((Math.atan2(Math.sin(f), Math.cos(f)) / Math.PI) + 1) % 1
                       * Math.PI);

    for (const [fot, laar, sving] of
         [["fotV", "laarV", svingV], ["fotH", "laarH", !svingV]]) {
      const k = this.kollidere[fot];
      if (k) k.setFriction(sving ? g.svevFriksjon : FYS.gulv.fotFriksjon);
      if (!sving) continue;

      /* ## Beinet loeftes fra HOFTA, ikke dyttes opp fra foten
       *
       * Foerste forsok la 22 N under foten. Maalt over en hel skrittsyklus:
       * foten stod paa 0.032 m hele veien, mens laarets hoyde SANK fra 0.204
       * til 0.182 naar kneet boyde seg. Han huket seg ned i stedet for aa ta et
       * skritt - beinet kortet seg av, og siden foten laa an mot gulvet, var
       * det kroppen som maatte gi etter.
       *
       * Et bein veier 2.35 kg (laar 0.95 + legg 0.80 + fot 0.60) = 32.9 N. Skal
       * det klare av bakken, maa noe baere hele den vekten ovenfra - det er
       * nettopp det hofta gjor naar man gaar. Loeftet paa foten blir staaende
       * som et tillegg, saa taa-enden ikke henger etter og subber. */
      this.kropper[laar].applyImpulse(
        { x: 0, y: u * g.hoftehiv * dt, z: 0 }, true);
      this.kropper[fot].applyImpulse(
        { x: 0, y: u * g.loeft * dt, z: 0 }, true);
    }
  }

  /* Naar han slutter aa gaa, maa begge foettene faa grepet tilbake - ellers
   * staar han igjen paa en fot som sklir. */
  _nullstillFotfriksjon() {
    for (const navn of FOETTER) {
      const k = this.kollidere[navn];
      if (k) k.setFriction(FYS.gulv.fotFriksjon);
    }
  }

  /* Bein- og armvinkler for skrittfasen, i HANS eget rom (vendingen legges paa
   * i `_byggMaalpositur`). Armene svinger motsatt av beinet paa samme side -
   * det er den ene detaljen som mest av alt faar gange til aa se ekte ut. */
  _gangepositur(q) {
    const g = FYS.gange;
    const f = this.gangFase * Math.PI * 2;
    const sv = Math.sin(f);          // venstre bein: fram naar sv > 0
    const sh = -sv;                  // hoyre gaar i motfase

    /* Kneet boyes bare mens beinet svinger FRAM. Et kne som boyer seg i
     * standfasen er nettopp det som ser ut som at han sklir. */
    const kne = (s) => Math.max(0, s) * g.kne;

    q.laarV = fraEuler(-sv * g.hofte, 0, 0);
    q.laarH = fraEuler(-sh * g.hofte, 0, 0);
    q.leggV = fraEuler(-sv * g.hofte + kne(sv), 0, 0);
    q.leggH = fraEuler(-sh * g.hofte + kne(sh), 0, 0);
    /* Foten holdes vannrett uansett hva laaret gjor, saa han lander flatt. */
    q.fotV = fraEuler(0, 0, 0);
    q.fotH = fraEuler(0, 0, 0);

    q.overarmV = fraEuler(-sh * g.arm, 0, 0.03);
    q.overarmH = fraEuler(-sv * g.arm, 0, -0.03);
    q.underarmV = fraEuler(-sh * g.arm * 0.6 + 0.15, 0, 0.02);
    q.underarmH = fraEuler(-sv * g.arm * 0.6 + 0.15, 0, -0.02);

    /* Torsoen lener seg framover hele tiden, og vugger litt i takt. */
    q.torso = fraEuler(-g.lut + Math.sin(f * 2) * 0.03, 0, 0);
    return q;
  }

  /* ── Maalposituren ──────────────────────────────────────────────────────
   *
   * Hva han PROEVER aa gjore. Fysikken avgjor hva som faktisk skjer.
   */
  settPositur(navn) {
    if (this.positur === navn) return;
    this.positur = navn;
    this.positurTid = 0;
  }

  _byggMaalpositur() {
    let navn = this.positur;
    /* Ligger han nede, proever han aa komme seg opp - uansett hva han holdt
     * paa med. Eieren §13: «Hvis recovery feiler: proev igjen. Det gjor feil
     * morsomme.» */
    if (this.tilstand === FYSISK.NEDE || this.tilstand === FYSISK.REISER) {
      navn = this.opprett() < -0.2 ? "reisFraMage" : "reisFraRygg";
    } else if (this.tilstand === FYSISK.I_LUFTA
               || this.tilstand === FYSISK.GREPET) {
      navn = "lufta";
    } else if (this.tilstand === FYSISK.FALLER) {
      navn = "fall";
    }

    const p = POSITURER[navn] || POSITURER.staa;
    const q = blandPositur(p, this.positurTid, fraEuler);

    /* Gaar han, overstyres bein, armer og torso av skrittfasen. */
    if (this.gaarMot !== null && (this.tilstand === FYSISK.STABIL
        || this.tilstand === FYSISK.BALANSERER || this.tilstand === FYSISK.GAAR)) {
      this._gangepositur(q);
    }

    /* Hodet ser mot et punkt hvis vi har ett. Eieren §21: «Bruk en begrenset
     * target rotation + spring. Dermed folger hodet litt forsinket.» Fjaeren er
     * PD-regulatoren; her setter vi bare maalet. */
    if (this.hodeMaal && q.hode) {
      const h = this.kropper.hode.translation();
      const vinkel = Math.atan2(this.hodeMaal.x - h.x, 0.6);
      const nikk = Math.atan2(-(this.hodeMaal.y - h.y), 0.6);
      q.hode = fraEuler(
        Math.max(-0.5, Math.min(0.5, nikk)),
        Math.max(-0.8, Math.min(0.8, vinkel)), 0);
    }

    /* Legg vendingen paa til slutt. Positurene er skrevet som om han staar rett
     * fram; her flyttes de over i verdensrommet han faktisk staar i. Rekkefolgen
     * er `vending * positur` og ikke omvendt: da dreies posituren SOM HELHET om
     * den loddrette aksen, i stedet for at hvert lem faar en ekstra egenrotasjon
     * om sin egen akse. */
    if (Math.abs(this.retning) > 1e-4) {
      const halv = this.retning / 2;
      const v = { x: 0, y: Math.sin(halv), z: 0, w: Math.cos(halv) };
      for (const navn of Object.keys(q)) q[navn] = ganger(v, q[navn]);
    }
    return q;
  }

  /* Hele ragdollen ute av et omraade? Eieren §17: «Naar hele ragdollens
   * bounding box er utenfor: despawn.» */
  heltUtenfor(margin) {
    for (const rb of Object.values(this.kropper)) {
      const p = rb.translation();
      if (p.x > -margin && p.x < this.bredde + margin && p.y > -margin) {
        return false;
      }
    }
    return true;
  }

  fjern() {
    this.hendelser.free();
    this.verden.free();
  }
}
