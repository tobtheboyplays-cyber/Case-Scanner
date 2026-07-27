/* Livet hans: hva han finner paa naar ingen roerer ham.
 *
 * ## Hvorfor dette er saa lite
 *
 * Fristelsen er aa skrive en oppfoerselsmotor her - tilstander for «gaar»,
 * «faller», «reiser seg», «blir kastet». Alt det finnes allerede, i fysikken,
 * og det er hele poenget med systemet. Eieren 26.07.2026:
 *
 *   «Hvis jeg gjor noe utvikleren ikke eksplisitt har programmert en animasjon
 *    for, skal Tobias fortsatt reagere troverdig fordi fysikksystemet
 *    haandterer situasjonen.»
 *
 * Denne fila bestemmer derfor bare TO ting: hvor han har lyst til aa gaa, og
 * hvilket fjes han har. Alt annet - at han snubler paa veien, at han lander paa
 * ryggen, at han bruker fem sekunder paa aa komme seg opp igjen - er noe
 * ragdollen finner ut av selv.
 *
 * ## «En soet forstyrrelse»
 *
 * Eieren 27.07.2026: «hele poenget er at han skal vaere en soet forstyrrelse»,
 * og «gjor litt mer av seg». Det er styringen for hvor ofte han finner paa noe.
 * Grensa gaar ved at han ikke skal MASE: han holder seg nede i det nederste
 * baandet av vinduet, han sier ingenting, og han staar stille i lange nok
 * perioder til at man kan lese en sak ferdig.
 */

import { FYSISK } from "./ragdoll.js";
import { UTTRYKK } from "../ansikt.js";

/* Hvor lenge han staar i ro for han finner paa noe. Kortere enn foerste utgave
 * (2.5-7.0 s): eieren ba om at han gjor mer av seg. */
const PAUSE = [1.6, 4.5];
/* Hvor ofte han gjor et lite paafunn - vinker, ser seg rundt, strekker seg. */
const PAAFUNN = [5, 13];
/* ## Hva han gjor hvis ingenting skjer
 *
 * Eieren 27.07.2026: «se hva han gjor hvis ingenting skjer».
 *
 * Maalt over fem minutter uten input i foerste utgave: han gikk 171 sekunder og
 * sto 128, i det uendelige, og sovnet aldri. SOVN-fjeset var i praksis doed kode
 * - `rolig` ble nullstilt hver gang han fant paa noe selv, saa telleren naadde
 * aldri fram.
 *
 * Feilen var hva som ble maalt. At HAN gaar en tur er ikke at det skjer noe;
 * det som teller er om NOEN har roert ham. Naa er det tida siden siste
 * beroering som avgjor, og da faar tomgangen en retning: han roer seg mindre,
 * setter seg til slutt, og sovner. Ett klikk vekker ham.
 *
 * Det er ogsaa det snilleste for en journalist som leser: figuren nederst paa
 * sida roer paa seg mens du er der, og legger seg naar du ikke er det. */
const DOVNER = 55;        // s uten beroering for han begynner aa roe seg
const SOVNER = 95;        // s uten beroering for han sovner

const mellom = (par) => par[0] + Math.random() * (par[1] - par[0]);
const velg = (liste) => liste[Math.floor(Math.random() * liste.length)];

export class Liv {
  constructor(ragdoll, bredde) {
    this.rag = ragdoll;
    this.bredde = bredde;
    this.tilNeste = mellom(PAUSE);
    this.tilPaafunn = mellom(PAAFUNN);
    this.blunkOm = 2 + Math.random() * 4;
    this.blunk = 0;
    this.uttrykk = UTTRYKK.NORMAL;
    this.paafunnTid = 0;
    this.rolig = 0;                 // hvor lenge ingenting har hendt
    /* Kortvarige fjes som overstyrer alt: {uttrykk, tid}. */
    this.reaksjon = null;
    this._forrigeTilstand = FYSISK.STABIL;
    this.uttrykkIRo = null;
    this._maksSpinn = 0;
    this._varGrepet = false;
    this.sidenRoert = 0;
  }

