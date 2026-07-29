/* Broen mellom fysikken og det du ser: løse mesher, ett fullskjerms lerret,
 * og en peker som griper kroppsdeler.
 *
 * Eieren 26.07.2026, §7: «Pointer/touch raycast mot kroppsdeler ... IKKE flytt
 * hele Tobias.»
 *
 * ## Hvorfor delene ikke henger sammen i Three
 *
 * I den forrige Tobias var meshene et hierarki: hodet under torsoen, haanden
 * under armen. Her er de FJORTEN LOESE objekter, hver med sin egen posisjon og
 * rotasjon lest rett fra sin rigid body. Hierarkiet finnes bare i fysikken.
 *
 * Det er ikke en forenkling - det er hele forskjellen. Rives armen av gaarde av
 * en finger, foelger meshen fordi KROPPEN flyttet seg, ikke fordi noen skrev en
 * animasjon for det.
 *
 * ## Fullskjerm
 *
 * Lerretet dekker hele viewporten (§17: «Behandle bunnen av viewport som fysisk
 * gulv»). Det er `pointer-events: none`, saa sida under er uberoert; bare naar
 * en stråle treffer en kroppsdel slaas de paa, og bare mens man holder.
 */

import { FYS } from "./konfig.js";
import { GRIPBARE } from "./skjelett.js";

/* Samme geometrier som fysikken bruker, saa det du ser er det som simuleres. */
function byggDel(THREE, navn, d, materialer) {
  let g;
  if (d.boks) {
    /* Avrundet: en skalert kule leser som «rund og litt chubby», og
     * kollideren er uansett en kasse. */
    g = new THREE.SphereGeometry(0.5, 18, 18);
    g.scale(d.boks[0] * 2.1, d.boks[1] * 2.1, d.boks[2] * 2.1);
  } else if (d.h) {
    g = new THREE.CapsuleGeometry(d.r, d.h * 2, 6, 12);
  } else {
    g = new THREE.SphereGeometry(d.r, 18, 18);
  }
  /* Bare leggen er moerk. Utkastet gjorde underarmen moerk ogsaa, og da ble
   * armen stripete - moerk skulder, lys overarm, moerk underarm, lys haand -
   * i stedet for én lem. Paa beina leser det motsatte som en stoevel, og der
   * blir det staaende. */
  const erLedd = navn.startsWith("legg");
  const m = new THREE.Mesh(g, erLedd ? materialer.ledd : materialer.hud);
  m.name = navn;

  /* Skulderkule. Den finnes ikke i fysikken - den er ren pynt, og den staar her
   * fordi den staar i den Tobias eieren allerede har godkjent (`modell.js`).
   * Uten den slutter torsoen og armen begynner med et lite hakk imellom, fordi
   * torsoen er smalere oppe der skulderen sitter enn nede ved magen. Kula
   * dekker overgangen, og gir samtidig armfestet en synlig «det er HER den
   * dreier»-markoer. */
  if (navn.startsWith("overarm")) {
    const kule = new THREE.Mesh(
      new THREE.SphereGeometry(0.048, 14, 14), materialer.ledd);
    kule.position.y = d.h + d.r;   // toppen av kapselen = skulderleddet
    m.add(kule);
  }
  return m;
}

export class Visning {
  constructor(THREE, RAPIER, ragdoll, Ansikt, farger) {
    this.THREE = THREE;
    this.R = RAPIER;
    this.rag = ragdoll;
    this.skala = FYS.pikslerPerMeter;

    this.scene = new THREE.Scene();
    /* Ortografisk kamera: da er skjermkoordinater og verdenskoordinater
     * proporsjonale, og en kroppsdel paa x = 3 m havner alltid paa samme
     * piksel. Med perspektiv ville dybden gjort omregningen tvetydig. */
    this.kamera = new THREE.OrthographicCamera(-1, 1, 1, -1, -50, 50);
    this.settStorrelse(innerWidth, innerHeight);

    this.scene.add(new THREE.HemisphereLight(0xdfe8ff, 0x2a2f3a, 1.6));
    const sol = new THREE.DirectionalLight(0xffffff, 1.5);
    sol.position.set(2, 4, 3);
    this.scene.add(sol);
    const kant = new THREE.DirectionalLight(farger.lys, 0.5);
    kant.position.set(-3, 1, -2);
    this.scene.add(kant);

    this.mat = {
      hud: new THREE.MeshStandardMaterial({
        color: farger.kropp, roughness: 0.42, metalness: 0.04 }),
      ledd: new THREE.MeshStandardMaterial({
        color: farger.ledd, roughness: 0.35, metalness: 0.5 }),
      skjerm: new THREE.MeshStandardMaterial({
        color: farger.skjerm, roughness: 0.08, metalness: 0.2 }),
    };

    this.deler = {};
    for (const [navn, d] of Object.entries(FYS.deler)) {
      const m = byggDel(THREE, navn, d, this.mat);
      this.scene.add(m);
      this.deler[navn] = m;
    }

    /* Ansiktet henger paa hodet - det ene stedet et foreldre/barn-forhold er
     * riktig, fordi displayet ER hodet. */
    this.ansikt = new Ansikt(THREE, farger);
    const hode = this.deler.hode;
    const display = new THREE.Mesh(
      new THREE.SphereGeometry(0.5, 16, 16), this.mat.skjerm);
    display.geometry.scale(0.34, 0.28, 0.12);
    display.position.z = 0.16;
    hode.add(display);
    const trekk = new THREE.Mesh(
      new THREE.PlaneGeometry(0.30, 0.24),
      new THREE.MeshBasicMaterial({
        map: this.ansikt.tekstur, transparent: true, depthWrite: false }));
    trekk.position.z = 0.225;
    hode.add(trekk);

    this.stråle = new THREE.Raycaster();
    this.pekervektor = new THREE.Vector2();

    /* Forrige fysikktilstand, til interpolasjon. Se `synk()`. */
    this.forrige = {};
    this._q0 = new THREE.Quaternion();
    this._q1 = new THREE.Quaternion();
    for (const navn of Object.keys(FYS.deler)) {
      const rb = this.rag.kropper[navn];
      const p = rb.translation(); const q = rb.rotation();
      this.forrige[navn] = {
        x: p.x, y: p.y, z: p.z, qx: q.x, qy: q.y, qz: q.z, qw: q.w };
    }
  }

