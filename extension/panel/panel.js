// Sidepanel-logikk: innlogging, kjøring av kontroll, rendering av rapport,
// og markering av funn i den aktive fanen.

const $ = (id) => document.getElementById(id);

const views = {
  oppsett: $("viewOppsett"),
  login: $("viewLogin"),
  hoved: $("viewHoved")
};

function visView(navn) {
  for (const [k, el] of Object.entries(views)) el.classList.toggle("skjult", k !== navn);
  $("loggUt").classList.toggle("skjult", navn !== "hoved");
}

// Holder på siste rapport + fane, slik at popup og stikkord kan hoppe i teksten.
let sisteRapport = null;
let sisteFane = null;

const KAT_NAVN = {
  sprak: "Språk",
  vvp: "Vær Varsom",
  fakta: "Fakta",
  presseetikk: "Presseetikk",
  dramaturgi: "Dramaturgi",
  lix: "Lesbarhet (LIX)",
  stil: "Skrivestil",
  ingress: "Ingress",
  tittel: "Tittel",
  mellomtitler: "Mellomtitler",
  annet: "Annet"
};

async function lagret() {
  return chrome.storage.local.get(["proxyUrl", "token", "brukernavn"]);
}

function hoppTilSitat(sitat) {
  if (sisteFane && sitat) chrome.tabs.sendMessage(sisteFane.id, { action: "rullTilSitat", sitat });
}

async function init() {
  const { proxyUrl, token } = await lagret();
  if (!proxyUrl) return visView("oppsett");
  if (!token) return visView("login");
  visView("hoved");
}

// --- Oppsett / innstillinger ------------------------------------------------
$("åpneInnstillinger").addEventListener("click", () => chrome.runtime.openOptionsPage());

// --- Innlogging -------------------------------------------------------------
$("loggInn").addEventListener("click", loggInn);
$("passord").addEventListener("keydown", (e) => e.key === "Enter" && loggInn());

