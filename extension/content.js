// Innhold-skript: injiseres i den aktive fanen på forespørsel fra sidepanelet.
// Ansvar:
//   1) Hente ut artikkelteksten (uten å endre den).
//   2) Legge fargemarkeringer OPPÅ teksten (overlay-lag) med notat ved hover.
//      Teksten i editoren røres aldri – markeringene er et eget lag som legges
//      over og reposisjoneres ved scroll/resize.

(() => {
  // Unngå dobbel-initialisering hvis skriptet injiseres flere ganger.
  if (window.__redaktorAssistent) {
    window.__redaktorAssistent.ready = true;
    return;
  }

  const FARGER = {
    sprak: { kant: "#e0a800", flate: "rgba(255, 214, 0, 0.28)" },
    vvp: { kant: "#c0392b", flate: "rgba(231, 76, 60, 0.25)" },
    fakta: { kant: "#d35400", flate: "rgba(230, 126, 34, 0.25)" },
    presseetikk: { kant: "#8e44ad", flate: "rgba(155, 89, 182, 0.25)" }
  };

  const state = {
    ready: true,
    root: null, // rot-elementet teksten ble hentet fra
    rootDoc: document, // dokumentet root ligger i (kan være et iframe-dokument)
    rootFrame: null, // iframe-elementet, hvis root ligger inne i et iframe
    markers: [], // { id, sitat, note, kategori, range }
    overlay: null,
    tooltip: null,
    repositionKø: false
  };
  window.__redaktorAssistent = state;

  // Forskyvning når teksten ligger inne i et iframe (koordinater må flyttes).
  function rammeForskyvning() {
    if (!state.rootFrame) return { x: 0, y: 0 };
    const r = state.rootFrame.getBoundingClientRect();
    return { x: r.left, y: r.top };
  }

  // --- Hjelp: normaliser og escape ---------------------------------------
  const escapeRegex = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

  // Finn en Range i `root` som matcher `needle` (fleksibel på mellomrom).
  function finnRange(root, needle) {
    if (!needle || !needle.trim()) return null;
    const ownerDoc = (root && root.ownerDocument) || document;
    const utsyn = ownerDoc.defaultView || window;
    const walker = ownerDoc.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode(node) {
        // Hopp over skjulte noder.
        const p = node.parentElement;
        if (!p) return NodeFilter.FILTER_REJECT;
        const stil = utsyn.getComputedStyle(p);
        if (stil.display === "none" || stil.visibility === "hidden")
          return NodeFilter.FILTER_REJECT;
        return NodeFilter.FILTER_ACCEPT;
      }
    });

    let full = "";
    const map = []; // map[i] = { node, offset }
    let node;
    while ((node = walker.nextNode())) {
      const t = node.nodeValue;
      for (let i = 0; i < t.length; i++) {
        full += t[i];
        map.push({ node, offset: i });
      }
    }

    // Bygg et regex som tåler ulikt antall mellomrom/linjeskift.
    const mønster = escapeRegex(needle.trim()).replace(/\s+/g, "\\s+");
    let treff;
    try {
      treff = new RegExp(mønster, "i").exec(full);
    } catch {
      return null;
    }
    if (!treff) return null;

    const start = treff.index;
    const slutt = start + treff[0].length - 1;
    if (!map[start] || !map[slutt]) return null;

    const range = ownerDoc.createRange();
    range.setStart(map[start].node, map[start].offset);
    range.setEnd(map[slutt].node, map[slutt].offset + 1);
    return range;
  }

  // --- Uthenting av tekst -------------------------------------------------
  function synligTekst(el) {
    return (el.innerText || el.textContent || "").trim();
  }

  // Selektorer for vanlige redigeringsfelt (inkl. rike editorer).
  const EDITOR_SELEKTOR =
    '[contenteditable="true"], [contenteditable=""], [role="textbox"], textarea, ' +
    ".ProseMirror, .public-DraftEditor-content, .ql-editor, .cke_editable, .mce-content-body";

  // Samle editor-kandidater fra hoveddokumentet + samme-opphav-iframes (TinyMCE m.fl.).
  function samleFelter() {
    const felter = [];
    const skann = (doc, frame) => {
      doc.querySelectorAll(EDITOR_SELEKTOR).forEach((el) => felter.push({ el, doc, frame }));
    };
    skann(document, null);
    document.querySelectorAll("iframe").forEach((fr) => {
      try {
        const d = fr.contentDocument;
        if (d && d.body) skann(d, fr);
      } catch {
        /* kryss-opphav iframe – kan ikke leses, hopp over */
      }
    });
    return felter;
  }

  function størstEditor() {
    let beste = null;
    let besteLengde = 40; // krev litt innhold for å unngå tomme felt
    for (const kand of samleFelter()) {
      const t = kand.el.tagName === "TEXTAREA" ? kand.el.value : synligTekst(kand.el);
      if (t && t.length > besteLengde) {
        besteLengde = t.length;
        beste = kand;
      }
    }
    return beste;
  }

  function settRot(el, doc, frame) {
    state.root = el;
    state.rootDoc = doc || (el && el.ownerDocument) || document;
    state.rootFrame = frame || null;
  }

  function hentTekst() {
    // 1) Markert tekst vinner (lar Mathias velge nøyaktig hva som sjekkes).
    const sel = window.getSelection();
    if (sel && sel.rangeCount && sel.toString().trim().length > 40) {
      const anker = sel.getRangeAt(0).commonAncestorContainer;
      settRot(anker.nodeType === 1 ? anker : anker.parentElement, document, null);
      return { text: sel.toString().trim(), kilde: "markering" };
    }

    // 2) Største redigerbare felt (typisk CMS-editoren), også inne i iframe.
    const editor = størstEditor();
    if (editor) {
      settRot(editor.el, editor.doc, editor.frame);
      const t = editor.el.tagName === "TEXTAREA" ? editor.el.value : synligTekst(editor.el);
      const kilde = editor.frame ? "editor (iframe)" : editor.el.tagName === "TEXTAREA" ? "tekstfelt" : "editor";
      return { text: t, kilde };
    }

    // 3) Fallback: <article> eller <main>.
    const artikkel = document.querySelector("article") || document.querySelector("main");
    if (artikkel) {
      settRot(artikkel, document, null);
      return { text: synligTekst(artikkel), kilde: "artikkel" };
    }

    // 4) Ingenting funnet – la panelet be om innliming.
    settRot(document.body, document, null);
    return { text: "", kilde: "ingen" };
  }

  // --- Markeringslag ------------------------------------------------------
  function sikreOverlay() {
    if (state.overlay) return;
    const overlay = document.createElement("div");
    overlay.id = "__redaktor-overlay";
    Object.assign(overlay.style, {
      position: "fixed",
      inset: "0",
      pointerEvents: "none",
      zIndex: "2147483646"
    });
    document.documentElement.appendChild(overlay);
    state.overlay = overlay;

    const tooltip = document.createElement("div");
    tooltip.id = "__redaktor-tooltip";
    Object.assign(tooltip.style, {
      position: "fixed",
      maxWidth: "320px",
      background: "#1c1c1c",
      color: "#fff",
      padding: "8px 10px",
      borderRadius: "6px",
      fontSize: "13px",
      lineHeight: "1.4",
      zIndex: "2147483647",
      pointerEvents: "none",
      display: "none",
      boxShadow: "0 4px 14px rgba(0,0,0,0.35)"
    });
    document.documentElement.appendChild(tooltip);
    state.tooltip = tooltip;

    window.addEventListener("scroll", planleggReposisjon, true);
    window.addEventListener("resize", planleggReposisjon, true);
  }

  function planleggReposisjon() {
    if (state.repositionKø) return;
    state.repositionKø = true;
    requestAnimationFrame(() => {
      state.repositionKø = false;
      tegnMarkeringer();
    });
  }

  function tegnMarkeringer() {
    if (!state.overlay) return;
    state.overlay.innerHTML = "";
    const off = rammeForskyvning();
    for (const m of state.markers) {
      if (!m.range) continue;
      const farge = FARGER[m.kategori] || FARGER.sprak;
      const rects = m.range.getClientRects();
      for (const r of rects) {
        if (r.width === 0 && r.height === 0) continue;
        const boks = document.createElement("div");
        Object.assign(boks.style, {
          position: "fixed",
          left: `${r.left + off.x}px`,
          top: `${r.top + off.y}px`,
          width: `${r.width}px`,
          height: `${r.height}px`,
          background: farge.flate,
          borderBottom: `2px solid ${farge.kant}`,
          borderRadius: "2px",
          pointerEvents: "auto",
          cursor: "help"
        });
        boks.dataset.markerid = m.id;
        boks.addEventListener("mouseenter", (e) => visTooltip(e, m));
        boks.addEventListener("mousemove", (e) => flyttTooltip(e));
        boks.addEventListener("mouseleave", skjulTooltip);
        state.overlay.appendChild(boks);
      }
    }
  }

  function visTooltip(e, m) {
    const tt = state.tooltip;
    tt.textContent = m.note || "";
    tt.style.display = "block";
    flyttTooltip(e);
  }
  function flyttTooltip(e) {
    const tt = state.tooltip;
    if (tt.style.display === "none") return;
    let x = e.clientX + 14;
    let y = e.clientY + 14;
    const b = tt.getBoundingClientRect();
    if (x + b.width > window.innerWidth) x = e.clientX - b.width - 14;
    if (y + b.height > window.innerHeight) y = e.clientY - b.height - 14;
    tt.style.left = `${Math.max(6, x)}px`;
    tt.style.top = `${Math.max(6, y)}px`;
  }
  function skjulTooltip() {
    if (state.tooltip) state.tooltip.style.display = "none";
  }

  function leggPåMarkeringer(markers) {
    sikreOverlay();
    const root = state.root || document.body;
    let funnet = 0;
    state.markers = markers.map((m) => {
      const range = finnRange(root, m.sitat);
      if (range) funnet++;
      return { ...m, range };
    });
    tegnMarkeringer();
    return { total: markers.length, funnet };
  }

  function rullTil(id) {
    const m = state.markers.find((x) => x.id === id);
    if (!m || !m.range) return false;
    const off = rammeForskyvning();
    const r = m.range.getBoundingClientRect();
    const y = r.top + off.y + window.scrollY - window.innerHeight / 3;
    window.scrollTo({ top: Math.max(0, y), behavior: "smooth" });
    // Blink.
    setTimeout(() => {
      tegnMarkeringer();
      const boks = state.overlay?.querySelector(`[data-markerid="${id}"]`);
      if (boks) {
        boks.animate(
          [
            { boxShadow: "0 0 0 0 rgba(0,0,0,0)" },
            { boxShadow: "0 0 0 4px rgba(52,152,219,0.9)" },
            { boxShadow: "0 0 0 0 rgba(0,0,0,0)" }
          ],
          { duration: 1200 }
        );
      }
    }, 350);
    return true;
  }

  function fjernMarkeringer() {
    state.markers = [];
    if (state.overlay) state.overlay.innerHTML = "";
    skjulTooltip();
  }

  // Hopp til et vilkårlig sitat (uavhengig av markeringene) og blink kort.
  function rullTilSitat(sitat) {
    const root = state.root || document.body;
    const range = finnRange(root, sitat);
    if (!range) return { ok: false };
    const off = rammeForskyvning();
    const r = range.getBoundingClientRect();
    window.scrollTo({ top: Math.max(0, r.top + off.y + window.scrollY - window.innerHeight / 3), behavior: "smooth" });
    setTimeout(() => {
      for (const rc of range.getClientRects()) {
        const b = document.createElement("div");
        Object.assign(b.style, {
          position: "fixed",
          left: `${rc.left + off.x}px`,
          top: `${rc.top + off.y}px`,
          width: `${rc.width}px`,
          height: `${rc.height}px`,
          background: "rgba(52,152,219,0.35)",
          border: "2px solid #2980b9",
          borderRadius: "3px",
          zIndex: "2147483645",
          pointerEvents: "none",
          transition: "opacity 0.5s"
        });
        document.documentElement.appendChild(b);
        setTimeout(() => {
          b.style.opacity = "0";
          setTimeout(() => b.remove(), 500);
        }, 1400);
      }
    }, 420);
    return { ok: true };
  }

  // --- Meldingslytter -----------------------------------------------------
  chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
    switch (msg?.action) {
      case "ping":
        sendResponse({ ok: true });
        break;
      case "hentTekst":
        sendResponse(hentTekst());
        break;
      case "leggPåMarkeringer":
        sendResponse(leggPåMarkeringer(msg.markers || []));
        break;
      case "rullTil":
        sendResponse({ ok: rullTil(msg.id) });
        break;
      case "fjernMarkeringer":
        fjernMarkeringer();
        sendResponse({ ok: true });
        break;
      default:
        sendResponse({ ok: false });
    }
    return true; // synkront svar, men behold kanalen for sikkerhets skyld
  });
})();
