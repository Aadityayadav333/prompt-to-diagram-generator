"""Shared helpers for route modules: auth guard, rate limiting, JSON validation, error mapping."""
from functools import wraps

from flask import g, jsonify, request, session

from config import Config
from database import DatabaseUnavailable
from providers import LLMError
from services.rate_limiter import limiter


def error(message: str, status: int = 400, **extra):
    return jsonify({"error": message, **extra}), status


def current_user_id():
    return session.get("user_id")


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        uid = current_user_id()
        if not uid:
            return error("Authentication required.", 401)
        g.user_id = uid
        return fn(*args, **kwargs)

    return wrapper


def rate_limit(bucket: str):
    limit = {
        "generate": Config.RATE_LIMIT_GENERATE,
        "project": Config.RATE_LIMIT_PROJECT,
        "auth": Config.RATE_LIMIT_AUTH,
    }.get(bucket, Config.RATE_LIMIT_DEFAULT)

    def deco(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            who = current_user_id() or request.remote_addr or "anon"
            ok, retry = limiter.check(f"{bucket}:{who}", limit)
            if not ok:
                resp = jsonify({"error": "Too many requests. Please slow down.", "retry_after": retry})
                resp.status_code = 429
                resp.headers["Retry-After"] = str(retry)
                return resp
            return fn(*args, **kwargs)

        return wrapper

    return deco


def json_body(required: dict | None = None, optional: dict | None = None):
    """Parse and validate a JSON object body. `required`/`optional` map field -> max length / type.

    Returns (data, None) or (None, error_response).
    """
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return None, error("Request body must be a JSON object.", 400)
    clean = {}
    for spec, must in ((required or {}, True), (optional or {}, False)):
        for name, typ in spec.items():
            val = data.get(name)
            if val is None or val == "":
                if must:
                    return None, error(f"'{name}' is required.", 400)
                continue
            if isinstance(typ, int):  # string with max length
                if not isinstance(val, str):
                    return None, error(f"'{name}' must be a string.", 400)
                if len(val) > typ:
                    return None, error(f"'{name}' is too long (max {typ} characters).", 413)
                clean[name] = val.strip()
            else:
                if not isinstance(val, typ):
                    return None, error(f"'{name}' has the wrong type.", 400)
                clean[name] = val
    return clean, None


def register_error_handlers(app):
    @app.errorhandler(LLMError)
    def _llm(exc):
        return error(str(exc), exc.status)

    @app.errorhandler(DatabaseUnavailable)
    def _db(exc):
        return error("The database is currently unavailable. Please try again later.", 503)

    @app.errorhandler(413)
    def _too_big(_):
        return error("Request body is too large.", 413)

    @app.errorhandler(404)
    def _nf(_):
        if request.path.startswith("/api/"):
            return error("Not found.", 404)
        return "Not found", 404

    @app.errorhandler(405)
    def _mna(_):
        return error("Method not allowed.", 405)

    @app.errorhandler(500)
    def _boom(_):
        return error("Internal server error.", 500)
