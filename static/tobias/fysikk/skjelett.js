/* Skjelettet: rigid bodies, collidere og ledd.
 *
 * Eieren 26.07.2026, §2-3. Fjorten kropper, tretten ledd.
 *
 *              HODE
 *               |  nakke (kule)
 *             TORSO
 *      skulder /   \ skulder        hofte /   \ hofte
 *        OVERARM     OVERARM        LAAR      LAAR
 *   albue |               | albue  kne |        | kne
 *        UNDERARM   UNDERARM        LEGG      LEGG
 *  haandledd |           |  ankel |        | ankel
 *          HAAND    HAAND          FOT       FOT
 *
 * ## Hvorfor primitiver og ikke meshen
 *
 * Eieren §2: «Ikke bruk mesh-geometrien direkte som komplisert collider.»
 * Grunnen er ikke bare ytelse: en konveks mesh-collider paa en kapselformet
 * arm gir hakete kontaktpunkter, og ragdollen begynner aa dirre. Kapsler og
 * kuler har analytiske kontakter og staar helt rolig.
 *
 * ## Hvorfor leddgrensene IKKE er harde leddstopp
 *
 * Rapier kan begrense et kuleledd, men et hardt stopp gir et rykk naar man
 * treffer det - og eieren ba om at han skal vaere «litt floppy». Grensene i
 * `FYS.ledd` haandheves derfor mykt av PD-regulatoren i `positur.js`. Hengsler
 * (albue, kne) faar ekte grenser, fordi et kne som boeyer feil vei ser oedelagt
 * ut og ikke kloenete.
 */

import { FYS } from "./konfig.js";

/* Leddene: [forelder, barn, type, hvor].
 *
 * `hvor` er ETT punkt, oppgitt paa én av to maater:
 *
 *   0.42          - andel mellom de to delenes SENTRE (0.5 = midt imellom)
 *   [x, y, z]     - eksplisitt verdenspunkt, i samme rom som `FYS.deler`
 *
 * Begge ankrene regnes ut av det ene punktet, i `ankre()` under.
 *
 * ## Hvorfor ankrene ikke staar her som to tall
 *
 * Foerste utkast hadde haandskrevne ankre for begge sider av hvert ledd. De
 * stemte ikke: hofta hadde forelderankeret paa verdenshoyde 0.265 og
 * barneankeret paa 0.280, kneet 0.135 mot 0.170. Solveren dro dem mot hverandre
 * fra foerste frame, beina foldet seg sammen, og Tobias sank ned i en haug -
 * maalt 26.07.2026: laar paa 0.057 m der de skulle staatt i 0.21, med foettene
 * OVER laarene.
 *
 * Derfor er det fortsatt ETT punkt som skrives, aldri to. Den eksplisitte
 * formen endrer bare HVOR punktet ligger, ikke garantien om at de to ankrene
 * beskriver samme sted.
 *
 * ## Hvorfor armene bruker den eksplisitte formen
 *
 * `andel` kan bare treffe punkter paa linja mellom to sentre. For hofta og
 * kneet er det riktig - de sitter mellom delene. Skulderen gjor ikke det: den
 * skal sitte i TOPPEN av overarmen, oppe paa siden av torsoen, saa armen henger
 * NED fra leddet. Med `andel` havnet den midt inne i torsoen paa hoyde med
 * armens midte, og armen hang fra sida si i stedet. Se `FYS.deler` for hva det
 * gjorde med utseendet. */
const LEDD = [
  ["torso", "hode", "nakke", 0.5],

  /* Skulderen sitter hoyt oppe paa siden av torsoen, i toppen av overarmen.
   * Albuen og haandleddet ligger midt i overlappen mellom delene (se
   * `FYS.deler`), ikke paa tuppene - derfor er ikke tallene helt de samme som
   * kapselendene. */
  ["torso", "overarmV", "skulder", [-0.215, 0.530, 0.03]],
  ["torso", "overarmH", "skulder", [0.215, 0.530, 0.03]],
  ["overarmV", "underarmV", "albue", [-0.215, 0.395, 0.03]],
  ["overarmH", "underarmH", "albue", [0.215, 0.395, 0.03]],
  ["underarmV", "haandV", "haandledd", [-0.215, 0.295, 0.03]],
  ["underarmH", "haandH", "haandledd", [0.215, 0.295, 0.03]],

  ["torso", "laarV", "hofte", 0.55],
  ["torso", "laarH", "hofte", 0.55],
  ["laarV", "leggV", "kne", 0.5],
  ["laarH", "leggH", "kne", 0.5],
  ["leggV", "fotV", "ankel", 0.55],
  ["leggH", "fotH", "ankel", 0.55],
];

/* Ett verdenspunkt, uttrykt i begge kroppenes lokale rom. Siden begge starter
 * uten rotasjon, er det bare en subtraksjon - men det er DEN subtraksjonen som
 * garanterer at de to ankrene beskriver samme punkt. */
function ankre(f, b, hvor) {
  const pf = { x: f.x || 0, y: f.y, z: f.z || 0 };
  const pb = { x: b.x || 0, y: b.y, z: b.z || 0 };
  const p = Array.isArray(hvor)
    ? { x: hvor[0], y: hvor[1], z: hvor[2] }
    : {
        x: pf.x + (pb.x - pf.x) * hvor,
        y: pf.y + (pb.y - pf.y) * hvor,
        z: pf.z + (pb.z - pf.z) * hvor,
      };
  return [
    { x: p.x - pf.x, y: p.y - pf.y, z: p.z - pf.z },
    { x: p.x - pb.x, y: p.y - pb.y, z: p.z - pb.z },
  ];
}

