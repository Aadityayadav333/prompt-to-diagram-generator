"""Server-side validation of generated diagram source.

Python cannot run Mermaid's real parser, so Mermaid checks here are structural heuristics
that catch the most common LLM mistakes. The browser additionally runs the authoritative
`mermaid.parse()` and reports failures back through /api/fix-diagram. PlantUML checks include
a safety filter (no file/URL includes). BPMN checks parse the XML with DTD/entities rejected.
"""
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from config import Config

MERMAID_HEADERS = (
    "flowchart", "graph", "sequenceDiagram", "classDiagram", "stateDiagram", "erDiagram", "journey",
    "gantt", "pie", "mindmap", "timeline", "quadrantChart", "requirementDiagram", "gitGraph",
    "block-beta", "architecture-beta", "xychart-beta", "sankey-beta",
)
SEQ_ARROW = re.compile(r"-->>|->>|--x|-x|--\)|-\)|-->|->")
SEQ_BLOCK_OPEN = re.compile(r"^\s*(alt|opt|loop|par|critical|break|rect)\b")
BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"

_FORBIDDEN_PLANTUML = re.compile(
    r"^\s*(!includeurl|!includesub|!include_many|!include_once|!import|!pragma|!assert|!log|!dump_memory)\b|%getenv|%env\(|%load_json|%file|%dirpath|%filename",
    re.IGNORECASE | re.MULTILINE,
)
_INCLUDE = re.compile(r"^\s*!include\s+(.*)$", re.IGNORECASE | re.MULTILINE)
_THEME = re.compile(r"^\s*!theme\s+(.*)$", re.IGNORECASE | re.MULTILINE)


@dataclass
class ValidationResult:
    valid: bool
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    def to_dict(self):
        return {"valid": self.valid, "errors": self.errors, "warnings": self.warnings}


def strip_fences(source: str) -> str:
    """Remove markdown code fences an LLM may have wrapped around the source."""
    text = (source or "").strip()
    text = re.sub(r"^```[a-zA-Z0-9_-]*\s*\n", "", text)
    text = re.sub(r"\n?```\s*$", "", text)
    return text.strip()


def _strip_quoted(line: str) -> str:
    return re.sub(r'"[^"]*"', '""', line)


def _meaningful_lines(source: str):
    """Yield (lineno, text) skipping blanks, %% comments and YAML front-matter."""
    in_front = False
    for i, raw in enumerate(source.splitlines(), 1):
        s = raw.strip()
        if i == 1 and s == "---":
            in_front = True
            continue
        if in_front:
            if s == "---":
                in_front = False
            continue
        if not s or s.startswith("%%") and not s.startswith("%%{"):
            continue
        yield i, raw


def validate_mermaid(source: str) -> ValidationResult:
    errors, warnings = [], []
    if "```" in source:
        errors.append("Source contains markdown code fences; provide raw Mermaid only.")
    low = source.lower()
    if "<script" in low or "javascript:" in low:
        errors.append("Source contains disallowed script content.")
    if "securitylevel" in low:
        errors.append("Source must not change Mermaid security settings.")

    lines = list(_meaningful_lines(source))
    if not lines:
        return ValidationResult(False, ["Source is empty."])

    # Header
    first_no, first = lines[0]
    header = first.strip()
    if header.startswith("%%{"):  # init directive: header is the next line
        lines = lines[1:]
        if not lines:
            return ValidationResult(False, ["Source has no diagram header."])
        first_no, first = lines[0]
        header = first.strip()
    kind = next((h for h in MERMAID_HEADERS if header.startswith(h)), None)
    if not kind:
        c4 = re.match(r"^C4(Context|Container|Component|Dynamic|Deployment)\b", header)
        if c4:
            kind = "c4"
        else:
            errors.append(f"Line {first_no}: unknown or missing diagram header '{header[:40]}'.")
            return ValidationResult(False, errors, warnings)

    body = [(n, t) for n, t in lines[1:]]

    for n, t in body:
        if re.match(r"^\s*click\s+", t):
            errors.append(f"Line {n}: 'click' directives are not allowed.")
        if _strip_quoted(t).count('"') % 2 == 1:
            errors.append(f"Line {n}: unbalanced double quote.")

    if kind in ("flowchart", "graph"):
        _check_flowchart(header, body, errors, warnings)
    elif kind == "sequenceDiagram":
        _check_sequence(body, errors)
    elif kind == "classDiagram":
        _check_balanced_braces(body, errors)
        if not any(re.match(r"^\s*class\s+\w+|^\s*\w+\s+(<\|--|\*--|o--|-->|\.\.>|\.\.\|>|--)", t) for _, t in body):
            errors.append("Class diagram defines no classes or relationships.")
    elif kind == "erDiagram":
        _check_er(body, errors)
    elif kind == "stateDiagram":
        _check_balanced_braces(body, errors)
        if not any("-->" in t for _, t in body):
            errors.append("State diagram has no transitions ('-->').")

    if len(source) > Config.MAX_SOURCE_CHARS:
        errors.append(f"Source exceeds {Config.MAX_SOURCE_CHARS} characters.")
    return ValidationResult(not errors, errors, warnings)


