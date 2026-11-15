"""Project CRUD. Every query is scoped to the logged-in user."""
from flask import Blueprint, g, jsonify, request

from database import repository as repo

from .utils import error, json_body, login_required, rate_limit

bp = Blueprint("projects", __name__, url_prefix="/api/projects")


@bp.get("")
@login_required
def list_projects():
    projects = repo.list_projects(g.user_id)
    return jsonify({"projects": projects})


@bp.post("")
@login_required
@rate_limit("default")
def create_project():
    data, err = json_body(required={"project_name": 120}, optional={"project_description": 2000})
    if err:
        return err
    project = repo.create_project(g.user_id, data["project_name"], data.get("project_description", ""))
    return jsonify({"project": project}), 201


@bp.get("/<project_id>")
@login_required
def get_project(project_id):
    project = repo.get_project(project_id, g.user_id)
    if not project:
        return error("Project not found.", 404)
    diagrams = repo.list_diagrams(g.user_id, project_id=project_id, limit=100)
    return jsonify({"project": project, "diagrams": diagrams})


@bp.put("/<project_id>")
@login_required
def update_project(project_id):
    data, err = json_body(optional={"project_name": 120, "project_description": 2000})
    if err:
        return err
    if not data:
        return error("Nothing to update.", 400)
    if not repo.update_project(project_id, g.user_id, data):
        return error("Project not found.", 404)
    return jsonify({"project": repo.get_project(project_id, g.user_id)})


@bp.delete("/<project_id>")
@login_required
def delete_project(project_id):
    if not repo.delete_project(project_id, g.user_id):
        return error("Project not found.", 404)
    return jsonify({"ok": True})
