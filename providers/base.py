"""Provider interface shared by the Gemini and Groq adapters."""
import time
from abc import ABC, abstractmethod

import requests


class LLMError(Exception):
    """Raised when an LLM call fails. `status` maps to an HTTP status for the API."""

    def __init__(self, message: str, status: int = 502, retryable: bool = False):
        super().__init__(message)
        self.status = status
        self.retryable = retryable


class ProviderNotConfigured(LLMError):
    def __init__(self, message: str):
        super().__init__(message, status=503)


class BaseProvider(ABC):
    name = "base"

    def __init__(self, api_key: str, model: str, timeout: int = 60, max_retries: int = 2):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries

    @abstractmethod
    def _request(self, system: str, prompt: str, temperature: float) -> str:
        """Perform one call and return the raw JSON text produced by the model."""

    def generate_json_text(self, system: str, prompt: str, temperature: float = 0.2) -> str:
        """Call the model, retrying transient failures (429/5xx/timeouts) with backoff."""
        if not self.api_key:
            raise ProviderNotConfigured(f"{self.name} is not configured (API key missing).")
        last: LLMError | None = None
        for attempt in range(self.max_retries + 1):
            try:
                return self._request(system, prompt, temperature)
            except LLMError as exc:
                last = exc
                if not exc.retryable or attempt == self.max_retries:
                    raise
                time.sleep(min(2 ** attempt, 8))
        raise last or LLMError("Unknown LLM failure")  # pragma: no cover

    # Shared HTTP helper so adapters stay tiny and error handling is uniform.
    def _post(self, url: str, headers: dict, payload: dict) -> dict:
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
        except requests.Timeout as exc:
            raise LLMError(f"{self.name} request timed out.", status=504, retryable=True) from exc
        except requests.RequestException as exc:
            raise LLMError(f"{self.name} network error: {exc.__class__.__name__}", retryable=True) from exc

        if resp.status_code == 429:
            raise LLMError(f"{self.name} rate limit reached. Try again shortly.", status=429, retryable=True)
        if resp.status_code >= 500:
            raise LLMError(f"{self.name} service error ({resp.status_code}).", retryable=True)
        if resp.status_code in (401, 403):
            raise LLMError(f"{self.name} rejected the API key.", status=502)
        if resp.status_code >= 400:
            detail = ""
            try:
                detail = resp.json().get("error", {}).get("message", "")[:200]
            except Exception:  # noqa: BLE001
                pass
            raise LLMError(f"{self.name} request failed ({resp.status_code}). {detail}".strip())
        try:
            return resp.json()
        except ValueError as exc:
            raise LLMError(f"{self.name} returned a non-JSON HTTP body.") from exc
