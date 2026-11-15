"""Diagram CRUD, version history and restore. Ownership is enforced in every repository call."""
from flask import Blueprint, g, jsonify, request

from config import Config
from database import repository as repo
from services.diagram_types import DIAGRAM_TYPES, valid_key
from services.diagram_validator import strip_fences, validate

from .utils import error, json_body, login_required, rate_limit

bp = Blueprint("diagrams", __name__, url_prefix="/api/diagrams")


@bp.get("")
@login_required
def list_diagrams():
    project_id = request.args.get("project_id")
    try:
        limit = max(1, min(int(request.args.get("limit", 50)), 100))
    except ValueError:
        return error("limit must be an integer.", 400)
    return jsonify({"diagrams": repo.list_diagrams(g.user_id, project_id, limit)})


@bp.post("")
@login_required
@rate_limit("default")
def create_diagram():
    """Save a diagram the client already holds (e.g. a guest result after logging in)."""
    data, err = json_body(
        required={"diagram_title": 160, "diagram_type": 64, "generated_source": Config.MAX_SOURCE_CHARS},
        optional={"original_prompt": Config.MAX_PROMPT_CHARS, "project_id": 64, "assumptions": list, "explanation": 600},
    )
    if err:
        return err
    if not valid_key(data["diagram_type"]):
        return error("Unknown diagram_type.", 400)
    engine = DIAGRAM_TYPES[data["diagram_type"]]["engine"]
    source = strip_fences(data["generated_source"])
    result = validate(engine, source)
    if not result.valid:
        return error("Source is not valid.", 422, validation_errors=result.errors)
    pid = data.get("project_id")
    if pid and not repo.get_project(pid, g.user_id):
        return error("Project not found.", 404)
    data = {**data, "generated_source": source, "diagram_engine": engine,
            "assumptions": [str(a)[:300] for a in data.get("assumptions", [])][:10]}
    return jsonify({"diagram": repo.create_diagram(g.user_id, data, pid)}), 201


@bp.get("/<diagram_id>")
@login_required
def get_diagram(diagram_id):
    d = repo.get_diagram(diagram_id, g.user_id)
    if not d:
        return error("Diagram not found.", 404)
    return jsonify({"diagram": d})


@bp.put("/<diagram_id>")
@login_required
@rate_limit("default")
def update_diagram(diagram_id):
    data, err = json_body(optional={"diagram_title": 160, "generated_source": Config.MAX_SOURCE_CHARS})
    if err:
        return err
    if not data:
        return error("Nothing to update.", 400)
    current = repo.get_diagram(diagram_id, g.user_id)
    if not current:
        return error("Diagram not found.", 404)
    if "generated_source" in data:
        data["generated_source"] = strip_fences(data["generated_source"])
        result = validate(current["diagram_engine"], data["generated_source"])
        if not result.valid:
            return error("Source is not valid.", 422, validation_errors=result.errors)
    return jsonify({"diagram": repo.update_diagram(diagram_id, g.user_id, data)})


@bp.delete("/<diagram_id>")
@login_required
def delete_diagram(diagram_id):
    if not repo.delete_diagram(diagram_id, g.user_id):
        return error("Diagram not found.", 404)
    return jsonify({"ok": True})


@bp.get("/<diagram_id>/history")
@login_required
def history(diagram_id):
    items = repo.list_history(diagram_id, g.user_id)
    if items is None:
        return error("Diagram not found.", 404)
    return jsonify({"history": items})


@bp.post("/<diagram_id>/restore")
@login_required
def restore(diagram_id):
    data, err = json_body(required={"version_number": int})
    if err:
        return err
    items = repo.list_history(diagram_id, g.user_id)
    if items is None:
        return error("Diagram not found.", 404)
    target = next((h for h in items if h["version_number"] == data["version_number"]), None)
    if not target:
        return error("Version not found.", 404)
    return jsonify({"diagram": repo.update_diagram(diagram_id, g.user_id, {"generated_source": target["source_code"]})})
