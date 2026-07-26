/* TobiasPhysicsConfig — ALLE fysikkverdier, samlet ett sted.
 *
 * Eieren 26.07.2026, §28: «Ikke hardcode physics values over hele codebasen.
 * Samle dem i TobiasPhysicsConfig.»
 *
 * Regelen er absolutt: staar et tall som paavirker fysikken et annet sted i
 * `fysikk/`, er det en feil. Grunnen er praktisk - en ragdoll tunes ved aa
 * skru paa ti tall om gangen og se hva som skjer, og det er umulig hvis de
 * ligger spredt.
 *
 * ## Enheter
 *
 * Verdenen er i METER, med Tobias ca. 1,0 m hoy. Rapier er stabilest rundt
 * den skalaen. Skjermkoordinater regnes om i `verden.js` - ett sted, med én
 * faktor, saa ingen del av systemet trenger aa vite om piksler.
 */

export const TOBIAS_PHYSICS_DEBUG = false;

export const FYS = {
  /* ── Verden ──────────────────────────────────────────────────────────── */
  tyngde: -14.0,            // m/s^2. Mer enn 9.81: en liten figur som faller
                            // med ekte jordtyngde ser ut som den sveiver.
  /* 120 Hz, ikke 60. Stabilitetskravet paa PD-regulatoren er `kd * dt < 1`, saa
   * halvert steg gir dobbelt tillatt demping - og dermed fire ganger tillatt
   * stivhet (kd = 2*sqrt(kp)). Det er nettopp den stivheten beina trenger for
   * aa baere kroppen. Fjorten kropper koster lite nok til at det er verdt det. */
  steg: 1 / 120,            // fast fysikksteg

  /* Solveren. En ragdoll er en kjede med stor massekontrast (torso 2,6 kg,
   * haand 0,12 kg), og standardverdiene til Rapier klarer ikke aa holde
   * hofteleddet sammen under vekten av overkroppen. */
  solver: { iter: 16, pgs: 4, friksjon: 4 },
  maksSteg: 8,              // hvor mange steg vi tar igjen etter en lang frame
  pikslerPerMeter: 130,     // skala mellom fysikk og skjerm

  /* ── Kroppsdeler: masse, stoerrelse, plassering ──────────────────────────
   *
   * `y` er senterhoyden naar han staar. `r`/`h` er kapselradius og halv
   * sylinderhoyde; `boks` er halve utstrekninger.
   *
   * Massene er IKKE realistiske - de er valgt for at han skal falle som en
   * leke: tungt underlag, lett overkropp, saa han lander paa foettene oftere
   * enn en ekte ragdoll ville gjort. Eieren §24: «Tobias virker kloenete, ikke
   * buggete.» */
  /* ## Massefordelingen er snudd, og det er hele poenget
   *
   * Foerste utkast hadde en realistisk fordeling: tung torso (2,6 kg), lette
   * bein (0,35 kg legg). Da klarte ikke beina aa baere kroppen - PD-momentet er
   * proporsjonalt med lemmets TREGHETSMOMENT, og et legg paa 0,35 kg har
   * I ≈ 0,0005. Det ga 0,31 Nm der det trengte 4. Maalt 26.07.2026: beina
   * foldet seg sammen og torsoen sank fra 0,42 til 0,18 m.
   *
   * Naa er det motsatt: tunge bein, lett overkropp. Det er UREALISTISK og helt
   * med vilje. Han er en leke, ikke et menneske - og en leke med tyngdepunktet
   * lavt lander paa foettene, staar stoedig, og ser kloenete ut i stedet for
   * ustabil. Nedsiden er ærlig nok: et lite dytt i brystet flytter ham mindre
   * enn det ville gjort en menneskefigur. */
  deler: {
    torso:    { y: 0.42, boks: [0.20, 0.17, 0.16], masse: 1.1 },
    hode:     { y: 0.72, r: 0.20,                  masse: 0.55 },
    /* ## Armene henger fra SKULDEREN, ikke fra sida si
     *
     * Foerste utkast satte armene paa x = ±0.255 med skulderleddet utledet av
     * `andel` mellom torsosenteret og armsenteret - altsaa et punkt INNE i
     * torsoen, paa hoyde med armens midte. Da hang armen fra sida si:
     * tyngdekraften dro senteret ned under leddet, PD-regulatoren dro den mot
     * loddrett, og likevekten ble kompromisset. Maalt 26.07.2026: overarmen
     * stod 25° ut, underarmen kom inn igjen, haanden endte 0.09 m innenfor
     * albuen. Paa skjermen leste det som kyllingvinger.
     *
     * Naa er skulderen et EKSPLISITT punkt i toppen av armen (se `LEDD` i
     * skjelett.js), og hele kjeden henger ende-mot-ende nedover fra den.
     * Da peker tyngdekraften og posituren samme vei, og armen staar loddrett
     * uten aa bli holdt der med makt - noe som igjen er grunnen til at
     * armstivheten kunne settes kraftig ned. En arm som henger fordi den
     * henger, svinger ogsaa naturlig naar han gaar eller blir dyttet.
     *
     * `z: 0.03` legger armene saa vidt foran kroppen. Uten det ligger haanden
     * i samme plan som laaret og skjaerer inn i det.
     *
     * ## Delene OVERLAPPER med vilje
     *
     * Andre utkast la kapslene tupp mot tupp - matematisk pent, og det saa ut
     * som tre loese perler paa en snor. En arm leses som ÉN lem foerst naar
     * delene gaar litt inn i hverandre, saa silhuetten er sammenhengende.
     * Derfor ligger albuen (0.395) over overarmens nedre tupp (0.370), og
     * haandleddet (0.295) godt inne i haandkula. Fysikken bryr seg ikke:
     * delene kolliderer ikke med hverandre uansett.
     *
     * ## Maalene er hentet fra den Tobias eieren allerede har godkjent
     *
     * `modell.js`: arm-radius 0.050, haand-kule 0.056, og skulderen litt lenger
     * ut enn torsoens halvbredde - der staar det uttrykkelig «saa armene
     * faktisk synes i stedet for aa ligge begravd i magen». Fysikkversjonen har
     * i tillegg en albue, fordi en ragdoll trenger et sted aa knekke; med
     * overlappen leser den likevel som den samme ene armen. */
    overarmV: { y: 0.450, x: -0.215, z: 0.03, r: 0.050, h: 0.030, masse: 0.13 },
    overarmH: { y: 0.450, x:  0.215, z: 0.03, r: 0.050, h: 0.030, masse: 0.13 },
    underarmV:{ y: 0.342, x: -0.215, z: 0.03, r: 0.047, h: 0.026, masse: 0.10 },
    underarmH:{ y: 0.342, x:  0.215, z: 0.03, r: 0.047, h: 0.026, masse: 0.10 },
    haandV:   { y: 0.270, x: -0.215, z: 0.03, r: 0.056,          masse: 0.08 },
    haandH:   { y: 0.270, x:  0.215, z: 0.03, r: 0.056,          masse: 0.08 },
    laarV:    { y: 0.21, x: -0.115, r: 0.058, h: 0.045, masse: 0.95 },
    laarH:    { y: 0.21, x:  0.115, r: 0.058, h: 0.045, masse: 0.95 },
    leggV:    { y: 0.11, x: -0.115, r: 0.054, h: 0.035, masse: 0.80 },
    leggH:    { y: 0.11, x:  0.115, r: 0.054, h: 0.035, masse: 0.80 },
    fotV:     { y: 0.035, x: -0.115, z: 0.02, boks: [0.068, 0.035, 0.092], masse: 0.60 },
    fotH:     { y: 0.035, x:  0.115, z: 0.02, boks: [0.068, 0.035, 0.092], masse: 0.60 },
  },

  /* ── Ledd ────────────────────────────────────────────────────────────────
   * Eieren §3: «Begrens joint ranges ... Men gjor dem litt myke. Han skal vaere
   * litt floppy.» Grensene haandheves av PD-regulatoren, ikke av harde
   * leddstopp - harde stopp gir rykk, myke grenser gir floppy. */
  ledd: {
    nakke:    { type: "kule", grense: 0.75 },
    skulder:  { type: "kule", grense: 2.30 },
    albue:    { type: "hengsel", akse: [1, 0, 0], min: -2.3, maks: 0.05 },
    haandledd:{ type: "kule", grense: 0.60 },
    hofte:    { type: "kule", grense: 1.50 },
    kne:      { type: "hengsel", akse: [1, 0, 0], min: -0.05, maks: 2.2 },
    ankel:    { type: "kule", grense: 0.55 },
  },

  /* ── Active ragdoll: PD-regulatoren ──────────────────────────────────────
   *
   * Eieren §4: «torque = poseError * stiffness - angularVelocity * damping.
   * Ikke teleporter body parts til target.»
   *
   * `stivhet` er hvor hardt han PROEVER aa holde posituen, `demping` hvor mye
   * han bremser sin egen bevegelse. Hoy stivhet = stiv dukke; lav = vaat klut.
   * Verdiene under er der «60 % kontrollert karakter + 40 % ragdoll» havner. */
  /* Alle tall i newtonmeter. `tak` er hvor mye moment leddet KAN levere -
   * musklenes styrke, ikke lemmets vekt. Beina maa baere hele kroppen og har
   * derfor klart hoyest tak; haendene har nesten ingen og henger stort sett. */
  /* `stivhet` (kp) i rad/s², `demping` (kd) i rad/s, `tak` i newtonmeter.
   *
   * Kp/kd foelger den vanlige stabilitetsregelen: kritisk demping ved
   * kd = 2*sqrt(kp), og kd * dt < 1 ved dt = 1/60. Bryter man den andre,
   * skyter dempeleddet forbi null hvert steg og pumper energi inn i stedet for
   * aa ta den ut - det var akkurat det som fikk haanden til aa stige opp over
   * skulderen 26.07.2026.
   *
   * Med dt = 1/120 er kd opp til ~110 lovlig, og kp opp til (kd/2)². */
  positur: {
    torso:  { stivhet: 2400, demping: 98, tak: 40 },
    hode:   { stivhet: 700,  demping: 53, tak: 6.0 },
    /* ## Armene ble MYKERE da geometrien ble riktig
     *
     * De stod lenge paa 2200. Grunnen var at skulderleddet satt feil, saa
     * tyngdekraften dro armen ut mens posituren dro den inn - og da maa
     * regulatoren vinne med makt for at armen skal se ut som den henger.
     *
     * En arm som holdes nede med 2200 rad/s² er stiv som en pinne: den svinger
     * ikke naar han gaar, den slenger ikke naar han faller, og et dytt flytter
     * den knapt. Naa som skulderen sitter i toppen av armen, HENGER den av seg
     * selv, og regulatoren trenger bare aa gi den retning. 800 er nok til det,
     * og resten blir bevegelse. */
    arm:    { stivhet: 800,  demping: 57, tak: 2.0 },
    /* Haendene styres nesten ikke - de dingler etter underarmen. */
    haand:  { stivhet: 300,  demping: 35, tak: 0.5 },
    bein:   { stivhet: 2800, demping: 105, tak: 60 },
    fot:    { stivhet: 1400, demping: 74, tak: 14 },
    maksMoment: 20,          // reserve for grupper uten eget tak
  },

  /* ── Balanse ─────────────────────────────────────────────────────────────
   * Eieren §5-6. Terskler i meter, maalt fra midt mellom foettene. */
  balanse: {
    styrke: 26,             // hvor hardt hofta jobber for aa holde ham oppe
    vingle: 0.045,          // under dette: bare smaa korreksjoner
    steg: 0.10,             // over dette: han tar et steg
    snuble: 0.20,           // over dette: han snubler
    fall: 0.32,             // over dette: han faller
    stegLengde: 0.16,
    stegTid: 0.34,
  },

  /* ── Gange ───────────────────────────────────────────────────────────────
   * Eieren §14: «Walking skal bruke physics. Ikke bare position.x += speed.»
   *
   * Vinklene under er hva han PROEVER; PD-regulatoren i beina (tak 60 Nm) har
   * kraft nok til at forsoket faktisk loefter en fot, og det er friksjonen
   * under standfoten som skyver ham fram. `len` er den eneste direkte kraften,
   * og den er med vilje for liten til aa flytte ham alene - den skal bare
   * skyve massesenteret foran standfoten, saa han MAA ta et skritt. */
  gange: {
    hofte: 0.55,            // rad, hvor langt laaret svinger fram/tilbake
    kne: 0.95,              // rad, ekstra knebøy mens beinet svinger fram
    arm: 0.42,              // rad, armsving (motsatt beinet paa samme side)
    lut: 0.10,              // rad, torsoens framoverlening
    len: 5.0,               // N, dyttet som legger massesenteret foran foten
    snuTid: 0.30,           // s, hvor lenge han bruker paa aa snu seg
    /* Foten veier 0.60 kg = 8.4 N. Loeftet maa overgaa det for at hofta i det
     * hele tatt skal faa beinet klar av gulvet. */
    loeft: 20,              // N, ekstra loeft paa taa-enden i svevfasen
    /* Hele svevbeinet veier 2.35 kg = 32.9 N. Hofta maa baere mer enn det for
     * at foten skal komme klar av gulvet i det hele tatt. */
    hoftehiv: 78,           // N, hofteloeftet som baerer svevbeinet
    svevFriksjon: 0.05,     // friksjon paa foten mens den svinger
  },

  /* ── Griping ─────────────────────────────────────────────────────────────
   * Eieren §7: «IKKE flytt hele Tobias. Opprett en temporary physics joint.» */
  grep: {
    stivhet: 260,           // hvor hardt pekeren drar i kroppsdelen
    demping: 22,
    maksKraft: 90,          // saa fingeren ikke kan rive ham i stykker
  },

  /* ── Kast ────────────────────────────────────────────────────────────────
   * Eieren §10: «beregn pointer velocity fra de siste ~100 ms». */
  kast: {
    sporMs: 110,
    /* Impulsen gaar paa den GREPNE delen (§10), og en haand paa 0,08 kg drar
     * ikke med seg fire kilo kropp. `kroppAndel` gir resten av kroppen en del
     * av farten direkte - ellers floey haanden av gaarde mens Tobias ble
     * staaende. Maalt 26.07.2026: han floey 2 cm paa et kast paa 14 m/s. */
    faktor: 1.0,
    kroppAndel: 0.75,
    maksFart: 14,           // m/s
  },

  /* ── Underlag ───────────────────────────────────────────────────────────
   * Eieren §15: «Ikke la foettene skli unaturlig. Men ikke sett friction
   * ekstremt hoyt. Litt sliding kan gjore Tobias morsommere.» */
  gulv: {
    friksjon: 0.85,
    sprett: 0.12,
    fotFriksjon: 1.10,
    kroppFriksjon: 0.45,
    kroppSprett: 0.30,
  },

  /* ── Demping per kropp ─────────────────────────────────────────────────── */
  /* Vinkeldempingen tar bort dirringen som ellers ligger igjen naar han staar
   * stille. Maalt: torsofarten falt fra 1,8 til under 0,3 m/s. */
  demping: { lineaer: 0.35, vinkel: 4.0 },

  /* ── Sammenstoet ────────────────────────────────────────────────────────
   * Eieren §12. Terskler paa impulsen fra kollisjonen. */
  smell: { liten: 0.9, middels: 2.2, stor: 4.5 },

  /* ── Soevn ───────────────────────────────────────────────────────────────
   * Eieren §26: «Sleep rigid bodies naar Tobias er inaktiv.» */
  soevn: { fart: 0.06, tid: 1.2 },
};

