(() => {
  "use strict";
  const root = document.documentElement, KEY = "plan-preview-theme";
  const $ = (sel, el) => (el || document).querySelector(sel);
  const all = (sel, el) => Array.from((el || document).querySelectorAll(sel));
  const lower = (s) => (s || "").toLocaleLowerCase("tr");
  const media = (q) => window.matchMedia && matchMedia(q).matches, reduced = media("(prefers-reduced-motion: reduce)");
  const theme = () => root.getAttribute("data-theme") || (media("(prefers-color-scheme: dark)") ? "dark" : "light");

  /* Theme */
  const themeButton = $("#theme");
  const themeLabel = () => {
    themeButton.title = "Temayı " + (theme() === "dark" ? "açık" : "koyu") + " yap";
    themeButton.setAttribute("aria-label", themeButton.title);
  };
  themeLabel();
  themeButton.addEventListener("click", () => {
    const next = theme() === "dark" ? "light" : "dark";
    root.setAttribute("data-theme", next);
    try { localStorage.setItem(KEY, next); } catch (e) { /* storage may be blocked */ }
    themeLabel(); drawCurrent();
  });

  /* Navigation drawer on a phone */
  const nav = $("#nav"), navToggle = $(".nav-toggle"), scrim = $(".scrim");
  const setNav = (open) => {
    nav.classList.toggle("is-open", open); scrim.hidden = !open;
    navToggle.setAttribute("aria-expanded", open ? "true" : "false");
    navToggle.setAttribute("aria-label", open ? "Menüyü kapat" : "Menüyü aç");
  };
  navToggle.addEventListener("click", () => setNav(!nav.classList.contains("is-open")));
  scrim.addEventListener("click", () => setNav(false));

  /* Sections as vertical tabs with arrow, Home and End keys */
  const tabs = all('[role="tab"]'), panels = all('[role="tabpanel"]');
  let currentTab = "";
  const activate = (name, focus) => {
    tabs.forEach((tab) => {
      const on = tab.dataset.tab === name;
      tab.setAttribute("aria-selected", on ? "true" : "false"); tab.tabIndex = on ? 0 : -1;
      if (on && focus) tab.focus();
    });
    panels.forEach((panel) => panel.classList.toggle("is-active", panel.dataset.tab === name));
    currentTab = name;
    if (nav.classList.contains("is-open")) setNav(false);
    if (name === "diyagramlar") selectDiagram(currentDiagram || firstId(".diagram"));
    if (name === "veri") { selectEntity(currentEntity || firstId(".entity")); drawUml(); }
  };
  tabs.forEach((tab, i) => {
    tab.addEventListener("click", (e) => {
      e.preventDefault(); activate(tab.dataset.tab);
      history.replaceState(null, "", "#panel-" + tab.dataset.tab); window.scrollTo(0, 0);
    });
    tab.addEventListener("keydown", (e) => {
      const n = tabs.length;
      const j = { ArrowDown: (i + 1) % n, ArrowRight: (i + 1) % n, ArrowUp: (i - 1 + n) % n, ArrowLeft: (i - 1 + n) % n,
        Home: 0, End: n - 1 }[e.key];
      if (j !== undefined) { e.preventDefault(); activate(tabs[j].dataset.tab, true); }
    });
  });
  const firstId = (sel) => { const el = $(sel); return el ? el.id : ""; };

  /* Collapsibles open and close with a short ease-out slide; with reduced motion they switch at once. */
  const slide = (el, from, to, done) => {
    if (reduced || !el.animate) { if (done) done(); return; }
    el.style.overflow = "hidden";
    el.animate([{ height: from + "px" }, { height: to + "px" }], { duration: 180, easing: "ease-out" }).onfinish = () => {
      el.style.overflow = ""; if (done) done();
    };
  };
  document.addEventListener("click", (e) => {
    const summary = e.target.closest && e.target.closest("details > summary");
    if (!summary || reduced) return;
    const d = summary.parentElement, start = d.offsetHeight;
    e.preventDefault();
    if (d.open) slide(d, start, summary.offsetHeight, () => { d.open = false; });
    else { d.open = true; slide(d, start, d.offsetHeight); }
  });

  /* Rows that open a detail row */
  const setRow = (row, open) => {
    const detail = $(".xdetail", row), body = $(".xbody", row);
    row.classList.toggle("is-open", open);
    $(".xtoggle", row).setAttribute("aria-expanded", open ? "true" : "false");
    if (open === !detail.hidden) return;
    if (open) { detail.hidden = false; slide(body, 0, body.offsetHeight); }
    else slide(body, body.offsetHeight, 0, () => { detail.hidden = true; });
  };
  document.addEventListener("click", (e) => {
    const main = e.target.closest && e.target.closest(".xmain");
    if (!main || (e.target.closest("a, input, select") && !e.target.closest(".xtoggle"))) return;
    const row = main.closest(".xrow");
    setRow(row, !row.classList.contains("is-open"));
  });

  /* One diagram and one table at a time, picked from the index */
  let currentDiagram = "", currentEntity = "";
  const pick = (items, links, attr, id) => {
    items.forEach((el) => el.classList.toggle("is-current", el.id === id));
    links.forEach((a) => a.setAttribute("aria-current", a.getAttribute(attr) === id ? "true" : "false"));
  };
  function selectDiagram(id) {
    if (!id) return;
    currentDiagram = id;
    pick(all(".diagram"), all("[data-diagram]"), "data-diagram", id);
    const fig = document.getElementById(id);
    if (fig && currentTab === "diyagramlar") requestAnimationFrame(() => draw(fig));
  }
  function selectEntity(id) {
    if (!id) return;
    currentEntity = id;
    pick(all(".entity"), all("[data-entity]"), "data-entity", id);
  }

  /* Data model view: the fields table or the UML class box, remembered per viewer */
  const VIEW_KEY = "plan-preview-entity-view", dataPanel = $("#panel-veri");
  const setView = (name) => {
    if (!dataPanel) return;
    dataPanel.classList.toggle("is-uml", name === "uml");
    drawUml();
    all("[data-view]", dataPanel).forEach((b) => b.setAttribute("aria-pressed", b.dataset.view === name ? "true" : "false"));
    try { localStorage.setItem(VIEW_KEY, name); } catch (e) { /* storage may be blocked */ }
  };
  all("[data-view]").forEach((b) => b.addEventListener("click", () => setView(b.dataset.view)));
  try { if (localStorage.getItem(VIEW_KEY) === "uml") setView("uml"); } catch (e) { /* storage may be blocked */ }

  /* Filters: each bar filters the rows its data-filters selector names */
  const bars = all("[data-filters]");
  const applyBar = (bar) => {
    const rows = all(bar.dataset.filters), controls = all("[data-key]", bar);
    rows.forEach((row) => {
      row.hidden = !controls.every((c) => {
        const value = c.value.trim();
        if (!value) return true;
        if (c.dataset.key === "q") return lower(row.dataset.q || row.textContent).includes(lower(value));
        return (" " + (row.dataset[c.dataset.key] || "") + " ").includes(" " + value + " ");
      });
    });
    const shown = rows.filter((r) => !r.hidden).length, out = $("[data-count]", bar);
    if (out) out.textContent = shown + " / " + rows.length + " gösteriliyor";
  };
  const resetBar = (bar) => { all("[data-key]", bar).forEach((c) => { c.value = ""; }); applyBar(bar); };
  bars.forEach((bar) => {
    all("[data-key]", bar).forEach((c) => c.addEventListener(c.tagName === "SELECT" ? "change" : "input", () => applyBar(bar)));
    const reset = $("[data-reset]", bar);
    if (reset) reset.addEventListener("click", () => resetBar(bar));
    applyBar(bar);
  });

  /* Deep links: switch section, clear a hiding filter, open the parents, scroll and highlight */
  const reveal = (id) => {
    const el = id && document.getElementById(id), panel = el && el.closest('[role="tabpanel"]');
    if (!el) return false;
    if (panel) activate(panel.dataset.tab);
    if (panel && el === panel) { window.scrollTo(0, 0); return true; }
    const row = el.closest(".xrow");
    if (row) setRow(row, true);
    const fig = el.closest(".diagram"), entity = el.closest(".entity");
    if (fig) selectDiagram(fig.id);
    if (entity) selectEntity(entity.id);
    for (let d = el.closest("details"); d; d = d.parentElement.closest("details")) d.open = true;
    if (el.closest("[hidden]")) bars.forEach(resetBar);
    requestAnimationFrame(() => {
      el.scrollIntoView({ block: fig || entity ? "start" : "center", behavior: reduced ? "auto" : "smooth" });
      const mark = row ? $(".xmain", row) : el;
      mark.classList.remove("flash"); void mark.offsetWidth; mark.classList.add("flash");
      if (!el.hasAttribute("tabindex")) el.setAttribute("tabindex", "-1");
      el.focus({ preventScroll: true });
    });
    return true;
  };
  const fromHash = () => {
    const id = decodeURIComponent(location.hash.slice(1));
    if (!reveal(id) && tabs.length) activate(tabs[0].dataset.tab);
  };
  window.addEventListener("hashchange", fromHash);
  document.addEventListener("click", (e) => {
    const a = e.target.closest && e.target.closest('a[href^="#"]');
    const id = a && a.getAttribute("role") !== "tab" && decodeURIComponent(a.getAttribute("href").slice(1));
    if (id && location.hash.slice(1) === id) { e.preventDefault(); reveal(id); }
  });

  /* Search over IDs and titles, grouped by category, as a combobox */
  const input = $("#q"), list = $("#q-results");
  const entries = all("[data-sid]").map((el) => ({ anchor: el.id, id: el.dataset.sid || "", title: el.dataset.stitle || "",
    cat: el.dataset.scat || "Diğer" }));
  const cats = [];
  entries.forEach((e) => { if (!cats.includes(e.cat)) cats.push(e.cat); });
  let active = -1, current = [];
  const close = () => {
    if (!list.hidden && !reduced && list.animate) {
      list.animate([{ opacity: 1 }, { opacity: 0, transform: "translateY(-4px)" }], { duration: 150, easing: "ease-out" })
        .onfinish = () => { if (input.getAttribute("aria-expanded") === "false") list.hidden = true; };
    } else list.hidden = true;
    active = -1;
    input.setAttribute("aria-expanded", "false"); input.removeAttribute("aria-activedescendant");
  };
  const mark = (i) => {
    const opts = all('[role="option"]', list);
    opts.forEach((o, k) => o.setAttribute("aria-selected", k === i ? "true" : "false"));
    active = i;
    if (!opts[i]) return;
    input.setAttribute("aria-activedescendant", opts[i].id); opts[i].scrollIntoView({ block: "nearest" });
  };
  const go = (anchor) => {
    close(); input.blur();
    if (location.hash.slice(1) === anchor) reveal(anchor); else location.hash = anchor;
  };
  const node = (tag, cls, text) => Object.assign(document.createElement(tag), { className: cls, textContent: text });
  input.addEventListener("input", () => {
    const q = lower(input.value.trim()), rank = (e) => (lower(e.id) === q ? 0 : lower(e.id).startsWith(q) ? 1 : 2);
    list.textContent = "";
    if (!q) { close(); return; }
    const found = entries.filter((e) => lower(e.id).includes(q) || lower(e.title).includes(q));
    // A category whose IDs match comes before one that matches only in titles; inside it, the best match first.
    const best = {};
    found.forEach((e) => { best[e.cat] = Math.min(best[e.cat] === undefined ? 9 : best[e.cat], rank(e)); });
    current = found.sort((a, b) => best[a.cat] - best[b.cat] || cats.indexOf(a.cat) - cats.indexOf(b.cat)
      || rank(a) - rank(b)).slice(0, 30);
    if (!current.length) list.appendChild(node("li", "qnone", "Eşleşen kimlik veya başlık yok."));
    let cat = "";
    current.forEach((e, i) => {
      if (e.cat !== cat) {
        cat = e.cat;
        const head = node("li", "qcat", cat);
        head.setAttribute("role", "presentation");
        list.appendChild(head);
      }
      const li = Object.assign(node("li", "", ""), { id: "q-opt-" + i });
      li.setAttribute("role", "option");
      li.append(node("span", "qid", e.id || "belge"), node("span", "qt", e.title));
      li.addEventListener("mousedown", (ev) => { ev.preventDefault(); go(e.anchor); });
      list.appendChild(li);
    });
    list.hidden = false; input.setAttribute("aria-expanded", "true");
    if (current.length) mark(0);
  });
  input.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown" && current.length) { e.preventDefault(); mark(Math.min(active + 1, current.length - 1)); }
    else if (e.key === "ArrowUp" && current.length) { e.preventDefault(); mark(Math.max(active - 1, 0)); }
    else if (e.key === "Enter" && current[active]) { e.preventDefault(); go(current[active].anchor); }
    else if (e.key === "Escape") { input.value = ""; close(); }
  });
  input.addEventListener("blur", () => setTimeout(close, 120));
  document.addEventListener("keydown", (e) => {
    const typing = /^(input|select|textarea)$/i.test(e.target.tagName || "");
    if ((e.key === "/" && !typing) || ((e.metaKey || e.ctrlKey) && lower(e.key) === "k")) { e.preventDefault(); input.focus(); }
    else if (e.key === "Escape") { setNav(false); all(".dstage.is-full").forEach((s) => setFull(s, false)); }
  });

  /* Copy an ID */
  document.addEventListener("click", (e) => {
    const button = e.target.closest && e.target.closest("[data-copy]");
    if (!button) return;
    const done = () => { button.classList.add("is-done"); setTimeout(() => button.classList.remove("is-done"), 1200); };
    const text = button.dataset.copy;
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(done, () => {});
    else {
      const area = Object.assign(document.createElement("textarea"), { value: text });
      document.body.appendChild(area); area.select();
      try { document.execCommand("copy"); done(); } catch (err) { /* copy is not allowed here */ }
      area.remove();
    }
  });

  /* Diagrams: drawn when shown, then panned and zoomed inside their canvas */
  const view = new Map();
  let counter = 0;
  const apply = (fig) => {
    const v = view.get(fig);
    $(".viewport", fig).style.transform = "translate(" + v.x + "px," + v.y + "px) scale(" + v.s + ")";
    $(".zoom", fig).textContent = Math.round(v.s * 100) + "%";
  };
  const place = (fig, mode) => {
    const v = view.get(fig), canvas = $(".canvas", fig);
    if (!v) return;
    const cw = canvas.clientWidth, ch = canvas.clientHeight, fit = Math.min(cw / v.w, ch / v.h) * 0.95;
    // A big diagram opens readable (never under 60%) and is panned, not shrunk into the box.
    v.s = mode === "fit" ? fit : mode === "reset" ? 1 : Math.min(1, Math.max(fit, 0.6));
    v.x = Math.max(16, (cw - v.w * v.s) / 2); v.y = Math.max(16, (ch - v.h * v.s) / 2);
    apply(fig);
  };
  const zoomAt = (fig, factor, cx, cy) => {
    const v = view.get(fig);
    if (!v) return;
    const s = Math.min(4, Math.max(0.2, v.s * factor));
    v.x = cx - (cx - v.x) * (s / v.s); v.y = cy - (cy - v.y) * (s / v.s); v.s = s;
    apply(fig);
  };
  const center = (fig) => { const c = $(".canvas", fig); return [c.clientWidth / 2, c.clientHeight / 2]; };
  function setFull(stage, on) {
    const fig = stage.closest(".diagram"), button = $('[data-act="full"]', stage);
    if (stage.requestFullscreen && on !== false && !document.fullscreenElement) { stage.requestFullscreen().catch(() => setFull(stage, true)); return; }
    if (document.fullscreenElement === stage) { document.exitFullscreen(); return; }
    stage.classList.toggle("is-full", on);
    button.setAttribute("aria-pressed", on ? "true" : "false");
    requestAnimationFrame(() => place(fig, "fit"));
  }
  document.addEventListener("fullscreenchange", () => all(".dstage").forEach((stage) => {
    const on = document.fullscreenElement === stage;
    $('[data-act="full"]', stage) && $('[data-act="full"]', stage).setAttribute("aria-pressed", on ? "true" : "false");
    const fig = stage.closest(".diagram");
    if (view.has(fig)) requestAnimationFrame(() => place(fig, on ? "fit" : "open"));
  }));
  all(".diagram").forEach((fig) => {
    const canvas = $(".canvas", fig);
    if (!canvas) return;
    all("[data-act]", fig).forEach((button) => button.addEventListener("click", () => {
      const act = button.dataset.act, [cx, cy] = center(fig);
      if (act === "in") zoomAt(fig, 1.25, cx, cy);
      else if (act === "out") zoomAt(fig, 0.8, cx, cy);
      else if (act === "full") setFull($(".dstage", fig), !$(".dstage", fig).classList.contains("is-full"));
      else place(fig, act);
    }));
    let drag = null;
    canvas.addEventListener("pointerdown", (e) => {
      const v = view.get(fig);
      if (!v || e.button !== 0) return;
      drag = { x: e.clientX - v.x, y: e.clientY - v.y }; canvas.setPointerCapture(e.pointerId); canvas.classList.add("is-dragging");
    });
    canvas.addEventListener("pointermove", (e) => {
      const v = view.get(fig);
      if (!drag || !v) return;
      v.x = e.clientX - drag.x; v.y = e.clientY - drag.y; apply(fig);
    });
    const stop = () => { drag = null; canvas.classList.remove("is-dragging"); };
    canvas.addEventListener("pointerup", stop); canvas.addEventListener("pointercancel", stop);
    canvas.addEventListener("wheel", (e) => {
      const v = view.get(fig);
      if (!v) return;
      const box = canvas.getBoundingClientRect();
      if (e.ctrlKey || e.metaKey) { e.preventDefault(); zoomAt(fig, e.deltaY < 0 ? 1.1 : 0.9, e.clientX - box.left, e.clientY - box.top); return; }
      // Plain scrolling pans only a diagram larger than its canvas; otherwise the page scrolls.
      if (v.w * v.s <= canvas.clientWidth && v.h * v.s <= canvas.clientHeight) return;
      e.preventDefault(); v.x -= e.deltaX; v.y -= e.deltaY; apply(fig);
    }, { passive: false });
    canvas.addEventListener("keydown", (e) => {
      const v = view.get(fig), [cx, cy] = center(fig), step = 48;
      if (!v) return;
      const moves = { ArrowLeft: [step, 0], ArrowRight: [-step, 0], ArrowUp: [0, step], ArrowDown: [0, -step] };
      if (moves[e.key]) { v.x += moves[e.key][0]; v.y += moves[e.key][1]; apply(fig); }
      else if (e.key === "+" || e.key === "=") zoomAt(fig, 1.25, cx, cy);
      else if (e.key === "-") zoomAt(fig, 0.8, cx, cy);
      else if (e.key === "0") place(fig, "reset");
      else if (lower(e.key) === "f") place(fig, "fit");
      else return;
      e.preventDefault();
    });
  });

  const offline = () => {
    if (!$("pre.mermaid")) return;
    root.classList.add("mermaid-offline");
    $(".mermaid-note").hidden = false;
    all(".dstatus").forEach((s) => { s.hidden = true; });
  };
  let ready = false;
  function draw(fig) {
    const src = $("pre.mermaid", fig), out = $(".viewport", fig), status = $(".dstatus", fig);
    if (!src || !ready || fig.dataset.drawn === theme()) return;
    try {
      mermaid.initialize({ startOnLoad: false, theme: theme() === "dark" ? "dark" : "neutral", securityLevel: "strict",
        fontFamily: getComputedStyle(document.body).fontFamily, flowchart: { useMaxWidth: false },
        sequence: { useMaxWidth: false }, er: { useMaxWidth: false }, state: { useMaxWidth: false } });
    } catch (e) { return; }
    fig.dataset.drawn = theme(); status.hidden = false; status.textContent = "Diyagram çiziliyor.";
    mermaid.render("mmd-" + (++counter), src.textContent).then((result) => {
      out.innerHTML = result.svg; out.hidden = false; status.hidden = true; fig.classList.remove("render-failed");
      const svg = $("svg", out), box = svg.viewBox && svg.viewBox.baseVal;
      const w = (box && box.width) || svg.getBoundingClientRect().width || 800;
      const h = (box && box.height) || svg.getBoundingClientRect().height || 600;
      svg.setAttribute("width", w); svg.setAttribute("height", h); svg.style.maxWidth = "none";
      const details = $(".diagram-src", fig);
      details.open = false; $("summary", details).textContent = "Mermaid kaynağını göster";
      const old = view.get(fig);
      view.set(fig, { w: w, h: h, s: 1, x: 0, y: 0 });
      if (old) { Object.assign(view.get(fig), { s: old.s, x: old.x, y: old.y }); apply(fig); } else place(fig, "open");
    }).catch((err) => {
      fig.classList.add("render-failed"); out.hidden = true; status.hidden = true; delete fig.dataset.drawn;
      $(".diagram-offline", fig).textContent = "Diyagram çizilemedi: " + ((err && err.message) || err) + ". Mermaid kaynağı aşağıda.";
      $(".diagram-src", fig).open = true;
    });
  }
  function drawCurrent() {
    all(".diagram").forEach((fig) => { delete fig.dataset.drawn; });
    const fig = currentDiagram && document.getElementById(currentDiagram);
    if (fig && currentTab === "diyagramlar") draw(fig);
    drawUml();
  }
  /* The UML class diagram of the data model is drawn when its view is shown. */
  function drawUml() {
    const fig = $(".uml-figure");
    if (fig && currentTab === "veri" && dataPanel.classList.contains("is-uml")) requestAnimationFrame(() => draw(fig));
  }
  window.planDraw = () => {
    if (!window.mermaid) { offline(); return; }
    // Mermaid would draw every pre.mermaid on window load, also the hidden ones; diagrams are drawn when shown.
    try { mermaid.initialize({ startOnLoad: false }); } catch (e) { offline(); return; }
    ready = true; drawCurrent();
  };
  window.planOffline = offline;

  window.addEventListener("beforeprint", () => all("details").forEach((d) => {
    d.dataset.wasOpen = d.open ? "1" : ""; d.open = true;
  }));
  window.addEventListener("afterprint", () => all("details").forEach((d) => { d.open = d.dataset.wasOpen === "1"; }));
  fromHash();

  // Reload keeps the section, the scroll position and the filters across a reload.
  // While the run is active the page reloads itself every 30 seconds, only when it is visible and nobody types in it.
  const RELOAD_KEY = "plan-preview-reload";
  const reload = () => {
    const values = {};
    bars.forEach((bar) => all("[data-key]", bar).forEach((c) => { values[bar.dataset.filters + "|" + c.dataset.key] = c.value; }));
    try {
      sessionStorage.setItem(RELOAD_KEY, JSON.stringify({ tab: currentTab, y: window.scrollY, filters: values }));
    } catch (e) { /* storage may be blocked */ }
    location.reload();
  };
  $("#reload").addEventListener("click", reload);
  let saved = null;
  try { saved = JSON.parse(sessionStorage.getItem(RELOAD_KEY) || "null"); sessionStorage.removeItem(RELOAD_KEY); }
  catch (e) { saved = null; }
  if (saved) {
    if (saved.tab && tabs.some((t) => t.dataset.tab === saved.tab)) activate(saved.tab);
    bars.forEach((bar) => {
      all("[data-key]", bar).forEach((c) => {
        const v = (saved.filters || {})[bar.dataset.filters + "|" + c.dataset.key];
        if (typeof v === "string") c.value = v;
      });
      applyBar(bar);
    });
    requestAnimationFrame(() => window.scrollTo(0, saved.y || 0));
  }
  if (root.dataset.live === "1") {
    setInterval(() => {
      const busy = document.activeElement && document.activeElement.matches("input, select, textarea");
      if (document.visibilityState === "visible" && !busy) reload();
    }, 30000);
  }
})();
