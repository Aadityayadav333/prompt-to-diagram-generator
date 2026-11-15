"""DiagramForge AI - Flask application factory."""
import logging

from flask import Flask, g, jsonify, redirect, render_template, request, session, url_for
from werkzeug.middleware.proxy_fix import ProxyFix

from config import Config
from database import db_mode
from routes import BLUEPRINTS
from routes.utils import current_user_id, error, register_error_handlers

CSP = (
    "default-src 'self'; "
    "script-src 'self' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://unpkg.com https://esm.sh; "
    "style-src 'self' 'unsafe-inline' https://unpkg.com https://fonts.googleapis.com; "
    "font-src 'self' data: https://fonts.gstatic.com https://unpkg.com; "
    "img-src 'self' data: blob:; "
    "connect-src 'self' https://esm.sh https://unpkg.com https://cdn.jsdelivr.net; "
    "object-src 'none'; base-uri 'self'; frame-ancestors 'self'; form-action 'self'"
)
CSRF_HEADER = "X-Requested-With"
CSRF_VALUE = "DiagramForge"


def create_app(config_overrides: dict | None = None) -> Flask:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    Config.ensure_secret_key()

    app = Flask(__name__)
    app.config.from_object(Config)
    if config_overrides:
        app.config.update(config_overrides)
    if Config.TRUST_PROXY:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    for bp in BLUEPRINTS:
        app.register_blueprint(bp)
    register_error_handlers(app)

    @app.before_request
    def csrf_guard():
        # Cookie-authenticated mutating API calls must carry a custom header. Browsers cannot add it
        # on cross-site requests without a CORS preflight (which this app never approves).
        if request.path.startswith("/api/") and request.method in ("POST", "PUT", "DELETE", "PATCH"):
            if request.headers.get(CSRF_HEADER) != CSRF_VALUE:
                return error("Missing or invalid request header.", 403)

    @app.after_request
    def security_headers(resp):
        resp.headers.setdefault("Content-Security-Policy", CSP)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        if request.path.startswith("/api/"):
            resp.headers.setdefault("Cache-Control", "no-store")
        return resp

    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok", "db_mode": db_mode(), "providers": Config.provider_status()})

    # ---- pages --------------------------------------------------------------------------
    def page(template, **ctx):
        return render_template(template, user_id=current_user_id(), **ctx)

    @app.get("/")
    def index():
        return page("index.html")

    @app.get("/dashboard")
    def dashboard():
        if not current_user_id():
            return redirect(url_for("login_page", next="/dashboard"))
        return page("dashboard.html")

    @app.get("/editor/<diagram_id>")
    def editor(diagram_id):
        if not current_user_id():
            return redirect(url_for("login_page", next=request.path))
        if not diagram_id.isalnum() or len(diagram_id) > 64:
            return "Not found", 404
        return page("editor.html", diagram_id=diagram_id)

    @app.get("/login")
    def login_page():
        return page("login.html", next_url=_safe_next(request.args.get("next")))

    @app.get("/register")
    def register_page():
        return page("register.html", next_url=_safe_next(request.args.get("next")))

    return app


def _safe_next(target):
    """Only allow same-site relative redirects (prevents open-redirect)."""
    if target and target.startswith("/") and not target.startswith("//") and "\\" not in target:
        return target
    return "/"


app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=Config.DEBUG)
