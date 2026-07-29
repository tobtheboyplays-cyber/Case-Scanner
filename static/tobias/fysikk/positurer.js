/* Posituene: hva Tobias PROEVER aa gjore.
 *
 * Eieren 26.07.2026: «Ikke fake dette med en stor samling canned animations.»
 *
 * Det er nettopp derfor det er saa faa av dem, og de er saa enkle. En positur
 * er ikke en animasjon - den er ett sett vinkler kroppen dras mot. Hva som
 * FAKTISK skjer avgjores av fysikken, og den kan overstyre alt her.
 *
 * Prov aa telle: det finnes ingen «fall fra stolen», ingen «kastet ut av
 * skjermen», ingen «reis deg opp fra hoyre side». De situasjonene haandteres av
 * at kroppen har masse, ledd og et gulv.
 *
 * ## Formen
 *
 *   { del: [x, y, z] }                     - fast positur
 *   { del: [[t0, x,y,z], [t1, x,y,z]] }    - punkter i tid (sekunder)
 *
 * Vinkler er Euler i radianer, i VERDENSROM. At de er i verdensrom og ikke
 * relativt forelderen er et bevisst valg: da kan PD-regulatoren jobbe direkte
 * mot kroppens egen rotasjon uten aa kjede seg gjennom hierarkiet, og en arm
 * som har blitt slaatt bort blir dratt tilbake mot der den SKAL vaere - ikke
 * mot der forelderen tilfeldigvis peker.
 */

const N = [0, 0, 0];