  settStorrelse(bp, hp) {
    this.bp = bp; this.hp = hp;
    const bm = bp / this.skala;
    const hm = hp / this.skala;
    const k = this.kamera;
    k.left = 0; k.right = bm; k.top = hm; k.bottom = 0;
    k.position.set(0, 0, 10);
    k.updateProjectionMatrix();
  }

  /* Skjerm -> verden. Y snus: skjermen teller nedover, fysikken oppover. */
  tilVerden(px, py) {
    return { x: px / this.skala, y: (this.hp - py) / this.skala, z: 0 };
  }

  /* Fysikktilstanden er nettopp lagret som «forrige». Kalles av loopen RETT
   * FOER fysikkstegene, saa interpolasjonen har to punkter aa gaa mellom. */
  merkForrige() {
    for (const [navn, f] of Object.entries(this.forrige)) {
      const rb = this.rag.kropper[navn];
      const p = rb.translation(); const q = rb.rotation();
      f.x = p.x; f.y = p.y; f.z = p.z;
      f.qx = q.x; f.qy = q.y; f.qz = q.z; f.qw = q.w;
    }
  }

  /* Kopier posisjon og rotasjon fra hver rigid body til sin mesh.
   *
   * ## Hvorfor det interpoleres
   *
   * Fysikken gaar i FASTE steg paa 1/120 s; skjermen tegner naar den vil, ofte
   * 1/60. Leser man raa fysikktilstand hver frame, faar man to fysikksteg i én
   * frame, saa null, saa to igjen - og det synes som smaa rykk selv naar
   * simuleringen er helt jevn.
   *
   * `alfa` er hvor langt inn i det NESTE steget vi er (`rest / steg`), og
   * meshen legges mellom forrige og naavaerende tilstand. Det er det samme
   * grepet spillmotorer bruker, og det er hele forskjellen mellom «riktig» og
   * «smooth».
   */
  synk() {
    const alfa = Math.max(0, Math.min(1, this.rag.rest / FYS.steg));
    for (const [navn, mesh] of Object.entries(this.deler)) {
      const rb = this.rag.kropper[navn];
      const p = rb.translation();
      const q = rb.rotation();
      const f = this.forrige[navn];
      mesh.position.set(
        f.x + (p.x - f.x) * alfa,
        f.y + (p.y - f.y) * alfa,
        f.z + (p.z - f.z) * alfa,
      );
      this._q0.set(f.qx, f.qy, f.qz, f.qw);
      this._q1.set(q.x, q.y, q.z, q.w);
      mesh.quaternion.copy(this._q0).slerp(this._q1, alfa);
    }
  }

  /* Hvilken kroppsdel ligger under pekeren? Returnerer navnet, eller null.
   * Eieren §7: «Pointer/touch raycast mot kroppsdeler.» */
  delUnder(px, py) {
    this.pekervektor.x = (px / this.bp) * 2 - 1;
    this.pekervektor.y = -(py / this.hp) * 2 + 1;
    this.stråle.setFromCamera(this.pekervektor, this.kamera);
    const treff = this.stråle.intersectObjects(Object.values(this.deler), false);
    for (const t of treff) {
      if (GRIPBARE.includes(t.object.name)) return t.object.name;
    }
    return null;
  }

  fjern() {
    for (const m of Object.values(this.deler)) {
      m.geometry.dispose();
    }
    for (const m of Object.values(this.mat)) m.dispose();
    this.ansikt.fjern();
  }
}
