/* Rendering engines (Mermaid / PlantUML / BPMN), pan & zoom, and the bounded auto-fix loop. */
(function () {
  "use strict";
  window.DF = window.DF || {};
  var R = (DF.renderer = {});
  var $ = function (id) { return document.getElementById(id); };

  var BPMN_VIEWER_JS = "https://unpkg.com/bpmn-js@17.11.1/dist/bpmn-navigated-viewer.production.min.js";
  var BPMN_CSS = "https://unpkg.com/bpmn-js@17.11.1/dist/assets/diagram-js.css";
  var AUTO_LAYOUT_ESM = "https://esm.sh/bpmn-auto-layout@1";

  R.THEMES = {
    mermaid: [["default", "Default"], ["neutral", "Neutral"], ["forest", "Forest"], ["dark", "Dark"], ["base", "Base"]],
    plantuml: [["", "Default"], ["plain", "Plain"], ["cerulean", "Cerulean"], ["materia", "Materia"], ["minty", "Minty"], ["blueprint", "Blueprint"], ["sketchy-outline", "Sketchy"]],
    bpmn: [["default", "Default"]],
  };

  var current = { engine: null, mermaidTheme: "default", size: { w: 0, h: 0 } };
  var view = { scale: 1, x: 0, y: 0 };
  var bpmnViewer = null, bpmnHost = null, counter = 0;
  R.onNodeClick = null; // set by the editor

  /* ---------- helpers ---------- */
  var loaded = {};
  function loadScript(url) {
    if (!loaded[url]) {
      loaded[url] = new Promise(function (resolve, reject) {
        var s = document.createElement("script");
        s.src = url; s.onload = resolve;
        s.onerror = function () { delete loaded[url]; reject(new Error("Could not load " + url.split("/").pop() + ". Check your connection or content blocker.")); };
        document.head.appendChild(s);
      });
    }
    return loaded[url];
  }
  function loadCss(url) {
    if (document.querySelector('link[href="' + url + '"]')) return;
    var l = document.createElement("link"); l.rel = "stylesheet"; l.href = url; document.head.appendChild(l);
  }
  function clip(msg) { return String(msg || "Unknown error").replace(/\s+\n/g, "\n").slice(0, 700); }

  /* ---------- zoom / pan ---------- */
  function apply() {
    var stage = $("stage");
    stage.style.transform = "translate(" + view.x + "px," + view.y + "px) scale(" + view.scale + ")";
    $("zoomLabel").textContent = Math.round(view.scale * 100) + "%";
  }
  function isBpmn() { return current.engine === "bpmn" && bpmnViewer; }

  R.fit = function () {
    if (isBpmn()) { bpmnViewer.get("canvas").zoom("fit-viewport", "auto"); return; }
    var wrap = $("canvasWrap"), cw = wrap.clientWidth, ch = wrap.clientHeight, pad = 32, sz = current.size;
    if (!sz.w || !sz.h) return;
    var s = Math.max(0.05, Math.min((cw - pad * 2) / sz.w, (ch - pad * 2) / sz.h, 2));
    view.scale = s; view.x = (cw - sz.w * s) / 2; view.y = (ch - sz.h * s) / 2; apply();
  };
  R.zoomBy = function (factor, cx, cy) {
    if (isBpmn()) { var c = bpmnViewer.get("canvas"); c.zoom(Math.min(8, Math.max(0.05, c.zoom() * factor))); return; }
    var wrap = $("canvasWrap");
    if (cx === undefined) { cx = wrap.clientWidth / 2; cy = wrap.clientHeight / 2; }
    var ns = Math.min(8, Math.max(0.05, view.scale * factor)), k = ns / view.scale;
    view.x = cx - (cx - view.x) * k; view.y = cy - (cy - view.y) * k; view.scale = ns; apply();
  };
  R.resetZoom = function () {
    if (isBpmn()) { bpmnViewer.get("canvas").zoom(1); return; }
    var wrap = $("canvasWrap"); view.scale = 1;
    view.x = (wrap.clientWidth - current.size.w) / 2; view.y = Math.max(16, (wrap.clientHeight - current.size.h) / 2); apply();
  };

  function initPanZoom() {
    var wrap = $("canvasWrap"), pointers = {}, startDist = 0, startScale = 1, moved = 0, downTarget = null;
    function ignore(e) { return e.target.closest && (e.target.closest(".zoom-controls") || e.target.closest(".canvas-msg > div")); }
    wrap.addEventListener("pointerdown", function (e) {
      if (isBpmn() || ignore(e) || (e.pointerType === "mouse" && e.button !== 0)) return;
      pointers[e.pointerId] = { x: e.clientX, y: e.clientY };
      downTarget = e.target; moved = 0;
      try { wrap.setPointerCapture(e.pointerId); } catch (err) { /* ignore */ }
      var ids = Object.keys(pointers);
      if (ids.length === 2) { startDist = dist(pointers[ids[0]], pointers[ids[1]]); startScale = view.scale; }
    });
    wrap.addEventListener("pointermove", function (e) {
      var p = pointers[e.pointerId]; if (!p) return;
      var ids = Object.keys(pointers);
      if (ids.length === 2) {
        pointers[e.pointerId] = { x: e.clientX, y: e.clientY };
        var d = dist(pointers[ids[0]], pointers[ids[1]]);
        if (startDist > 0) { var r = wrap.getBoundingClientRect(); R.zoomBy((startScale * d / startDist) / view.scale, (pointers[ids[0]].x + pointers[ids[1]].x) / 2 - r.left, (pointers[ids[0]].y + pointers[ids[1]].y) / 2 - r.top); }
        moved += 10; return;
      }
      var dx = e.clientX - p.x, dy = e.clientY - p.y;
      moved += Math.abs(dx) + Math.abs(dy);
      if (moved > 5) wrap.classList.add("panning");
      view.x += dx; view.y += dy; pointers[e.pointerId] = { x: e.clientX, y: e.clientY }; apply();
    });
    function up(e) {
      if (!pointers[e.pointerId]) return;
      delete pointers[e.pointerId];
      wrap.classList.remove("panning");
      if (moved <= 5 && e.type === "pointerup" && downTarget && R.onNodeClick) R.onNodeClick(downTarget);
    }
    wrap.addEventListener("pointerup", up);
    wrap.addEventListener("pointercancel", up);
    wrap.addEventListener("wheel", function (e) {
      if (isBpmn() || ignore(e)) return;
      e.preventDefault();
      var r = wrap.getBoundingClientRect(), f = Math.exp(-e.deltaY * (e.ctrlKey ? 0.01 : 0.0015));
      R.zoomBy(f, e.clientX - r.left, e.clientY - r.top);
    }, { passive: false });
    wrap.addEventListener("keydown", function (e) {
      if (e.target !== wrap) return;
      if (e.key === "+" || e.key === "=") R.zoomBy(1.2);
      else if (e.key === "-") R.zoomBy(1 / 1.2);
      else if (e.key === "0") R.fit();
    });
    var ro = window.ResizeObserver ? new ResizeObserver(function () { if (current.autoFit) R.fit(); }) : null;
    if (ro) ro.observe(wrap);
    document.addEventListener("fullscreenchange", function () { setTimeout(R.fit, 60); });
    $("zoomIn").addEventListener("click", function () { current.autoFit = false; R.zoomBy(1.25); });
    $("zoomOut").addEventListener("click", function () { current.autoFit = false; R.zoomBy(1 / 1.25); });
    $("zoomFit").addEventListener("click", function () { current.autoFit = true; R.fit(); });
    $("zoomReset").addEventListener("click", function () { current.autoFit = false; R.resetZoom(); });
    wrap.addEventListener("pointerdown", function () { current.autoFit = false; });
  }
  function dist(a, b) { return Math.hypot(a.x - b.x, a.y - b.y); }

  /* ---------- engines ---------- */
  function naturalSize(svg) {
    var vb = svg.viewBox && svg.viewBox.baseVal;
    if (vb && vb.width && vb.height) return { w: vb.width, h: vb.height };
    var w = parseFloat(svg.getAttribute("width")), h = parseFloat(svg.getAttribute("height"));
    if (w && h) return { w: w, h: h };
    var bb = svg.getBBox();
    return { w: Math.max(bb.width, 10), h: Math.max(bb.height, 10) };
  }
  function mountSvg(svgMarkup) {
    var stage = $("stage");
    stage.hidden = false; stage.innerHTML = svgMarkup;
    var svg = stage.querySelector("svg");
    if (!svg) throw new Error("The engine returned no diagram.");
    var sz = naturalSize(svg);
    svg.removeAttribute("style");
    svg.setAttribute("width", sz.w); svg.setAttribute("height", sz.h);
    if (!svg.getAttribute("viewBox")) svg.setAttribute("viewBox", "0 0 " + sz.w + " " + sz.h);
    current.size = sz;
    return svg;
  }

  async function renderMermaid(source) {
    if (!window.mermaid) throw fatal("Mermaid failed to load. Check your connection or content blocker, then reload.");
    mermaid.initialize({
      startOnLoad: false, securityLevel: "strict", theme: current.mermaidTheme, logLevel: "fatal",
      fontFamily: "Inter, system-ui, sans-serif",
      // SVG text (not HTML labels) keeps PNG/PDF export crisp and canvas-safe.
      flowchart: { htmlLabels: false, curve: "basis", useMaxWidth: false },
      sequence: { useMaxWidth: false }, er: { useMaxWidth: false },
      class: { htmlLabels: false, useMaxWidth: false }, state: { useMaxWidth: false },
    });
    await mermaid.parse(source); // authoritative syntax check; throws with line info
    var id = "dfm" + ++counter, out;
    try { out = await mermaid.render(id, source); }
    finally { var junk = document.getElementById("d" + id); if (junk) junk.remove(); }
    return mountSvg(out.svg);
  }

  async function renderPlantuml(source) {
    if (!window.DOMPurify) throw fatal("DOMPurify failed to load; refusing to render untrusted SVG.");
    var text;
    try { text = await DF.apiText("POST", "/api/render-plantuml", { source: source, format: "svg" }); }
    catch (e) { if (e.status >= 500 || e.status === 429 || e.status === 0) e.fatal = true; throw e; }
    var clean = DOMPurify.sanitize(text, { USE_PROFILES: { svg: true, svgFilters: true } });
    return mountSvg(clean);
  }

  var MODEL = "http://www.omg.org/spec/BPMN/20100524/MODEL", DI = "http://www.omg.org/spec/BPMN/20100524/DI",
    DC = "http://www.omg.org/spec/DD/20100524/DC", DDDI = "http://www.omg.org/spec/DD/20100524/DI";
  var FLOW_NODE = /^(startEvent|endEvent|intermediateCatchEvent|intermediateThrowEvent|task|userTask|serviceTask|scriptTask|sendTask|receiveTask|manualTask|businessRuleTask|callActivity|subProcess|exclusiveGateway|inclusiveGateway|parallelGateway|eventBasedGateway|complexGateway)$/;

  /** Simple left-to-right layered layout, used when no layout library is reachable. */
  R.fallbackBpmnLayout = function (xml) {
    var doc = new DOMParser().parseFromString(xml, "application/xml");
    if (doc.getElementsByTagName("parsererror").length) throw new Error("BPMN XML is not well-formed.");
    var root = doc.documentElement, proc = doc.getElementsByTagNameNS(MODEL, "process")[0];
    if (!proc) throw new Error("BPMN has no process element.");
    var nodes = [], map = {}, flows = [];
    Array.prototype.forEach.call(proc.getElementsByTagNameNS(MODEL, "*"), function (el) {
      var n = el.localName, id = el.getAttribute("id");
      if (!id) return;
      if (n === "sequenceFlow") flows.push({ id: id, s: el.getAttribute("sourceRef"), t: el.getAttribute("targetRef") });
      else if (FLOW_NODE.test(n)) {
        var ev = /Event$/.test(n), gw = /Gateway$/.test(n);
        var o = { id: id, w: ev ? 36 : gw ? 50 : 100, h: ev ? 36 : gw ? 50 : 80, level: 0, row: 0 };
        nodes.push(o); map[id] = o;
      }
    });
    for (var it = 0; it < nodes.length; it++) {
      var changed = false;
      flows.forEach(function (f) { var s = map[f.s], t = map[f.t]; if (s && t && t.level < s.level + 1 && it < nodes.length - 1) { t.level = s.level + 1; changed = true; } });
      if (!changed) break;
    }
    var rows = {};
    nodes.forEach(function (n) { rows[n.level] = (rows[n.level] || 0); n.row = rows[n.level]++; n.cx = 90 + n.level * 190; n.cy = 80 + n.row * 130; });
    var maxY = nodes.reduce(function (m, n) { return Math.max(m, n.cy + n.h / 2); }, 0);
    [["bpmndi", DI], ["dc", DC], ["di", DDDI]].forEach(function (p) { root.setAttributeNS("http://www.w3.org/2000/xmlns/", "xmlns:" + p[0], p[1]); });
    var diagram = doc.createElementNS(DI, "bpmndi:BPMNDiagram"); diagram.setAttribute("id", "DF_Diagram");
    var plane = doc.createElementNS(DI, "bpmndi:BPMNPlane"); plane.setAttribute("id", "DF_Plane"); plane.setAttribute("bpmnElement", proc.getAttribute("id"));
    diagram.appendChild(plane);
    nodes.forEach(function (n) {
      var shape = doc.createElementNS(DI, "bpmndi:BPMNShape"); shape.setAttribute("id", "DF_S_" + n.id); shape.setAttribute("bpmnElement", n.id);
      var b = doc.createElementNS(DC, "dc:Bounds");
      b.setAttribute("x", n.cx - n.w / 2); b.setAttribute("y", n.cy - n.h / 2); b.setAttribute("width", n.w); b.setAttribute("height", n.h);
      shape.appendChild(b); plane.appendChild(shape);
    });
    flows.forEach(function (f) {
      var s = map[f.s], t = map[f.t]; if (!s || !t) return;
      var pts = t.level > s.level
        ? (s.cy === t.cy ? [[s.cx + s.w / 2, s.cy], [t.cx - t.w / 2, t.cy]] : [[s.cx + s.w / 2, s.cy], [(s.cx + s.w / 2 + t.cx - t.w / 2) / 2, s.cy], [(s.cx + s.w / 2 + t.cx - t.w / 2) / 2, t.cy], [t.cx - t.w / 2, t.cy]])
        : [[s.cx, s.cy + s.h / 2], [s.cx, maxY + 60], [t.cx, maxY + 60], [t.cx, t.cy + t.h / 2]];
      var edge = doc.createElementNS(DI, "bpmndi:BPMNEdge"); edge.setAttribute("id", "DF_E_" + f.id); edge.setAttribute("bpmnElement", f.id);
      pts.forEach(function (p) { var w = doc.createElementNS(DDDI, "di:waypoint"); w.setAttribute("x", p[0]); w.setAttribute("y", p[1]); edge.appendChild(w); });
      plane.appendChild(edge);
    });
    root.appendChild(diagram);
    return new XMLSerializer().serializeToString(doc);
  };

  async function addBpmnLayout(xml) {
    try {
      var mod = await Promise.race([import(AUTO_LAYOUT_ESM), new Promise(function (_, rej) { setTimeout(function () { rej(new Error("timeout")); }, 8000); })]);
      return await mod.layoutProcess(xml);
    } catch (e) {
      return R.fallbackBpmnLayout(xml); // library unreachable: use the built-in simple layout
    }
  }

  async function renderBpmn(source) {
    loadCss(BPMN_CSS);
    await loadScript(BPMN_VIEWER_JS).catch(function (e) { throw fatal(e.message); });
    var wrap = $("canvasWrap");
    if (!bpmnHost) { bpmnHost = document.createElement("div"); bpmnHost.className = "bpmn-host"; wrap.insertBefore(bpmnHost, $("canvasMsg")); }
    if (bpmnViewer) { bpmnViewer.destroy(); bpmnViewer = null; }
    bpmnHost.hidden = false; $("stage").hidden = true;
    var viewer = new window.BpmnJS({ container: bpmnHost });
    var xml = /BPMNDiagram/.test(source) ? source : await addBpmnLayout(source);
    try { await viewer.importXML(xml); }
    catch (e) { viewer.destroy(); throw new Error("BPMN import failed: " + clip(e.message)); }
    bpmnViewer = viewer;
    var canvas = viewer.get("canvas");
    canvas.zoom("fit-viewport", "auto");
    viewer.on("canvas.viewbox.changed", function () { $("zoomLabel").textContent = Math.round(canvas.zoom() * 100) + "%"; });
    $("zoomLabel").textContent = Math.round(canvas.zoom() * 100) + "%";
    return viewer;
  }

  function fatal(msg) { var e = new Error(msg); e.fatal = true; return e; }

  /* ---------- public API ---------- */
  R.hasView = function () { return !!current.engine; };
  R.engine = function () { return current.engine; };
  R.setMermaidTheme = function (t) { current.mermaidTheme = t || "default"; };
  R.mermaidTheme = function () { return current.mermaidTheme; };
  R.bpmnViewer = function () { return bpmnViewer; };

  R.clear = function () {
    $("stage").innerHTML = ""; $("stage").hidden = false;
    if (bpmnViewer) { bpmnViewer.destroy(); bpmnViewer = null; }
    if (bpmnHost) bpmnHost.hidden = true;
    current.engine = null;
  };

  R.showMessage = function (node, kind) {
    var box = $("canvasMsg"), inner = box.firstElementChild;
    inner.innerHTML = ""; inner.appendChild(node); box.hidden = false;
    box.dataset.kind = kind || "";
  };
  R.hideMessage = function () { $("canvasMsg").hidden = true; };

  /** Render once; throws on failure (message is user-presentable). */
  R.render = async function (engine, source, opts) {
    opts = opts || {};
    if (engine !== "bpmn") {
      if (bpmnViewer) { bpmnViewer.destroy(); bpmnViewer = null; }
      if (bpmnHost) bpmnHost.hidden = true;
      $("stage").hidden = false;
    }
    try {
      if (engine === "mermaid") await renderMermaid(source);
      else if (engine === "plantuml") await renderPlantuml(source);
      else if (engine === "bpmn") await renderBpmn(source);
      else throw new Error("Unsupported engine: " + engine);
    } catch (e) {
      var err = new Error(clip(e.message)); err.fatal = !!e.fatal; err.status = e.status; throw err;
    }
    current.engine = engine;
    R.hideMessage();
    if (engine !== "bpmn") { current.autoFit = opts.keepView ? current.autoFit : true; if (opts.keepView) apply(); else R.fit(); }
    return true;
  };

  /**
   * Render; if it fails with a syntax-type error, ask the server to repair the source (max 3 attempts).
   * Returns {ok, source, fixed, attempts, error}. Never reports success for a failed render.
   */
  R.renderWithAutoFix = async function (engine, source, opts) {
    opts = opts || {};
    var attempts = 0, cur = source, last = null;
    for (;;) {
      try { await R.render(engine, cur, opts); return { ok: true, source: cur, fixed: attempts > 0, attempts: attempts }; }
      catch (e) { last = e; }
      if (last.fatal || !opts.autoFix || attempts >= 3) return { ok: false, source: cur, error: last.message, attempts: attempts, fatal: !!last.fatal };
      attempts++;
      if (opts.onAttempt) opts.onAttempt(attempts);
      try {
        var res = await DF.api("POST", "/api/fix-diagram", { source: cur, engine: engine, error: last.message, attempt: attempts, diagram_type: opts.diagramType || undefined });
        cur = res.source;
      } catch (apiErr) {
        return { ok: false, source: cur, error: "Automatic fix failed: " + apiErr.message + " (original error: " + last.message + ")", attempts: attempts };
      }
    }
  };

  R.nodeIdFromElement = function (el) {
    var g = el && el.closest && el.closest("g.node");
    if (!g) return null;
    var d = g.getAttribute("data-id");
    if (d) return d;
    var m = /^flowchart-(.+)-\d+$/.exec(g.id || "");
    return m ? m[1] : null;
  };
  R.highlightNode = function (id) {
    Array.prototype.forEach.call($("stage").querySelectorAll(".df-selected"), function (n) { n.classList.remove("df-selected"); });
    if (!id) return;
    Array.prototype.forEach.call($("stage").querySelectorAll("g.node"), function (g) {
      var gid = g.getAttribute("data-id") || ((/^flowchart-(.+)-\d+$/.exec(g.id || "") || [])[1]);
      if (gid === id) g.classList.add("df-selected");
    });
  };

  document.addEventListener("DOMContentLoaded", function () { if ($("canvasWrap")) initPanZoom(); });
})();
