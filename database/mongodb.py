"""MongoDB Atlas connection (PyMongo), created lazily so the app boots even if Atlas is down."""
import logging
import threading

from config import Config

from .memory_store import MemoryDB

log = logging.getLogger(__name__)

_lock = threading.Lock()
_db = None
_mode = "unconfigured"


class DatabaseUnavailable(Exception):
    """The database cannot be reached or is not configured."""


def _create_indexes(db) -> None:
    db["users"].create_index("email", unique=True)
    db["users"].create_index("username_lower", unique=True)
    db["projects"].create_index("project_id", unique=True)
    db["projects"].create_index("user_id")
    db["diagrams"].create_index("diagram_id", unique=True)
    db["diagrams"].create_index("user_id")
    db["diagrams"].create_index("project_id")
    db["diagram_history"].create_index("diagram_id")


def get_db():
    global _db, _mode
    if _db is not None:
        return _db
    with _lock:
        if _db is not None:
            return _db
        if Config.MONGODB_URI:
            try:
                from pymongo import MongoClient
                from pymongo.errors import PyMongoError
            except ImportError as exc:
                raise DatabaseUnavailable("pymongo is not installed (pip install -r requirements.txt).") from exc
            try:
                client = MongoClient(Config.MONGODB_URI, serverSelectionTimeoutMS=Config.MONGODB_TIMEOUT_MS)
                client.admin.command("ping")
                db = client[Config.MONGODB_DB_NAME]
                _create_indexes(db)
            except PyMongoError as exc:
                raise DatabaseUnavailable("Could not connect to MongoDB.") from exc  # no URI in message
            _db, _mode = db, "mongodb"
        elif Config.ALLOW_MEMORY_DB:
            log.warning("MONGODB_URI not set: using the in-memory dev database. Data is NOT persisted.")
            db = MemoryDB()
            _create_indexes(db)
            _db, _mode = db, "memory"
        else:
            raise DatabaseUnavailable("MONGODB_URI is not configured.")
        return _db


def db_mode() -> str:
    return _mode


def reset_for_tests(db=None) -> None:
    """Swap the active database (used by the test-suite)."""
    global _db, _mode
    _db = db
    _mode = "test" if db is not None else "unconfigured"
