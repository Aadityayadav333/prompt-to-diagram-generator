import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["MONGODB_URI"] = ""
os.environ.setdefault("FLASK_ENV", "development")

from app import create_app  # noqa: E402
from config import Config  # noqa: E402
from database import mongodb  # noqa: E402
from database.memory_store import MemoryDB  # noqa: E402
from services import llm_service  # noqa: E402
from services.rate_limiter import limiter  # noqa: E402

GOOD_FLOWCHART = 'flowchart TD\n  A(["Start"]) --> B["Validate input"]\n  B --> C{"Valid?"}\n  C -->|"yes"| D["Save"]\n  C -->|"no"| E["Show error"]\n  D --> F(["End"])\n  E --> F'
BAD_FLOWCHART = 'flowchart TD\n  A["Start"] --> B[Process (x)]\n  subgraph S["Group"]\n  B --> C["Done"]'
GOOD_ER = 'erDiagram\n  CUSTOMER ||--o{ ORDER : places\n  CUSTOMER {\n    string id PK\n    string email UK\n  }\n  ORDER {\n    string id PK\n    string customer_id FK\n  }'
GOOD_SEQ = 'sequenceDiagram\n  actor U as User\n  participant S as Server\n  U->>S: login\n  S-->>U: token'
GOOD_PUML = "@startuml\nactor User\nrectangle System {\n  usecase \"Login\" as UC1\n}\nUser --> UC1\n@enduml"


def analysis(**over):
    base = {
        "project_name": "Shop", "system_description": "An online shop.",
        "requested_diagram_type": None, "recommended_diagram_types": ["flowchart"],
        "actors": [{"name": "Customer", "description": ""}], "entities": [], "components": [],
        "database_tables": [], "relationships": [], "data_flows": [], "dependencies": [],
        "processes": [], "system_boundaries": [], "external_services": [], "assumptions": ["Generic web app"],
    }
    base.update(over)
    return base


class FakeLLM:
    """Routes calls by system prompt: analysis / generation / fix. Records every call."""

    def __init__(self):
        self.analysis = analysis()
        self.generate = lambda dtype_prompt: {"title": "T", "diagram_type": "flowchart", "explanation": "E",
                                              "source": GOOD_FLOWCHART, "assumptions": []}
        self.fixes = []  # queue of sources returned by fix calls
        self.calls = []

    def __call__(self, system, prompt, provider=None, temperature=0.2):
        if "business analyst" in system:
            kind = "analysis"
            out = self.analysis
        elif "repair broken diagram" in system:
            kind = "fix"
            out = {"source": self.fixes.pop(0) if self.fixes else GOOD_FLOWCHART, "changes": "x"}
        else:
            kind = "generate"
            out = self.generate(prompt)
        self.calls.append(kind)
        if isinstance(out, Exception):
            raise out
        return json.loads(json.dumps(out))


@pytest.fixture
def fake_llm(monkeypatch):
    fake = FakeLLM()
    monkeypatch.setattr(llm_service, "generate_json", fake)
    return fake


@pytest.fixture
def app():
    Config.MONGODB_URI = ""
    db = MemoryDB()
    mongodb._create_indexes(db)
    mongodb.reset_for_tests(db)
    limiter.reset()
    application = create_app({"TESTING": True})
    yield application
    mongodb.reset_for_tests(None)


@pytest.fixture
def client(app):
    c = app.test_client()
    c.environ_base["HTTP_X_REQUESTED_WITH"] = "DiagramForge"
    return c


def register(client, name="alice", email="alice@example.com", password="correct-horse-1"):
    return client.post("/api/auth/register", json={"username": name, "email": email, "password": password})