  /* Kalles av verten naar noen faktisk roerer ham. Vekker ham. */
  roert() {
    this.sidenRoert = 0;
    this.sover = false;
  }

  /* Musepekeren: han ser paa den. Null naar pekeren forlater vinduet. */
  seMot(punkt) { this.rag.hodeMaal = punkt; }

  /* Sett et fjes som varer en liten stund og overstyrer resten. */
  reager(uttrykk, sekunder) {
    this.reaksjon = { uttrykk, tid: sekunder };
  }

  oppdater(dt) {
    const r = this.rag;
    const t = r.tilstand;
    /* Forrige tilstand maa oppdateres HER, ikke nederst: funksjonen har flere
     * tidlige returer, og med oppdateringen til slutt ville `forrige` blitt
     * staaende paa den samme verdien i alle de tilfellene. Da ville «han landet
     * nettopp» aldri blitt sant. */
    const forrige = this._forrigeTilstand;
    this._forrigeTilstand = t;

    /* Tida siden noen roerte ham. Blir han grepet eller kastet, nullstilles den
     * her ogsaa - ikke bare av `roert()` - saa han vaakner selv om verten skulle
     * glemme aa si fra. */
    if (t === FYSISK.GREPET || t === FYSISK.I_LUFTA) this.roert();
    else this.sidenRoert += dt;
    if (this.sidenRoert > SOVNER && !this.sover) {
      /* Stopp turen med det samme han sovner. Gjores det lenger nede, naas det
       * aldri: der er vi allerede returnert ut fordi tilstanden er `walking`. */
      this.sover = true;
      r.stoppGange();
    }
    const dovner = this.sidenRoert > DOVNER;

    /* ── Hendelser: fjes som svarer paa noe som FAKTISK skjedde ──────────── */

    /* Hvor mye han har rullet mens han var ute av kontroll. Har han snurret
     * skikkelig, blir han svimmel naar han lander - ikke fordi en teller sa
     * det, men fordi rotasjonen ble maalt. */
    if (t === FYSISK.I_LUFTA || t === FYSISK.FALLER || t === FYSISK.NEDE) {
      this._maksSpinn = Math.max(this._maksSpinn, r.spinn());
    }
    const landet = (t === FYSISK.STABIL || t === FYSISK.BALANSERER)
      && (forrige === FYSISK.I_LUFTA || forrige === FYSISK.FALLER);
    if (landet) {
      if (this._maksSpinn > 9) this.reager(UTTRYKK.SVIMMEL, 2.6);
      else if (this._maksSpinn > 1.0) this.reager(UTTRYKK.GLIS, 1.8);
      this._maksSpinn = 0;
    }
    if (t !== FYSISK.GREPET && t !== FYSISK.I_LUFTA && t !== FYSISK.FALLER
        && t !== FYSISK.NEDE) {
      this._maksSpinn *= 1 - Math.min(1, dt);
    }

    /* Sluppet forsiktig - altsaa klappet, ikke kastet. */
    if (this._varGrepet && t !== FYSISK.GREPET) {
      if (r.fart() < 1.2) this.reager(UTTRYKK.HJERTE, 2.2);
      this._varGrepet = false;
    }
    if (t === FYSISK.GREPET) this._varGrepet = true;

    /* Hardt smell. `sisteSmell` er maalt anslagsfart, ikke en gjetning. */
    if (r.sisteSmell > 3.2 && !this.reaksjon) this.reager(UTTRYKK.AU, 1.1);

    /* ── Fjeset ellers, lest av fysikken ─────────────────────────────────── */
    if (this.reaksjon) {
      this.reaksjon.tid -= dt;
      if (this.reaksjon.tid <= 0) this.reaksjon = null;
    }

    let u;
    if (this.reaksjon) u = this.reaksjon.uttrykk;
    else if (t === FYSISK.GREPET || t === FYSISK.I_LUFTA) u = UTTRYKK.PANIC;
    else if (t === FYSISK.FALLER || t === FYSISK.SNUBLER) u = UTTRYKK.PANIC;
    else if (t === FYSISK.NEDE) u = UTTRYKK.AU;
    else if (t === FYSISK.REISER) u = UTTRYKK.CURIOUS;
    /* Soevnen kommer FOER gange-fjeset: sovner han mens han er paa vei det
     * siste steget, skal han se sovende ut, ikke glad. */
    else if (this.sover) u = UTTRYKK.SLEEP;
    else if (t === FYSISK.GAAR) u = UTTRYKK.HAPPY;
    else u = this.uttrykkIRo || UTTRYKK.NORMAL;
    this.uttrykk = u;

    /* Blunk. Bare naar han er rolig - man blunker ikke mens man faller. */
    if (t === FYSISK.STABIL || t === FYSISK.BALANSERER) {
      this.blunkOm -= dt;
      if (this.blunkOm <= 0) {
        this.blunk = 0.16;
        this.blunkOm = 2 + Math.random() * 5;
      }
    }
    if (this.blunk > 0) this.blunk -= dt;

    /* ── Hva han finner paa ────────────────────────────────────────────────
     *
     * Bare naar han staar stoett. Ligger han nede, holder ragdollen allerede
     * paa med aa reise seg, og en ny beskjed om aa gaa ville avbrutt den. */
    if (t !== FYSISK.STABIL && t !== FYSISK.BALANSERER) {
      this.tilNeste = mellom(PAUSE);
      this.rolig = 0;
      return;
    }
    this.rolig += dt;

    if (this.paafunnTid > 0) {
      this.paafunnTid -= dt;
      if (this.paafunnTid <= 0) {
        r.settPositur("staa");
        this.uttrykkIRo = null;
      }
      return;
    }

    /* Et lite paafunn: han vinker, ser seg rundt, eller ser fornoeyd ut.
     * Ingen av dem flytter ham - de er der for at han ikke skal staa som en
     * statue mellom turene. */
    /* Sover han, staar han bare stille. Ingen positur - kroppen henger i sin
     * egen vekt, og det er nettopp derfor det ser ut som at han hviler. */
    if (this.sover) { r.stoppGange(); return; }

    this.tilPaafunn -= dt;
    if (this.tilPaafunn <= 0) {
      this.tilPaafunn = mellom(PAAFUNN);
      const hva = velg(["vinke", "vinke", "se seg rundt", "fornoeyd"]);
      if (hva === "vinke") {
        r.settPositur("vinke");
        this.paafunnTid = 1.7;
        this.uttrykkIRo = UTTRYKK.HAPPY;
      } else if (hva === "se seg rundt") {
        this.paafunnTid = 1.6;
        this.uttrykkIRo = UTTRYKK.CURIOUS;
      } else {
        this.paafunnTid = 1.4;
        this.uttrykkIRo = UTTRYKK.BLUNK;
      }
      this.rolig = 0;
      return;
    }

    if (r.gaarMot !== null) return;      // han er allerede paa vei et sted
    this.tilNeste -= dt;
    if (this.tilNeste > 0) return;
    /* Doevner han, gaar det lenger mellom turene - han roer seg mindre og
     * mindre i stedet for aa slutte brått. */
    this.tilNeste = mellom(PAUSE) * (dovner ? 4 : 1);
    this.rolig = 0;

    /* Et nytt sted aa gaa, minst en halv meter unna saa turen synes, og godt
     * innenfor kanten saa han ikke gaar rett ut av skjermen av seg selv. */
    const naa = this.rag.massesenter().x;
    const kant = 0.6;
    let maal = kant + Math.random() * Math.max(0.1, this.bredde - 2 * kant);
    if (Math.abs(maal - naa) < 0.5) maal = naa + (maal > naa ? 0.7 : -0.7);
    r.gaaMot(Math.max(kant, Math.min(this.bredde - kant, maal)));
  }
}