def _check_balanced_braces(body, errors):
    depth = 0
    for n, t in body:
        s = _strip_quoted(t)
        depth += s.count("{") - s.count("}")
        if depth < 0:
            errors.append(f"Line {n}: closing '}}' without opening '{{'.")
            return
    if depth != 0:
        errors.append("Unbalanced curly braces.")


def _check_flowchart(header, body, errors, warnings):
    if not re.match(r"^(flowchart|graph)(\s+(TD|TB|BT|LR|RL))?\s*;?$", header):
        errors.append(f"Invalid flowchart header '{header}'. Use e.g. 'flowchart TD'.")
    opens = ends = 0
    edge = re.compile(r"-->|---|-\.->|==>|-\.-|--[ox]")
    for n, t in body:
        s = t.strip()
        if re.match(r"^subgraph\b", s):
            opens += 1
        elif s == "end":
            ends += 1
        if re.search(r"\[[^\]\"]*[()][^\]\"]*\]", _strip_quoted(t)) and "[(" not in t and "[[" not in t and "([" not in t:
            errors.append(f"Line {n}: label contains parentheses; wrap the label in double quotes.")
        if re.match(r"^\s*end\b\s*(-->|---|\[|\()", t) or re.search(r"(-->|---)\s*end\s*($|\[|\(|;)", t):
            errors.append(f"Line {n}: 'end' cannot be used as a node id.")
    if opens != ends:
        errors.append(f"{opens} 'subgraph' block(s) but {ends} 'end' line(s): every subgraph needs a closing 'end'.")
    if not any(edge.search(t) for _, t in body):
        errors.append("Flowchart has no edges (e.g. 'A --> B').")
    # Curly braces are decision shapes in flowcharts, so they are not brace-checked here.


def _check_sequence(body, errors):
    opens = ends = 0
    messages = 0
    for n, t in body:
        s = t.strip()
        if SEQ_BLOCK_OPEN.match(s):
            opens += 1
        elif s == "end":
            ends += 1
        elif SEQ_ARROW.search(s) and ":" in s:
            messages += 1
    if opens != ends:
        errors.append(f"{opens} block(s) (alt/opt/loop/par) but {ends} 'end' line(s).")
    if messages == 0:
        errors.append("Sequence diagram has no messages ('A->>B: text').")


_ER_REL = re.compile(r"^\s*[\w-]+\s+[|}][|o](--|\.\.)[|o][|{]\s+[\w-]+\s*:\s*\S.*$")
_ER_ATTR = re.compile(r'^\s*\w+(\[\])?\s+\w+(\s+(PK|FK|UK)(\s*,\s*(PK|FK|UK))*)?(\s+"[^"]*")?\s*$')


def _check_er(body, errors):
    inside = False
    entities = 0
    for n, t in body:
        s = t.strip()
        if inside:
            if s == "}":
                inside = False
            elif not _ER_ATTR.match(t):
                errors.append(f"Line {n}: invalid attribute '{s[:40]}'. Use 'type name [PK|FK|UK]'.")
            continue
        if s.endswith("{") and re.match(r'^[\w-]+(\["[^"]*"\])?\s*\{$', s):
            inside = True
            entities += 1
        elif "--" in s or ".." in s:
            if not _ER_REL.match(t):
                errors.append(f"Line {n}: invalid relationship '{s[:50]}'. Example: CUSTOMER ||--o{{ ORDER : places")
            entities += 1
        elif s == "}":
            errors.append(f"Line {n}: stray '}}'.")
        elif re.match(r"^[\w-]+$", s):
            entities += 1
        else:
            errors.append(f"Line {n}: unrecognised ER syntax '{s[:40]}'.")
    if inside:
        errors.append("Entity block is not closed with '}'.")
    if entities == 0:
        errors.append("ER diagram has no entities.")


