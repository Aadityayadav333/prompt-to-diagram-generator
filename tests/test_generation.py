import pytest

from conftest import BAD_FLOWCHART, GOOD_ER, GOOD_FLOWCHART, GOOD_PUML, analysis
from providers import LLMError
from services import diagram_generator as gen
from services import llm_service
from services.diagram_types import DIAGRAM_TYPES, detect_type_hint
from services.prompt_analyzer import analyze_prompt, normalize_analysis


def post(client, url, **body):
    return client.post(url, json=body)


# ---- Stage 1: analysis --------------------------------------------------------------------------
def test_normalize_fills_missing_fields_and_drops_invalid_types():
    out = normalize_analysis({"project_name": "X", "recommended_diagram_types": ["nonsense", "erd", "erd"]})
    assert out["recommended_diagram_types"] == ["erd"]
    assert out["requested_diagram_type"] is None
    for k in ("actors", "entities", "components", "assumptions"):
        assert out[k] == []


def test_missing_requirements_falls_back_to_flowchart():
    out = normalize_analysis({})
    assert out["recommended_diagram_types"] == ["flowchart"]
    assert out["project_name"] == "Untitled Project"


def test_ambiguous_prompt_uses_recommendation(fake_llm):
    fake_llm.analysis = analysis(recommended_diagram_types=["sequence", "flowchart"])
    a = analyze_prompt("do something with users", None)
    assert gen.choose_type(a) == "sequence"


def test_explicit_type_wins_over_model_choice(fake_llm):
    a = analyze_prompt("x", None, forced_type="erd")
    assert a["requested_diagram_type"] == "erd"
    assert gen.choose_type(a, "class") == "class"


def test_detect_type_hint_keywords():
    assert detect_type_hint("Create a UML sequence diagram for login")[0]["key"] == "sequence"
    assert detect_type_hint("ERD for a library")[0]["key"] == "erd"
    assert detect_type_hint("zzz qqq") == []


def test_every_type_has_known_engine_and_rules():
    for key, t in DIAGRAM_TYPES.items():
        assert t["engine"] in ("mermaid", "plantuml", "bpmn"), key
        assert t["rules"] and t["hint"], key
    assert len(DIAGRAM_TYPES) >= 40


# ---- Stage 2: generation + fix loop -------------------------------------------------------------
def test_generate_valid_first_try(fake_llm):
    d = gen.generate_diagram(analysis(), "flowchart")
    assert d["validation_status"] == "valid" and d["fix_attempts"] == 0
    assert fake_llm.calls == ["generate"]


def test_generate_auto_fix_succeeds_on_second_try(fake_llm):
    fake_llm.generate = lambda p: {"title": "T", "source": BAD_FLOWCHART}
    fake_llm.fixes = [BAD_FLOWCHART, GOOD_FLOWCHART]
    d = gen.generate_diagram(analysis(), "flowchart")
    assert d["validation_status"] == "fixed" and d["fix_attempts"] == 2
    assert fake_llm.calls.count("fix") == 2


def test_fix_loop_stops_after_three_attempts(fake_llm):
    fake_llm.generate = lambda p: {"title": "T", "source": BAD_FLOWCHART}
    fake_llm.fixes = [BAD_FLOWCHART] * 5
    with pytest.raises(gen.GenerationError) as ei:
        gen.generate_diagram(analysis(), "flowchart")
    assert ei.value.attempts == 3 and fake_llm.calls.count("fix") == 3
    assert ei.value.errors and ei.value.draft


def test_fenced_model_output_is_cleaned(fake_llm):
    fake_llm.generate = lambda p: {"title": "T", "source": f"```mermaid\n{GOOD_FLOWCHART}\n```"}
    assert gen.generate_diagram(analysis(), "flowchart")["source"] == GOOD_FLOWCHART


def test_plantuml_and_er_types_generate(fake_llm):
    fake_llm.generate = lambda p: {"title": "T", "source": GOOD_PUML}
    assert gen.generate_diagram(analysis(), "use_case")["engine"] == "plantuml"
    fake_llm.generate = lambda p: {"title": "T", "source": GOOD_ER}
    assert gen.generate_diagram(analysis(), "erd")["engine"] == "mermaid"


# ---- Multiple diagrams ---------------------------------------------------------------------------
def test_project_set_tolerates_partial_failure(fake_llm):
    def g(prompt):
        if "Diagram type key: erd" in prompt:
            return {"title": "bad", "source": "not a diagram"}
        return {"title": "ok", "source": GOOD_FLOWCHART}

    fake_llm.generate = g
    fake_llm.fixes = ["still bad"] * 3
    res = gen.generate_project_set(analysis(), ["flowchart", "erd", "decision_tree"])
    assert [r["ok"] for r in res] == [True, False, True]
    assert res[1]["error"] and res[1]["diagram_type"] == "erd"


