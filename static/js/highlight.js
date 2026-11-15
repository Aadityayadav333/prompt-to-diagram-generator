/* Dependency-free syntax highlighter for Mermaid, PlantUML and BPMN XML.
 * Pure function (no DOM) so it can be unit-tested in Node. All text is HTML-escaped. */
(function (root) {
  "use strict";

  var ESC = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
  function esc(s) { return s.replace(/[&<>"']/g, function (c) { return ESC[c]; }); }

  var MERMAID_KW = "flowchart|graph|subgraph|end|sequenceDiagram|participant|actor|classDiagram|class|erDiagram|" +
    "stateDiagram-v2|stateDiagram|state|alt|else|opt|loop|par|and|Note|note|over|of|activate|deactivate|direction|" +
    "autonumber|title|style|classDef|linkStyle|TD|TB|BT|LR|RL|as|C4Context|C4Container|C4Component";
  var PUML_KW = "@startuml|@enduml|actor|usecase|participant|component|node|package|class|interface|database|cloud|" +
    "rectangle|artifact|object|state|start|stop|end|if|then|else|elseif|endif|fork|again|while|endwhile|repeat|" +
    "skinparam|title|note|left|right|top|bottom|direction|to|as|robust|concise|port|portin|portout|enum|abstract|" +
    "!include|!theme|Person|System|System_Ext|Container|ContainerDb|Component|Rel|System_Boundary|Container_Boundary";

  var RULES = {
    mermaid: [
      ["comment", "%%[^\\n]*"],
      ["string", '"[^"\\n]*"'],
      ["arrow", "<?[-=.]{1,3}[>xo)]{1,2}|-->>|->>|--[>ox]?|\\|\\|--[o|]?[{|]|[}|][o|]--[|o]?[{|]?|<\\|--|\\*--|o--|\\.\\.>|\\.\\.\\|>"],
      ["keyword", "\\b(?:" + MERMAID_KW + ")\\b"],
      ["number", "\\b\\d+(?:\\.\\d+)?\\b"],
    ],
    plantuml: [
      ["comment", "'[^\\n]*"],
      ["string", '"[^"\\n]*"'],
      ["keyword", "(?:@|!)?\\b(?:" + PUML_KW + ")\\b|@startuml|@enduml"],
      ["arrow", "[<*o#x+-]{0,2}[-.=]{1,3}(?:\\[[^\\]\\n]*\\])?[-.=]*[>*o#x+\\\\/|]{1,2}"],
      ["number", "\\b\\d+(?:\\.\\d+)?\\b"],
    ],
    bpmn: [
      ["comment", "<!--[\\s\\S]*?-->"],
      ["tag", "</?[\\w:.-]+|/?>"],
      ["attr", "[\\w:.-]+(?==)"],
      ["string", '"[^"]*"'],
    ],
  };

  var compiled = {};
  function getRegex(engine) {
    if (compiled[engine]) return compiled[engine];
    var rules = RULES[engine] || [];
    var re = new RegExp(rules.map(function (r) { return "(" + r[1] + ")"; }).join("|"), "g");
    compiled[engine] = { re: re, names: rules.map(function (r) { return r[0]; }) };
    return compiled[engine];
  }

  function highlight(engine, code) {
    var spec = getRegex(engine);
    if (!spec.names.length) return esc(code);
    var out = "", last = 0, m;
    spec.re.lastIndex = 0;
    while ((m = spec.re.exec(code)) !== null) {
      if (m[0] === "") { spec.re.lastIndex++; continue; }
      var idx = -1;
      for (var i = 1; i < m.length; i++) { if (m[i] !== undefined) { idx = i - 1; break; } }
      out += esc(code.slice(last, m.index));
      out += '<span class="tok-' + spec.names[idx] + '">' + esc(m[0]) + "</span>";
      last = m.index + m[0].length;
    }
    return out + esc(code.slice(last));
  }

  var api = { highlight: highlight, escapeHtml: esc };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else { root.DF = root.DF || {}; root.DF.highlight = highlight; root.DF.escapeHtml = esc; }
})(typeof window !== "undefined" ? window : globalThis);