def validate_plantuml(source: str) -> ValidationResult:
    errors, warnings = [], []
    if "```" in source:
        errors.append("Source contains markdown code fences; provide raw PlantUML only.")
    s = source.strip()
    if not s.lower().startswith("@startuml"):
        errors.append("PlantUML source must begin with @startuml.")
    if not s.lower().rstrip().endswith("@enduml"):
        errors.append("PlantUML source must end with @enduml.")
    if len(re.findall(r"@startuml", s, re.IGNORECASE)) != 1 or len(re.findall(r"@enduml", s, re.IGNORECASE)) != 1:
        errors.append("PlantUML source must contain exactly one @startuml/@enduml pair.")

    # Safety: only allow standard-library includes (<...>), no URLs/files/env access.
    if _FORBIDDEN_PLANTUML.search(s):
        errors.append("Disallowed PlantUML directive (file/URL/env access).")
    for m in _INCLUDE.finditer(s):
        target = m.group(1).strip()
        if not re.match(r"^<[\w./-]+>$", target):
            errors.append("Only standard-library includes like '!include <C4/C4_Context>' are allowed.")
    for m in _THEME.finditer(s):
        if not re.match(r"^[\w-]+$", m.group(1).strip()):
            errors.append("!theme must be a plain built-in theme name.")

    depth = 0
    for line in _strip_quoted(s).splitlines():
        if line.lstrip().startswith("'"):
            continue
        depth += line.count("{") - line.count("}")
    if depth != 0:
        errors.append("Unbalanced curly braces in PlantUML source.")
    ifs = len(re.findall(r"^\s*if\s*\(", s, re.MULTILINE | re.IGNORECASE))
    endifs = len(re.findall(r"^\s*endif\b", s, re.MULTILINE | re.IGNORECASE))
    if ifs != endifs:
        errors.append(f"{ifs} 'if' vs {endifs} 'endif' in activity flow.")
    if len(s) > Config.MAX_SOURCE_CHARS:
        errors.append(f"Source exceeds {Config.MAX_SOURCE_CHARS} characters.")
    if len([l for l in s.splitlines() if l.strip()]) <= 2:
        errors.append("PlantUML source has no content between @startuml and @enduml.")
    return ValidationResult(not errors, errors, warnings)


def validate_bpmn(source: str) -> ValidationResult:
    errors, warnings = [], []
    s = source.strip()
    if re.search(r"<!DOCTYPE|<!ENTITY", s, re.IGNORECASE):
        return ValidationResult(False, ["DOCTYPE/ENTITY declarations are not allowed."])
    if len(s) > Config.MAX_SOURCE_CHARS:
        return ValidationResult(False, [f"Source exceeds {Config.MAX_SOURCE_CHARS} characters."])
    try:
        root = ET.fromstring(s)
    except ET.ParseError as exc:
        return ValidationResult(False, [f"XML is not well-formed: {exc}"])

    if root.tag != f"{{{BPMN_NS}}}definitions":
        errors.append("Root element must be bpmn:definitions in the BPMN 2.0 MODEL namespace.")
        return ValidationResult(False, errors)

    ids, refs = {}, []
    for el in root.iter():
        i = el.get("id")
        if i:
            if i in ids:
                errors.append(f"Duplicate id '{i}'.")
            ids[i] = el.tag
        for attr in ("sourceRef", "targetRef"):
            if el.get(attr):
                refs.append((el.tag.split("}")[-1], attr, el.get(attr)))
    procs = list(root.iter(f"{{{BPMN_NS}}}process"))
    if not procs:
        errors.append("No bpmn:process found.")
    if not list(root.iter(f"{{{BPMN_NS}}}startEvent")):
        errors.append("Process has no startEvent.")
    if not list(root.iter(f"{{{BPMN_NS}}}endEvent")):
        errors.append("Process has no endEvent.")
    for tag, attr, ref in refs:
        if ref not in ids:
            errors.append(f"{tag} {attr}='{ref}' does not match any element id.")
    if not list(root.iter(f"{{{BPMN_NS}}}sequenceFlow")):
        errors.append("Process has no sequenceFlow elements.")
    if not list(root.iter("{http://www.omg.org/spec/BPMN/20100524/DI}BPMNDiagram")):
        warnings.append("No diagram layout (BPMNDiagram); the client will auto-layout.")
    return ValidationResult(not errors, errors, warnings)


def validate(engine: str, source: str) -> ValidationResult:
    if not isinstance(source, str) or not source.strip():
        return ValidationResult(False, ["Source is empty."])
    if engine == "mermaid":
        return validate_mermaid(source)
    if engine == "plantuml":
        return validate_plantuml(source)
    if engine == "bpmn":
        return validate_bpmn(source)
    return ValidationResult(False, [f"Unsupported engine '{engine}'."])
