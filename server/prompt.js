// System-prompt og JSON-skjema for den redaksjonelle kvalitetskontrollen.
// Prompten er skrevet for Stavanger Aftenblads standard. Modellen skal ALDRI
// finne på fakta eller endre meningsinnhold – kun vurdere og foreslå.

export const SYSTEM_PROMPT = `Du er en erfaren nyhetsredaktør og språkvasker på nivå med en seniorredaktør i Stavanger Aftenblad. Oppgaven din er å gjennomføre en fullstendig redaksjonell kvalitetskontroll av en artikkel før publisering.

Vær streng, kritisk og grundig. Ikke vær høflig dersom teksten har svakheter – påpek dem tydelig. Målet er at artikkelen skal holde et profesjonelt publiseringsnivå i en ledende norsk redaksjon.

ABSOLUTTE REGLER (anker – ikke bryt disse):
- Du skal ALDRI finne på fakta eller endre meningsinnholdet.
- Dersom noe virker uklart, feil eller mangler dokumentasjon, skal du påpeke det og forklare hvorfor – ikke «rette» det til noe du gjetter.
- Alle sitater du oppgir i feltet «sitat» skal være ordrett kopiert fra artikkelen, slik at de kan finnes igjen i teksten. Ikke omskriv sitatet.
- Når du viser til Vær Varsom-plakaten, skal du ALLTID bruke et ekte punktnummer fra REFERANSEANKERET under. Er du usikker på hvilket punkt som gjelder, skriv «VVP generelt» heller enn å finne på et nummer.
- LIX skal beregnes etter formelen i ankeret – ikke gjett et rundt tall. Forankre vurderingen i faktiske lange setninger og lange ord.
- Begrunn alle vurderinger med et konkret eksempel/sitat. Ikke gi ros eller kritikk uten dekning i teksten.
- All output skal være på norsk (bokmål).

═══ REFERANSEANKER (grunnlaget for alle vurderinger) ═══

VÆR VARSOM-PLAKATEN – kapitler og sentrale punkter (bruk disse numrene):
• Kap 1 Pressens samfunnsrolle: 1.1 informasjon/debatt, 1.4 avdekke kritikkverdige forhold, 1.5 beskytte enkeltmennesker mot overgrep/forsømmelser.
• Kap 2 Integritet og troverdighet: 2.6–2.9 skarpt skille mellom redaksjonelt stoff og reklame/sponsing/innholdsmarkedsføring; kommersielt innhold og lenker skal merkes tydelig.
• Kap 3 Journalistisk atferd og kilder: 3.2 kontroller at opplysninger er korrekte + kildekritikk og kildebredde; 3.3 gjør premissene klare i kontakt med kilder; 3.7 gjengi meningsinnhold korrekt (sitat/sitatsjekk); 3.9 opptre hensynsfullt.
• Kap 4 Publiseringsregler: 4.1 saklighet og omtanke; 4.2 klart skille fakta/kommentar; 4.3 respekter privatliv, identitet, legning, etnisitet – ikke fremhev private forhold uten relevans; 4.4 sørg for dekning for titler, ingress og henvisninger – ikke gå lenger enn det er dekning for; 4.5 unngå forhåndsdom; 4.6 omtanke ved ulykker/sorg; 4.7 varsomhet ved identifisering; 4.8 vern om barn; 4.10–4.12 saklig og korrekt bildebruk (samme aktsomhet som tekst); 4.13 rett opp og beklag feil; 4.14 samtidig imøtegåelse ved sterke beskyldninger; 4.15 tilsvarsrett.

LIX (lesbarhetsindeks): LIX = (antall ord / antall setninger) + (antall lange ord × 100 / antall ord), der lange ord har 7 bokstaver eller mer. Skala: under 30 = svært lettlest; 30–40 = lettlest / normalt avisspråk; 40–50 = middels/saklig; 50–60 = tungt; over 60 = svært tungt. Redaksjonens mål er under 30 (svært tilgjengelig), men 30–40 er normalt for avis – ikke straff en tekst hardt for å ligge der, men pek på det som kan forenkles.

SJANGERNORMER: nyhet (viktigst først, balanse, samtidig imøtegåelse), reportasje/feature (scene, nærvær, dramaturgi), kommentar/analyse (tydelig avsender, skille fra nyhet – 4.2), portrett (person i sentrum, flere kilder for kontekst), notis (kort, ett poeng), forklarende journalistikk (svarer på «hvorfor/hvordan»).

KLARSPRÅK / AFTENBLADET-STIL: aktivt språk framfor passiv, korte setninger, konkrete ord framfor byråkratspråk, tydelig vinkling, forklar fagbegrep, unngå klisjeer og fyllord, leservennlighet.

═══════════════════════════════════════════════════════

Du skal vurdere teksten på disse punktene og fylle ut det oppgitte JSON-skjemaet nøyaktig:

1. Førsteinntrykk: kort helhetsvurdering, styrker, svakheter, og om du ville sendt den til publisering slik den er.
2. LIX: beregn LIX-score etter formelen i ankeret, og forankre den i faktiske lange setninger og lange ord. Tolk scoren mot skalaen i ankeret (mål under 30, men 30–40 er normalt avisspråk). Pek ut de vanskeligste setningene med enklere forslag. Se etter lange setninger, vanskelige ord, passiv språkbruk og unødvendig komplisert språk.
3. Dramaturgi: hvordan er historien bygget opp? Røpes hovedpoenget for tidlig? Bygges nysgjerrighet? Kommer det sterkeste på riktig tidspunkt? Tydelig rød tråd? Mister teksten tempo? Gi konkrete forslag.
4. Sjanger: identifiser journalistisk sjanger (nyhet, reportasje, feature, kommentar, analyse, portrett, intervju, notis, forklarende journalistikk osv.) og vurder om teksten følger normene.
5. Vær Varsom-plakaten (VVP): kontroller teksten mot punktene i ankeret – særlig 3.2 (opplysningskontroll/kildebredde), 4.1 (saklighet/omtanke), 4.3 (privatliv/identitet), 4.4 (dekning for titler/ingress), 4.14 (samtidig imøtegåelse ved sterke beskyldninger) og 2.6–2.9 (skille redaksjonelt/kommersielt). For hvert mulig problem: oppgi det konkrete VVP-punktnummeret i «omrade», ordrett sitat, forklaring og alvorlighetsgrad. Bruk aldri et punktnummer du ikke finner i ankeret.
6. Generell presseetikk: unødvendige karakteristikker, ladet språk, spekulasjoner, konklusjoner uten dekning, ubalanse, manglende nyanser, skjult vinkling, manglende kildekritikk.
7. Språk: grammatikk, rettskrivning, tegnsetting, orddeling, flyt, ordvalg, gjentakelser, klisjeer, passiv språkbruk, tungt språk, overflødige ord. For hvert funn: original (ordrett sitat), forslag til bedre formulering, og en kort forklaring.
8. Navn, titler og fakta: kontroller navn, titler, steder, organisasjoner, datoer, årstall og tall. Påpek det som virker inkonsekvent eller mulig feil – ikke finn på riktige opplysninger.
9. Stavanger Aftenblads skrivestil: klart språk, korte setninger, naturlig flyt, presis journalistikk, aktiv språkbruk, konkret språk, lite byråkratisk språk, tydelig vinkling, leservennlighet. Gi konkrete forbedringsforslag.
10. Ingress: skaper den interesse? Avslører den for mye? Oppsummerer den saken riktig? For lang? Lettlest? Skriv en ny ingress dersom det trengs.
11. Mellomtitler: flyt, lesbarhet, plassering, variasjon, og om de hjelper leseren videre. Gi forslag til bedre mellomtitler.
12. Tittel: lag minst fem alternative titler. Hver tittel skal følge modellen «en kort forklarende setning:» etterfulgt av et sterkt, ordrett sitat fra saken. Titlene skal være presise, journalistiske, dekningsmessige, ikke overdrive og ikke være klikkagn.
13. Omskriving: for dårlige avsnitt, vis hvordan de burde vært skrevet (original + omskriving + forklaring).
14. Kritiske feil: del i «må rettes før publisering» og «bør forbedres før publisering», rangert etter alvorlighetsgrad.
15. Sluttvurdering: gi delkarakterer 0–10 for lesbarhet, språk, dramaturgi, presseetikk, VVP, sjangertilpasning, tittel, ingress og helhetsinntrykk. Sett «publiseringsklar» til JA eller NEI, og begrunn.
16. Score-forklaringer: for HVER delkarakter, list de konkrete grunnene til at scoren ikke er 10 – altså hva som trekker den ned. Oppgi et ordrett sitat fra artikkelen der problemet oppstår når det er mulig (tom streng hvis grunnen gjelder helheten). Hvis en delkarakter er tilnærmet perfekt, kan listen være tom.
17. Oppsummering i stikkord: lag en kort liste med nøkkelord/stikkord som oppsummerer ALLE funn og problemer i saken, slik at redaktøren ser alt på ett sted uten å åpne hver seksjon. Hvert stikkord skal være kort (2–6 ord), ha en kategori, og gjerne et ordrett sitat der problemet er.

Prioriter journalistisk kvalitet fremfor høflighet. Vær konkret. Omskriv når noe kan bli bedre.`;

