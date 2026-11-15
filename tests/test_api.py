import json

import pytest

from conftest import GOOD_ER, GOOD_FLOWCHART, GOOD_PUML, register
from config import Config
from database import DatabaseUnavailable, mongodb
from services import export_service as exp
from services.rate_limiter import limiter


def saved_diagram(client, source=GOOD_FLOWCHART, dtype="flowchart"):
    r = client.post("/api/diagrams", json={"diagram_title": "My Flow", "diagram_type": dtype,
                                           "generated_source": source, "original_prompt": "p"})
    assert r.status_code == 201, r.get_json()
    return r.get_json()["diagram"]


# ---- security basics -----------------------------------------------------------------------------
def test_health_never_exposes_secrets(client):
    body = client.get("/api/health").get_json()
    assert set(body["providers"]) == {"gemini", "groq"} and all(isinstance(v, bool) for v in body["providers"].values())
    assert body["db_mode"] in ("memory", "test", "unconfigured", "mongodb")


def test_csrf_header_required_for_mutations(app):
    c = app.test_client()  # no header
    assert c.post("/api/auth/login", json={"email": "a@b.co", "password": "x"}).status_code == 403
    assert c.get("/api/health").status_code == 200


def test_security_headers_present(client):
    h = client.get("/api/health").headers
    assert "default-src 'self'" in h["Content-Security-Policy"] and h["X-Content-Type-Options"] == "nosniff"


def test_request_size_limit(app, client):
    app.config["MAX_CONTENT_LENGTH"] = 1000
    r = client.post("/api/validate-diagram", json={"source": "x" * 5000, "engine": "mermaid"})
    assert r.status_code == 413


def test_rate_limit_returns_429_with_retry_after(client):
    for _ in range(Config.RATE_LIMIT_AUTH):
        client.post("/api/auth/login", json={"email": "no@one.co", "password": "wrong-password"})
    r = client.post("/api/auth/login", json={"email": "no@one.co", "password": "wrong-password"})
    assert r.status_code == 429 and int(r.headers["Retry-After"]) >= 1


# ---- auth ----------------------------------------------------------------------------------------
def test_register_login_logout_and_password_is_hashed(client):
    assert register(client).status_code == 201
    stored = mongodb.get_db()["users"].find_one({"email": "alice@example.com"})
    assert stored["password_hash"] != "correct-horse-1" and "correct-horse-1" not in json.dumps(stored)
    assert client.get("/api/auth/me").get_json()["user"]["username"] == "alice"
    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").get_json()["user"] is None
    assert client.post("/api/auth/login", json={"email": "ALICE@example.com", "password": "correct-horse-1"}).status_code == 200
    limiter.reset()
    assert client.post("/api/auth/login", json={"email": "alice@example.com", "password": "nope-nope"}).status_code == 401


@pytest.mark.parametrize("payload", [
    {"username": "a", "email": "a@b.co", "password": "longenough1"},
    {"username": "valid_name", "email": "not-an-email", "password": "longenough1"},
    {"username": "valid_name", "email": "a@b.co", "password": "short"},
])
def test_register_validation(client, payload):
    assert client.post("/api/auth/register", json=payload).status_code == 400


def test_duplicate_registration_conflicts(client):
    register(client)
    assert register(client, name="alice2").status_code == 409
    assert register(client, email="other@example.com").status_code == 409


# ---- ownership / CRUD / history ------------------------------------------------------------------
def test_private_resources_require_login_and_are_isolated(app, client):
    assert client.get("/api/projects").status_code == 401
    assert client.get("/api/diagrams/abc").status_code == 401
    register(client)
    d = saved_diagram(client)
    other = app.test_client()
    other.environ_base["HTTP_X_REQUESTED_WITH"] = "DiagramForge"
    register(other, name="bob", email="bob@example.com")
    assert other.get(f"/api/diagrams/{d['diagram_id']}").status_code == 404
    assert other.put(f"/api/diagrams/{d['diagram_id']}", json={"diagram_title": "hax"}).status_code == 404
    assert other.delete(f"/api/diagrams/{d['diagram_id']}").status_code == 404
    assert other.get(f"/api/diagrams/{d['diagram_id']}/export").status_code == 404
    assert other.get(f"/api/diagrams/{d['diagram_id']}/history").status_code == 404
    assert other.get("/api/diagrams").get_json()["diagrams"] == []
    assert client.get(f"/api/diagrams/{d['diagram_id']}").status_code == 200


def test_update_creates_history_versions_and_restore(client):
    register(client)
    d = saved_diagram(client)
    v2 = GOOD_FLOWCHART + '\n  F --> G["Extra"]'
    r = client.put(f"/api/diagrams/{d['diagram_id']}", json={"generated_source": v2})
    assert r.status_code == 200 and r.get_json()["diagram"]["version"] == 2
    # title-only change does not create a version
    r = client.put(f"/api/diagrams/{d['diagram_id']}", json={"diagram_title": "Renamed"})
    assert r.get_json()["diagram"]["version"] == 2
    hist = client.get(f"/api/diagrams/{d['diagram_id']}/history").get_json()["history"]
    assert [h["version_number"] for h in hist] == [2, 1]
    r = client.post(f"/api/diagrams/{d['diagram_id']}/restore", json={"version_number": 1})
    assert r.get_json()["diagram"]["generated_source"] == GOOD_FLOWCHART and r.get_json()["diagram"]["version"] == 3


