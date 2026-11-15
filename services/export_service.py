"""Server-side export helpers and the safe PlantUML rendering proxy.

PNG/SVG/PDF for the *visible canvas* are produced in the browser (static/js/export.js) so they match
exactly what the user sees. The server provides source downloads and, for PlantUML, SVG/PNG rendering
through a configurable PlantUML server (validated source only).
"""
import re
import string
import zlib

import requests

from config import Config

from .diagram_validator import validate

_SOURCE_EXT = {"mermaid": ("mmd", "text/plain"), "plantuml": ("puml", "text/plain"), "bpmn": ("bpmn", "application/xml")}

_PLANTUML_B64 = string.digits + string.ascii_uppercase + string.ascii_lowercase + "-_"
_STD_B64 = string.ascii_uppercase + string.ascii_lowercase + string.digits + "+/"
_TRANS = str.maketrans(_STD_B64, _PLANTUML_B64)


class ExportError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def safe_filename(title: str, ext: str) -> str:
    base = re.sub(r"[^A-Za-z0-9_-]+", "_", title or "diagram").strip("_")[:60] or "diagram"
    return f"{base}.{ext}"


def source_download(diagram: dict) -> tuple[bytes, str, str]:
    ext, mime = _SOURCE_EXT.get(diagram["diagram_engine"], ("txt", "text/plain"))
    return diagram["generated_source"].encode("utf-8"), mime, safe_filename(diagram["diagram_title"], ext)


def encode_plantuml(source: str) -> str:
    """PlantUML text encoding: raw deflate + its custom base64 alphabet."""
    import base64

    comp = zlib.compressobj(9, zlib.DEFLATED, -15)
    data = comp.compress(source.encode("utf-8")) + comp.flush()
    return base64.b64encode(data).decode("ascii").rstrip("=").translate(_TRANS)


_SCRIPT = re.compile(r"<script\b.*?</script\s*>", re.IGNORECASE | re.DOTALL)
_ON_ATTR = re.compile(r"""\son\w+\s*=\s*("[^"]*"|'[^']*'|[^\s>]+)""", re.IGNORECASE)
_JS_URL = re.compile(r"""(href|xlink:href)\s*=\s*("|')\s*javascript:[^"']*\2""", re.IGNORECASE)


def sanitize_svg(svg: str) -> str:
    """Defence-in-depth: strip scripts, inline handlers and javascript: links (client also uses DOMPurify)."""
    svg = _SCRIPT.sub("", svg)
    svg = _ON_ATTR.sub("", svg)
    svg = _JS_URL.sub(r'\1=\2#\2', svg)
    return svg


def render_plantuml(source: str, fmt: str = "svg") -> tuple[bytes, str]:
    """Render validated PlantUML via the configured server. Returns (bytes, mime)."""
    if fmt not in ("svg", "png"):
        raise ExportError("Format must be 'svg' or 'png'.")
    result = validate("plantuml", source)
    if not result.valid:
        raise ExportError("; ".join(result.errors[:3]), status=422)
    url = f"{Config.PLANTUML_SERVER}/{fmt}/{encode_plantuml(source)}"
    try:
        resp = requests.get(url, timeout=Config.PLANTUML_TIMEOUT_SECONDS)
    except requests.Timeout as exc:
        raise ExportError("PlantUML server timed out.", status=504) from exc
    except requests.RequestException as exc:
        raise ExportError("PlantUML server is unreachable.", status=502) from exc
    # The PlantUML server returns 400 with an SVG/PNG error image for syntax errors.
    if resp.status_code >= 500:
        raise ExportError("PlantUML server error.", status=502)
    if resp.status_code == 400:
        raise ExportError("PlantUML could not render this source (syntax error).", status=422)
    if resp.status_code != 200:
        raise ExportError(f"PlantUML server returned {resp.status_code}.", status=502)
    if fmt == "svg":
        text = resp.text
        if "<svg" not in text[:2000].lower() and "<svg" not in text.lower():
            raise ExportError("PlantUML server returned an unexpected response.", status=502)
        return sanitize_svg(text).encode("utf-8"), "image/svg+xml"
    return resp.content, "image/png"
