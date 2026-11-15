/* Source-level helpers behind the "visual" editing controls.
 *
 * Mermaid auto-lays-out diagrams, so there is no drag-and-drop positioning. Instead, clicking a node
 * in a flowchart lets the user rename / delete it and add nodes and edges; each action rewrites the
 * Mermaid SOURCE, which is then re-rendered, so the source editor and the visual controls stay in sync.
 * Pure string functions (no DOM) so they are unit-tested in Node (tests/js/flowedit.test.js).
 */
(function (root) {
  "use strict";

  var PAIRS = { "[[": "]]", "[(": ")]", "([": "])", "((": "))", "{{": "}}", "[": "]", "(": ")", "{": "}" };
  var SKIP_LINE = /^\s*(subgraph|end|style|classDef|class|click|linkStyle|%%|direction)\b/;
  var NODE_DEF = /(?<![\w-])([A-Za-z_][\w-]*)(\[\[|\[\(|\(\[|\(\(|\{\{|\[|\(|\{)\s*(?:"([^"]*)"|([^\]\)\}"]*?))\s*(\]\]|\)\]|\]\)|\)\)|\}\}|\]|\)|\})/g;
  var EDGE_SPLIT = /-->|---|-\.->|-\.-|==>|--[ox]|~~~/;

  function headerIndex(lines) {
    for (var i = 0; i < lines.length; i++) {
      var s = lines[i].trim();
      if (s && !s.startsWith("%%")) return i;
    }
    return 0;
  }

  function isFlowchart(src) {
    var lines = (src || "").split("\n");
    return /^\s*(flowchart|graph)\b/.test(lines[headerIndex(lines)] || "");
  }

  function esc(label) { return String(label).replace(/"/g, "#quot;").replace(/\n/g, " ").trim(); }
  function unesc(label) { return String(label).replace(/#quot;/g, '"'); }
  function stripQuoted(s) { return s.replace(/"[^"]*"/g, '""'); }

  /** Returns { id: {id, label, open, close, defined} } for every node mentioned in the flowchart. */
  function parseNodes(src) {
    var nodes = {}, order = [];
    var lines = (src || "").split("\n");
    for (var li = headerIndex(lines) + 1; li < lines.length; li++) {
      var line = lines[li];
      if (SKIP_LINE.test(line)) continue;
      NODE_DEF.lastIndex = 0;
      var m;
      while ((m = NODE_DEF.exec(line)) !== null) {
        if (PAIRS[m[2]] !== m[5]) continue;
        if (!nodes[m[1]] || !nodes[m[1]].defined) {
          nodes[m[1]] = { id: m[1], label: unesc(m[3] !== undefined ? m[3] : (m[4] || m[1])), open: m[2], close: m[5], defined: true };
          if (order.indexOf(m[1]) < 0) order.push(m[1]);
        }
      }
      // bare references (ids used only inside edges)
      var bare = stripQuoted(line).replace(/\|[^|]*\|/g, " ").replace(NODE_DEF, function (all, id) { return id + " "; });
      bare.split(EDGE_SPLIT).forEach(function (part) {
        var t = part.trim().replace(/;$/, "");
        var idm = /^([A-Za-z_][\w-]*)\b/.exec(t);
        if (idm && !/^(end|subgraph|direction)$/.test(idm[1]) && !nodes[idm[1]]) {
          nodes[idm[1]] = { id: idm[1], label: idm[1], open: "[", close: "]", defined: false };
          order.push(idm[1]);
        }
      });
    }
    return { map: nodes, order: order };
  }

  function nodeList(src) {
    var p = parseNodes(src);
    return p.order.map(function (id) { return p.map[id]; });
  }

  function escRe(s) { return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"); }

  function renameNode(src, id, newLabel) {
    var label = esc(newLabel);
    if (!label) throw new Error("Label cannot be empty.");
    var lines = src.split("\n"), done = false;
    var re = new RegExp("(?<![\\w-])" + escRe(id) + "(\\[\\[|\\[\\(|\\(\\[|\\(\\(|\\{\\{|\\[|\\(|\\{)\\s*(?:\"[^\"]*\"|[^\\]\\)\\}\"]*?)\\s*(\\]\\]|\\)\\]|\\]\\)|\\)\\)|\\}\\}|\\]|\\)|\\})");
    for (var i = headerIndex(lines) + 1; i < lines.length && !done; i++) {
      if (SKIP_LINE.test(lines[i])) continue;
      lines[i] = lines[i].replace(re, function (all, open, close) {
        if (PAIRS[open] !== close || done) return all;
        done = true;
        return id + open + '"' + label + '"' + close;
      });
    }
    if (!done) lines.push("  " + id + '["' + label + '"]'); // node had no explicit definition yet
    return lines.join("\n");
  }

  function nextId(src) {
    var used = parseNodes(src).map, n = 1;
    while (used["N" + n]) n++;
    return "N" + n;
  }

  function addNode(src, label, shape) {
    var id = nextId(src);
    var open = "[", close = "]";
    if (shape === "decision") { open = "{"; close = "}"; }
    else if (shape === "rounded") { open = "("; close = ")"; }
    else if (shape === "database") { open = "[("; close = ")]"; }
    var text = esc(label);
    if (!text) throw new Error("Label cannot be empty.");
    return { src: src.replace(/\s+$/, "") + "\n  " + id + open + '"' + text + '"' + close, id: id };
  }

  function addEdge(src, from, to, label) {
    var nodes = parseNodes(src).map;
    if (!nodes[from] || !nodes[to]) throw new Error("Both nodes must exist.");
    var text = esc(label || "");
    var arrow = text ? '-->|"' + text + '"|' : "-->";
    return src.replace(/\s+$/, "") + "\n  " + from + " " + arrow + " " + to;
  }

  function deleteNode(src, id) {
    var before = parseNodes(src).map;
    if (!before[id]) throw new Error("Node not found.");
    var lines = src.split("\n");
    var ref = new RegExp("(?<![\\w-])" + escRe(id) + "(?![\\w-])");
    var hdr = headerIndex(lines);
    var kept = lines.filter(function (line, i) {
      if (i <= hdr) return true;
      if (/^\s*(subgraph|end|%%|direction)\b/.test(line)) return true;
      return !ref.test(stripQuoted(line));
    });
    var out = kept.join("\n");
    // Re-declare nodes whose only definition lived on a removed line (e.g. `X --> Y["Label"]`).
    var after = parseNodes(out).map;
    Object.keys(before).forEach(function (k) {
      if (k === id || !before[k].defined) return;
      if (!after[k] || !after[k].defined) {
        var b = before[k];
        out += "\n  " + k + b.open + '"' + esc(b.label) + '"' + b.close;
      }
    });
    return out;
  }

  /* ---- layout direction & themes (source level) ---- */
  var DIR_TYPES = /^\s*(flowchart|graph|stateDiagram|classDiagram)/;

  function getDirection(src, engine) {
    if (engine === "plantuml") {
      if (/^\s*left to right direction\s*$/im.test(src)) return "LR";
      if (/^\s*top to bottom direction\s*$/im.test(src)) return "TB";
      return "";
    }
    var lines = (src || "").split("\n"), h = lines[headerIndex(lines)] || "";
    var m = /^\s*(?:flowchart|graph)\s+(TD|TB|BT|LR|RL)/.exec(h);
    if (m) return m[1] === "TD" ? "TB" : m[1];
    var d = /^\s*direction\s+(TB|BT|LR|RL)\s*$/m.exec(src || "");
    return d ? d[1] : "";
  }

  function supportsDirection(src, engine) {
    if (engine === "plantuml") return true;
    var lines = (src || "").split("\n");
    return engine === "mermaid" && DIR_TYPES.test(lines[headerIndex(lines)] || "");
  }

  function setDirection(src, dir, engine) {
    var lines = src.split("\n"), h = headerIndex(lines);
    if (engine === "plantuml") {
      lines = lines.filter(function (l) { return !/^\s*(left to right|top to bottom) direction\s*$/i.test(l); });
      var at = lines.findIndex(function (l) { return /^\s*@startuml/i.test(l); });
      if (at >= 0 && dir === "LR") lines.splice(at + 1, 0, "left to right direction");
      else if (at >= 0 && dir === "TB") lines.splice(at + 1, 0, "top to bottom direction");
      return lines.join("\n");
    }
    var fc = /^(\s*)(flowchart|graph)\b[^\n]*$/.exec(lines[h]);
    if (fc) { lines[h] = fc[1] + fc[2] + " " + dir; return lines.join("\n"); }
    if (DIR_TYPES.test(lines[h])) {
      lines = lines.filter(function (l, i) { return !(i > h && /^\s*direction\s+(TB|BT|LR|RL)\s*$/.test(l) && !/^\s{4,}/.test(l)); });
      lines.splice(h + 1, 0, "  direction " + dir);
    }
    return lines.join("\n");
  }

  function getPlantumlTheme(src) {
    var m = /^\s*!theme\s+([\w-]+)\s*$/im.exec(src || "");
    return m ? m[1] : "";
  }

  function setPlantumlTheme(src, name) {
    var lines = src.split("\n").filter(function (l) { return !/^\s*!theme\s+/i.test(l); });
    var at = lines.findIndex(function (l) { return /^\s*@startuml/i.test(l); });
    if (name && at >= 0) lines.splice(at + 1, 0, "!theme " + name);
    return lines.join("\n");
  }

  var api = {
    isFlowchart: isFlowchart, parseNodes: parseNodes, nodeList: nodeList, renameNode: renameNode,
    addNode: addNode, addEdge: addEdge, deleteNode: deleteNode, getDirection: getDirection,
    setDirection: setDirection, supportsDirection: supportsDirection,
    getPlantumlTheme: getPlantumlTheme, setPlantumlTheme: setPlantumlTheme,
  };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else { root.DF = root.DF || {}; root.DF.flow = api; }
})(typeof window !== "undefined" ? window : globalThis);
