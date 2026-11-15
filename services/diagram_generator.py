"""Stage 2: generate diagram source from the analysis, validate it, and auto-fix (max 3 tries)."""
import logging
from concurrent.futures import ThreadPoolExecutor

from config import Config

from . import llm_service
from .diagram_types import DEFAULT_PROJECT_SET, DIAGRAM_TYPES, FALLBACK_TYPE, normalize_keys, valid_key
from .diagram_validator import strip_fences, validate
from .prompt_analyzer import analysis_for_prompt

log = logging.getLogger(__name__)

GEN_SYSTEM = """You are an expert at writing syntactically perfect diagram source code.
You convert a structured requirements analysis into ONE diagram.

Rules:
- Draw only what is supported by the analysis. No decorative or unnecessary components.
- Reuse the exact names from the analysis so a set of diagrams stays consistent.
- Clear labels on every relationship/flow; correct cardinality where the diagram type supports it.
- Choose a sensible layout direction and group related elements.
- Assumptions made by the analysis may be drawn but must not be presented as user-stated facts.
- Output ONLY the JSON object requested. The "source" must be raw diagram code with no markdown fences."""

GEN_SCHEMA = """Return ONE JSON object:
{
  "title": string (concise),
  "diagram_type": "<the key given below>",
  "explanation": string (1-3 sentences describing what the diagram shows),
  "source": string (complete raw diagram source),
  "assumptions": [string] (assumptions specific to this diagram, may be empty)
}"""

FIX_SYSTEM = """You repair broken diagram source code. Fix ONLY the reported problems, keep the meaning, names and structure.
Return ONE JSON object: {"source": string, "changes": string}. The source must be raw code with no markdown fences."""


class GenerationError(Exception):
    def __init__(self, message, status=422, draft=None, errors=None, attempts=0):
        super().__init__(message)
        self.status = status
        self.draft = draft
        self.errors = errors or []
        self.attempts = attempts


def choose_type(analysis: dict, requested: str | None = None) -> str:
    if valid_key(requested):
        return requested
    if valid_key(analysis.get("requested_diagram_type")):
        return analysis["requested_diagram_type"]
    recs = normalize_keys(analysis.get("recommended_diagram_types"))
    return recs[0] if recs else FALLBACK_TYPE


def _generation_prompt(analysis: dict, dtype: str) -> str:
    t = DIAGRAM_TYPES[dtype]
    return (
        f"Diagram type key: {dtype} ({t['label']})\nEngine: {t['engine']}\n"
        f"Guidance for this type: {t['hint']}\n\n{t['rules']}\n\n{GEN_SCHEMA}\n\n"
        f"Requirements analysis (JSON data):\n{analysis_for_prompt(analysis)}"
    )


def fix_source(engine: str, source: str, errors: list[str], provider: str | None = None, dtype: str | None = None) -> str:
    rules = DIAGRAM_TYPES[dtype]["rules"] if valid_key(dtype) else ""
    prompt = (
        f"Engine: {engine}\n{rules}\n\nProblems found:\n- " + "\n- ".join(errors[:10]) +
        f"\n\nBroken source:\n<<<\n{source}\n>>>"
    )
    raw = llm_service.generate_json(FIX_SYSTEM, prompt, provider=provider, temperature=0.0)
    fixed = strip_fences(str(raw.get("source", "")))
    if not fixed:
        raise GenerationError("The model returned an empty fix.", status=502)
    return fixed


def generate_diagram(analysis: dict, dtype: str, provider: str | None = None) -> dict:
    """Generate and validate one diagram. Raises GenerationError if it cannot be made valid."""
    t = DIAGRAM_TYPES[dtype]
    engine = t["engine"]
    raw = llm_service.generate_json(GEN_SYSTEM, _generation_prompt(analysis, dtype), provider=provider, temperature=0.2)
    source = strip_fences(str(raw.get("source", "")))
    result = validate(engine, source)

    attempts = 0
    status = "valid"
    while not result.valid and attempts < Config.MAX_FIX_ATTEMPTS:
        attempts += 1
        log.info("diagram %s invalid (%s); fix attempt %d", dtype, result.errors[:2], attempts)
        try:
            source = fix_source(engine, source, result.errors, provider, dtype)
        except GenerationError:
            raise
        result = validate(engine, source)
        status = "fixed"

    if not result.valid:
        raise GenerationError(
            "Could not produce valid diagram source after 3 correction attempts.",
            draft=source, errors=result.errors, attempts=attempts,
        )
    return {
        "title": str(raw.get("title") or t["label"])[:160],
        "diagram_type": dtype,
        "diagram_label": t["label"],
        "engine": engine,
        "explanation": str(raw.get("explanation") or "")[:600],
        "source": source,
        "assumptions": [str(a) for a in (raw.get("assumptions") or []) if a][:10],
        "validation_status": status,  # set by the server, not claimed by the model
        "fix_attempts": attempts,
        "warnings": result.warnings,
    }


def generate_project_set(analysis: dict, types: list[str] | None, provider: str | None = None) -> list[dict]:
    """Generate a coordinated set of diagrams from ONE shared analysis (keeps them consistent)."""
    keys = normalize_keys(types) or list(DEFAULT_PROJECT_SET)
    keys = keys[:12]

    def one(key):
        try:
            return {"ok": True, **generate_diagram(analysis, key, provider)}
        except GenerationError as exc:
            return {"ok": False, "diagram_type": key, "diagram_label": DIAGRAM_TYPES[key]["label"],
                    "error": str(exc), "errors": exc.errors, "draft_source": exc.draft}
        except Exception as exc:  # noqa: BLE001 - one failure must not sink the whole set
            return {"ok": False, "diagram_type": key, "diagram_label": DIAGRAM_TYPES[key]["label"],
                    "error": str(exc) or "Generation failed."}

    with ThreadPoolExecutor(max_workers=3) as pool:
        return list(pool.map(one, keys))