// JSON-skjema for strukturert output. Følger begrensningene i Structured Outputs
// (additionalProperties:false + required på alle objekter; ingen min/max/length).
export const REVIEW_SCHEMA = {
  type: "object",
  additionalProperties: false,
  required: [
    "forsteinntrykk",
    "lix",
    "dramaturgi",
    "sjanger",
    "vvp",
    "presseetikk",
    "sprak",
    "fakta",
    "stil",
    "ingress",
    "mellomtitler",
    "titler",
    "omskrivinger",
    "kritiske_feil",
    "sluttvurdering",
    "score_forklaringer",
    "oppsummering_stikkord"
  ],
  properties: {
    forsteinntrykk: {
      type: "object",
      additionalProperties: false,
      required: ["vurdering", "styrker", "svakheter", "ville_publisert"],
      properties: {
        vurdering: { type: "string", description: "3–6 setningers helhetsvurdering." },
        styrker: { type: "array", items: { type: "string" } },
        svakheter: { type: "array", items: { type: "string" } },
        ville_publisert: { type: "boolean", description: "Ville du sendt den til publisering slik den er?" }
      }
    },
    lix: {
      type: "object",
      additionalProperties: false,
      required: ["score", "vurdering", "vanskelige_setninger"],
      properties: {
        score: { type: "integer", description: "Anslått LIX-score. Mål: under 30." },
        vurdering: { type: "string" },
        vanskelige_setninger: {
          type: "array",
          items: {
            type: "object",
            additionalProperties: false,
            required: ["sitat", "forslag", "forklaring"],
            properties: {
              sitat: { type: "string", description: "Ordrett vanskelig setning fra teksten." },
              forslag: { type: "string" },
              forklaring: { type: "string" }
            }
          }
        }
      }
    },
    dramaturgi: {
      type: "object",
      additionalProperties: false,
      required: ["vurdering", "forslag"],
      properties: {
        vurdering: { type: "string" },
        forslag: { type: "array", items: { type: "string" } }
      }
    },
    sjanger: {
      type: "object",
      additionalProperties: false,
      required: ["sjanger", "folger_normene", "forklaring"],
      properties: {
        sjanger: { type: "string" },
        folger_normene: { type: "boolean" },
        forklaring: { type: "string" }
      }
    },
    vvp: {
      type: "object",
      additionalProperties: false,
      required: ["funn"],
      properties: {
        funn: {
          type: "array",
          items: {
            type: "object",
            additionalProperties: false,
            required: ["omrade", "sitat", "forklaring", "alvorlighet"],
            properties: {
              omrade: { type: "string", description: "Hvilket VVP-punkt/område som er berørt." },
              sitat: { type: "string", description: "Ordrett sitat fra teksten (tom streng hvis det gjelder helheten)." },
              forklaring: { type: "string" },
              alvorlighet: { type: "string", enum: ["lav", "middels", "hoy"] }
            }
          }
        }
      }
    },
    presseetikk: {
      type: "object",
      additionalProperties: false,
      required: ["funn"],
      properties: {
        funn: {
          type: "array",
          items: {
            type: "object",
            additionalProperties: false,
            required: ["beskrivelse", "sitat"],
            properties: {
              beskrivelse: { type: "string" },
              sitat: { type: "string", description: "Ordrett sitat fra teksten, eller tom streng." }
            }
          }
        }
      }
    },
    sprak: {
      type: "object",
      additionalProperties: false,
      required: ["funn"],
      properties: {
        funn: {
          type: "array",
          items: {
            type: "object",
            additionalProperties: false,
            required: ["original", "forslag", "forklaring"],
            properties: {
              original: { type: "string", description: "Ordrett tekst fra artikkelen som bør endres." },
              forslag: { type: "string", description: "Bedre formulering." },
              forklaring: { type: "string" }
            }
          }
        }
      }
    },
    fakta: {
      type: "object",
      additionalProperties: false,
      required: ["funn"],
      properties: {
        funn: {
          type: "array",
          items: {
            type: "object",
            additionalProperties: false,
            required: ["element", "sitat", "problem"],
            properties: {
              element: { type: "string", description: "Navn/tittel/sted/dato/tall som er kontrollert." },
              sitat: { type: "string", description: "Ordrett sitat fra teksten der elementet står." },
              problem: { type: "string", description: "Hva som virker inkonsekvent eller mulig feil." }
            }
          }
        }
      }
    },
    stil: {
      type: "object",
      additionalProperties: false,
      required: ["vurdering", "forslag"],
      properties: {
        vurdering: { type: "string" },
        forslag: { type: "array", items: { type: "string" } }
      }
    },
    ingress: {
      type: "object",
      additionalProperties: false,
      required: ["vurdering", "trenger_ny", "ny_ingress"],
      properties: {
        vurdering: { type: "string" },
        trenger_ny: { type: "boolean" },
        ny_ingress: { type: "string", description: "Forslag til ny ingress (tom streng hvis ikke nødvendig)." }
      }
    },
    mellomtitler: {
      type: "object",
      additionalProperties: false,
      required: ["vurdering", "forslag"],
      properties: {
        vurdering: { type: "string" },
        forslag: {
          type: "array",
          items: {
            type: "object",
            additionalProperties: false,
            required: ["original", "forslag"],
            properties: {
              original: { type: "string", description: "Eksisterende mellomtittel, eller tom streng hvis ny." },
              forslag: { type: "string" }
            }
          }
        }
      }
    },
    titler: {
      type: "array",
      description: "Minst fem alternative titler. Format: forklarende setning + ordrett sitat.",
      items: {
        type: "object",
        additionalProperties: false,
        required: ["forklarende", "sitat"],
        properties: {
          forklarende: { type: "string", description: "Kort forklarende setning, f.eks. «Ny badeplass åpner i byen:»" },
          sitat: { type: "string", description: "Sterkt, ordrett sitat fra saken, f.eks. «– Dette har vi ventet på i flere år»" }
        }
      }
    },
    omskrivinger: {
      type: "array",
      items: {
        type: "object",
        additionalProperties: false,
        required: ["original", "omskriving", "forklaring"],
        properties: {
          original: { type: "string", description: "Ordrett svakt avsnitt fra artikkelen." },
          omskriving: { type: "string" },
          forklaring: { type: "string" }
        }
      }
    },
    kritiske_feil: {
      type: "object",
      additionalProperties: false,
      required: ["ma_rettes", "bor_forbedres"],
      properties: {
        ma_rettes: { type: "array", items: { type: "string" }, description: "Må rettes før publisering, mest alvorlig først." },
        bor_forbedres: { type: "array", items: { type: "string" }, description: "Bør forbedres før publisering, mest alvorlig først." }
      }
    },
    sluttvurdering: {
      type: "object",
      additionalProperties: false,
      required: [
        "lesbarhet",
        "sprak",
        "dramaturgi",
        "presseetikk",
        "vvp",
        "sjangertilpasning",
        "tittel",
        "ingress",
        "helhetsinntrykk",
        "publiseringsklar",
        "begrunnelse"
      ],
      properties: {
        lesbarhet: { type: "integer" },
        sprak: { type: "integer" },
        dramaturgi: { type: "integer" },
        presseetikk: { type: "integer" },
        vvp: { type: "integer" },
        sjangertilpasning: { type: "integer" },
        tittel: { type: "integer" },
        ingress: { type: "integer" },
        helhetsinntrykk: { type: "integer" },
        publiseringsklar: { type: "string", enum: ["JA", "NEI"] },
        begrunnelse: { type: "string" }
      }
    },
    score_forklaringer: {
      type: "object",
      additionalProperties: false,
      description: "For hver delkarakter: hva som trekker scoren ned, med sitat der det skjer.",
      required: [
        "lesbarhet",
        "sprak",
        "dramaturgi",
        "presseetikk",
        "vvp",
        "sjangertilpasning",
        "tittel",
        "ingress",
        "helhetsinntrykk"
      ],
      properties: {
        lesbarhet: scoreForklaringListe(),
        sprak: scoreForklaringListe(),
        dramaturgi: scoreForklaringListe(),
        presseetikk: scoreForklaringListe(),
        vvp: scoreForklaringListe(),
        sjangertilpasning: scoreForklaringListe(),
        tittel: scoreForklaringListe(),
        ingress: scoreForklaringListe(),
        helhetsinntrykk: scoreForklaringListe()
      }
    },
    oppsummering_stikkord: {
      type: "array",
      description: "Kort stikkords-oversikt over ALLE funn/problemer, for rask skanning.",
      items: {
        type: "object",
        additionalProperties: false,
        required: ["stikkord", "kategori", "sitat"],
        properties: {
          stikkord: { type: "string", description: "Kort nøkkelord/stikkord (2–6 ord)." },
          kategori: {
            type: "string",
            enum: ["sprak", "vvp", "fakta", "presseetikk", "dramaturgi", "lix", "stil", "ingress", "tittel", "mellomtitler", "annet"]
          },
          sitat: { type: "string", description: "Ordrett sitat der det gjelder, ellers tom streng." }
        }
      }
    }
  }
};

// Liste over grunner til at en delkarakter trekkes ned (med sitat der det skjer).
function scoreForklaringListe() {
  return {
    type: "array",
    items: {
      type: "object",
      additionalProperties: false,
      required: ["grunn", "sitat"],
      properties: {
        grunn: { type: "string", description: "Hva som trekker scoren ned." },
        sitat: { type: "string", description: "Ordrett sitat der problemet er, eller tom streng hvis det gjelder helheten." }
      }
    }
  };
}
