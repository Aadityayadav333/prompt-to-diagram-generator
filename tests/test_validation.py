import pytest

from conftest import BAD_FLOWCHART, GOOD_ER, GOOD_FLOWCHART, GOOD_PUML, GOOD_SEQ
from services.diagram_validator import strip_fences, validate

BPMN_OK = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" id="d" targetNamespace="x">
  <bpmn:process id="p" isExecutable="false">
    <bpmn:startEvent id="s"/><bpmn:task id="t" name="Do"/><bpmn:endEvent id="e"/>
    <bpmn:sequenceFlow id="f1" sourceRef="s" targetRef="t"/>
    <bpmn:sequenceFlow id="f2" sourceRef="t" targetRef="e"/>
  </bpmn:process>
</bpmn:definitions>"""


@pytest.mark.parametrize("src", [GOOD_FLOWCHART, GOOD_ER, GOOD_SEQ])
def test_valid_mermaid(src):
    assert validate("mermaid", src).valid, validate("mermaid", src).errors


def test_invalid_mermaid_flowchart_reports_paren_and_subgraph():
    r = validate("mermaid", BAD_FLOWCHART)
    assert not r.valid
    joined = " ".join(r.errors)
    assert "parentheses" in joined and "subgraph" in joined


@pytest.mark.parametrize("src,needle", [
    ("hello world", "header"),
    ("", "empty"),
    ("flowchart TD\n  A --> B\n  click A callback", "click"),
    ("flowchart TD\n  A[\"x] --> B", "quote"),
    ("sequenceDiagram\n  alt x\n  A->>B: hi", "end"),
    ("erDiagram\n  A ||--|| : bad", "relationship"),
    ("flowchart TD\n  A --> B\n%%{init: {'securityLevel':'loose'}}%%", "security"),
])
def test_invalid_mermaid_cases(src, needle):
    r = validate("mermaid", src)
    assert not r.valid and needle in " ".join(r.errors).lower()


def test_mermaid_fences_rejected_but_strippable():
    fenced = f"```mermaid\n{GOOD_FLOWCHART}\n```"
    assert not validate("mermaid", fenced).valid
    assert validate("mermaid", strip_fences(fenced)).valid


def test_plantuml_valid_and_invalid():
    assert validate("plantuml", GOOD_PUML).valid
    assert not validate("plantuml", "actor A").valid
    assert not validate("plantuml", "@startuml\nA -> B\n").valid


@pytest.mark.parametrize("directive", [
    "!include /etc/passwd", "!include http://evil.example/x.puml", "!includeurl http://x", "!import foo.jar",
    "title %getenv(\"SECRET\")", "!pragma graphviz_dot jdot",
])
def test_plantuml_blocks_unsafe_directives(directive):
    assert not validate("plantuml", f"@startuml\n{directive}\nA -> B\n@enduml").valid


def test_plantuml_allows_stdlib_include():
    src = "@startuml\n!include <C4/C4_Context>\nPerson(u, \"User\")\nSystem(s, \"S\")\nRel(u, s, \"uses\")\n@enduml"
    assert validate("plantuml", src).valid


def test_bpmn_valid_invalid():
    assert validate("bpmn", BPMN_OK).valid
    assert not validate("bpmn", BPMN_OK.replace('targetRef="e"', 'targetRef="zzz"')).valid
    assert not validate("bpmn", "<bpmn:definitions").valid
    assert not validate("bpmn", '<!DOCTYPE x [<!ENTITY a "b">]>' + BPMN_OK).valid


def test_large_source_rejected():
    big = "flowchart TD\n" + "\n".join(f"  N{i} --> N{i+1}" for i in range(6000))
    r = validate("mermaid", big)
    assert not r.valid and "exceeds" in " ".join(r.errors)


def test_unknown_engine():
    assert not validate("graphviz", "x").valid