/* Tuning-panelet i §28 skriver hit. Alt er flatt med vilje, saa en slider kan
 * peke rett paa en verdi uten aa vite hvor den bor. */
export const TUNING = [
  ["balanseStyrke", () => FYS.balanse.styrke, (v) => (FYS.balanse.styrke = v), 0, 80],
  ["positurStivhet", () => FYS.positur.torso.stivhet, (v) => (FYS.positur.torso.stivhet = v), 0, 90],
  ["positurDemping", () => FYS.positur.torso.demping, (v) => (FYS.positur.torso.demping = v), 0, 20],
  ["beinStyrke", () => FYS.positur.bein.stivhet, (v) => (FYS.positur.bein.stivhet = v), 0, 60],
  ["armStyrke", () => FYS.positur.arm.stivhet, (v) => (FYS.positur.arm.stivhet = v), 0, 40],
  ["nakkeStyrke", () => FYS.positur.hode.stivhet, (v) => (FYS.positur.hode.stivhet = v), 0, 50],
  ["fotFriksjon", () => FYS.gulv.fotFriksjon, (v) => (FYS.gulv.fotFriksjon = v), 0, 3],
  ["tyngde", () => FYS.tyngde, (v) => (FYS.tyngde = v), -40, 0],
  ["maksMoment", () => FYS.positur.maksMoment, (v) => (FYS.positur.maksMoment = v), 0, 12],
  ["stegTerskel", () => FYS.balanse.steg, (v) => (FYS.balanse.steg = v), 0.02, 0.4],
  ["grepStivhet", () => FYS.grep.stivhet, (v) => (FYS.grep.stivhet = v), 20, 600],
];
