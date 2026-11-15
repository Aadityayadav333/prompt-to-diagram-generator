"""Data-access functions. Every user-owned query is filtered by user_id."""
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

from .memory_store import MemoryDuplicateKey
from .mongodb import DatabaseUnavailable, get_db

NO_ID = {"_id": 0}


class DuplicateError(Exception):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return uuid.uuid4().hex


@contextmanager
def _translate():
    """Map driver-specific exceptions to our own so routes stay driver-agnostic."""
    try:
        yield
    except MemoryDuplicateKey as exc:
        raise DuplicateError(str(exc)) from exc
    except DatabaseUnavailable:
        raise
    except Exception as exc:  # noqa: BLE001
        name = exc.__class__.__name__
        if name == "DuplicateKeyError":
            raise DuplicateError("duplicate") from exc
        if exc.__class__.__module__.startswith("pymongo"):
            raise DatabaseUnavailable("Database operation failed.") from exc
        raise


# ---- users -----------------------------------------------------------------
def create_user(username: str, email: str, password_hash: str) -> dict:
    doc = {
        "user_id": _new_id(),
        "username": username,
        "username_lower": username.lower(),
        "email": email.lower(),
        "password_hash": password_hash,
        "created_at": _now(),
    }
    with _translate():
        get_db()["users"].insert_one(dict(doc))
    return doc


def get_user_by_email(email: str):
    with _translate():
        return get_db()["users"].find_one({"email": email.lower()}, NO_ID)


def get_user(user_id: str):
    with _translate():
        return get_db()["users"].find_one({"user_id": user_id}, NO_ID)


# ---- projects --------------------------------------------------------------
def create_project(user_id: str, name: str, description: str = "") -> dict:
    now = _now()
    doc = {
        "project_id": _new_id(),
        "user_id": user_id,
        "project_name": name,
        "project_description": description,
        "created_at": now,
        "updated_at": now,
    }
    with _translate():
        get_db()["projects"].insert_one(dict(doc))
    return doc


def list_projects(user_id: str) -> list[dict]:
    with _translate():
        return list(get_db()["projects"].find({"user_id": user_id}, NO_ID).sort("updated_at", -1))


def get_project(project_id: str, user_id: str):
    with _translate():
        return get_db()["projects"].find_one({"project_id": project_id, "user_id": user_id}, NO_ID)


def update_project(project_id: str, user_id: str, fields: dict) -> bool:
    fields = {**fields, "updated_at": _now()}
    with _translate():
        return _update("projects", {"project_id": project_id, "user_id": user_id}, fields)


def _update(collection: str, flt: dict, fields: dict) -> bool:
    res = get_db()[collection].update_one(flt, {"$set": fields})
    # PyMongo returns UpdateResult; the memory store returns an int.
    matched = getattr(res, "matched_count", res)
    return bool(matched)


def delete_project(project_id: str, user_id: str) -> bool:
    with _translate():
        db = get_db()
        if not db["projects"].find_one({"project_id": project_id, "user_id": user_id}, NO_ID):
            return False
        for d in db["diagrams"].find({"project_id": project_id, "user_id": user_id}, NO_ID):
            db["diagram_history"].delete_many({"diagram_id": d["diagram_id"]})
        db["diagrams"].delete_many({"project_id": project_id, "user_id": user_id})
        db["projects"].delete_one({"project_id": project_id, "user_id": user_id})
        return True


# ---- diagrams --------------------------------------------------------------
def create_diagram(user_id: str, data: dict, project_id: str | None = None) -> dict:
    now = _now()
    doc = {
        "diagram_id": _new_id(),
        "project_id": project_id,
        "user_id": user_id,
        "diagram_title": data["diagram_title"],
        "diagram_type": data["diagram_type"],
        "original_prompt": data.get("original_prompt", ""),
        "generated_source": data["generated_source"],
        "diagram_engine": data["diagram_engine"],
        "assumptions": data.get("assumptions", []),
        "explanation": data.get("explanation", ""),
        "created_at": now,
        "updated_at": now,
        "version": 1,
    }
    with _translate():
        db = get_db()
        db["diagrams"].insert_one(dict(doc))
        db["diagram_history"].insert_one(
            {
                "history_id": _new_id(),
                "diagram_id": doc["diagram_id"],
                "source_code": doc["generated_source"],
                "version_number": 1,
                "timestamp": now,
            }
        )
    if project_id:
        with _translate():
            _update("projects", {"project_id": project_id, "user_id": user_id}, {"updated_at": now})
    return doc


def get_diagram(diagram_id: str, user_id: str):
    with _translate():
        return get_db()["diagrams"].find_one({"diagram_id": diagram_id, "user_id": user_id}, NO_ID)


def list_diagrams(user_id: str, project_id: str | None = None, limit: int = 50) -> list[dict]:
    flt = {"user_id": user_id}
    if project_id:
        flt["project_id"] = project_id
    with _translate():
        return list(get_db()["diagrams"].find(flt, NO_ID).sort("updated_at", -1).limit(limit))


def update_diagram(diagram_id: str, user_id: str, fields: dict):
    """Update a diagram. When the source changes, snapshot it into history and bump the version."""
    with _translate():
        db = get_db()
        current = db["diagrams"].find_one({"diagram_id": diagram_id, "user_id": user_id}, NO_ID)
        if not current:
            return None
        now = _now()
        changes = {k: v for k, v in fields.items() if v is not None}
        changes["updated_at"] = now
        new_source = changes.get("generated_source")
        if new_source is not None and new_source != current["generated_source"]:
            changes["version"] = current["version"] + 1
            db["diagram_history"].insert_one(
                {
                    "history_id": _new_id(),
                    "diagram_id": diagram_id,
                    "source_code": new_source,
                    "version_number": changes["version"],
                    "timestamp": now,
                }
            )
        _update("diagrams", {"diagram_id": diagram_id, "user_id": user_id}, changes)
        return {**current, **changes}


def delete_diagram(diagram_id: str, user_id: str) -> bool:
    with _translate():
        db = get_db()
        if not db["diagrams"].find_one({"diagram_id": diagram_id, "user_id": user_id}, NO_ID):
            return False
        db["diagram_history"].delete_many({"diagram_id": diagram_id})
        db["diagrams"].delete_one({"diagram_id": diagram_id, "user_id": user_id})
        return True


def list_history(diagram_id: str, user_id: str):
    """Return history for a diagram the user owns, newest first (None if not owned)."""
    if not get_diagram(diagram_id, user_id):
        return None
    with _translate():
        return list(get_db()["diagram_history"].find({"diagram_id": diagram_id}, NO_ID).sort("version_number", -1))
