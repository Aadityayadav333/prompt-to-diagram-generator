/* Client-side export: SVG, high-resolution PNG, PDF, and source download. */
(function () {
  "use strict";
  window.DF = window.DF || {};
  var X = (DF.exporter = {});
  var MAX_SIDE = 16384, MAX_PIXELS = 120e6;
  var EXT = { mermaid: ["mmd", "text/plain", "Mermaid source"], plantuml: ["puml", "text/plain", "PlantUML source"], bpmn: ["bpmn", "application/xml", "BPMN XML"] };

  X.extFor = function (engine) { return EXT[engine] || ["txt", "text/plain", "Source"]; };
  function fileName(title, ext) { return ((title || "diagram").replace(/[^A-Za-z0-9_-]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 60) || "diagram") + "." + ext; }
  function save(blob, name) {
    var a = document.createElement("a"), url = URL.createObjectURL(blob);
    a.href = url; a.download = name; document.body.appendChild(a); a.click(); a.remove();
    setTimeout(function () { URL.revokeObjectURL(url); }, 2000);
  }

  /** Returns {svg, width, height, background} for the diagram currently on screen. */
  X.getSvg = async function (engine, theme) {
    var bg = engine === "mermaid" && theme === "dark" ? "#1e1e1e" : "#ffffff";
    if (engine === "bpmn") {
      var v = DF.renderer.bpmnViewer();
      if (!v) throw new Error("Nothing to export.");
      var out = await v.saveSVG(), m = /viewBox="[\d.\-]+\s+[\d.\-]+\s+([\d.]+)\s+([\d.]+)"/.exec(out.svg) || /width="([\d.]+)"[^>]*height="([\d.]+)"/.exec(out.svg);
      return { svg: out.svg, width: m ? parseFloat(m[1]) : 1200, height: m ? parseFloat(m[2]) : 800, background: bg };
    }
    var el = document.querySelector("#stage svg");
    if (!el) throw new Error("Nothing to export.");
    var clone = el.cloneNode(true);
    clone.querySelectorAll(".df-selected").forEach(function (n) { n.classList.remove("df-selected"); });
    var w = parseFloat(clone.getAttribute("width")), h = parseFloat(clone.getAttribute("height"));
    clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
    clone.setAttribute("xmlns:xlink", "http://www.w3.org/1999/xlink");
    clone.removeAttribute("style");
    return { svg: new XMLSerializer().serializeToString(clone), width: w, height: h, background: bg };
  };

  X.svg = async function (engine, theme, title) {
    var s = await X.getSvg(engine, theme);
    var body = s.svg.replace(/^<\?xml[^>]*\?>\s*/, "");
    save(new Blob(['<?xml version="1.0" encoding="UTF-8"?>\n' + body], { type: "image/svg+xml" }), fileName(title, "svg"));
  };

  function rasterize(s, scale) {
    var w = s.width, h = s.height, notes = null;
    var k = Math.min(scale, MAX_SIDE / w, MAX_SIDE / h, Math.sqrt(MAX_PIXELS / (w * h)));
    if (k < scale) notes = "Reduced to " + k.toFixed(1) + "× (browser canvas limit for very large diagrams).";
    return new Promise(function (resolve, reject) {
      var img = new Image();
      img.onload = function () {
        var c = document.createElement("canvas");
        c.width = Math.max(1, Math.round(w * k)); c.height = Math.max(1, Math.round(h * k));
        var ctx = c.getContext("2d");
        ctx.fillStyle = s.background; ctx.fillRect(0, 0, c.width, c.height);
        ctx.imageSmoothingQuality = "high";
        ctx.drawImage(img, 0, 0, c.width, c.height);
        try { resolve({ canvas: c, notes: notes, scale: k }); } catch (e) { reject(e); }
      };
      img.onerror = function () { reject(new Error("The browser could not rasterize this diagram.")); };
      var svg = s.svg;
      if (!/\swidth="/.test(svg.slice(0, 400))) svg = svg.replace("<svg", '<svg width="' + w + '" height="' + h + '"');
      img.src = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(svg);
    });
  }

  X.png = async function (engine, theme, title, scale) {
    var r = await rasterize(await X.getSvg(engine, theme), scale || 3);
    await new Promise(function (res, rej) {
      r.canvas.toBlob(function (b) { if (!b) return rej(new Error("PNG encoding failed (diagram too large).")); save(b, fileName(title, "png")); res(); }, "image/png");
    });
    return r.notes;
  };

  X.pdf = async function (engine, theme, title, scale) {
    if (!window.jspdf) throw new Error("PDF library failed to load. Check your connection or content blocker.");
    var s = await X.getSvg(engine, theme), r = await rasterize(s, scale || 3);
    var pad = 24, pw = s.width * 0.75 + pad * 2, ph = s.height * 0.75 + pad * 2; // px -> pt
    var pdf = new window.jspdf.jsPDF({ orientation: pw >= ph ? "landscape" : "portrait", unit: "pt", format: [pw, ph], compress: true });
    pdf.setFillColor(s.background); pdf.rect(0, 0, pw, ph, "F");
    pdf.addImage(r.canvas.toDataURL("image/png"), "PNG", pad, pad, s.width * 0.75, s.height * 0.75, undefined, "FAST");
    pdf.setProperties({ title: title || "Diagram", creator: "DiagramForge AI" });
    pdf.save(fileName(title, "pdf"));
    return r.notes;
  };

  X.source = function (engine, source, title) {
    var e = X.extFor(engine);
    save(new Blob([source], { type: e[1] + ";charset=utf-8" }), fileName(title, e[0]));
  };
})();
