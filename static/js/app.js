/* App shell: API client, toasts, settings, theme, navigation, auth pages, home (generation), dashboard. */
(function () {
  "use strict";
  window.DF = window.DF || {};
  var $ = function (id) { return document.getElementById(id); };
  var page = function () { return document.body.dataset.page; };

  /* ---------- API ---------- */
  async function request(method, url, body, asText) {
    var opts = { method: method, credentials: "same-origin", headers: { "X-Requested-With": "DiagramForge" } };
    if (body !== undefined) { opts.headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(body); }
    var res;
    try { res = await fetch(url, opts); }
    catch (e) { var ne = new Error("Network error. Check your connection."); ne.status = 0; throw ne; }
    var isJson = (res.headers.get("content-type") || "").indexOf("json") >= 0;
    if (!res.ok) {
      var data = isJson ? await res.json().catch(function () { return null; }) : null;
      var err = new Error((data && data.error) || "Request failed (" + res.status + ").");
      err.status = res.status; err.data = data; throw err;
    }
    return asText ? res.text() : (isJson ? res.json() : null);
  }
  DF.api = function (m, u, b) { return request(m, u, b, false); };
  DF.apiText = function (m, u, b) { return request(m, u, b, true); };

  DF.toast = function (msg, kind) {
    var t = document.createElement("div"); t.className = "toast " + (kind || ""); t.textContent = msg;
    $("toasts").appendChild(t); setTimeout(function () { t.remove(); }, kind === "error" ? 6500 : 3500);
  };

  DF.settings = {
    get: function (k, d) { try { var v = localStorage.getItem("df." + k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
    set: function (k, v) { try { localStorage.setItem("df." + k, JSON.stringify(v)); } catch (e) { /* storage blocked */ } },
  };
  DF.user = null;
  DF.types = [];
  DF.typeLabel = function (key) { var t = DF.types.find(function (x) { return x.key === key; }); return t ? t.label : key; };

  function el(tag, props, children) {
    var n = document.createElement(tag);
    Object.keys(props || {}).forEach(function (k) { if (k === "text") n.textContent = props[k]; else if (k === "class") n.className = props[k]; else n.setAttribute(k, props[k]); });
    (children || []).forEach(function (c) { n.appendChild(typeof c === "string" ? document.createTextNode(c) : c); });
    return n;
  }
  function fmtDate(s) { try { return new Date(s).toLocaleDateString(undefined, { month: "short", day: "numeric" }); } catch (e) { return ""; } }

  /* ---------- theme / nav ---------- */
  function applyThemeLabel() { $("themeLabel").textContent = document.documentElement.getAttribute("data-theme") === "dark" ? "Light theme" : "Dark theme"; }
  function initShell() {
    applyThemeLabel();
    $("themeToggle").addEventListener("click", function () {
      var next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", next);
      try { localStorage.setItem("df.theme", next); } catch (e) { /* ignore */ }
      applyThemeLabel();
    });
    $("navToggle").addEventListener("click", function () { document.body.classList.add("nav-open"); });
    $("scrim").addEventListener("click", function () { document.body.classList.remove("nav-open"); });
    $("navTemplates").addEventListener("click", openTemplates);
    $("navSettings").addEventListener("click", openSettings);
    var map = { home: "navNew", dashboard: "navProjects" };
    if (map[page()]) $(map[page()]).classList.add("active");
  }

  function renderAccount() {
    var box = $("accountBox"); box.innerHTML = "";
    if (DF.user) {
      var out = el("button", { class: "nav-item", type: "button" }, [el("span", { text: "Log out" })]);
      out.addEventListener("click", async function () { await DF.api("POST", "/api/auth/logout"); location.href = "/"; });
      box.appendChild(el("div", { class: "user-chip" }, [el("span", { class: "avatar", text: DF.user.username.slice(0, 1) }), el("span", { text: DF.user.username })]));
      box.appendChild(out);
    } else {
      var next = encodeURIComponent(location.pathname);
      box.appendChild(el("a", { class: "nav-item", href: "/login?next=" + next, text: "Log in" }));
      box.appendChild(el("a", { class: "nav-item", href: "/register?next=" + next, text: "Create account" }));
    }
  }

  DF.refreshRecents = async function () {
    var box = $("recentList");
    if (!DF.user) { box.innerHTML = ""; box.appendChild(el("div", { class: "empty-hint", text: "Log in to see your saved diagrams." })); return; }
    try {
      var res = await DF.api("GET", "/api/diagrams?limit=8");
      box.innerHTML = "";
      if (!res.diagrams.length) box.appendChild(el("div", { class: "empty-hint", text: "Nothing yet. Generate your first diagram." }));
      res.diagrams.slice(0, 6).forEach(function (d) {
        box.appendChild(el("a", { class: "recent-item", href: "/editor/" + d.diagram_id }, [d.diagram_title, el("small", { text: DF.typeLabel(d.diagram_type) })]));
      });
      if (page() === "home") renderRecentGrid(res.diagrams);
    } catch (e) { box.innerHTML = ""; box.appendChild(el("div", { class: "empty-hint", text: "Could not load recent diagrams." })); }
  };
  function diagramCard(d) {
    return el("a", { class: "card diagram-card", href: "/editor/" + d.diagram_id }, [
      el("h3", { text: d.diagram_title }),
      el("div", { class: "meta" }, [el("span", { class: "badge", text: DF.typeLabel(d.diagram_type) }), el("span", { text: "v" + d.version + " · " + fmtDate(d.updated_at) })]),
    ]);
  }
  function renderRecentGrid(list) {
    var sec = $("recentSection"), grid = $("recentGrid"); if (!sec) return;
    grid.innerHTML = ""; sec.hidden = !list.length;
    list.forEach(function (d) { grid.appendChild(diagramCard(d)); });
  }

  /* ---------- modals ---------- */
  function modal(title, body, actions) {
    var root = $("modalRoot"); root.innerHTML = "";
    var back = el("div", { class: "modal-back", role: "dialog", "aria-modal": "true", "aria-label": title });
    var box = el("div", { class: "card modal" }, [el("h2", { text: title }), body]);
    if (actions) box.appendChild(actions);
    back.appendChild(box); root.appendChild(back);
    function close() { root.innerHTML = ""; document.removeEventListener("keydown", esc); }
    function esc(e) { if (e.key === "Escape") close(); }
    document.addEventListener("keydown", esc);
    back.addEventListener("mousedown", function (e) { if (e.target === back) close(); });
    var f = box.querySelector("input,select,textarea,button"); if (f) f.focus();
    return close;
  }

  var TEMPLATES = [
    ["sequence", "E-commerce checkout", "Create a UML sequence diagram for an e-commerce application where a customer logs in, searches for products, adds products to a cart, completes payment and receives order confirmation."],
    ["architecture_high", "AI chatbot architecture", "Create a complete architecture diagram for an AI chatbot built using Flask, MongoDB, Cohere embeddings, a vector database and an LLM."],
    ["erd", "Library management ERD", "Design an entity relationship diagram for a library system with members, books, authors, loans, reservations and fines."],
    ["use_case", "Hospital use cases", "Create a use case diagram for a hospital management system with patients, doctors, receptionists and administrators."],
    ["class", "Online banking classes", "Create a class diagram for an online banking system with customers, accounts, transactions, cards and notifications."],
    ["dfd_1", "Food delivery DFD", "Create a Level 1 data flow diagram for a food delivery app with customers, restaurants, delivery partners and payments."],
    ["ci_cd", "CI/CD pipeline", "Create a CI/CD pipeline diagram: commit, build, unit tests, security scan, container image, staging deploy, approval and production deploy with rollback."],
    ["state", "Order lifecycle", "Create a state machine for an order: created, paid, packed, shipped, delivered, cancelled and refunded."],
    ["bpmn", "Leave approval (BPMN)", "Create a BPMN diagram for an employee leave request approved by a manager and then recorded by HR, with a rejection path."],
    ["auth_flow", "OAuth login flow", "Create an authentication flow for OAuth 2.0 login with an authorization code between user, web app, auth server and API."],
    ["three_tier", "Three-tier web app", "Create a three-tier architecture for a web application with browser clients, an application server and a relational database."],
    ["network_topology", "Office network", "Create a network topology for an office with a firewall, core switch, two access switches, Wi-Fi access points, a DMZ with web servers and a VPN gateway."],
  ];
  DF.templates = TEMPLATES;

  function openTemplates() {
    document.body.classList.remove("nav-open");
    var list = el("div", { class: "examples" });
    TEMPLATES.forEach(function (t) {
      var b = el("button", { class: "example", type: "button" }, [el("b", { text: DF.typeLabel(t[0]) }), t[1]]);
      b.addEventListener("click", function () {
        DF.settings.set("pendingTemplate", { type: t[0], prompt: t[2] });
        if (page() === "home") { applyPending(); $("modalRoot").innerHTML = ""; if ($("workspace") && !$("workspace").hidden) backToHome(); } else location.href = "/";
      });
      list.appendChild(b);
    });
    var close = el("button", { class: "btn", type: "button", text: "Close" });
    var actions = el("div", { class: "modal-actions" }, [close]);
    var c = modal("Diagram templates", list, actions); close.addEventListener("click", c);
  }

  function openSettings() {
    document.body.classList.remove("nav-open");
    var prov = el("select", { id: "setProv" }, [el("option", { value: "gemini", text: "Gemini" }), el("option", { value: "groq", text: "Groq" })]);
    prov.value = DF.settings.get("provider", "gemini");
    var scale = el("select", { id: "setScale" }, [1, 2, 3, 4].map(function (n) { return el("option", { value: n, text: n + "× " + ["standard", "sharp", "high", "max"][n - 1] }); }));
    scale.value = DF.settings.get("exportScale", 3);
    var theme = el("select", { id: "setTheme" }, [["default", "Default"], ["neutral", "Neutral"], ["forest", "Forest"], ["dark", "Dark"], ["base", "Base"]].map(function (t) { return el("option", { value: t[0], text: t[1] }); }));
    theme.value = DF.settings.get("mermaidTheme", "default");
    var fix = el("input", { type: "checkbox", id: "setFix" }); fix.checked = DF.settings.get("autoFix", true);
    var status = el("div", { class: "note", style: "color:var(--muted);font-size:13px", text: "Checking server…" });
    var form = el("div", { class: "form-grid" }, [
      el("label", { class: "field" }, ["AI provider", prov]), el("label", { class: "field" }, ["Default export quality", scale]),
      el("label", { class: "field" }, ["Default Mermaid theme", theme]),
      el("label", { class: "field", style: "flex-direction:row;align-items:center;gap:8px" }, [fix, "Automatically repair diagrams that fail to render (max 3 attempts)"]), status,
    ]);
    DF.api("GET", "/api/providers").then(function (p) {
      status.textContent = "Server providers configured: " + Object.keys(p.configured).map(function (k) { return k + (p.configured[k] ? " ✓" : " ✗ (no API key)"); }).join(", ");
    }).catch(function () { status.textContent = "Could not read provider status."; });
    var save = el("button", { class: "btn primary", type: "button", text: "Save" }), cancel = el("button", { class: "btn", type: "button", text: "Cancel" });
    var close = modal("Settings", form, el("div", { class: "modal-actions" }, [cancel, save]));
    cancel.addEventListener("click", close);
    save.addEventListener("click", function () {
      DF.settings.set("provider", prov.value); DF.settings.set("exportScale", parseInt(scale.value, 10)); DF.settings.set("mermaidTheme", theme.value); DF.settings.set("autoFix", fix.checked);
      if (DF.renderer) DF.renderer.setMermaidTheme(theme.value);
      if ($("providerSelect")) $("providerSelect").value = prov.value;
      if ($("exportScale")) $("exportScale").value = String(scale.value);
      close(); DF.toast("Settings saved.", "success");
    });
  }

  /* ---------- auth pages ---------- */
  function initAuth() {
    var reg = page() === "register";
    $("authForm").addEventListener("submit", async function (e) {
      e.preventDefault();
      var err = $("authError"), btn = $("authSubmit"); err.hidden = true;
      var body = { email: $("email").value.trim(), password: $("password").value };
      if (reg) body.username = $("username").value.trim();
      btn.disabled = true;
      try { await DF.api("POST", reg ? "/api/auth/register" : "/api/auth/login", body); location.href = document.body.dataset.next || "/"; }
      catch (ex) { err.textContent = ex.message; err.hidden = false; btn.disabled = false; }
    });
  }

  /* ---------- dashboard ---------- */
  async function initDashboard() {
    var box = $("projectsBox"), loose = $("looseGrid"), errBox = $("dashError");
    async function load() {
      try {
        var p = await DF.api("GET", "/api/projects"), d = await DF.api("GET", "/api/diagrams?limit=100");
        box.innerHTML = ""; loose.innerHTML = "";
        var byProject = {};
        d.diagrams.forEach(function (x) { if (x.project_id) (byProject[x.project_id] = byProject[x.project_id] || []).push(x); });
        if (!p.projects.length) box.appendChild(el("div", { class: "empty-hint", text: "No projects yet. Use “Complete documentation” on the home page, or create an empty project." }));
        p.projects.forEach(function (pr) {
          var del = el("button", { class: "btn sm danger", type: "button", text: "Delete project" });
          del.addEventListener("click", async function () {
            if (!confirm("Delete “" + pr.project_name + "” and all its diagrams? This cannot be undone.")) return;
            try { await DF.api("DELETE", "/api/projects/" + pr.project_id); load(); DF.refreshRecents(); } catch (e) { DF.toast(e.message, "error"); }
          });
          var grid = el("div", { class: "grid-cards" });
          (byProject[pr.project_id] || []).forEach(function (x) { grid.appendChild(diagramCard(x)); });
          if (!(byProject[pr.project_id] || []).length) grid.appendChild(el("div", { class: "empty-hint", text: "No diagrams in this project yet." }));
          box.appendChild(el("section", { class: "card project" }, [
            el("div", { class: "project-head" }, [el("div", {}, [el("h2", { text: pr.project_name, style: "font-size:18px" }), el("p", { text: pr.project_description || "Updated " + fmtDate(pr.updated_at) })]), del]), grid]));
        });
        d.diagrams.filter(function (x) { return !x.project_id; }).forEach(function (x) { loose.appendChild(diagramCard(x)); });
      } catch (e) { errBox.textContent = e.message; errBox.hidden = false; }
    }
    $("btnNewProject").addEventListener("click", function () {
      var name = el("input", { type: "text", maxlength: "120", placeholder: "Project name" }), desc = el("input", { type: "text", maxlength: "2000", placeholder: "Description (optional)" });
      var ok = el("button", { class: "btn primary", type: "button", text: "Create" }), cancel = el("button", { class: "btn", type: "button", text: "Cancel" });
      var close = modal("New project", el("div", { class: "form-grid" }, [el("label", { class: "field" }, ["Name", name]), el("label", { class: "field" }, ["Description", desc])]), el("div", { class: "modal-actions" }, [cancel, ok]));
      cancel.addEventListener("click", close);
      ok.addEventListener("click", async function () {
        if (!name.value.trim()) { name.focus(); return; }
        try { await DF.api("POST", "/api/projects", { project_name: name.value.trim(), project_description: desc.value.trim() || undefined }); close(); load(); } catch (e) { DF.toast(e.message, "error"); }
      });
    });
    load();
  }

  /* ---------- home: generation ---------- */
  var EXAMPLES = [["sequence", 0], ["architecture_high", 1], ["erd", 2], ["use_case", 3], ["dfd_1", 5], ["ci_cd", 6]];
  function applyPending() {
    var p = DF.settings.get("pendingTemplate", null); if (!p) return;
    DF.settings.set("pendingTemplate", null);
    $("promptInput").value = p.prompt; $("typeSelect").value = p.type; updateCounter(); updateDetect();
    $("promptInput").focus();
  }
  function updateCounter() { $("promptCounter").textContent = $("promptInput").value.length + " / 8000"; }
  var detectTimer = null;
  function updateDetect() {
    clearTimeout(detectTimer);
    var box = $("detectBox"), sel = $("typeSelect").value, txt = $("promptInput").value.trim();
    if (sel) { box.innerHTML = ""; box.appendChild(el("span", { text: "Diagram type: " })); box.appendChild(el("span", { class: "badge", text: DF.typeLabel(sel) })); box.appendChild(el("span", { text: "(chosen manually)" })); return; }
    if (txt.length < 8) { box.textContent = "Automatic diagram detection: start typing…"; return; }
    detectTimer = setTimeout(async function () {
      try {
        var r = await DF.api("POST", "/api/detect-type", { prompt: txt });
        box.innerHTML = ""; box.appendChild(el("span", { text: "Automatic detection (preview): " }));
        if (!r.suggestions.length) box.appendChild(el("span", { text: "no obvious match: the AI will analyse and recommend one." }));
        r.suggestions.forEach(function (s) { var c = el("button", { class: "chip", type: "button", text: s.label }); c.addEventListener("click", function () { $("typeSelect").value = s.key; updateDetect(); }); box.appendChild(c); });
      } catch (e) { box.textContent = "Automatic diagram detection unavailable."; }
    }, 450);
  }

  function steps(list) { // progress UI
    var ul = $("progressList"); ul.innerHTML = ""; $("progressBox").hidden = false;
    var nodes = list.map(function (t) { var li = el("li", { text: t }); ul.appendChild(li); return li; });
    return function (i, note) {
      nodes.forEach(function (li, k) { li.className = k < i ? "done" : k === i ? "active" : ""; li.textContent = (k < i ? "✓ " : k === i ? "… " : "") + list[k]; });
      $("progressNote").textContent = note || "";
    };
  }
  function homeError(msg) { var b = $("homeError"); b.textContent = msg; b.hidden = !msg; }
  function setHomeBusy(busy) { ["btnGenerate", "btnGenerateDocs"].forEach(function (id) { $(id).disabled = busy; }); }
  function backToHome() { $("workspace").hidden = true; $("homeView").hidden = false; DF.renderer.clear(); }

  async function generateSingle() {
    var prompt = $("promptInput").value.trim(); homeError("");
    if (prompt.length < 10) { homeError("Please describe what you want in a little more detail (at least 10 characters)."); return; }
    var provider = $("providerSelect").value, dtype = $("typeSelect").value || undefined;
    DF.settings.set("provider", provider); setHomeBusy(true);
    var set = steps(["Analysing requirements", "Generating diagram source", "Validating and rendering"]);
    try {
      set(0);
      var a = (await DF.api("POST", "/api/analyze-prompt", { prompt: prompt, provider: provider, diagram_type: dtype })).analysis;
      var key = dtype || a.requested_diagram_type || a.recommended_diagram_types[0];
      var db = $("detectBox"); db.innerHTML = ""; db.appendChild(el("span", { text: "AI selected: " })); db.appendChild(el("span", { class: "badge ok", text: DF.typeLabel(key) }));
      set(1, a.assumptions.length ? "Assumptions: " + a.assumptions.slice(0, 2).join("; ") : "");
      var res = await DF.api("POST", "/api/generate-diagram", { prompt: prompt, provider: provider, diagram_type: key, analysis: a, save: !!DF.user });
      set(2);
      var it = DF.editor.fromGenerated(res.diagram, { prompt: prompt, diagram_id: res.diagram_id || null });
      DF.editor.open([it], { prompt: prompt, analysis: a }, backToHome);
      $("progressBox").hidden = true;
      if (res.saved && DF.refreshRecents) DF.refreshRecents();
      if (!DF.user) DF.toast("Log in to save this diagram to your projects.", "");
    } catch (e) {
      homeError(e.message + (e.data && e.data.validation_errors ? " Details: " + e.data.validation_errors.slice(0, 2).join("; ") : ""));
      $("progressBox").hidden = true;
      if (e.data && e.data.draft_source) { DF.editor.open([{ title: "Draft (needs fixing)", diagram_type: key || "flowchart", engine: (DF.types.find(function (t) { return t.key === key; }) || {}).engine || "mermaid", source: "", draft_source: e.data.draft_source, ok: false, error: e.message + " " + e.data.validation_errors.join("; ") }], { prompt: prompt }, backToHome); }
    } finally { setHomeBusy(false); }
  }

  async function generateDocs() {
    var prompt = $("promptInput").value.trim(); homeError("");
    if (prompt.length < 20) { homeError("Describe the whole project (a few sentences) to generate complete documentation."); return; }
    var provider = $("providerSelect").value; setHomeBusy(true);
    var set = steps(["Analysing the project", "Generating a coordinated set of diagrams", "Rendering"]);
    set(0); setTimeout(function () { if (!$("progressBox").hidden) set(1, "This can take 1–2 minutes: up to 10 diagrams are generated and validated."); }, 2500);
    try {
      var res = await DF.api("POST", "/api/generate-project-diagrams", { prompt: prompt, provider: provider, save: !!DF.user });
      set(2);
      var items = res.results.map(function (r) {
        if (r.ok) return DF.editor.fromGenerated(r, { prompt: prompt, diagram_id: r.diagram_id || null });
        return { title: r.diagram_label, label: r.diagram_label, diagram_type: r.diagram_type, engine: (DF.types.find(function (t) { return t.key === r.diagram_type; }) || {}).engine || "mermaid", source: "", draft_source: r.draft_source || "", ok: false, error: r.error + (r.errors ? " " + r.errors.join("; ") : "") };
      });
      DF.editor.open(items, { prompt: prompt, analysis: res.analysis }, backToHome);
      $("progressBox").hidden = true;
      var failed = items.filter(function (i) { return i.ok === false; }).length;
      DF.toast("Generated " + (items.length - failed) + " of " + items.length + " diagrams" + (res.saved ? " and saved the project." : ". Log in to save them."), failed ? "error" : "success");
      if (res.saved && DF.refreshRecents) DF.refreshRecents();
    } catch (e) { homeError(e.message); $("progressBox").hidden = true; }
    finally { setHomeBusy(false); }
  }

  async function initHome() {
    var sel = $("typeSelect"), groups = {};
    DF.types.forEach(function (t) {
      if (!groups[t.category]) { groups[t.category] = el("optgroup", { label: t.category }); sel.appendChild(groups[t.category]); }
      groups[t.category].appendChild(el("option", { value: t.key, text: t.label }));
    });
    $("providerSelect").value = DF.settings.get("provider", "gemini");
    EXAMPLES.forEach(function (x) {
      var t = TEMPLATES[x[1]], b = el("button", { class: "example", type: "button" }, [el("b", { text: DF.typeLabel(t[0]) }), t[2].length > 120 ? t[2].slice(0, 117) + "…" : t[2]]);
      b.addEventListener("click", function () { $("promptInput").value = t[2]; sel.value = t[0]; updateCounter(); updateDetect(); $("promptInput").focus(); });
      $("examples").appendChild(b);
    });
    $("promptInput").addEventListener("input", function () { updateCounter(); updateDetect(); });
    $("promptInput").addEventListener("keydown", function (e) { if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); generateSingle(); } });
    sel.addEventListener("change", updateDetect);
    $("promptForm").addEventListener("submit", function (e) { e.preventDefault(); generateSingle(); });
    $("btnGenerateDocs").addEventListener("click", generateDocs);
    applyPending();
  }

  /* ---------- boot ---------- */
  document.addEventListener("DOMContentLoaded", async function () {
    initShell();
    try { var me = await DF.api("GET", "/api/auth/me"); DF.user = me.user; } catch (e) { DF.user = null; }
    if ((page() === "dashboard" || page() === "editor") && !DF.user) { location.href = "/login?next=" + encodeURIComponent(location.pathname); return; }
    renderAccount();
    if (page() === "login" || page() === "register") { initAuth(); return; }
    try { DF.types = (await DF.api("GET", "/api/diagram-types")).types; } catch (e) { DF.types = []; }
    if (page() === "home") initHome();
    if (page() === "dashboard") initDashboard();
    if (page() === "editor") DF.editor.loadSaved(document.body.dataset.diagramId);
    DF.refreshRecents();
  });
})();
