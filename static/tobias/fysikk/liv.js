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
 */

import { FYSISK } from "./ragdoll.js";
import { UTTRYKK } from "../ansikt.js";

/* Hvor lenge han staar i ro for han finner paa noe. */
const PAUSE = [2.5, 7.0];
const VINKEPAUSE = [11, 26];

const mellom = (par) => par[0] + Math.random() * (par[1] - par[0]);

export class Liv {
  constructor(ragdoll, bredde) {
    this.rag = ragdoll;
    this.bredde = bredde;
    this.tilNeste = mellom(PAUSE);
    this.tilVink = mellom(VINKEPAUSE);
    this.blunkOm = 2 + Math.random() * 4;
    this.blunk = 0;
    this.uttrykk = UTTRYKK.NORMAL;
    this.vinkeTid = 0;
  }

  /* Musepekeren: han ser paa den. Null naar pekeren forlater vinduet. */
  seMot(punkt) { this.rag.hodeMaal = punkt; }

  oppdater(dt) {
    const r = this.rag;
    const t = r.tilstand;

    /* ── Fjeset. Det leses av fysikken, ikke av hva vi «holder paa med». ──── */
    let u = UTTRYKK.NORMAL;
    if (t === FYSISK.GREPET) u = UTTRYKK.PANIC;
    else if (t === FYSISK.I_LUFTA) u = UTTRYKK.PANIC;
    else if (t === FYSISK.FALLER || t === FYSISK.SNUBLER) u = UTTRYKK.PANIC;
    else if (t === FYSISK.NEDE) u = UTTRYKK.CURIOUS;
    else if (t === FYSISK.REISER) u = UTTRYKK.CURIOUS;
    else if (t === FYSISK.GAAR) u = UTTRYKK.HAPPY;
    else if (r.sisteSmell > 1.5) u = UTTRYKK.SMUG;
    this.uttrykk = u;

    /* Blunk. Bare naar han er rolig - man blunker ikke mens man faller. */
    if (t === FYSISK.STABIL || t === FYSISK.BALANSERER) {
      this.blunkOm -= dt;
      if (this.blunkOm <= 0) { this.blunk = 0.16; this.blunkOm = 2 + Math.random() * 5; }
    }
    if (this.blunk > 0) this.blunk -= dt;

    /* ── Hva han finner paa ────────────────────────────────────────────────
     *
     * Bare naar han staar stoett. Ligger han nede, holder ragdollen allerede
     * paa med aa reise seg, og en ny beskjed om aa gaa ville avbrutt den. */
    if (t !== FYSISK.STABIL && t !== FYSISK.BALANSERER) {
      this.tilNeste = mellom(PAUSE);
      return;
    }

    if (this.vinkeTid > 0) {
      this.vinkeTid -= dt;
      if (this.vinkeTid <= 0) r.settPositur("staa");
      return;
    }

    this.tilVink -= dt;
    if (this.tilVink <= 0) {
      this.tilVink = mellom(VINKEPAUSE);
      this.vinkeTid = 1.7;
      r.settPositur("vinke");
      return;
    }

    if (r.gaarMot !== null) return;      // han er allerede paa vei et sted
    this.tilNeste -= dt;
    if (this.tilNeste > 0) return;
    this.tilNeste = mellom(PAUSE);

    /* Et nytt sted aa gaa, minst en halv meter unna saa turen synes, og godt
     * innenfor kanten saa han ikke gaar rett ut av skjermen av seg selv. */
    const naa = this.rag.massesenter().x;
    const kant = 0.6;
    let maal = kant + Math.random() * Math.max(0.1, this.bredde - 2 * kant);
    if (Math.abs(maal - naa) < 0.5) maal = naa + (maal > naa ? 0.7 : -0.7);
    r.gaaMot(Math.max(kant, Math.min(this.bredde - kant, maal)));
  }
}
