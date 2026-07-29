/* Roboten og kontorstolen, bygget av Three.js-geometrier.
 *
 * Eieren 26.07.2026: «Lag roboten programmatisk av enkle Three.js-geometrier
 * slik at vi ikke trenger en ekstern modell i foerste versjon.»
 *
 * Alt her er ren oppbygging - ingen animasjon. Modulen returnerer et objekt med
 * navngitte referanser (`hode`, `armV`, `beinH`, `antenne` …) som
 * tilstandsmaskinen animerer. Skillet er med vilje: skal noen bytte utseende
 * senere, roerer de bare denne fila.
 *
 * ## Enheter
 *
 * Roboten er bygget rundt hoyde 1.0 i verdensenheter, med foettene paa y=0.
 * Kameraet skalerer det til piksler. Da kan alle maal her leses som «andel av
 * robotens hoyde», og en stoerrelsesendring er én linje i konfigurasjonen.
 */

import { UTTRYKK, Ansikt } from "./ansikt.js";

/* Avrundet boks. Three har ingen innebygd, og en skarp kube ser hard ut paa en
 * figur som skal vaere «rund og litt chubby». Vi jukser med en kule som
 * skaleres - billigere enn ekte avrunding, og formen er den samme paa avstand. */
function rundBoks(THREE, b, h, d, segmenter = 20) {
  const g = new THREE.SphereGeometry(0.5, segmenter, segmenter);
  g.scale(b, h, d);
  return g;
}

export function byggRobot(THREE, farge) {
  const rot = new THREE.Group();

  const hud = new THREE.MeshStandardMaterial({
    color: farge.kropp, roughness: 0.42, metalness: 0.04,
  });
  const leddM = new THREE.MeshStandardMaterial({
    color: farge.ledd, roughness: 0.35, metalness: 0.55,
  });
  const skjermM = new THREE.MeshStandardMaterial({
    color: farge.skjerm, roughness: 0.08, metalness: 0.2,
  });
  const lysM = new THREE.MeshStandardMaterial({
    color: farge.lys, emissive: farge.lys, emissiveIntensity: 1.6,
    roughness: 0.3,
  });

  /* ── Kropp ─────────────────────────────────────────────────────────────── */
  /* «Rund og litt chubby»: bredere enn hoy i midjen, smalere mot skuldrene. */
  const torso = new THREE.Mesh(rundBoks(THREE, 0.46, 0.38, 0.36), hud);
  torso.position.y = 0.40;
  torso.castShadow = true;
  rot.add(torso);

  /* Navnet paa brystet. Tegnes paa et lite lerret; ingen font-fil aa laste. */
  const merke = document.createElement("canvas");
  merke.width = 256; merke.height = 64;
  const mc = merke.getContext("2d");
  mc.fillStyle = "rgba(0,0,0,0)";
  mc.fillRect(0, 0, 256, 64);
  mc.font = "bold 34px ui-sans-serif, system-ui, -apple-system, sans-serif";
  mc.textAlign = "center";
  mc.textBaseline = "middle";
  /* Foerste utkast brukte leddfargen. Paa en off-white kropp forsvant den
   * nesten helt - teksten var der, men ingen kunne lese den. */
  mc.fillStyle = "#5b636d";
  mc.letterSpacing = "5px";
  mc.fillText("TOBIAS", 128, 34);
  const merkeTex = new THREE.CanvasTexture(merke);
  merkeTex.colorSpace = THREE.SRGBColorSpace;
  const brystmerke = new THREE.Mesh(
    new THREE.PlaneGeometry(0.26, 0.066),
    new THREE.MeshBasicMaterial({ map: merkeTex, transparent: true }),
  );
  /* Merket maa ligge UTENFOR torsoens halvdybde, ellers forsvinner det inn i
   * kroppen. Da torsoen ble dypere (0.36 -> 0.40) ble teksten borte uten at
   * noe feilet - den var der, bare inni ham. */
  brystmerke.position.set(0, 0.00, 0.187);
  torso.add(brystmerke);

  /* ── Hode ──────────────────────────────────────────────────────────────── */
  const hode = new THREE.Group();
  hode.position.y = 0.66;
  rot.add(hode);

  const skalle = new THREE.Mesh(rundBoks(THREE, 0.44, 0.38, 0.40), hud);
  skalle.castShadow = true;
  hode.add(skalle);

  /* Ansiktsdisplayet: svart og blankt, litt buet ut. */
  const ansikt = new Ansikt(THREE, farge);
  const display = new THREE.Mesh(rundBoks(THREE, 0.35, 0.28, 0.12, 16), skjermM);
  display.position.z = 0.16;
  hode.add(display);

  const trekk = new THREE.Mesh(
    new THREE.PlaneGeometry(0.30, 0.24),
    new THREE.MeshBasicMaterial({
      map: ansikt.tekstur, transparent: true, depthWrite: false,
    }),
  );
  trekk.position.z = 0.225;
  hode.add(trekk);

  /* Oerer/hoyttalere paa sidene - bryter opp den runde formen. */
  for (const s of [-1, 1]) {
    const ore = new THREE.Mesh(
      new THREE.CylinderGeometry(0.06, 0.06, 0.035, 16), leddM);
    ore.rotation.z = Math.PI / 2;
    ore.position.set(s * 0.215, -0.01, 0);
    hode.add(ore);
  }

  /* ── Antenne ───────────────────────────────────────────────────────────── */
  /* Egen gruppe, fordi den skal henge etter kroppen (sekundaerbevegelse). */
  const antenne = new THREE.Group();
  antenne.position.set(0, 0.18, 0);
  hode.add(antenne);

  const stang = new THREE.Mesh(
    new THREE.CylinderGeometry(0.013, 0.017, 0.10, 10), leddM);
  stang.position.y = 0.05;
  antenne.add(stang);

  const kule = new THREE.Mesh(new THREE.SphereGeometry(0.045, 16, 16), lysM);
  kule.position.y = 0.115;
  antenne.add(kule);

  /* ── Armer ─────────────────────────────────────────────────────────────── */
  /* Hver arm henger fra en gruppe i skulderen, saa rotasjon skjer om skulderen
   * og ikke om armens midtpunkt. */
  function lagArm(side) {
    const g = new THREE.Group();
    /* Skulderen sitter LAVT og TETT inntil kroppen. Foerste utkast hadde den
     * paa 0.60 og 0.245 ut, og da laa de moerke skulderkulene rett ved siden
     * av hodet - de leste som skulderputer, ikke som armfester. */
    /* Litt lenger ut enn torsoens halvbredde (0.23), saa armene faktisk synes
     * i stedet for aa ligge begravd i magen. */
    g.position.set(side * 0.245, 0.52, 0.015);
    const skulder = new THREE.Mesh(new THREE.SphereGeometry(0.048, 14, 14), leddM);
    g.add(skulder);
    const arm = new THREE.Mesh(
      new THREE.CapsuleGeometry(0.050, 0.12, 6, 12), hud);
    arm.position.y = -0.105;
    arm.castShadow = true;
    g.add(arm);
    const haand = new THREE.Mesh(new THREE.SphereGeometry(0.058, 14, 14), hud);
    haand.position.y = -0.195;
    g.add(haand);
    rot.add(g);
    return g;
  }
  const armV = lagArm(-1);
  const armH = lagArm(1);

  /* ── Bein ──────────────────────────────────────────────────────────────── */
  function lagBein(side) {
    const g = new THREE.Group();
    g.position.set(side * 0.125, 0.22, 0);
    const hofte = new THREE.Mesh(new THREE.SphereGeometry(0.052, 14, 14), leddM);
    g.add(hofte);
    const bein = new THREE.Mesh(
      new THREE.CapsuleGeometry(0.062, 0.055, 6, 12), hud);
    bein.position.y = -0.075;
    bein.castShadow = true;
    g.add(bein);
    /* Foten stikker litt fram, saa han ser ut til aa staa og ikke sveve. */
    const fot = new THREE.Mesh(rundBoks(THREE, 0.14, 0.075, 0.19, 14), hud);
    fot.position.set(0, -0.155, 0.035);
    g.add(fot);
    rot.add(g);
    return g;
  }
  const beinV = lagBein(-1);
  const beinH = lagBein(1);

  return {
    rot, torso, hode, skalle, antenne, antenneKule: kule,
    armV, armH, beinV, beinH, ansikt, display,
    materialer: [hud, leddM, skjermM, lysM],
    teksturer: [merkeTex],
  };
}