/* Hvilken PD-gruppe hver del hoerer til. Styrer stivhet og demping. */
export const GRUPPE = {
  torso: "torso", hode: "hode",
  overarmV: "arm", overarmH: "arm", underarmV: "arm", underarmH: "arm",
  haandV: "haand", haandH: "haand",
  laarV: "bein", laarH: "bein", leggV: "bein", leggH: "bein",
  fotV: "fot", fotH: "fot",
};

export const FOETTER = ["fotV", "fotH"];

/* Delene brukeren kan gripe. Eieren §18: «Brukeren kan ta Tobias i hodet, arm,
 * haand, torso, bein, fot.» Alle fjorten er gripbare - det er nettopp poenget
 * at ingen kombinasjon er «ikke programmert». */
export const GRIPBARE = Object.keys(GRUPPE);

export function byggSkjelett(RAPIER, verden, x0, y0) {
  const kropper = {};
  const kollidere = {};

  for (const [navn, d] of Object.entries(FYS.deler)) {
    const rbd = RAPIER.RigidBodyDesc.dynamic()
      .setTranslation(x0 + (d.x || 0), y0 + d.y, d.z || 0)
      .setLinearDamping(FYS.demping.lineaer)
      /* Armene demper mer enn resten - se `FYS.demping.vinkelArm` for maalingen
       * som ligger bak. Beina maa IKKE ha det: hoy demping der gjor skrittet
       * tregt og han slutter aa gaa. */
      .setAngularDamping(GRUPPE[navn] === "arm" || GRUPPE[navn] === "haand"
        ? FYS.demping.vinkelArm : FYS.demping.vinkel)
      /* Kontinuerlig kollisjonsdeteksjon paa de smaa, raske delene: uten den
       * kan en haand som kastes gaa TVERS GJENNOM gulvet paa én frame. */
      .setCcdEnabled(true);
    const rb = verden.createRigidBody(rbd);

    let cd;
    if (d.boks) cd = RAPIER.ColliderDesc.cuboid(...d.boks);
    else if (d.h) cd = RAPIER.ColliderDesc.capsule(d.h, d.r);
    else cd = RAPIER.ColliderDesc.ball(d.r);

    const erFot = navn.startsWith("fot");
    cd.setMass(d.masse)
      .setFriction(erFot ? FYS.gulv.fotFriksjon : FYS.gulv.kroppFriksjon)
      .setRestitution(erFot ? 0.02 : FYS.gulv.kroppSprett)
      /* Alle deler i samme gruppe kolliderer med verden, men IKKE med
       * hverandre. Uten dette skyver naboledd hverandre fra hverandre og
       * ragdollen rister seg selv i stykker. */
      .setCollisionGroups(0x0002_FFFD)
      .setActiveEvents(RAPIER.ActiveEvents.COLLISION_EVENTS);

    kollidere[navn] = verden.createCollider(cd, rb);
    kropper[navn] = rb;
  }

  const ledd = [];
  for (const [f, b, type, hvor] of LEDD) {
    const spek = FYS.ledd[type];
    const [a1, a2] = ankre(FYS.deler[f], FYS.deler[b], hvor);
    let data;
    if (spek.type === "hengsel") {
      data = RAPIER.JointData.revolute(
        a1, a2,
        { x: spek.akse[0], y: spek.akse[1], z: spek.akse[2] },
      );
      /* Ekte grenser her: et kne som boeyer feil vei ser oedelagt ut, ikke
       * kloenete. */
      data.limitsEnabled = true;
      data.limits = [spek.min, spek.maks];
    } else {
      data = RAPIER.JointData.spherical(a1, a2);
    }
    const j = verden.createImpulseJoint(data, kropper[f], kropper[b], true);
    ledd.push({ navn: `${f}->${b}`, type, j, forelder: f, barn: b });
  }

  return { kropper, kollidere, ledd };
}

/* Gulvet og de to veggene. Eieren §17: «Behandle bunnen av viewport som fysisk
 * gulv.» Veggene staar langt utenfor skjermen, saa han KAN kastes ut - de er
 * der bare for at han ikke skal falle uendelig langt vekk i x. */
export function byggVerden(RAPIER, verden, bredde) {
  const gulv = verden.createRigidBody(
    RAPIER.RigidBodyDesc.fixed().setTranslation(0, -0.05, 0));
  verden.createCollider(
    RAPIER.ColliderDesc.cuboid(bredde * 3, 0.05, 3)
      .setFriction(FYS.gulv.friksjon)
      .setRestitution(FYS.gulv.sprett),
    gulv,
  );
  /* En usynlig plate bak og foran, saa han holder seg i planet vi ser. Uten
   * dem roterer han ut i z og blir borte i dybden. */
  for (const z of [-0.55, 0.55]) {
    const v = verden.createRigidBody(
      RAPIER.RigidBodyDesc.fixed().setTranslation(0, 2, z));
    verden.createCollider(
      RAPIER.ColliderDesc.cuboid(bredde * 3, 4, 0.05).setFriction(0.02), v);
  }
  return gulv;
}
