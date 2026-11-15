"""Groq adapter (OpenAI-compatible chat completions API, no SDK)."""
from config import Config

from .base import BaseProvider, LLMError


class GroqProvider(BaseProvider):
    name = "groq"
    ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"

    def __init__(self):
        super().__init__(Config.GROQ_API_KEY, Config.GROQ_MODEL, Config.LLM_TIMEOUT_SECONDS, Config.LLM_MAX_RETRIES)

    def _request(self, system: str, prompt: str, temperature: float) -> str:
        payload = {
            "model": self.model,
            "temperature": temperature,
            "response_format": {"type": "json_object"},  # JSON mode
            "messages": [
                # JSON mode requires the word "JSON" to appear in the messages.
                {"role": "system", "content": system + "\nRespond with a single valid JSON object only."},
                {"role": "user", "content": prompt},
            ],
        }
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"}
        data = self._post(self.ENDPOINT, headers, payload)
        try:
            return data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("Groq returned no usable content.") from exc