/* ── Kontorstolen ──────────────────────────────────────────────────────────
 *
 * Eieren: «lage frem en liten kontorstol ... svart sete, rygg, base, smaa
 * hjul». Den lages én gang og gjenbrukes; `synlig` styrer om den vises.
 */
export function byggStol(THREE, farge) {
  const rot = new THREE.Group();
  const svart = new THREE.MeshStandardMaterial({
    color: farge.stol, roughness: 0.55, metalness: 0.15,
  });
  const metall = new THREE.MeshStandardMaterial({
    color: farge.stolMetall, roughness: 0.3, metalness: 0.8,
  });

  const sete = new THREE.Mesh(rundBoks(THREE, 0.42, 0.09, 0.40, 14), svart);
  sete.position.y = 0.30;
  rot.add(sete);

  const rygg = new THREE.Mesh(rundBoks(THREE, 0.40, 0.40, 0.09, 14), svart);
  rygg.position.set(0, 0.50, -0.17);
  rygg.rotation.x = -0.14;              // lett tilbakelent
  rot.add(rygg);

  const stamme = new THREE.Mesh(
    new THREE.CylinderGeometry(0.035, 0.045, 0.24, 12), metall);
  stamme.position.y = 0.15;
  rot.add(stamme);

  /* Fem armer med hjul, som en ekte kontorstol. */
  for (let i = 0; i < 5; i++) {
    const v = (i / 5) * Math.PI * 2;
    const arm = new THREE.Mesh(
      new THREE.BoxGeometry(0.035, 0.028, 0.22), metall);
    arm.position.set(Math.sin(v) * 0.10, 0.045, Math.cos(v) * 0.10);
    arm.rotation.y = v;
    rot.add(arm);
    const hjul = new THREE.Mesh(new THREE.SphereGeometry(0.035, 10, 10), svart);
    hjul.position.set(Math.sin(v) * 0.20, 0.032, Math.cos(v) * 0.20);
    rot.add(hjul);
  }

  rot.visible = false;
  return { rot, materialer: [svart, metall] };
}

export { UTTRYKK };
