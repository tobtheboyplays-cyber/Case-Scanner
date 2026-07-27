/* Active ragdoll: PD-regulatoren som drar kroppen mot en oensket positur.
 *
 * Eieren 26.07.2026, §4 - og han skrev formelen selv:
 *
 *     torque = poseError * stiffness - angularVelocity * damping;
 *
 * med tillegget «Ikke teleporter body parts til target. Bruk fysisk
 * kraft/torque.»
 *
 * Det er hele modulen. Resten er detaljene som gjor at den ikke eksploderer.
 *
 * ## Hva `poseError` faktisk er
 *
 * Feilen mellom to ROTASJONER er ikke en subtraksjon. Vi trenger den korteste
 * veien fra naavaerende orientering til maalet, uttrykt som en akse og en
 * vinkel - da blir dreiemomentet en vektor langs den aksen.
 *
 *     feil = maal * naavaerende⁻¹        (kvaternion)
 *     akse, vinkel = akseVinkel(feil)
 *     moment = akse * vinkel * stivhet - vinkelfart * demping
 *
 * ## De tre tingene som holder den stabil
 *
 * 1. **Korteste vei.** En kvaternion og dens negasjon er samme rotasjon, men
 *    den ene gir en vei paa 350° og den andre paa 10°. Uten `if (q.w < 0) q =
 *    -q` snurrer lemmene den lange veien rundt.
 * 2. **Momenttak.** En stor feil ganget med stivheten kan gi et moment som
 *    sender lemmet i bane. `FYS.positur.maksMoment` klipper det.
 * 3. **Myke leddgrenser.** Grensene i `FYS.ledd` haandheves som en EKSTRA
 *    fjaer naar leddet er utenfor omraadet, ikke som et hardt stopp. Eieren:
 *    «gjor dem litt myke. Han skal vaere litt floppy.»
 */

import { FYS } from "./konfig.js";
import { GRUPPE } from "./skjelett.js";

/* ── Kvaternionregning. Rapier gir oss {x,y,z,w}; vi trenger bare fire ting. */

function konj(q) {
  return { x: -q.x, y: -q.y, z: -q.z, w: q.w };
}

export function gang(a, b) {
  return {
    x: a.w * b.x + a.x * b.w + a.y * b.z - a.z * b.y,
    y: a.w * b.y - a.x * b.z + a.y * b.w + a.z * b.x,
    z: a.w * b.z + a.x * b.y - a.y * b.x + a.z * b.w,
    w: a.w * b.w - a.x * b.x - a.y * b.y - a.z * b.z,
  };
}

/* Kvaternion -> rotasjonsvektor (akse * vinkel). Dette ER `poseError`. */
export function feilvektor(naa, maal) {
  let d = gang(maal, konj(naa));
  /* Korteste vei. Uten denne linja gaar lemmet 350° i stedet for 10°. */
  if (d.w < 0) d = { x: -d.x, y: -d.y, z: -d.z, w: -d.w };
  const sin = Math.sqrt(d.x * d.x + d.y * d.y + d.z * d.z);
  if (sin < 1e-6) return { x: 0, y: 0, z: 0 };
  const vinkel = 2 * Math.atan2(sin, d.w);
  const k = vinkel / sin;
  return { x: d.x * k, y: d.y * k, z: d.z * k };
}

/* Kvaternion fra Euler (YXZ), som er det posituene er skrevet i. */
export function fraEuler(x, y, z) {
  const cx = Math.cos(x / 2), sx = Math.sin(x / 2);
  const cy = Math.cos(y / 2), sy = Math.sin(y / 2);
  const cz = Math.cos(z / 2), sz = Math.sin(z / 2);
  return {
    x: sx * cy * cz + cx * sy * sz,
    y: cx * sy * cz - sx * cy * sz,
    z: cx * cy * sz - sx * sy * cz,
    w: cx * cy * cz - sx * sy * sz,
  };
}

const lengde = (v) => Math.hypot(v.x, v.y, v.z);

/* Treghetsmomentet som ett tall. Rapier gir det som en vektor langs kroppens
 * hovedakser; for saa runde kropper som disse er de nesten like, og snittet er
 * godt nok. Gulvet paa 1e-4 hindrer deling paa noe naer null. */
function tregleik(rb) {
  const i = rb.principalInertia?.();
  if (!i) return 0.01;
  return Math.max(1e-4, (i.x + i.y + i.z) / 3);
}

/* ── Selve regulatoren ─────────────────────────────────────────────────────
 *
 * `maal` er {delnavn: kvaternion} i VERDENSROM. Kraften er `styrke` 0..1, som
 * balansekontrolleren skrur ned naar han holder paa aa falle - da skal fysikken
 * faa lov til aa vinne. Eieren: «60 % kontrollert karakter + 40 % ragdoll.»
 */
