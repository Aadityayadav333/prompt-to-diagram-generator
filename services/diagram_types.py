"""Catalog of supported diagram types, their rendering engine and generation guidance."""
import re

MERMAID, PLANTUML, BPMN = "mermaid", "plantuml", "bpmn"

# ---- engine-level syntax rules that are injected into generation prompts ------------------
FLOWCHART_RULES = """Mermaid flowchart rules:
- First line: `flowchart TD` (or LR). Never use the word `end` as a node id.
- Node ids: letters/digits/underscore only, no spaces (e.g. AuthSvc). Put ALL labels in double quotes: AuthSvc["Auth Service"].
- Shapes: ["rect"], ("rounded"), [("database")], {"decision"}, (["stadium"]), [["subroutine"]], (("circle")).
- Edges: A --> B, A -->|"label"| B, A -.-> B (dotted), A ==> B (thick). Quote edge labels.
- Group with: subgraph Id["Title"] ... end (every subgraph closed by `end`).
- No parentheses/brackets inside unquoted labels. No HTML. No `click` directives."""

SEQUENCE_RULES = """Mermaid sequenceDiagram rules:
- First line `sequenceDiagram`. Declare `participant Id as Label` / `actor Id as Label` first.
- Messages: A->>B: text (solid), A-->>B: text (reply/dashed). Use activate/deactivate sparingly.
- Blocks: alt/else/end, opt/end, loop/end, par/and/end - each must be closed with `end`.
- Notes: Note over A,B: text."""

CLASS_RULES = """Mermaid classDiagram rules:
- First line `classDiagram`. Define members inside braces: class User { +String id  +login() bool }.
- Relationships: A <|-- B (inheritance), A *-- B (composition), A o-- B (aggregation), A --> B (association), A ..> B (dependency), A ..|> B (realization).
- Cardinality in quotes: Customer "1" --> "0..*" Order : places.
- Class names: PascalCase, no spaces. Use <<interface>> style annotations as `class Foo { <<interface>> }`."""

ER_RULES = """Mermaid erDiagram rules:
- First line `erDiagram`. Entity names UPPER_SNAKE_CASE without spaces.
- Relationships: CUSTOMER ||--o{ ORDER : places   (||=exactly one, |o=zero or one, }o=zero or many, }|=one or many).
- Attributes: ENTITY { string id PK  string email UK  int customer_id FK  string name }.
- Attribute types are single words (string, int, float, date, datetime, boolean). Keys: PK, FK, UK."""

STATE_RULES = """Mermaid stateDiagram-v2 rules:
- First line `stateDiagram-v2`. Start/end: [*] --> Idle ; Done --> [*].
- Transitions: Idle --> Running : start. State ids have no spaces; use `state "Long name" as Id`.
- Composite states: state Parent { ... }."""

PLANTUML_RULES = """PlantUML rules:
- Begin with @startuml and end with @enduml. Output nothing outside them.
- Never use !include (except standard library includes like `!include <C4/C4_Container>`), !includeurl, !import, !pragma or %getenv.
- Quote names containing spaces. Keep identifiers simple. skinparam lines are allowed."""

BPMN_RULES = """BPMN 2.0 XML rules:
- Root <bpmn:definitions> with xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL", xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI", xmlns:dc="http://www.omg.org/spec/DD/20100524/DC", xmlns:di="http://www.omg.org/spec/DD/20100524/DI" and targetNamespace.
- One <bpmn:process id=... isExecutable="false"> containing startEvent, tasks (task/userTask/serviceTask), exclusiveGateway, endEvent, and <bpmn:sequenceFlow id sourceRef targetRef name?>.
- Use <bpmn:laneSet> with lanes only for swimlane-style requests. All ids unique, start with a letter, and every sourceRef/targetRef must exist.
- You do NOT need to supply <bpmndi:BPMNDiagram> coordinates; the client auto-layouts. No DOCTYPE or entities."""


def _t(key, label, category, engine, rules, hint, keywords=()):
    return {
        "key": key,
        "label": label,
        "category": category,
        "engine": engine,
        "rules": rules,
        "hint": hint,
        "keywords": list(keywords),
    }


_C = {
    "uml": "UML",
    "data": "Data Modeling",
    "arch": "Software Architecture",
    "process": "Process & Workflow",
    "network": "Network & Infrastructure",
    "security": "Security",
    "devops": "Testing & DevOps",
}

