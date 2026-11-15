/* Diagram workspace: tabs, source editor, inspector, visual node editing, save/history, export menu. */
(function () {
  "use strict";
  window.DF = window.DF || {};
  var E = (DF.editor = {});
  var $ = function (id) { return document.getElementById(id); };
  var S = { items: [], active: 0, prompt: "", analysis: null, selectedNode: null, busy: false };
  var onBack = null;

  function item() { return S.items[S.active]; }
  function saved() { var it = item(); return it && it.diagram_id; }

  /* ---------- item constructors ---------- */
  E.fromGenerated = function (g, extra) {
    return Object.assign({
      title: g.title, diagram_type: g.diagram_type, engine: g.engine, source: g.source, original: g.source,
      explanation: g.explanation || "", assumptions: g.assumptions || [], status: g.validation_status || "valid",
      diagram_id: null, version: 1, ok: true,
    }, extra || {});
  };
  E.fromSaved = function (d) {
    return {
      title: d.diagram_title, diagram_type: d.diagram_type, engine: d.diagram_engine, source: d.generated_source,
      original: d.generated_source, explanation: d.explanation || "", assumptions: d.assumptions || [],
      diagram_id: d.diagram_id, version: d.version, prompt: d.original_prompt, ok: true, status: "saved",
    };
  };

  /** Open the workspace with one or more diagrams. */
  E.open = function (items, ctx, backFn) {
    S.items = items; S.active = Math.max(0, items.findIndex(function (i) { return i.ok !== false; }));
    S.prompt = (ctx && ctx.prompt) || ""; S.analysis = (ctx && ctx.analysis) || null; onBack = backFn || null;
    var ws = $("workspace"); ws.hidden = false;
    if ($("homeView")) $("homeView").hidden = true;
    renderTabs(); showItem(S.active);
  };

  function renderTabs() {
    var box = $("projectTabs");
    box.hidden = S.items.length < 2; box.innerHTML = "";
    S.items.forEach(function (it, i) {
      var b = document.createElement("button");
      b.type = "button"; b.className = "tab" + (i === S.active ? " active" : "") + (it.ok === false ? " failed" : "");
      b.setAttribute("role", "tab"); b.setAttribute("aria-selected", i === S.active ? "true" : "false");
      var t = document.createElement("span"); t.textContent = (it.ok === false ? "⚠ " : "") + (it.title || it.label || it.diagram_type);
      b.appendChild(t); b.addEventListener("click", function () { if (i !== S.active) { commitTitle(); S.active = i; renderTabs(); showItem(i); } });
      box.appendChild(b);
    });
  }

  /* ---------- show / render ---------- */
  function engineName(e) { return { mermaid: "Mermaid", plantuml: "PlantUML", bpmn: "BPMN.io" }[e] || e; }

  function showItem(i) {
    var it = S.items[i]; S.selectedNode = null;
    $("wsTitle").value = it.title || it.label || "";
    $("wsBadge").textContent = (DF.typeLabel ? DF.typeLabel(it.diagram_type) : it.diagram_type) + " · " + engineName(it.engine || "mermaid");
    var st = $("wsStatus");
    st.hidden = !(it.status === "fixed"); st.textContent = "auto-fixed by AI";
    var failed = it.ok === false;
    it.engine = it.engine || "mermaid";
    setSource(it.source || it.draft_source || "", false);
    $("srcEngine").textContent = engineName(it.engine);
    var ext = DF.exporter.extFor(it.engine);
    $("exportSourceLabel").textContent = ext[2]; $("exportSourceExt").textContent = "." + ext[0];
    $("btnSave").disabled = false; $("btnSave").querySelector(".lbl").textContent = saved() ? "Save changes" : "Save";
    buildInspector();
    loadHistory();
    if (failed) { showFailure(it); setSourceOpen(true); return; }
    renderCurrent(false);
  }

  function setBusy(msg) {
    var d = document.createElement("div"); d.innerHTML = '<span class="spinner"></span><div></div>'; d.lastChild.textContent = msg;
    DF.renderer.showMessage(d, "busy");
  }
  function showFailure(it, msg) {
    var d = document.createElement("div");
    var a = document.createElement("div"); a.className = "alert"; a.textContent = msg || it.error || "This diagram could not be rendered.";
    var b = document.createElement("button"); b.className = "btn sm"; b.type = "button"; b.textContent = "Edit source to fix";
    b.addEventListener("click", function () { setSourceOpen(true); });
    d.appendChild(a); d.appendChild(b); DF.renderer.clear(); DF.renderer.showMessage(d, "error");
  }

  async function renderCurrent(keepView) {
    var it = item(); if (!it || !it.source) { showFailure(it || {}, "No source to render."); return false; }
    setBusy("Rendering…");
    var res = await DF.renderer.renderWithAutoFix(it.engine, it.source, {
      autoFix: DF.settings.get("autoFix", true), diagramType: it.diagram_type, keepView: keepView,
      onAttempt: function (n) { setBusy("Syntax problem found: asking AI to fix it (attempt " + n + " of 3)…"); },
    });
    if (!res.ok) { it.ok = false; it.error = res.error; showFailure(it, "Could not render: " + res.error); setErrors([res.error]); setSourceOpen(true); renderTabs(); return false; }
    it.ok = true; setErrors([]);
    if (res.fixed) {
      it.source = res.source; it.status = "fixed"; setSource(res.source, false); $("wsStatus").hidden = false;
      if (saved()) persist({ generated_source: it.source }, true);
      DF.toast("The AI repaired a syntax error in this diagram.", "success");
    }
    renderTabs(); refreshNodeLists(); return true;
  }

  /* ---------- source editor ---------- */
  function setSource(text, dirty) {
    $("srcInput").value = text; paint(); markDirty(dirty);
  }
  function paint() {
    var it = item(), pre = $("srcHl");
    pre.innerHTML = DF.highlight(it ? it.engine : "mermaid", $("srcInput").value) + "\n";
    syncScroll();
  }
  function syncScroll() { var t = $("srcInput"), p = $("srcHl"); p.scrollTop = t.scrollTop; p.scrollLeft = t.scrollLeft; }
  function markDirty(d) { $("srcDirty").hidden = !d; }
  function setErrors(list) {
    var box = $("srcErrors"); box.innerHTML = "";
    if (!list.length) { box.hidden = true; return; }
    var u = document.createElement("ul");
    list.forEach(function (m) { var li = document.createElement("li"); li.textContent = m; u.appendChild(li); });
    var h = document.createElement("strong"); h.textContent = "Problems"; box.appendChild(h); box.appendChild(u); box.hidden = false;
  }
  function setSourceOpen(open) {
    $("sourcePanel").hidden = !open; $("btnToggleSource").setAttribute("aria-pressed", open ? "true" : "false");
    setTimeout(function () { if (DF.renderer.hasView()) DF.renderer.fit(); }, 50);
  }

  async function applySource(text) {
    var it = item(); text = text !== undefined ? text : $("srcInput").value;
    if (!text.trim()) { DF.toast("Source is empty.", "error"); return false; }
    var prev = it.source; it.source = text; setBusy("Rendering…");
    var res = await DF.renderer.renderWithAutoFix(it.engine, text, { autoFix: false, diagramType: it.diagram_type });
    if (!res.ok) {
      it.source = prev; setErrors([res.error]);
      if (prev && DF.renderer.engine()) { DF.renderer.hideMessage(); } else { showFailure(it, "Could not render: " + res.error); }
      DF.toast("Source has errors. Fix them or use Auto-fix.", "error"); return false;
    }
    it.ok = true; setErrors([]); markDirty(false); refreshNodeLists(); buildInspector(true); renderTabs();
    if (saved()) await persist({ generated_source: text }, true);
    return true;
  }

  async function autoFixSource() {
    var it = item(), btn = $("srcFix"); btn.disabled = true;
    try {
      var res = await DF.api("POST", "/api/fix-diagram", { source: $("srcInput").value, engine: it.engine, error: ($("srcErrors").textContent || "").replace(/^Problems/, "").slice(0, 1500), attempt: 1, diagram_type: it.diagram_type, provider: DF.settings.get("provider") });
      setSource(res.source, true);
      if (!res.changed) DF.toast("No issues found by the validator.", "success");
      else if (!res.valid) setErrors(res.errors);
      else { DF.toast("Fix applied to the editor. Click Apply changes to render.", "success"); setErrors([]); }
    } catch (e) { DF.toast(e.message, "error"); } finally { btn.disabled = false; }
  }

  /* ---------- inspector ---------- */
  function buildInspector(soft) {
    var it = item(); $("optType").value = DF.typeLabel ? DF.typeLabel(it.diagram_type) : it.diagram_type;
    var src = $("srcInput").value || it.source || "";
    var dirWrap = $("optDirectionWrap"), dirOk = DF.flow.supportsDirection(src, it.engine);
    dirWrap.hidden = !dirOk;
    if (dirOk) $("optDirection").value = DF.flow.getDirection(src, it.engine) || "TB";
    var sel = $("optTheme"); sel.innerHTML = "";
    (DF.renderer.THEMES[it.engine] || []).forEach(function (t) { var o = document.createElement("option"); o.value = t[0]; o.textContent = t[1]; sel.appendChild(o); });
    sel.value = it.engine === "mermaid" ? DF.renderer.mermaidTheme() : it.engine === "plantuml" ? DF.flow.getPlantumlTheme(src) : "default";
    sel.disabled = it.engine === "bpmn";
    $("optNote").textContent = it.engine === "plantuml" ? "PlantUML themes are written into the source (!theme)." : it.engine === "bpmn" ? "BPMN uses the standard notation styling." : "";
    var flowOk = it.engine === "mermaid" && DF.flow.isFlowchart(src);
    $("nodeSection").hidden = !flowOk; if (!soft) $("nodeEditor").hidden = true;
    var info = it.explanation || (it.assumptions && it.assumptions.length);
    $("infoSection").hidden = !info; $("explanation").textContent = it.explanation || "";
    var ul = $("assumptions"); ul.innerHTML = ""; (it.assumptions || []).forEach(function (a) { var li = document.createElement("li"); li.textContent = a; ul.appendChild(li); });
    $("assumptionsBox").hidden = !(it.assumptions && it.assumptions.length);
    if (flowOk) refreshNodeLists();
  }
  function refreshNodeLists() {
    var it = item(); if (!it || it.engine !== "mermaid" || !DF.flow.isFlowchart(it.source)) return;
    var nodes = DF.flow.nodeList(it.source);
    ["edgeFrom", "edgeTo"].forEach(function (id, k) {
      var s = $(id), prev = s.value; s.innerHTML = "";
      nodes.forEach(function (n) { var o = document.createElement("option"); o.value = n.id; o.textContent = n.label.length > 24 ? n.label.slice(0, 23) + "…" : n.label; s.appendChild(o); });
      if (prev && nodes.some(function (n) { return n.id === prev; })) s.value = prev; else if (k === 1 && nodes.length > 1) s.selectedIndex = 1;
    });
  }

  async function sourceTransform(fn, okMsg) {
    var it = item();
    try {
      var out = fn(it.source);
      var next = typeof out === "string" ? out : out.src;
      setSource(next, true);
      if (await applySource(next) && okMsg) DF.toast(okMsg, "success");
      return out;
    } catch (e) { DF.toast(e.message, "error"); return null; }
  }

  function selectNode(id) {
    S.selectedNode = id; DF.renderer.highlightNode(id);
    var box = $("nodeEditor");
    if (!id) { box.hidden = true; return; }
    var n = DF.flow.parseNodes(item().source).map[id]; if (!n) { box.hidden = true; return; }
    box.hidden = false; $("nodeId").textContent = id; $("nodeLabel").value = n.label;
    if (window.matchMedia("(max-width:1024px)").matches) document.body.classList.add("inspector-open");
  }

  /* ---------- persistence ---------- */
  async function persist(fields, quiet) {
    var it = item();
    try {
      var res = await DF.api("PUT", "/api/diagrams/" + it.diagram_id, fields);
      it.version = res.diagram.version; it.original = it.source;
      if (!quiet) DF.toast("Saved.", "success");
      loadHistory(); return true;
    } catch (e) { DF.toast("Could not save: " + e.message, "error"); return false; }
  }
  async function save() {
    var it = item(); commitTitle();
    if (it.ok === false) { DF.toast("Fix the diagram before saving.", "error"); return; }
    if (!DF.user) { location.href = "/login?next=" + encodeURIComponent(location.pathname); return; }
    if (saved()) { await persist({ generated_source: it.source, diagram_title: it.title }); return; }
    try {
      var res = await DF.api("POST", "/api/diagrams", { diagram_title: it.title || "Untitled", diagram_type: it.diagram_type, generated_source: it.source, original_prompt: it.prompt || S.prompt || undefined, assumptions: it.assumptions, explanation: it.explanation || undefined });
      it.diagram_id = res.diagram.diagram_id; it.version = 1;
      $("btnSave").querySelector(".lbl").textContent = "Save changes"; DF.toast("Saved to your projects.", "success");
      if (DF.refreshRecents) DF.refreshRecents(); loadHistory();
    } catch (e) { DF.toast(e.message, "error"); }
  }
  function commitTitle() {
    var it = item(); if (!it) return; var v = $("wsTitle").value.trim();
    if (v && v !== it.title) { it.title = v; renderTabs(); if (saved()) persist({ diagram_title: v }, true); }
  }

  async function loadHistory() {
    var box = $("historyList"), sec = $("historySection");
    if (!saved()) { sec.hidden = true; return; }
    try {
      var res = await DF.api("GET", "/api/diagrams/" + item().diagram_id + "/history");
      box.innerHTML = ""; sec.hidden = res.history.length < 1;
      res.history.forEach(function (h) {
        var row = document.createElement("div"); row.className = "history-item";
        var l = document.createElement("div"), b = document.createElement("strong"); b.textContent = "v" + h.version_number;
        var t = document.createElement("time"); t.textContent = " " + new Date(h.timestamp).toLocaleString(); l.appendChild(b); l.appendChild(t);
        row.appendChild(l);
        if (h.version_number !== item().version) {
          var r = document.createElement("button"); r.className = "btn sm"; r.type = "button"; r.textContent = "Restore";
          r.addEventListener("click", function () { restore(h.version_number); }); row.appendChild(r);
        } else { var c = document.createElement("span"); c.className = "badge ok"; c.textContent = "current"; row.appendChild(c); }
        box.appendChild(row);
      });
    } catch (e) { sec.hidden = true; }
  }
  async function restore(v) {
    try {
      var res = await DF.api("POST", "/api/diagrams/" + item().diagram_id + "/restore", { version_number: v });
      var it = item(); it.source = res.diagram.generated_source; it.version = res.diagram.version;
      setSource(it.source, false); await renderCurrent(false); buildInspector(); loadHistory(); DF.toast("Restored version " + v + ".", "success");
    } catch (e) { DF.toast(e.message, "error"); }
  }

  async function regenerate() {
    var it = item(), prompt = it.prompt || S.prompt;
    if (!prompt) { DF.toast("The original prompt is not available for this diagram.", "error"); return; }
    var btn = $("btnRegenerate"); btn.disabled = true; setBusy("Regenerating…");
    try {
      var res = await DF.api("POST", "/api/generate-diagram", { prompt: prompt, diagram_type: it.diagram_type, provider: DF.settings.get("provider") });
      var g = res.diagram; it.source = g.source; it.explanation = g.explanation; it.assumptions = g.assumptions; it.status = g.validation_status; it.ok = true;
      setSource(g.source, false); buildInspector();
      if (await renderCurrent(false) && saved()) await persist({ generated_source: it.source }, true);
    } catch (e) { DF.toast(e.message, "error"); if (DF.renderer.hasView()) DF.renderer.hideMessage(); else showFailure(it, e.message); }
    finally { btn.disabled = false; }
  }

  /* ---------- export ---------- */
  async function doExport(kind) {
    var it = item(), theme = it.engine === "mermaid" ? DF.renderer.mermaidTheme() : "";
    var title = $("wsTitle").value || it.title, scale = parseInt($("exportScale").value, 10) || 3;
    $("exportMenu").hidden = true; $("exportMenuBtn").setAttribute("aria-expanded", "false");
    try {
      if (kind === "source") { DF.exporter.source(it.engine, $("srcInput").value || it.source, title); return; }
      if (it.ok === false || !DF.renderer.hasView()) { DF.toast("Nothing rendered to export yet.", "error"); return; }
      var note = null;
      if (kind === "svg") await DF.exporter.svg(it.engine, theme, title);
      else if (kind === "png") note = await DF.exporter.png(it.engine, theme, title, scale);
      else if (kind === "pdf") note = await DF.exporter.pdf(it.engine, theme, title, scale);
      DF.toast(note || "Export ready.", note ? "" : "success");
    } catch (e) { DF.toast("Export failed: " + e.message, "error"); }
  }

  /* ---------- wiring ---------- */
  function wire() {
    $("srcInput").addEventListener("input", function () { paint(); markDirty(true); });
    $("srcInput").addEventListener("scroll", syncScroll);
    $("srcInput").addEventListener("keydown", function (e) {
      if (e.key === "Tab") { e.preventDefault(); var t = e.target, s = t.selectionStart; t.value = t.value.slice(0, s) + "  " + t.value.slice(t.selectionEnd); t.selectionStart = t.selectionEnd = s + 2; paint(); markDirty(true); }
      else if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); applySource(); }
    });
    $("srcApply").addEventListener("click", function () { applySource(); });
    $("srcReset").addEventListener("click", function () { var it = item(); setSource(it.original || it.source, false); setErrors([]); applySource(it.original || it.source); });
    $("srcFix").addEventListener("click", autoFixSource);
    $("srcCopy").addEventListener("click", function () {
      var v = $("srcInput").value;
      (navigator.clipboard ? navigator.clipboard.writeText(v) : Promise.reject()).then(function () { DF.toast("Source copied.", "success"); }, function () { $("srcInput").select(); document.execCommand("copy"); DF.toast("Source copied.", "success"); });
    });
    $("btnToggleSource").addEventListener("click", function () { setSourceOpen($("sourcePanel").hidden); });
    $("btnSave").addEventListener("click", save);
    $("btnRegenerate").addEventListener("click", regenerate);
    $("wsTitle").addEventListener("change", commitTitle);
    $("btnFullscreen").addEventListener("click", function () {
      var w = $("canvasWrap");
      if (document.fullscreenElement) document.exitFullscreen(); else if (w.requestFullscreen) w.requestFullscreen(); else DF.toast("Full screen is not supported in this browser.", "error");
    });
    $("btnToggleInspector").addEventListener("click", function () { document.body.classList.toggle("inspector-open"); });
    $("btnBack").addEventListener("click", function () { if (onBack) onBack(); else location.href = "/dashboard"; });
    var mb = $("exportMenuBtn"), menu = $("exportMenu");
    mb.addEventListener("click", function (e) { e.stopPropagation(); menu.hidden = !menu.hidden; mb.setAttribute("aria-expanded", String(!menu.hidden)); });
    document.addEventListener("click", function (e) { if (!menu.hidden && !menu.contains(e.target)) { menu.hidden = true; mb.setAttribute("aria-expanded", "false"); } });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape") { menu.hidden = true; document.body.classList.remove("inspector-open"); } });
    menu.querySelectorAll("[data-export]").forEach(function (b) { b.addEventListener("click", function () { doExport(b.dataset.export); }); });
    $("exportScale").value = String(DF.settings.get("exportScale", 3));

    $("optDirection").addEventListener("change", function () { var it = item(); sourceTransform(function (s) { return DF.flow.setDirection($("srcInput").value || s, $("optDirection").value, it.engine); }); });
    $("optTheme").addEventListener("change", function () {
      var it = item(), v = $("optTheme").value;
      if (it.engine === "mermaid") { DF.renderer.setMermaidTheme(v); DF.settings.set("mermaidTheme", v); renderCurrent(true); }
      else if (it.engine === "plantuml") sourceTransform(function (s) { return DF.flow.setPlantumlTheme($("srcInput").value || s, v); });
    });
    DF.renderer.onNodeClick = function (el) { var it = item(); if (it && it.engine === "mermaid" && DF.flow.isFlowchart(it.source)) selectNode(DF.renderer.nodeIdFromElement(el)); };
    $("nodeRename").addEventListener("click", function () { var id = S.selectedNode; if (id) sourceTransform(function (s) { return DF.flow.renameNode(s, id, $("nodeLabel").value); }).then(function () { selectNode(id); }); });
    $("nodeDelete").addEventListener("click", function () { var id = S.selectedNode; if (id) sourceTransform(function (s) { return DF.flow.deleteNode(s, id); }, "Node deleted.").then(function () { selectNode(null); }); });
    $("addNodeBtn").addEventListener("click", function () { sourceTransform(function (s) { return DF.flow.addNode(s, $("addNodeLabel").value, $("addNodeShape").value); }, "Node added.").then(function (r) { if (r) $("addNodeLabel").value = ""; }); });
    $("addEdgeBtn").addEventListener("click", function () { sourceTransform(function (s) { return DF.flow.addEdge(s, $("edgeFrom").value, $("edgeTo").value, $("edgeLabel").value); }, "Connection added."); });
    DF.renderer.setMermaidTheme(DF.settings.get("mermaidTheme", "default"));
  }

  E.loadSaved = async function (id) {
    try { var res = await DF.api("GET", "/api/diagrams/" + encodeURIComponent(id)); E.open([E.fromSaved(res.diagram)], { prompt: res.diagram.original_prompt }); }
    catch (e) { $("workspace").hidden = false; showFailure({}, e.status === 404 ? "Diagram not found." : e.message); }
  };

  document.addEventListener("DOMContentLoaded", function () {
    if (!$("workspace")) return;
    wire(); // the editor page itself is opened by app.js once the type catalog has loaded
  });
})();