export function draModPositur(kropper, maal, styrke, dt) {
  const tak = FYS.positur.maksMoment;

  for (const [navn, rb] of Object.entries(kropper)) {
    const m = maal[navn];
    if (!m) continue;

    const gruppe = FYS.positur[GRUPPE[navn]] || FYS.positur.arm;
    const feil = feilvektor(rb.rotation(), m);
    const w = rb.angvel();

    /* Formelen eieren skrev, med treghetsmomentet som skala:
     *
     *     moment = I * (kp * feil - kd * vinkelfart)
     *
     * ## Hvorfor `I` maa vaere med, og hvorfor taket IKKE skal ha den
     *
     * Dette tok to runder aa faa riktig, og begge feilene er laererike:
     *
     * · Foerste utkast ganget med MASSEN. Feil stoerrelse: det er treghets-
     *   momentet, ikke massen, som avgjor hvor mye moment som trengs for en
     *   gitt vinkelakselerasjon.
     * · Andre utkast fjernet skaleringen helt og brukte absolutte newtonmeter.
     *   Da ble dempingen ustabil: `kd * dt / I` var rundt 50 for et lite lem,
     *   og alt over 1 betyr at dempeleddet SKYTER FORBI null hvert steg. I
     *   stedet for aa bremse, pumpet den energi inn - maalt 26.07.2026 ved at
     *   haanden steg opp over skulderen mens han skulle staa stille.
     *
     * Med `I` som faktor er `kp` og `kd` rene rad/s² og rad/s, og stabilitets-
     * kravet blir det vanlige: kritisk demping ved kd = 2*sqrt(kp), og
     * kd * dt < 1. Se tallene i konfig.js - de er valgt etter den regelen.
     *
     * TAKET er derimot en ekte kraftgrense i newtonmeter (hvor sterkt leddet
     * ER), og den skal ikke skaleres med noe som helst. */
    const I = tregleik(rb);
    let mx = (feil.x * gruppe.stivhet - w.x * gruppe.demping) * I * styrke;
    let my = (feil.y * gruppe.stivhet - w.y * gruppe.demping) * I * styrke;
    let mz = (feil.z * gruppe.stivhet - w.z * gruppe.demping) * I * styrke;

    /* Momenttak. En stor feil ganget med stivheten kan ellers sende lemmet i
     * bane, og da eksploderer hele ragdollen numerisk. */
    const l = Math.hypot(mx, my, mz);
    const grense = gruppe.tak ?? tak;
    if (l > grense) {
      const k = grense / l;
      mx *= k; my *= k; mz *= k;
    }

    rb.applyTorqueImpulse({ x: mx * dt, y: my * dt, z: mz * dt }, true);
  }
}

/* ── Myke leddgrenser ──────────────────────────────────────────────────────
 *
 * Kuleledd har ingen ekte grense i oppsettet vaart (se `skjelett.js` for
 * hvorfor). I stedet dyttes barnet tilbake naar vinkelen mellom det og
 * forelderen blir for stor - som en gummistrikk, ikke som en vegg.
 */
/* ## Strikken maa foelge de samme reglene som regulatoren
 *
 * Foerste utgave regnet momentet som `over * 14` - absolutte newtonmeter, uten
 * treghetsskalering og uten tak. For torsoen er det harmloest. For en haand er
 * det ikke: haanden er en kule paa 0.08 kg med treghetsmoment 1e-4, saa 35 Nm
 * blir 350 000 rad/s² - og siden strikken ikke har noen demping, sparker den
 * haanden forbi grensen paa den andre sida og gjor det igjen.
 *
 * Maalt 27.07.2026: begge hendene snurret vedvarende i 1000-3100 rad/s mens han
 * bare sto der. Det er nettopp «armene hans begynner aa riste overalt» - og det
 * var IKKE griping som utloeste det. Det ble synlig da armstivheten ble satt
 * ned for at armene skulle henge naturlig: med svakere regulator drev haanden
 * utenfor grensen, og da tok den udempede strikken over.
 *
 * Naa gjelder de samme tre reglene som i `draModPositur`: skaler med treghets-
 * momentet saa tallene betyr det samme for alle ledd, demp mot den relative
 * farten saa den ikke kan pumpe, og sett et tak. */
export function holdLeddgrenser(ledd, kropper, dt) {
  for (const l of ledd) {
    const spek = FYS.ledd[l.type];
    if (spek.type !== "kule") continue;
    const f = kropper[l.forelder];
    const b = kropper[l.barn];
    const rel = feilvektor(f.rotation(), b.rotation());
    const v = lengde(rel);
    if (v <= spek.grense) continue;

    /* Bare det som er UTENFOR grensen straffes. Da merkes ingenting saa lenge
     * han holder seg innenfor, og strikken strammer gradvis. */
    const over = v - spek.grense;
    const I = tregleik(b);
    const w = b.angvel();
    const wf = f.angvel();
    const k = -(over * FYS.ledd.grenseStivhet) / v;
    let mx = (rel.x * k - (w.x - wf.x) * FYS.ledd.grenseDemping) * I;
    let my = (rel.y * k - (w.y - wf.y) * FYS.ledd.grenseDemping) * I;
    let mz = (rel.z * k - (w.z - wf.z) * FYS.ledd.grenseDemping) * I;
    const lm = Math.hypot(mx, my, mz);
    if (lm > FYS.ledd.grenseTak) {
      const s = FYS.ledd.grenseTak / lm;
      mx *= s; my *= s; mz *= s;
    }
    b.applyTorqueImpulse({ x: mx * dt, y: my * dt, z: mz * dt }, true);
  }
}