async function loggInn() {
  $("loginFeil").textContent = "";
  const { proxyUrl } = await lagret();
  const brukernavn = $("brukernavn").value.trim();
  const passord = $("passord").value;
  if (!brukernavn || !passord) {
    $("loginFeil").textContent = "Fyll inn brukernavn og passord.";
    return;
  }
  try {
    const res = await fetch(`${proxyUrl.replace(/\/$/, "")}/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ brukernavn, passord })
    });
    const data = await res.json();
    if (!res.ok) {
      $("loginFeil").textContent = data.feil || "Innlogging feilet.";
      return;
    }
    await chrome.storage.local.set({ token: data.token, brukernavn: data.brukernavn });
    $("passord").value = "";
    visView("hoved");
  } catch {
    $("loginFeil").textContent = "Får ikke kontakt med serveren. Sjekk adressen i innstillingene.";
  }
}

$("loggUt").addEventListener("click", async () => {
  await chrome.storage.local.remove(["token", "brukernavn"]);
  visView("login");
});

// --- Kjøre kontroll ---------------------------------------------------------
$("sjekk").addEventListener("click", () => kjør({ fraSide: true }));
$("sjekkManuell").addEventListener("click", () => {
  const t = $("manuellTekst").value.trim();
  if (t) kjør({ fraSide: false, tekst: t });
});

async function aktivFane() {
  const [fane] = await chrome.tabs.query({ active: true, currentWindow: true });
  return fane;
}

async function injiserOgSpør(tabId, melding) {
  await chrome.scripting.executeScript({ target: { tabId }, files: ["content.js"] });
  return chrome.tabs.sendMessage(tabId, melding);
}

function settStatus(tekst) {
  $("status").textContent = tekst;
}

let tellerId = null;
function startTeller() {
  const t0 = Date.now();
  settStatus("Kjører redaksjonell kvalitetskontroll … (0 s)");
  tellerId = setInterval(() => {
    settStatus(`Kjører redaksjonell kvalitetskontroll … (${Math.round((Date.now() - t0) / 1000)} s)`);
  }, 1000);
  return () => {
    if (tellerId) clearInterval(tellerId);
    tellerId = null;
  };
}

async function kopierTekst(tekst) {
  try {
    await navigator.clipboard.writeText(tekst);
  } catch {
    const ta = document.createElement("textarea");
    ta.value = tekst;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    ta.remove();
  }
}

async function kjør({ fraSide, tekst }) {
  const { proxyUrl, token } = await lagret();
  $("sjekk").disabled = true;
  $("sjekkManuell").disabled = true;
  $("resultat").innerHTML = "";
  $("limInn").classList.add("skjult");

  let fane = null;
  try {
    let artikkeltekst = tekst || "";

    if (fraSide) {
      settStatus("Henter teksten fra siden …");
      fane = await aktivFane();
      try {
        const svar = await injiserOgSpør(fane.id, { action: "hentTekst" });
        artikkeltekst = (svar && svar.text) || "";
        if (!artikkeltekst) {
          settStatus("Fant ikke teksten automatisk.");
          $("limInn").classList.remove("skjult");
          return;
        }
      } catch {
        settStatus("Kan ikke lese denne siden. Lim inn teksten manuelt.");
        $("limInn").classList.remove("skjult");
        return;
      }
    }

    const start = Date.now();
    const stoppTeller = startTeller();
    let res;
    try {
      res = await fetch(`${proxyUrl.replace(/\/$/, "")}/review`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify({ text: artikkeltekst })
      });
    } finally {
      stoppTeller();
    }

    if (res.status === 401) {
      await chrome.storage.local.remove(["token"]);
      settStatus("");
      visView("login");
      return;
    }

    const data = await res.json();
    if (!res.ok) {
      settStatus(data.feil || "Noe gikk galt.");
      return;
    }

    const sek = Math.max(1, Math.round((Date.now() - start) / 1000));
    const markers = byggMarkører(data.resultat);
    renderRapport(data.resultat, markers, fraSide ? fane : null);

    let statuslinje = `Ferdig på ${sek} s${data.modell ? " · " + data.modell : ""}`;
    if (fraSide && fane && markers.length) {
      try {
        const r = await chrome.tabs.sendMessage(fane.id, { action: "leggPåMarkeringer", markers });
        if (r) statuslinje = `Markerte ${r.funnet}/${r.total} funn i teksten · ${sek} s`;
      } catch {
        /* markering feilet – rapporten vises uansett */
      }
    }
    settStatus(statuslinje);
  } catch (e) {
    settStatus("Uventet feil: " + (e.message || e));
  } finally {
    $("sjekk").disabled = false;
    $("sjekkManuell").disabled = false;
  }
}

// --- Bygg markører (sitat -> uthevning i teksten) ---------------------------
function byggMarkører(r) {
  const markers = [];
  const legg = (kategori, sitat, note) => {
    if (sitat && sitat.trim()) markers.push({ id: `${kategori}-${markers.length}`, kategori, sitat, note });
  };
  (r.sprak?.funn || []).forEach((f) =>
    legg("sprak", f.original, `Språk: ${f.forslag}${f.forklaring ? " — " + f.forklaring : ""}`)
  );
  (r.vvp?.funn || []).forEach((f) =>
    legg("vvp", f.sitat, `Vær Varsom (${f.omrade}): ${f.forklaring}`)
  );
  (r.fakta?.funn || []).forEach((f) =>
    legg("fakta", f.sitat, `Fakta (${f.element}): ${f.problem}`)
  );
  (r.presseetikk?.funn || []).forEach((f) => legg("presseetikk", f.sitat, `Presseetikk: ${f.beskrivelse}`));
  return markers;
}

// --- Rendering --------------------------------------------------------------
function el(tag, cls, html) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (html != null) n.innerHTML = html;
  return n;
}
function esc(s) {
  return (s ?? "").toString().replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
}

function seksjon(tittel, teller, åpen) {
  const d = el("details", "seksjon");
  if (åpen) d.open = true;
  const s = el("summary", null, esc(tittel) + (teller != null ? ` <span class="teller">(${teller})</span>` : ""));
  d.appendChild(s);
  const inn = el("div", "innhold");
  d.appendChild(inn);
  return { d, inn };
}

function liste(arr) {
  const ul = el("ul", "liste");
  (arr || []).forEach((x) => ul.appendChild(el("li", null, esc(x))));
  return ul;
}

function renderRapport(r, markers, fane) {
  const rot = $("resultat");
  rot.innerHTML = "";
  sisteRapport = r;
  sisteFane = fane;
  const s = r.sluttvurdering || {};

  // Publiseringsbanner
  const klar = (s.publiseringsklar || "").toUpperCase() === "JA";
  rot.appendChild(
    el("div", `publisering ${klar ? "ja" : "nei"}`, `Publiseringsklar: ${esc(s.publiseringsklar || "?")}`)
  );

  // Handlingsrad (kopier rapport / fjern markeringer) + fargeforklaring
  byggHandlingsrad(rot, r, fane);

  // Scorekort
  const kort = el("div", "scorekort");
  const scorer = [
    ["Lesbarhet", "lesbarhet", s.lesbarhet],
    ["Språk", "sprak", s.sprak],
    ["Dramaturgi", "dramaturgi", s.dramaturgi],
    ["Presseetikk", "presseetikk", s.presseetikk],
    ["VVP", "vvp", s.vvp],
    ["Sjanger", "sjangertilpasning", s.sjangertilpasning],
    ["Tittel", "tittel", s.tittel],
    ["Ingress", "ingress", s.ingress],
    ["Helhet", "helhetsinntrykk", s.helhetsinntrykk]
  ];
  scorer.forEach(([navn, kat, tall]) => {
    const c = el("div", "score klikkbar");
    c.appendChild(el("div", "tall", `${tall ?? "–"}<span style="font-size:12px;color:#999">/10</span>`));
    c.appendChild(el("div", "navn", esc(navn)));
    c.title = "Klikk for å se hva som trekker ned";
    c.addEventListener("click", () => openScorePopup(navn, kat, tall));
    kort.appendChild(c);
  });
  rot.appendChild(kort);
  if (s.begrunnelse) rot.appendChild(el("div", "boks", esc(s.begrunnelse)));

  // Stikkords-oversikt over alle funn (rask skanning)
  byggStikkord(rot, r);

  // Kritiske feil (åpen)
  {
    const kf = r.kritiske_feil || {};
    const antall = (kf.ma_rettes?.length || 0) + (kf.bor_forbedres?.length || 0);
    const { d, inn } = seksjon("Kritiske feil", antall, true);
    inn.appendChild(el("p", null, "<strong>Må rettes før publisering</strong>"));
    inn.appendChild(liste(kf.ma_rettes));
    inn.appendChild(el("p", null, "<strong>Bør forbedres før publisering</strong>"));
    inn.appendChild(liste(kf.bor_forbedres));
    rot.appendChild(d);
  }

  // Førsteinntrykk
  {
    const f = r.forsteinntrykk || {};
    const { d, inn } = seksjon("Førsteinntrykk", null, true);
    inn.appendChild(el("p", null, esc(f.vurdering)));
    inn.appendChild(el("p", null, "<strong>Styrker</strong>"));
    inn.appendChild(liste(f.styrker));
    inn.appendChild(el("p", null, "<strong>Svakheter</strong>"));
    inn.appendChild(liste(f.svakheter));
    inn.appendChild(
      el("p", "smånote", f.ville_publisert ? "→ Ville sendt til publisering slik den er." : "→ Ville IKKE sendt til publisering slik den er.")
    );
    rot.appendChild(d);
  }

  // Klikkbare funn-seksjoner
  const funnSeksjon = (tittel, kategori, funnListe, tegn) => {
    if (!funnListe || !funnListe.length) return;
    const { d, inn } = seksjon(tittel, funnListe.length);
    funnListe.forEach((f, i) => {
      const div = el("div", `funn k-${kategori}`);
      tegn(div, f);
      const id = `${kategori}-${i}`;
      if (fane && markers.some((m) => m.id === id)) {
        div.addEventListener("click", () => chrome.tabs.sendMessage(fane.id, { action: "rullTil", id }));
      }
      inn.appendChild(div);
    });
    rot.appendChild(d);
  };

  funnSeksjon("Språk", "sprak", r.sprak?.funn, (div, f) => {
    div.appendChild(
      el(
        "div",
        null,
        `<span class="orig">${esc(f.original)}</span><span class="pil">→</span><span class="forsl">${esc(f.forslag)}</span>`
      )
    );
    if (f.forklaring) div.appendChild(el("div", "forkl", esc(f.forklaring)));
  });

  funnSeksjon("Vær Varsom-plakaten", "vvp", r.vvp?.funn, (div, f) => {
    const lapp = f.alvorlighet ? `<span class="merkelapp ${esc(f.alvorlighet)}">${esc(f.alvorlighet)}</span>` : "";
    div.appendChild(el("div", null, `<strong>${esc(f.omrade)}</strong>${lapp}`));
    if (f.sitat) div.appendChild(el("div", "orig", "«" + esc(f.sitat) + "»"));
    div.appendChild(el("div", "forkl", esc(f.forklaring)));
  });

  funnSeksjon("Navn, titler og fakta", "fakta", r.fakta?.funn, (div, f) => {
    div.appendChild(el("div", null, `<strong>${esc(f.element)}</strong>`));
    if (f.sitat) div.appendChild(el("div", "orig", "«" + esc(f.sitat) + "»"));
    div.appendChild(el("div", "forkl", esc(f.problem)));
  });

  funnSeksjon("Presseetikk", "presseetikk", r.presseetikk?.funn, (div, f) => {
    div.appendChild(el("div", null, esc(f.beskrivelse)));
    if (f.sitat) div.appendChild(el("div", "orig", "«" + esc(f.sitat) + "»"));
  });

  // LIX
  {
    const l = r.lix || {};
    const { d, inn } = seksjon(`LIX: ${l.score ?? "–"}`, l.vanskelige_setninger?.length || null);
    inn.appendChild(el("p", null, esc(l.vurdering)));
    (l.vanskelige_setninger || []).forEach((v) => {
      const div = el("div", "funn k-sprak");
      div.appendChild(el("div", "orig", "«" + esc(v.sitat) + "»"));
      div.appendChild(el("div", null, `<span class="forsl">${esc(v.forslag)}</span>`));
      if (v.forklaring) div.appendChild(el("div", "forkl", esc(v.forklaring)));
      inn.appendChild(div);
    });
    rot.appendChild(d);
  }

  // Dramaturgi
  {
    const dr = r.dramaturgi || {};
    const { d, inn } = seksjon("Dramaturgi", null);
    inn.appendChild(el("p", null, esc(dr.vurdering)));
    inn.appendChild(liste(dr.forslag));
    rot.appendChild(d);
  }

  // Sjanger
  {
    const sj = r.sjanger || {};
    const { d, inn } = seksjon(`Sjanger: ${esc(sj.sjanger || "?")}`, null);
    inn.appendChild(
      el("p", "smånote", sj.folger_normene ? "→ Følger normene for sjangeren." : "→ Bryter med sjangerkravene.")
    );
    inn.appendChild(el("p", null, esc(sj.forklaring)));
    rot.appendChild(d);
  }

  // Aftenblad-stil
  {
    const st = r.stil || {};
    const { d, inn } = seksjon("Stavanger Aftenblads skrivestil", null);
    inn.appendChild(el("p", null, esc(st.vurdering)));
    inn.appendChild(liste(st.forslag));
    rot.appendChild(d);
  }

  // Ingress
  {
    const ing = r.ingress || {};
    const { d, inn } = seksjon("Ingress", null);
    inn.appendChild(el("p", null, esc(ing.vurdering)));
    if (ing.trenger_ny && ing.ny_ingress) {
      inn.appendChild(el("p", null, "<strong>Forslag til ny ingress:</strong>"));
      inn.appendChild(el("div", "boks", esc(ing.ny_ingress)));
    }
    rot.appendChild(d);
  }

  // Mellomtitler
  {
    const mt = r.mellomtitler || {};
    const { d, inn } = seksjon("Mellomtitler", mt.forslag?.length || null);
    inn.appendChild(el("p", null, esc(mt.vurdering)));
    (mt.forslag || []).forEach((f) => {
      const div = el("div", "boks");
      if (f.original) div.appendChild(el("div", "smånote", "Fra: " + esc(f.original)));
      div.appendChild(el("div", null, "<strong>" + esc(f.forslag) + "</strong>"));
      inn.appendChild(div);
    });
    rot.appendChild(d);
  }

  // Titler
  {
    const { d, inn } = seksjon("Tittelforslag", r.titler?.length || null);
    (r.titler || []).forEach((t) => {
      const div = el("div", "tittelforslag");
      div.appendChild(el("span", "forkl-tittel", esc(t.forklarende)));
      div.appendChild(el("span", "sitat-tittel", esc(t.sitat)));
      inn.appendChild(div);
    });
    rot.appendChild(d);
  }

  // Omskrivinger
  if (r.omskrivinger?.length) {
    const { d, inn } = seksjon("Omskrivinger", r.omskrivinger.length);
    r.omskrivinger.forEach((o) => {
      const div = el("div", "boks");
      div.appendChild(el("div", "smånote", "Original:"));
      div.appendChild(el("div", "orig", esc(o.original)));
      div.appendChild(el("div", "smånote", "Forslag:"));
      div.appendChild(el("div", null, esc(o.omskriving)));
      if (o.forklaring) div.appendChild(el("div", "forkl", esc(o.forklaring)));
      inn.appendChild(div);
    });
    rot.appendChild(d);
  }

  // Kopi-bokser med ferdige endringsforslag (nederst)
  byggKopibokser(rot, r);
}

// --- Stikkords-oversikt -----------------------------------------------------
function byggStikkord(rot, r) {
  const liste = r.oppsummering_stikkord || [];
  if (!liste.length) return;
  const { d, inn } = seksjon("Alle funn – stikkord", liste.length, true);
  const sky = el("div", "stikkordsky");
  liste.forEach((s) => {
    const chip = el("button", `chip k-${esc(s.kategori)}`, esc(s.stikkord));
    chip.title = (KAT_NAVN[s.kategori] || s.kategori) + (s.sitat ? " – klikk for å hoppe til teksten" : "");
    if (s.sitat && sisteFane) chip.addEventListener("click", () => hoppTilSitat(s.sitat));
    else chip.classList.add("passiv");
    sky.appendChild(chip);
  });
  inn.appendChild(sky);
  if (sisteFane) inn.appendChild(el("p", "smånote", "Klikk et stikkord for å hoppe til stedet i teksten."));
  rot.appendChild(d);
}

// --- Score-popup ------------------------------------------------------------
function openScorePopup(navn, kat, tall) {
  const forkl = (sisteRapport?.score_forklaringer && sisteRapport.score_forklaringer[kat]) || [];
  const backdrop = el("div", "popup-backdrop");
  const boks = el("div", "popup");
  const head = el("div", "popup-head");
  head.appendChild(el("strong", null, `${esc(navn)} — ${tall ?? "–"}/10`));
  const lukk = el("button", "popup-lukk", "✕");
  lukk.addEventListener("click", () => backdrop.remove());
  head.appendChild(lukk);
  boks.appendChild(head);

  if (!forkl.length) {
    boks.appendChild(el("p", "smånote", "Ingen konkrete trekk registrert her – god score."));
  } else {
    boks.appendChild(el("p", "popup-undertittel", "Dette trekker ned:"));
    forkl.forEach((f) => {
      const row = el("div", "popup-grunn");
      row.appendChild(el("div", null, "• " + esc(f.grunn)));
      if (f.sitat) {
        row.appendChild(el("div", "orig", "«" + esc(f.sitat) + "»"));
        if (sisteFane) {
          const b = el("button", "minivis", "Vis i tekst →");
          b.addEventListener("click", () => {
            backdrop.remove();
            hoppTilSitat(f.sitat);
          });
          row.appendChild(b);
        }
      }
      boks.appendChild(row);
    });
  }
  backdrop.appendChild(boks);
  backdrop.addEventListener("click", (e) => {
    if (e.target === backdrop) backdrop.remove();
  });
  document.body.appendChild(backdrop);
}

// --- Kopi-bokser ------------------------------------------------------------
function byggKopibokser(rot, r) {
  const items = [];
  (r.sprak?.funn || []).forEach((f) => f.forslag && items.push(["Språk", f.forslag]));
  if (r.ingress?.trenger_ny && r.ingress?.ny_ingress) items.push(["Ny ingress", r.ingress.ny_ingress]);
  (r.mellomtitler?.forslag || []).forEach((f) => f.forslag && items.push(["Mellomtittel", f.forslag]));
  (r.omskrivinger || []).forEach((o) => o.omskriving && items.push(["Omskriving", o.omskriving]));
  (r.titler || []).forEach((t) => items.push(["Tittelforslag", `${t.forklarende}\n${t.sitat}`]));
  if (!items.length) return;

  const { d, inn } = seksjon("Ditt forslag til endringene – klar til å kopiere", items.length, true);
  items.forEach(([merke, tekst]) => inn.appendChild(kopiBoks(merke, tekst)));
  rot.appendChild(d);
}

function kopiBoks(merke, tekst) {
  const boks = el("div", "kopiboks");
  const topp = el("div", "kopiboks-topp");
  topp.appendChild(el("span", "kopiboks-merke", esc(merke)));
  const knapp = el("button", "kopiboks-knapp", "Kopier");
  knapp.addEventListener("click", async () => {
    await kopierTekst(tekst);
    knapp.textContent = "Kopiert ✓";
    setTimeout(() => (knapp.textContent = "Kopier"), 1500);
  });
  topp.appendChild(knapp);
  boks.appendChild(topp);
  boks.appendChild(el("div", "kopiboks-tekst", esc(tekst)));
  return boks;
}

// --- Handlingsrad + fargeforklaring -----------------------------------------
function byggHandlingsrad(rot, r, fane) {
  const rad = el("div", "handlingsrad");
  const kopi = el("button", "småknapp", "Kopier hele rapporten");
  kopi.addEventListener("click", async () => {
    await kopierTekst(rapportSomMarkdown(r));
    kopi.textContent = "Kopiert ✓";
    setTimeout(() => (kopi.textContent = "Kopier hele rapporten"), 1500);
  });
  rad.appendChild(kopi);
  if (fane) {
    const fjern = el("button", "småknapp", "Fjern markeringer");
    fjern.addEventListener("click", () => chrome.tabs.sendMessage(fane.id, { action: "fjernMarkeringer" }));
    rad.appendChild(fjern);
  }
  rot.appendChild(rad);

  const leg = el("div", "forklaring");
  [
    ["sprak", "Språk"],
    ["fakta", "Fakta"],
    ["vvp", "Vær Varsom"],
    ["presseetikk", "Presseetikk"]
  ].forEach(([k, navn]) => {
    const item = el("span", "leg-item");
    item.appendChild(el("span", `leg-prikk k-${k}`));
    item.appendChild(el("span", null, navn));
    leg.appendChild(item);
  });
  rot.appendChild(leg);
}

// --- Rapport som Markdown (for kopiering til e-post/dokument) ----------------
function rapportSomMarkdown(r) {
  const s = r.sluttvurdering || {};
  const L = [];
  L.push(`# Redaksjonell vurdering`);
  L.push(`**Publiseringsklar: ${s.publiseringsklar || "?"}**`);
  if (s.begrunnelse) L.push(s.begrunnelse);
  L.push("");
  L.push(`## Terningkast`);
  [
    ["Lesbarhet", s.lesbarhet],
    ["Språk", s.sprak],
    ["Dramaturgi", s.dramaturgi],
    ["Presseetikk", s.presseetikk],
    ["VVP", s.vvp],
    ["Sjanger", s.sjangertilpasning],
    ["Tittel", s.tittel],
    ["Ingress", s.ingress],
    ["Helhet", s.helhetsinntrykk]
  ].forEach(([n, v]) => L.push(`- ${n}: ${v ?? "–"}/10`));

  const kf = r.kritiske_feil || {};
  L.push("", `## Kritiske feil`, `**Må rettes:**`);
  (kf.ma_rettes || []).forEach((x) => L.push(`- ${x}`));
  L.push(`**Bør forbedres:**`);
  (kf.bor_forbedres || []).forEach((x) => L.push(`- ${x}`));

  if (r.oppsummering_stikkord?.length) {
    L.push("", `## Alle funn (stikkord)`);
    r.oppsummering_stikkord.forEach((x) => L.push(`- [${KAT_NAVN[x.kategori] || x.kategori}] ${x.stikkord}`));
  }
  if (r.sprak?.funn?.length) {
    L.push("", `## Språk`);
    r.sprak.funn.forEach((f) => L.push(`- «${f.original}» → «${f.forslag}» (${f.forklaring})`));
  }
  if (r.vvp?.funn?.length) {
    L.push("", `## Vær Varsom-plakaten`);
    r.vvp.funn.forEach((f) => L.push(`- ${f.omrade}: ${f.forklaring}${f.sitat ? ` («${f.sitat}»)` : ""}`));
  }
  if (r.fakta?.funn?.length) {
    L.push("", `## Navn, titler og fakta`);
    r.fakta.funn.forEach((f) => L.push(`- ${f.element}: ${f.problem}${f.sitat ? ` («${f.sitat}»)` : ""}`));
  }
  if (r.titler?.length) {
    L.push("", `## Tittelforslag`);
    r.titler.forEach((t) => L.push(`- ${t.forklarende} ${t.sitat}`));
  }
  if (r.ingress?.trenger_ny && r.ingress?.ny_ingress) {
    L.push("", `## Forslag til ny ingress`, r.ingress.ny_ingress);
  }
  if (r.omskrivinger?.length) {
    L.push("", `## Omskrivinger`);
    r.omskrivinger.forEach((o) => L.push(`- Original: «${o.original}»`, `  Forslag: «${o.omskriving}»`));
  }
  return L.join("\n");
}

// Esc lukker en åpen popup.
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    const b = document.querySelector(".popup-backdrop");
    if (b) b.remove();
  }
});

init();