_TYPES = [
    # --- UML ---------------------------------------------------------------------------
    _t("class", "Class Diagram", _C["uml"], MERMAID, CLASS_RULES, "Classes with attributes, methods and typed relationships.", ["class diagram", "classes", "inheritance", "oop"]),
    _t("object", "Object Diagram", _C["uml"], PLANTUML, PLANTUML_RULES, "Use `object name { field = value }` instances and links between them.", ["object diagram", "instances", "snapshot"]),
    _t("use_case", "Use Case Diagram", _C["uml"], PLANTUML, PLANTUML_RULES, "Actors (`actor`), use cases (`usecase`), a `rectangle` system boundary; use <<include>>/<<extend>> where justified.", ["use case", "use-case", "actors", "requirements"]),
    _t("sequence", "Sequence Diagram", _C["uml"], MERMAID, SEQUENCE_RULES, "Ordered messages between participants, with alt/loop blocks for branches.", ["sequence", "interaction", "message flow", "login flow", "api call"]),
    _t("activity", "Activity Diagram", _C["uml"], PLANTUML, PLANTUML_RULES, "Use the PlantUML new activity syntax: start, :action;, if/else/endif, fork/end fork, stop.", ["activity diagram", "activity"]),
    _t("state", "State Machine Diagram", _C["uml"], MERMAID, STATE_RULES, "States and event-labelled transitions with [*] start/end.", ["state machine", "state diagram", "lifecycle", "states"]),
    _t("component", "Component Diagram", _C["uml"], PLANTUML, PLANTUML_RULES, "Use `component`, `interface`, `package` and dependencies with `..>` / `-->`.", ["component diagram", "components", "interfaces"]),
    _t("deployment", "Deployment Diagram", _C["uml"], PLANTUML, PLANTUML_RULES, "Use `node`, `artifact`, `database`, `cloud` with nesting and labelled links.", ["deployment", "servers", "nodes", "artifact"]),
    _t("package", "Package Diagram", _C["uml"], PLANTUML, PLANTUML_RULES, "Use `package` blocks (nested) and dependency arrows `..>`.", ["package diagram", "packages", "modules", "namespaces"]),
    _t("composite_structure", "Composite Structure Diagram", _C["uml"], PLANTUML, PLANTUML_RULES, "Use `component` with nested parts, `port`/`portin`/`portout` and connectors.", ["composite structure", "parts", "ports"]),
    _t("communication", "Communication Diagram", _C["uml"], PLANTUML, PLANTUML_RULES, "Objects as `object`/`rectangle` with numbered message labels on links (1: msg, 2: msg).", ["communication diagram", "collaboration"]),
    _t("interaction_overview", "Interaction Overview Diagram", _C["uml"], PLANTUML, PLANTUML_RULES, "Activity-style control flow where each step is a named interaction (use :Interaction name; actions and if/fork).", ["interaction overview"]),
    _t("timing", "Timing Diagram", _C["uml"], PLANTUML, PLANTUML_RULES, "Use `robust`/`concise` participants, `@time` markers and state changes.", ["timing diagram", "timeline of states", "signal timing"]),
    _t("profile", "Profile Diagram", _C["uml"], PLANTUML, PLANTUML_RULES, "Use `class Name <<stereotype>>`, `metaclass`-style classes and `..>` for extension relationships.", ["profile diagram", "stereotype", "uml profile"]),
    # --- Data ---------------------------------------------------------------------------
    _t("dfd_0", "DFD Level 0 (Context)", _C["data"], MERMAID, FLOWCHART_RULES, "One central process (circle) for the whole system, external entities as rectangles, labelled data flows. No data stores.", ["dfd level 0", "context diagram", "dfd 0", "data flow diagram"]),
    _t("dfd_1", "DFD Level 1", _C["data"], MERMAID, FLOWCHART_RULES, "Numbered processes (1.0, 2.0...) as circles, data stores as open-ended `[(...)]`, external entities as rectangles, every edge labelled with the data moved.", ["dfd level 1", "dfd 1", "level 1 dfd"]),
    _t("dfd_2", "DFD Level 2", _C["data"], MERMAID, FLOWCHART_RULES, "Decompose ONE Level-1 process into sub-processes (e.g. 2.1, 2.2) with data stores and flows.", ["dfd level 2", "dfd 2", "level 2 dfd"]),
    _t("erd", "Entity Relationship Diagram", _C["data"], MERMAID, ER_RULES, "Entities with attributes, keys and cardinalities.", ["erd", "entity relationship", "er diagram", "entities"]),
    _t("db_schema", "Database Schema Diagram", _C["data"], MERMAID, ER_RULES, "Physical tables with column types, PK/FK/UK, and foreign-key relationships.", ["database schema", "schema", "tables", "columns", "foreign key"]),
    _t("data_lineage", "Data Lineage Diagram", _C["data"], MERMAID, FLOWCHART_RULES, "Left-to-right flow from sources through transformations to targets/consumers; label transformations.", ["data lineage", "lineage", "etl", "data pipeline"]),
    # --- Architecture ---------------------------------------------------------------------
    _t("architecture_high", "High-Level Architecture", _C["arch"], MERMAID, FLOWCHART_RULES, "Major components grouped in subgraphs (clients, backend, data, external services); only labelled key interactions.", ["architecture", "high-level architecture", "system design", "overview"]),
    _t("architecture_low", "Low-Level Architecture", _C["arch"], MERMAID, FLOWCHART_RULES, "Detailed internal modules, classes/services, queues, caches and the specific calls between them.", ["low-level architecture", "detailed design", "internal design"]),
    _t("c4_context", "C4 System Context", _C["arch"], PLANTUML, PLANTUML_RULES + "\n- Use `!include <C4/C4_Context>` with Person(), System(), System_Ext(), Rel().", "C4 level 1: the system, its people and external systems.", ["c4 context", "system context"]),
    _t("c4_container", "C4 Container Diagram", _C["arch"], PLANTUML, PLANTUML_RULES + "\n- Use `!include <C4/C4_Container>` with Person(), System_Boundary(), Container(), ContainerDb(), System_Ext(), Rel().", "C4 level 2: deployable containers inside the system boundary.", ["c4 container", "container diagram"]),
    _t("c4_component", "C4 Component Diagram", _C["arch"], PLANTUML, PLANTUML_RULES + "\n- Use `!include <C4/C4_Component>` with Container_Boundary(), Component(), ContainerDb(), Rel().", "C4 level 3: components inside ONE container.", ["c4 component", "component c4"]),
    _t("microservices", "Microservices Architecture", _C["arch"], MERMAID, FLOWCHART_RULES, "API gateway, independently owned services each with its own datastore, message broker, external services.", ["microservice", "microservices", "service mesh"]),
    _t("client_server", "Client-Server Architecture", _C["arch"], MERMAID, FLOWCHART_RULES, "Clients, network boundary, server(s) and data stores with request/response labels.", ["client-server", "client server"]),
    _t("three_tier", "Three-Tier Architecture", _C["arch"], MERMAID, FLOWCHART_RULES, "Exactly three subgraphs: Presentation, Application (business logic), Data.", ["three-tier", "three tier", "3-tier", "3 tier"]),
    _t("event_driven", "Event-Driven Architecture", _C["arch"], MERMAID, FLOWCHART_RULES, "Producers, event broker/bus/topics, consumers; label events by name.", ["event-driven", "event driven", "pub/sub", "kafka", "message queue"]),
    _t("cloud", "Cloud Architecture", _C["arch"], MERMAID, FLOWCHART_RULES, "Cloud regions/VPC/subnets as subgraphs with managed services; use generic names unless a provider was specified.", ["cloud architecture", "aws", "azure", "gcp", "vpc"]),
    # --- Process ---------------------------------------------------------------------------
    _t("flowchart", "Flowchart", _C["process"], MERMAID, FLOWCHART_RULES, "Start/end stadium nodes, process rectangles, decision diamonds with labelled branches.", ["flowchart", "flow chart", "algorithm", "steps", "process flow"]),
    _t("bpmn", "BPMN Diagram", _C["process"], BPMN, BPMN_RULES, "BPMN 2.0 process with events, tasks, gateways and sequence flows.", ["bpmn", "business process model"]),
    _t("swimlane", "Swimlane Diagram", _C["process"], PLANTUML, PLANTUML_RULES + "\n- Use activity syntax with swimlanes: |Lane Name| then :action; lines.", "Activity flow split into lanes per actor/department.", ["swimlane", "swim lane", "lanes", "responsibilities"]),
    _t("decision_tree", "Decision Tree", _C["process"], MERMAID, FLOWCHART_RULES, "Top-down tree of decision diamonds with labelled branches ending in outcome leaves.", ["decision tree", "decision"]),
    _t("business_workflow", "Business Workflow Diagram", _C["process"], MERMAID, FLOWCHART_RULES, "Business steps grouped by role/department subgraphs, approvals as decisions.", ["business workflow", "approval workflow", "workflow", "business process"]),
    # --- Network ---------------------------------------------------------------------------
    _t("network_topology", "Network Topology", _C["network"], MERMAID, FLOWCHART_RULES, "Devices (routers, switches, firewalls, hosts) and physical/logical links; group by zone/site.", ["network topology", "topology", "lan", "wan"]),
    _t("network_architecture", "Network Architecture", _C["network"], MERMAID, FLOWCHART_RULES, "Layers/zones (edge, DMZ, core, internal), firewalls and traffic paths with protocols/ports where given.", ["network architecture", "dmz", "firewall", "subnet"]),
    _t("infrastructure", "Infrastructure Diagram", _C["network"], MERMAID, FLOWCHART_RULES, "Servers, load balancers, storage, databases and monitoring grouped by environment.", ["infrastructure", "servers", "load balancer", "devops infra"]),
    # --- Security --------------------------------------------------------------------------
    _t("threat_model", "Threat Model Diagram", _C["security"], MERMAID, FLOWCHART_RULES, "Data-flow diagram with TRUST BOUNDARIES as subgraphs; annotate flows with STRIDE threats only where plausible.", ["threat model", "stride", "trust boundary", "attack surface"]),
    _t("auth_flow", "Authentication Flow", _C["security"], MERMAID, SEQUENCE_RULES, "Sequence of credentials/tokens between user, client, auth server and resource server.", ["authentication", "oauth", "login flow", "jwt", "sso", "auth flow"]),
    _t("access_control", "Authorization & Access Control", _C["security"], MERMAID, FLOWCHART_RULES, "Roles, permissions/resources and policy decision points (RBAC/ABAC) as a graph.", ["authorization", "access control", "rbac", "permissions", "roles"]),
    # --- DevOps / Testing ----------------------------------------------------------------
    _t("ci_cd", "CI/CD Pipeline", _C["devops"], MERMAID, FLOWCHART_RULES, "Left-to-right stages: commit, build, test, scan, package, deploy; show failure paths.", ["ci/cd", "cicd", "ci cd", "continuous integration", "github actions", "jenkins"]),
    _t("test_flow", "Test Flow Diagram", _C["devops"], MERMAID, FLOWCHART_RULES, "Test planning to execution to defect handling to retest/sign-off.", ["test flow", "testing process", "qa flow", "test cycle"]),
    _t("testing_pyramid", "Software Testing Pyramid", _C["devops"], MERMAID, FLOWCHART_RULES, "A top-down stack of levels (E2E, integration, unit) drawn as stacked nodes with narrower-to-wider emphasis in labels (cost/speed/volume).", ["testing pyramid", "test pyramid"]),
    _t("deployment_pipeline", "Deployment Pipeline", _C["devops"], MERMAID, FLOWCHART_RULES, "Environments (dev, staging, prod) with promotion gates, approvals and rollback.", ["deployment pipeline", "release pipeline", "blue green", "canary", "rollback"]),
]