def test_invalid_source_rejected_on_save_and_update(client):
    register(client)
    r = client.post("/api/diagrams", json={"diagram_title": "x", "diagram_type": "flowchart", "generated_source": "garbage"})
    assert r.status_code == 422 and r.get_json()["validation_errors"]
    d = saved_diagram(client)
    assert client.put(f"/api/diagrams/{d['diagram_id']}", json={"generated_source": "garbage"}).status_code == 422


def test_delete_project_cascades(client):
    register(client)
    p = client.post("/api/projects", json={"project_name": "P"}).get_json()["project"]
    r = client.post("/api/diagrams", json={"diagram_title": "d", "diagram_type": "flowchart",
                                           "generated_source": GOOD_FLOWCHART, "project_id": p["project_id"]})
    did = r.get_json()["diagram"]["diagram_id"]
    assert client.delete(f"/api/projects/{p['project_id']}").status_code == 200
    assert client.get(f"/api/diagrams/{did}").status_code == 404
    assert client.get(f"/api/projects/{p['project_id']}").status_code == 404


# ---- database failure ----------------------------------------------------------------------------
def test_database_failure_returns_503(client, monkeypatch):
    def boom():
        raise DatabaseUnavailable("down")

    monkeypatch.setattr(mongodb, "get_db", boom)
    monkeypatch.setattr("database.repository.get_db", boom)
    r = client.post("/api/auth/register", json={"username": "carol", "email": "c@example.com", "password": "longenough1"})
    assert r.status_code == 503 and "unavailable" in r.get_json()["error"]
    assert client.get("/api/health").status_code == 200  # app stays up


def test_no_database_configured_in_production_mode(monkeypatch):
    mongodb.reset_for_tests(None)
    monkeypatch.setattr(Config, "MONGODB_URI", "")
    monkeypatch.setattr(Config, "ALLOW_MEMORY_DB", False)
    with pytest.raises(DatabaseUnavailable):
        mongodb.get_db()


# ---- export --------------------------------------------------------------------------------------
def test_source_export_per_engine(client):
    register(client)
    d = saved_diagram(client)
    r = client.get(f"/api/diagrams/{d['diagram_id']}/export")
    assert r.status_code == 200 and r.data.decode() == GOOD_FLOWCHART
    assert 'filename="My_Flow.mmd"' in r.headers["Content-Disposition"]
    p = saved_diagram(client, GOOD_PUML, "use_case")
    r = client.get(f"/api/diagrams/{p['diagram_id']}/export")
    assert 'filename="My_Flow.puml"' in r.headers["Content-Disposition"]
    assert client.get(f"/api/diagrams/{d['diagram_id']}/export?format=svg").status_code == 400  # mermaid: client-side
    assert client.get(f"/api/diagrams/{d['diagram_id']}/export?format=exe").status_code == 400
    assert client.get(f"/api/diagrams/{d['diagram_id']}/export?format=json").get_json()["diagram_id"] == d["diagram_id"]


def test_plantuml_encoding_round_trips():
    """Decode with the PlantUML alphabet + raw inflate and compare with the input."""
    import base64
    import zlib

    src = "@startuml\nAlice -> Bob: héllo\n@enduml"
    enc = exp.encode_plantuml(src)
    assert set(enc) <= set(exp._PLANTUML_B64)
    std = enc.translate(str.maketrans(exp._PLANTUML_B64, exp._STD_B64))
    std += "=" * (-len(std) % 4)
    assert zlib.decompress(base64.b64decode(std), -15).decode("utf-8") == src
    assert enc.startswith("SoWkIImgAStDuN")  # well-known prefix of "@startuml\nAlice -> Bob"


class _Resp:
    def __init__(self, status=200, text="<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script><rect onclick='x()'/></svg>"):
        self.status_code, self.text, self.content = status, text, text.encode()


def test_plantuml_render_proxy_sanitizes_and_maps_errors(client, monkeypatch):
    monkeypatch.setattr(exp.requests, "get", lambda *a, **k: _Resp())
    r = client.post("/api/render-plantuml", json={"source": GOOD_PUML})
    assert r.status_code == 200 and r.mimetype == "image/svg+xml"
    assert b"<script" not in r.data and b"onclick" not in r.data
    monkeypatch.setattr(exp.requests, "get", lambda *a, **k: _Resp(400, "syntax"))
    assert client.post("/api/render-plantuml", json={"source": GOOD_PUML}).status_code == 422
    monkeypatch.setattr(exp.requests, "get", lambda *a, **k: _Resp(503, ""))
    assert client.post("/api/render-plantuml", json={"source": GOOD_PUML}).status_code == 502

    def timeout(*a, **k):
        raise exp.requests.Timeout()

    monkeypatch.setattr(exp.requests, "get", timeout)
    assert client.post("/api/render-plantuml", json={"source": GOOD_PUML}).status_code == 504


def test_plantuml_render_refuses_unsafe_source_without_network(client, monkeypatch):
    def no_network(*a, **k):
        raise AssertionError("must not call the PlantUML server for unsafe source")

    monkeypatch.setattr(exp.requests, "get", no_network)
    r = client.post("/api/render-plantuml", json={"source": "@startuml\n!include /etc/passwd\nA->B\n@enduml"})
    assert r.status_code == 422


# ---- pages ---------------------------------------------------------------------------------------
def test_open_redirect_is_blocked(client):
    from app import _safe_next
    assert _safe_next("//evil.example") == "/" and _safe_next("https://evil.example") == "/"
    assert _safe_next("/dashboard") == "/dashboard"
