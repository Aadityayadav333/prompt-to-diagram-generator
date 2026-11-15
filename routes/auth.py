"""Registration, login and session endpoints. Passwords are hashed (scrypt via Werkzeug)."""
import re

from flask import Blueprint, jsonify, session
from werkzeug.security import check_password_hash, generate_password_hash

from database import repository as repo

from .utils import current_user_id, error, json_body, rate_limit

bp = Blueprint("auth", __name__, url_prefix="/api/auth")

USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}\.[^@\s]{2,}$")
# Constant-time-ish dummy hash so unknown emails cost the same as wrong passwords.
_DUMMY_HASH = generate_password_hash("not-a-real-password")


def _public(user: dict) -> dict:
    return {"user_id": user["user_id"], "username": user["username"], "email": user["email"]}


@bp.post("/register")
@rate_limit("auth")
def register():
    data, err = json_body(required={"username": 64, "email": 320, "password": 256})
    if err:
        return err
    if not USERNAME_RE.match(data["username"]):
        return error("Username must be 3-32 characters: letters, numbers, . _ -", 400)
    if not EMAIL_RE.match(data["email"]):
        return error("Enter a valid email address.", 400)
    pw = data["password"]
    if len(pw) < 8:
        return error("Password must be at least 8 characters.", 400)
    try:
        user = repo.create_user(data["username"], data["email"], generate_password_hash(pw))
    except repo.DuplicateError:
        return error("That username or email is already registered.", 409)
    session.clear()
    session["user_id"] = user["user_id"]
    session.permanent = True
    return jsonify({"user": _public(user)}), 201


@bp.post("/login")
@rate_limit("auth")
def login():
    data, err = json_body(required={"email": 320, "password": 256})
    if err:
        return err
    user = repo.get_user_by_email(data["email"])
    ok = check_password_hash(user["password_hash"] if user else _DUMMY_HASH, data["password"])
    if not (user and ok):
        return error("Invalid email or password.", 401)
    session.clear()
    session["user_id"] = user["user_id"]
    session.permanent = True
    return jsonify({"user": _public(user)})


@bp.post("/logout")
def logout():
    session.clear()
    return jsonify({"ok": True})


@bp.get("/me")
def me():
    uid = current_user_id()
    if not uid:
        return jsonify({"user": None})
    user = repo.get_user(uid)
    if not user:
        session.clear()
        return jsonify({"user": None})
    return jsonify({"user": _public(user)})
