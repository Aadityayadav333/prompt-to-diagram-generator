"""Provider selection and robust JSON extraction on top of the adapters."""
import json
import re

from config import Config
from providers import PROVIDERS, BaseProvider, LLMError

_FENCE = re.compile(r"^```[a-zA-Z0-9_-]*\s*|\s*```$", re.MULTILINE)


def get_provider(name: str | None = None) -> BaseProvider:
    key = (name or Config.DEFAULT_PROVIDER or "gemini").lower()
    if key not in PROVIDERS:
        raise LLMError(f"Unknown provider '{key}'. Choose one of: {', '.join(PROVIDERS)}.", status=400)
    return PROVIDERS[key]()


def extract_json(text: str) -> dict:
    """Parse a JSON object from model output, tolerating code fences and stray prose."""
    if not text or not text.strip():
        raise ValueError("empty response")
    cleaned = _FENCE.sub("", text.strip()).strip()
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end <= start:
            raise ValueError("no JSON object found")
        value = json.loads(cleaned[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("top-level JSON value is not an object")
    return value


def generate_json(system: str, prompt: str, provider: str | None = None, temperature: float = 0.2) -> dict:
    """Ask the model for JSON. If the reply is unparseable, retry once with a stricter nudge."""
    llm = get_provider(provider)
    raw = llm.generate_json_text(system, prompt, temperature)
    try:
        return extract_json(raw)
    except (ValueError, json.JSONDecodeError):
        nudge = prompt + "\n\nYour previous reply was not valid JSON. Return ONLY one valid JSON object."
        raw = llm.generate_json_text(system, nudge, 0.0)
        try:
            return extract_json(raw)
        except (ValueError, json.JSONDecodeError) as exc:
            raise LLMError("The model did not return valid JSON.", status=502) from exc