DIAGRAM_TYPES = {t["key"]: t for t in _TYPES}

# Sensible default for "Generate Complete System Documentation".
DEFAULT_PROJECT_SET = [
    "architecture_high",
    "use_case",
    "dfd_0",
    "dfd_1",
    "erd",
    "class",
    "sequence",
    "activity",
    "component",
    "deployment",
]

FALLBACK_TYPE = "flowchart"


def valid_key(key) -> bool:
    return isinstance(key, str) and key in DIAGRAM_TYPES


def normalize_keys(keys) -> list[str]:
    seen, out = set(), []
    for k in keys or []:
        if valid_key(k) and k not in seen:
            seen.add(k)
            out.append(k)
    return out


def public_catalog() -> list[dict]:
    return [
        {k: t[k] for k in ("key", "label", "category", "engine", "hint")} for t in _TYPES
    ]


def detect_type_hint(text: str, limit: int = 3) -> list[dict]:
    """Keyword-based preview of likely diagram types (no LLM call).

    This only drives the instant 'detected' indicator in the UI. Real selection
    happens in the LLM prompt-analysis stage.
    """
    low = (text or "").lower()
    scored = []
    for t in _TYPES:
        score = 0
        for kw in t["keywords"]:
            if re.search(r"(?<![a-z])" + re.escape(kw) + r"(?![a-z])", low):
                score += 2 if " " in kw or len(kw) > 6 else 1
        if score:
            scored.append((score, t))
    scored.sort(key=lambda s: -s[0])
    return [{"key": t["key"], "label": t["label"], "engine": t["engine"]} for _, t in scored[:limit]]
