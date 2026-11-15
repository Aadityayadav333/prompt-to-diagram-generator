"""Source downloads and the PlantUML rendering proxy."""
import json

from flask import Blueprint, Response, g, request

from database import repository as repo
from services import export_service as exp

from .utils import error, json_body, login_required, rate_limit

bp = Blueprint("export", __name__, url_prefix="/api")


@bp.post("/render-plantuml")
@rate_limit("default")
def render_plantuml():
    """Render validated PlantUML to SVG/PNG. Works for guests; the source is validated first."""
    data, err = json_body(required={"source": 60000}, optional={"format": 10})
    if err:
        return err
    try:
        payload, mime = exp.render_plantuml(data["source"], data.get("format", "svg"))
    except exp.ExportError as exc:
        return error(str(exc), exc.status)
    return Response(payload, mimetype=mime, headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


@bp.get("/diagrams/<diagram_id>/export")
@login_required
def export_diagram(diagram_id):
    """?format=source (default) | json | svg | png. svg/png are only available server-side for PlantUML;
    for Mermaid and BPMN, vector/raster/PDF export is produced in the browser to match the canvas."""
    d = repo.get_diagram(diagram_id, g.user_id)
    if not d:
        return error("Diagram not found.", 404)
    fmt = request.args.get("format", "source").lower()

    if fmt == "source":
        body, mime, name = exp.source_download(d)
    elif fmt == "json":
        body = json.dumps(d, indent=2).encode("utf-8")
        mime, name = "application/json", exp.safe_filename(d["diagram_title"], "json")
    elif fmt in ("svg", "png"):
        if d["diagram_engine"] != "plantuml":
            return error("Server-side SVG/PNG is only available for PlantUML. Use the in-app export for this diagram.", 400)
        try:
            body, mime = exp.render_plantuml(d["generated_source"], fmt)
        except exp.ExportError as exc:
            return error(str(exc), exc.status)
        name = exp.safe_filename(d["diagram_title"], fmt)
    else:
        return error("format must be source, json, svg or png.", 400)

    return Response(body, mimetype=mime, headers={
        "Content-Disposition": f'attachment; filename="{name}"',
        "X-Content-Type-Options": "nosniff",
    })
