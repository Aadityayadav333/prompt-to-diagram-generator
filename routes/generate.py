"""AI endpoints: analysis, single-diagram generation, project documentation, validation and fixing."""
from flask import Blueprint, jsonify

from config import Config
from database import repository as repo
from providers import LLMError
from services import diagram_generator as gen
from services.diagram_types import DIAGRAM_TYPES, detect_type_hint, public_catalog, valid_key
from services.diagram_validator import strip_fences, validate
from services.prompt_analyzer import analyze_prompt, normalize_analysis

from .utils import current_user_id, error, json_body, rate_limit

bp = Blueprint("generate", __name__, url_prefix="/api")

PROMPT_MAX = Config.MAX_PROMPT_CHARS


@bp.get("/diagram-types")
def diagram_types():
    return jsonify({"types": public_catalog()})


@bp.get("/providers")
def providers():
    return jsonify({"default": Config.DEFAULT_PROVIDER, "configured": Config.provider_status()})


@bp.post("/detect-type")
@rate_limit("default")
def detect_type():
    data, err = json_body(required={"prompt": PROMPT_MAX})
    if err:
        return err
    return jsonify({"suggestions": detect_type_hint(data["prompt"])})


@bp.post("/analyze-prompt")
@rate_limit("generate")
def analyze():
    data, err = json_body(required={"prompt": PROMPT_MAX}, optional={"provider": 20, "diagram_type": 64})
    if err:
        return err
    if data.get("diagram_type") and not valid_key(data["diagram_type"]):
        return error("Unknown diagram_type.", 400)
    analysis = analyze_prompt(data["prompt"], data.get("provider"), data.get("diagram_type"))
    return jsonify({"analysis": analysis})


def _persist(user_id, diagram: dict, prompt: str, project_id=None):
    return repo.create_diagram(
        user_id,
        {
            "diagram_title": diagram["title"],
            "diagram_type": diagram["diagram_type"],
            "original_prompt": prompt,
            "generated_source": diagram["source"],
            "diagram_engine": diagram["engine"],
            "assumptions": diagram["assumptions"],
            "explanation": diagram["explanation"],
        },
        project_id,
    )


@bp.post("/generate-diagram")
@rate_limit("generate")
def generate_diagram():
    data, err = json_body(
        required={"prompt": PROMPT_MAX},
        optional={"provider": 20, "diagram_type": 64, "analysis": dict, "save": bool, "project_id": 64},
    )
    if err:
        return err
    if data.get("diagram_type") and not valid_key(data["diagram_type"]):
        return error("Unknown diagram_type.", 400)

    # Stage 1 - analysis (skipped when the client already ran /api/analyze-prompt and sends it back,
    # which lets the UI show the detected type and assumptions before generation starts)
    if data.get("analysis"):
        analysis = normalize_analysis(data["analysis"], data.get("diagram_type"))
    else:
        analysis = analyze_prompt(data["prompt"], data.get("provider"), data.get("diagram_type"))
    dtype = gen.choose_type(analysis, data.get("diagram_type"))

    # Stage 2 - generation + validation + bounded auto-fix
    try:
        diagram = gen.generate_diagram(analysis, dtype, data.get("provider"))
    except gen.GenerationError as exc:
        return error(str(exc), exc.status, validation_errors=exc.errors, draft_source=exc.draft,
                     fix_attempts=exc.attempts, analysis=analysis)

    body = {"diagram": diagram, "analysis": analysis, "saved": False}
    if data.get("save"):
        uid = current_user_id()
        if not uid:
            body["save_error"] = "Log in to save diagrams."
        else:
            pid = data.get("project_id")
            if pid and not repo.get_project(pid, uid):
                return error("Project not found.", 404)
            saved = _persist(uid, diagram, data["prompt"], pid)
            body.update(saved=True, diagram_id=saved["diagram_id"])
    return jsonify(body)


@bp.post("/generate-project-diagrams")
@rate_limit("project")
def generate_project_diagrams():
    data, err = json_body(
        required={"prompt": PROMPT_MAX}, optional={"provider": 20, "types": list, "save": bool}
    )
    if err:
        return err
    types = data.get("types") or []
    if len(types) > 12 or any(not valid_key(t) for t in types):
        return error("'types' must be at most 12 valid diagram type keys.", 400)

    analysis = analyze_prompt(data["prompt"], data.get("provider"))
    results = gen.generate_project_set(analysis, types, data.get("provider"))
    ok = [r for r in results if r.get("ok")]
    if not ok:
        return error("No diagrams could be generated.", 502, results=results, analysis=analysis)

    body = {"analysis": analysis, "results": results, "saved": False}
    if data.get("save"):
        uid = current_user_id()
        if not uid:
            body["save_error"] = "Log in to save projects."
        else:
            project = repo.create_project(uid, analysis["project_name"], analysis["system_description"])
            for r in ok:
                saved = _persist(uid, r, data["prompt"], project["project_id"])
                r["diagram_id"] = saved["diagram_id"]
            body.update(saved=True, project=project)
    return jsonify(body)


@bp.post("/validate-diagram")
@rate_limit("default")
def validate_diagram():
    data, err = json_body(
        required={"source": Config.MAX_SOURCE_CHARS * 2, "engine": 20}, optional={"diagram_type": 64}
    )
    if err:
        return err
    if data["engine"] not in ("mermaid", "plantuml", "bpmn"):
        return error("engine must be mermaid, plantuml or bpmn.", 400)
    return jsonify(validate(data["engine"], strip_fences(data["source"])).to_dict())


@bp.post("/fix-diagram")
@rate_limit("generate")
def fix_diagram():
    """Repair source that failed validation or failed to render in the browser (max 3 attempts)."""
    data, err = json_body(
        required={"source": Config.MAX_SOURCE_CHARS * 2, "engine": 20},
        optional={"error": 2000, "attempt": int, "provider": 20, "diagram_type": 64},
    )
    if err:
        return err
    if data["engine"] not in ("mermaid", "plantuml", "bpmn"):
        return error("engine must be mermaid, plantuml or bpmn.", 400)
    attempt = data.get("attempt", 1)
    if not isinstance(attempt, int) or attempt < 1 or attempt > Config.MAX_FIX_ATTEMPTS:
        return error(f"Automatic fixing is limited to {Config.MAX_FIX_ATTEMPTS} attempts.", 422)

    source = strip_fences(data["source"])
    problems = list(validate(data["engine"], source).errors)
    if data.get("error"):
        problems.append(f"Renderer error: {data['error']}")
    if not problems:
        return jsonify({"source": source, "valid": True, "changed": False, "errors": []})

    dtype = data.get("diagram_type") if valid_key(data.get("diagram_type")) else None
    try:
        fixed = gen.fix_source(data["engine"], source, problems, data.get("provider"), dtype)
    except gen.GenerationError as exc:
        return error(str(exc), exc.status)
    result = validate(data["engine"], fixed)
    return jsonify({"source": fixed, "valid": result.valid, "changed": fixed != source,
                    "errors": result.errors, "attempt": attempt})