export const POSITURER = {
  /* Staa. Nesten alt er null; det er tyngdekraften og balansen som gir
   * bevegelsen. */
  staa: {
    torso: N, hode: N,
    /* Armene henger rett ned - og det er nesten ingenting aa be om her, fordi
     * skulderen naa sitter i TOPPEN av overarmen (se `LEDD` i skjelett.js).
     * Da er loddrett ogsaa der tyngdekraften vil ha dem, og posituren trenger
     * bare aa bekrefte det.
     *
     * Foerste utkast ba om 0.16 rad ut med skulderen inne i torsoen. Da dro
     * tyngdekraften den ene veien og regulatoren den andre, og likevekten ble
     * 25° sprik uansett hva som stod her - noe man ikke kan skru seg ut av med
     * vinkler. De smaa restene under (0.02-0.03 rad, ca. 1.5°) er bare for at
     * han ikke skal se ut som en tinnsoldat. */
    overarmV: [0.02, 0, 0.03], overarmH: [0.02, 0, -0.03],
    underarmV: [0.03, 0, 0.02], underarmH: [0.03, 0, -0.02],
    haandV: N, haandH: N,
    laarV: N, laarH: N, leggV: N, leggH: N, fotV: N, fotH: N,
  },

  /* I lufta eller grepet: lemmene slipper opp og henger. Lav stivhet i
   * `FYS.positur` gjor resten. */
  lufta: {
    torso: N, hode: [-0.15, 0, 0],
    overarmV: [-0.8, 0, 0.6], overarmH: [-0.8, 0, -0.6],
    underarmV: [-0.5, 0, 0.3], underarmH: [-0.5, 0, -0.3],
    haandV: N, haandH: N,
    laarV: [0.5, 0, 0.15], laarH: [0.5, 0, -0.15],
    leggV: [0.8, 0, 0], leggH: [0.8, 0, 0],
    fotV: N, fotH: N,
  },

  /* Faller: armene fram, som en refleks. */
  fall: {
    torso: N, hode: [-0.3, 0, 0],
    overarmV: [-1.5, 0, 0.5], overarmH: [-1.5, 0, -0.5],
    underarmV: [-0.6, 0, 0], underarmH: [-0.6, 0, 0],
    haandV: N, haandH: N,
    laarV: [0.3, 0, 0], laarH: [0.3, 0, 0],
    leggV: [0.5, 0, 0], leggH: [0.5, 0, 0],
    fotV: N, fotH: N,
  },

  /* Reise seg fra ryggen. Eieren §13 ga selve sekvensen; her er den som
   * positurpunkter i tid, og fysikken maa faktisk faa ham opp.
   * Feiler den, gaar han tilbake til `NEDE` og proever paa nytt. */
  reisFraRygg: {
    torso: [[0, 0, 0, 0], [0.5, -0.5, 0, 0], [1.2, -1.1, 0, 0], [1.8, 0, 0, 0]],
    hode: [[0, -0.4, 0, 0], [0.4, -0.6, 0, 0], [1.2, -0.2, 0, 0], [1.8, 0, 0, 0]],
    overarmV: [[0, 0.4, 0, 0.8], [0.6, 1.4, 0, 0.9], [1.4, 0.3, 0, 0.3], [1.8, 0.1, 0, 0.16]],
    overarmH: [[0, 0.4, 0, -0.8], [0.6, 1.4, 0, -0.9], [1.4, 0.3, 0, -0.3], [1.8, 0.1, 0, -0.16]],
    underarmV: [[0, 0.3, 0, 0], [0.8, 1.0, 0, 0], [1.8, 0.16, 0, 0.1]],
    underarmH: [[0, 0.3, 0, 0], [0.8, 1.0, 0, 0], [1.8, 0.16, 0, -0.1]],
    haandV: N, haandH: N,
    /* Knaerne inn foerst, saa foettene under massesenteret. */
    laarV: [[0, 0, 0, 0], [0.5, -1.3, 0, 0], [1.1, -0.9, 0, 0], [1.8, 0, 0, 0]],
    laarH: [[0, 0, 0, 0], [0.5, -1.3, 0, 0], [1.1, -0.9, 0, 0], [1.8, 0, 0, 0]],
    leggV: [[0, 0, 0, 0], [0.5, 1.5, 0, 0], [1.1, 1.1, 0, 0], [1.8, 0, 0, 0]],
    leggH: [[0, 0, 0, 0], [0.5, 1.5, 0, 0], [1.1, 1.1, 0, 0], [1.8, 0, 0, 0]],
    fotV: N, fotH: N,
  },

  /* Fra magen: han ruller foerst over paa siden. */
  reisFraMage: {
    torso: [[0, 0, 0, 0.9], [0.6, 0, 0, 0.3], [1.3, -0.9, 0, 0], [1.9, 0, 0, 0]],
    hode: [[0, 0.3, 0, 0], [0.8, -0.3, 0, 0], [1.9, 0, 0, 0]],
    overarmV: [[0, -1.2, 0, 0.5], [0.7, 1.2, 0, 0.7], [1.9, 0.1, 0, 0.16]],
    overarmH: [[0, -1.2, 0, -0.5], [0.7, 1.2, 0, -0.7], [1.9, 0.1, 0, -0.16]],
    underarmV: [[0, 0.5, 0, 0], [0.9, 1.1, 0, 0], [1.9, 0.16, 0, 0.1]],
    underarmH: [[0, 0.5, 0, 0], [0.9, 1.1, 0, 0], [1.9, 0.16, 0, -0.1]],
    haandV: N, haandH: N,
    laarV: [[0, 0.3, 0, 0], [0.8, -1.2, 0, 0], [1.9, 0, 0, 0]],
    laarH: [[0, 0.3, 0, 0], [0.8, -1.2, 0, 0], [1.9, 0, 0, 0]],
    leggV: [[0, 0, 0, 0], [0.8, 1.4, 0, 0], [1.9, 0, 0, 0]],
    leggH: [[0, 0, 0, 0], [0.8, 1.4, 0, 0], [1.9, 0, 0, 0]],
    fotV: N, fotH: N,
  },

  /* Sitte. Eieren §16: «IKKE parent Tobias til stolen. Han skal faktisk sitte
   * fysisk paa den.» Denne posituren boeyer bare hofter og knaer; om han blir
   * SITTENDE avgjores av om det staar noe under ham. */
  sitte: {
    torso: [-0.12, 0, 0], hode: [-0.05, 0, 0],
    overarmV: [0.35, 0, 0.25], overarmH: [0.35, 0, -0.25],
    underarmV: [0.5, 0, 0.1], underarmH: [0.5, 0, -0.1],
    haandV: N, haandH: N,
    laarV: [-1.35, 0, 0], laarH: [-1.35, 0, 0],
    leggV: [0.35, 0, 0], leggH: [0.35, 0, 0],
    fotV: N, fotH: N,
  },

  /* Vinke: bare hoyre arm avviker fra `staa`. */
  vinke: {
    torso: N, hode: N,
    overarmV: [0.10, 0, 0.16],
    overarmH: [[0, 0.1, 0, -0.16], [0.25, -2.3, 0, -0.5], [1.4, -2.3, 0, -0.5], [1.7, 0.1, 0, -0.16]],
    underarmV: [0.16, 0, 0.10],
    underarmH: [[0, 0.16, 0, -0.1], [0.4, -0.6, 0, -0.9], [0.7, -0.6, 0, 0.2], [1.0, -0.6, 0, -0.9], [1.4, -0.6, 0, 0.2], [1.7, 0.16, 0, -0.1]],
    haandV: N, haandH: N,
    laarV: N, laarH: N, leggV: N, leggH: N, fotV: N, fotH: N,
  },
};

/* Slaa opp posituren paa et tidspunkt. Faste verdier returneres som de er;
 * tidslinjer interpoleres lineaert mellom punktene og fryser paa det siste.
 *
 * Lineaert holder her, og det er med vilje: PD-regulatoren og massene gjor all
 * utjevningen. Legger man easing HER ogsaa, blir bevegelsen dobbelt myk og
 * mister den kloenete kanten eieren ba om. */
export function blandPositur(positur, tid, fraEuler) {
  const ut = {};
  for (const [del, v] of Object.entries(positur)) {
    if (typeof v[0] === "number") {
      ut[del] = fraEuler(v[0], v[1], v[2]);
      continue;
    }
    let a = v[0];
    let b = v[v.length - 1];
    for (let i = 0; i < v.length - 1; i++) {
      if (tid >= v[i][0] && tid <= v[i + 1][0]) { a = v[i]; b = v[i + 1]; break; }
    }
    if (tid >= b[0]) { ut[del] = fraEuler(b[1], b[2], b[3]); continue; }
    const spenn = b[0] - a[0];
    const t = spenn > 0 ? (tid - a[0]) / spenn : 0;
    ut[del] = fraEuler(
      a[1] + (b[1] - a[1]) * t,
      a[2] + (b[2] - a[2]) * t,
      a[3] + (b[3] - a[3]) * t,
    );
  }
  return ut;
}
