"""Google Gemini adapter (REST, no SDK)."""
from config import Config

from .base import BaseProvider, LLMError


class GeminiProvider(BaseProvider):
    name = "gemini"
    ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    def __init__(self):
        super().__init__(
            Config.GEMINI_API_KEY, Config.GEMINI_MODEL, Config.LLM_TIMEOUT_SECONDS, Config.LLM_MAX_RETRIES
        )

    def _request(self, system: str, prompt: str, temperature: float) -> str:
        payload = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "responseMimeType": "application/json",  # structured JSON output
            },
        }
        # The key travels in a header, never in the URL, so it cannot leak into logs.
        headers = {"Content-Type": "application/json", "x-goog-api-key": self.api_key}
        data = self._post(self.ENDPOINT.format(model=self.model), headers, payload)
        try:
            candidate = data["candidates"][0]
            parts = candidate["content"]["parts"]
            return "".join(p.get("text", "") for p in parts)
        except (KeyError, IndexError, TypeError) as exc:
            reason = ""
            try:
                reason = data["promptFeedback"]["blockReason"]
            except Exception:  # noqa: BLE001
                pass
            raise LLMError(f"Gemini returned no usable content. {reason}".strip()) from exc