def test_project_set_defaults_to_ten_diagrams(fake_llm):
    def g(prompt):
        from services.diagram_types import DIAGRAM_TYPES as T
        key = prompt.split("Diagram type key: ")[1].split(" ")[0]
        return {"title": key, "source": GOOD_PUML if T[key]["engine"] == "plantuml" else (
            GOOD_ER if key == "erd" else GOOD_FLOWCHART)}

    fake_llm.generate = g
    res = gen.generate_project_set(analysis(), None)
    assert len(res) == 10
    failed = [(r["diagram_type"], r.get("error")) for r in res if not r["ok"]]
    # class and sequence need their own syntax; the fake returns flowchart source for them -> expected failures
    assert {k for k, _ in failed} <= {"class", "sequence"}


# ---- API layer -----------------------------------------------------------------------------------
def test_generate_endpoint_happy_path(client, fake_llm):
    r = post(client, "/api/generate-diagram", prompt="A login flow", diagram_type="flowchart")
    assert r.status_code == 200
    body = r.get_json()
    assert body["diagram"]["source"] == GOOD_FLOWCHART and body["saved"] is False
    assert body["analysis"]["project_name"] == "Shop"


def test_generate_endpoint_validation(client, fake_llm):
    assert post(client, "/api/generate-diagram").status_code == 400
    assert post(client, "/api/generate-diagram", prompt="x" * 9000).status_code == 413
    assert post(client, "/api/generate-diagram", prompt="x", diagram_type="bogus").status_code == 400
    assert client.post("/api/generate-diagram", data="nope", content_type="text/plain").status_code == 400


def test_generate_endpoint_returns_422_not_success_for_unfixable(client, fake_llm):
    fake_llm.generate = lambda p: {"title": "T", "source": BAD_FLOWCHART}
    fake_llm.fixes = [BAD_FLOWCHART] * 3
    r = post(client, "/api/generate-diagram", prompt="x", diagram_type="flowchart")
    assert r.status_code == 422
    body = r.get_json()
    assert "diagram" not in body and body["validation_errors"] and body["fix_attempts"] == 3


def test_provider_failures_map_to_http_status(client, fake_llm):
    fake_llm.analysis = LLMError("gemini rate limit reached.", status=429)
    r = post(client, "/api/generate-diagram", prompt="x")
    assert r.status_code == 429 and "rate limit" in r.get_json()["error"]
    fake_llm.analysis = LLMError("gemini is not configured (API key missing).", status=503)
    assert post(client, "/api/analyze-prompt", prompt="x").status_code == 503


def test_llm_json_extraction_and_invalid_json(monkeypatch):
    assert llm_service.extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert llm_service.extract_json('Sure! {"a": 2} hope that helps') == {"a": 2}
    with pytest.raises(ValueError):
        llm_service.extract_json("no json here")

    class Stub:
        calls = 0

        def generate_json_text(self, *a, **k):
            Stub.calls += 1
            return "not json"

    monkeypatch.setattr(llm_service, "get_provider", lambda name=None: Stub())
    with pytest.raises(LLMError):
        llm_service.generate_json("s", "p")
    assert Stub.calls == 2  # one retry


def test_fix_endpoint_attempt_limit_and_success(client, fake_llm):
    fake_llm.fixes = [GOOD_FLOWCHART]
    r = post(client, "/api/fix-diagram", source=BAD_FLOWCHART, engine="mermaid", attempt=1, error="Parse error")
    assert r.status_code == 200 and r.get_json()["valid"] is True
    assert post(client, "/api/fix-diagram", source=BAD_FLOWCHART, engine="mermaid", attempt=4).status_code == 422


def test_fix_endpoint_noop_on_valid_source_without_error(client, fake_llm):
    r = post(client, "/api/fix-diagram", source=GOOD_FLOWCHART, engine="mermaid")
    assert r.get_json()["changed"] is False and fake_llm.calls == []


def test_project_endpoint_saves_for_logged_in_user(client, fake_llm):
    from conftest import register
    register(client)
    fake_llm.analysis = analysis(recommended_diagram_types=["flowchart"])
    r = post(client, "/api/generate-project-diagrams", prompt="Bank", types=["flowchart", "decision_tree"], save=True)
    assert r.status_code == 200
    body = r.get_json()
    assert body["saved"] and len(body["results"]) == 2 and all(x["diagram_id"] for x in body["results"])
    listed = client.get(f"/api/projects/{body['project']['project_id']}").get_json()
    assert len(listed["diagrams"]) == 2


def test_project_endpoint_all_failed_is_502(client, fake_llm):
    fake_llm.generate = lambda p: LLMError("boom", status=502)
    r = post(client, "/api/generate-project-diagrams", prompt="x", types=["flowchart"])
    assert r.status_code == 502 and r.get_json()["results"][0]["ok"] is False
