const test = require("node:test");
const assert = require("node:assert");
const flow = require("../../static/js/flowedit.js");
const { highlight } = require("../../static/js/highlight.js");

const SRC = [
  "flowchart TD",
  '  A(["Start"]) --> B["Validate input"]',
  '  B --> C{"Valid?"}',
  '  C -->|"yes"| D["Save"]',
  '  C -->|"no"| E["Show error"]',
  '  subgraph G["Group (x)"]',
  "    D --> F",
  "  end",
].join("\n");

test("parseNodes finds labels, shapes and bare references", () => {
  const m = flow.parseNodes(SRC).map;
  assert.strictEqual(m.A.label, "Start");
  assert.strictEqual(m.B.label, "Validate input");
  assert.strictEqual(m.C.open, "{");
  assert.strictEqual(m.F.defined, false);
  assert.ok(!m.G, "subgraph id must not be treated as a node");
  assert.ok(!m.end);
});

test("isFlowchart", () => {
  assert.ok(flow.isFlowchart(SRC));
  assert.ok(!flow.isFlowchart("sequenceDiagram\n A->>B: hi"));
});

test("renameNode rewrites only that node's label and keeps shape", () => {
  const out = flow.renameNode(SRC, "C", 'Is "valid"?');
  assert.ok(out.includes('C{"Is #quot;valid#quot;?"}'));
  assert.ok(out.includes('B["Validate input"]'));
  assert.strictEqual(flow.parseNodes(out).map.C.label, 'Is "valid"?');
});

test("renameNode on undefined node appends a definition", () => {
  const out = flow.renameNode(SRC, "F", "Finish");
  assert.strictEqual(flow.parseNodes(out).map.F.label, "Finish");
});

test("renameNode rejects empty labels", () => {
  assert.throws(() => flow.renameNode(SRC, "B", "   "));
});

test("addNode picks a free id; addEdge validates endpoints", () => {
  const a = flow.addNode(SRC, "Audit log");
  assert.strictEqual(a.id, "N1");
  assert.strictEqual(flow.parseNodes(a.src).map.N1.label, "Audit log");
  const b = flow.addNode(a.src, "Another", "decision");
  assert.strictEqual(b.id, "N2");
  const e = flow.addEdge(b.src, "D", "N1", "log it");
  assert.ok(e.endsWith('D -->|"log it"| N1'));
  assert.throws(() => flow.addEdge(SRC, "A", "nope", ""));
});

test("deleteNode removes the node and its edges but keeps definitions declared inline elsewhere", () => {
  const src = 'flowchart TD\n  A["a"] --> B["b"]\n  B --> C["c"]\n  C --> D["d"]';
  const out = flow.deleteNode(src, "B");
  const m = flow.parseNodes(out).map;
  assert.ok(!m.B);
  assert.strictEqual(m.A.label, "a"); // A was defined on the removed line, must be re-declared
  assert.strictEqual(m.C.label, "c");
  assert.strictEqual(m.D.label, "d");
  assert.ok(!/B/.test(out.replace(/Group/g, "")));
});

test("deleteNode keeps subgraph structure intact", () => {
  const out = flow.deleteNode(SRC, "D");
  assert.ok(out.includes('subgraph G["Group (x)"]'));
  assert.ok(out.split("\n").some((l) => l.trim() === "end"));
  assert.ok(!flow.parseNodes(out).map.D);
});

test("direction get/set for mermaid and plantuml", () => {
  assert.strictEqual(flow.getDirection(SRC, "mermaid"), "TB");
  assert.ok(flow.setDirection(SRC, "LR", "mermaid").startsWith("flowchart LR\n"));
  const st = "stateDiagram-v2\n  [*] --> A\n  A --> [*]";
  const st2 = flow.setDirection(st, "LR", "mermaid");
  assert.ok(st2.includes("  direction LR"));
  assert.strictEqual(flow.getDirection(st2, "mermaid"), "LR");
  assert.ok(!flow.supportsDirection("sequenceDiagram\n A->>B: x", "mermaid"));
  const pu = "@startuml\nA -> B\n@enduml";
  const pu2 = flow.setDirection(pu, "LR", "plantuml");
  assert.ok(pu2.split("\n")[1] === "left to right direction");
  assert.strictEqual(flow.setDirection(pu2, "TB", "plantuml").split("\n")[1], "top to bottom direction");
});

test("plantuml theme set/replace/clear", () => {
  const pu = "@startuml\nA -> B\n@enduml";
  const t = flow.setPlantumlTheme(pu, "cerulean");
  assert.strictEqual(flow.getPlantumlTheme(t), "cerulean");
  assert.strictEqual(flow.getPlantumlTheme(flow.setPlantumlTheme(t, "minty")), "minty");
  assert.strictEqual(flow.getPlantumlTheme(flow.setPlantumlTheme(t, "")), "");
});

test("highlight escapes HTML and tags tokens", () => {
  const html = highlight("mermaid", 'flowchart TD\n  A["<img src=x onerror=alert(1)>"] --> B %% c');
  assert.ok(!html.includes("<img"));
  assert.ok(html.includes("&lt;img"));
  assert.ok(html.includes('class="tok-keyword"') && html.includes('class="tok-comment"') && html.includes('class="tok-string"'));
  const x = highlight("bpmn", '<bpmn:task id="t1"/><script>x</script>');
  assert.ok(!x.includes("<script>"));
  assert.strictEqual(highlight("unknown", "<b>"), "&lt;b&gt;");
});
