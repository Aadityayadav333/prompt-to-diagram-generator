"""Central configuration. Every secret comes from environment variables."""
import logging
import os
import secrets

try:  # python-dotenv is optional at runtime (Render injects real env vars)
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass

log = logging.getLogger(__name__)


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


class Config:
    ENV = os.environ.get("FLASK_ENV", os.environ.get("APP_ENV", "development")).lower()
    IS_PRODUCTION = ENV == "production"
    DEBUG = _bool("FLASK_DEBUG", False) and not IS_PRODUCTION

    # --- Sessions / security -------------------------------------------------
    SECRET_KEY = os.environ.get("SECRET_KEY") or ""
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = IS_PRODUCTION
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 24 * 14  # 14 days
    MAX_CONTENT_LENGTH = _int("MAX_CONTENT_BYTES", 512 * 1024)
    TRUST_PROXY = _bool("TRUST_PROXY", IS_PRODUCTION)  # Render sits behind a proxy

    # --- Input limits --------------------------------------------------------
    MAX_PROMPT_CHARS = _int("MAX_PROMPT_CHARS", 8000)
    MAX_SOURCE_CHARS = _int("MAX_SOURCE_CHARS", 60000)
    MAX_FIX_ATTEMPTS = 3

    # --- Rate limits (requests per minute, per user or IP, per worker) -------
    RATE_LIMIT_GENERATE = _int("RATE_LIMIT_GENERATE", 10)
    RATE_LIMIT_PROJECT = _int("RATE_LIMIT_PROJECT", 3)
    RATE_LIMIT_AUTH = _int("RATE_LIMIT_AUTH", 10)
    RATE_LIMIT_DEFAULT = _int("RATE_LIMIT_DEFAULT", 120)

    # --- LLM providers -------------------------------------------------------
    DEFAULT_PROVIDER = os.environ.get("LLM_PROVIDER", "gemini").lower()
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
    GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
    GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
    LLM_TIMEOUT_SECONDS = _int("LLM_TIMEOUT_SECONDS", 60)
    LLM_MAX_RETRIES = _int("LLM_MAX_RETRIES", 2)

    # --- MongoDB -------------------------------------------------------------
    MONGODB_URI = os.environ.get("MONGODB_URI", "")
    MONGODB_DB_NAME = os.environ.get("MONGODB_DB_NAME", "diagramforge")
    MONGODB_TIMEOUT_MS = _int("MONGODB_TIMEOUT_MS", 5000)
    # In-memory store is for local development only; never on by default in prod.
    ALLOW_MEMORY_DB = _bool("ALLOW_MEMORY_DB", not IS_PRODUCTION)

    # --- PlantUML ------------------------------------------------------------
    # Diagram text is sent to this server. Self-host it for private diagrams:
    #   docker run -d -p 8080:8080 plantuml/plantuml-server:jetty
    PLANTUML_SERVER = os.environ.get("PLANTUML_SERVER", "https://www.plantuml.com/plantuml").rstrip("/")
    PLANTUML_TIMEOUT_SECONDS = _int("PLANTUML_TIMEOUT_SECONDS", 20)

    @classmethod
    def ensure_secret_key(cls) -> None:
        if cls.SECRET_KEY:
            return
        if cls.IS_PRODUCTION:
            raise RuntimeError("SECRET_KEY must be set in production.")
        cls.SECRET_KEY = secrets.token_hex(32)
        log.warning("SECRET_KEY not set: using a random key (sessions reset on restart).")

    @classmethod
    def provider_status(cls) -> dict:
        return {"gemini": bool(cls.GEMINI_API_KEY), "groq": bool(cls.GROQ_API_KEY)}
