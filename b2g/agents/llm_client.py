"""One OpenAI-compatible LLM client for every provider (Groq, OpenRouter, Cerebras, Ollama).

Every LLM call in the project goes through `LLMClient.complete`, which:
- sends the request to the provider chosen in `.env` (see `LLMSettings.from_env`),
- answers repeated requests from a disk cache, so re-running an experiment spends no tokens,
- retries rate limits (HTTP 429), provider overload (500/502/503) and network drops,
- logs every call (request, response, tokens, latency in s, cached yes/no) to
  `results/runs/<run_id>/llm_calls.jsonl`, one JSON object per line.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping

import requests

from b2g import REPO_ROOT

# OpenAI-compatible base URLs (the client appends /chat/completions)
PROVIDER_BASE_URLS = {
    "cerebras": "https://api.cerebras.ai/v1",  # the base paper's provider (default)
    "groq": "https://api.groq.com/openai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "ollama": "http://localhost:11434/v1",  # local server, no key needed
}
DEFAULT_PROVIDER = "cerebras"
DEFAULT_MODEL = "llama-3.1-8b"  # the original config.py default
CACHE_MODES = ("on", "off", "refresh")  # refresh = always ask the provider, then overwrite the cache
RETRYABLE_STATUS = {429, 500, 502, 503}


def load_env() -> None:
    """Load the repo's `.env` without overriding variables already set (e.g. by the CLI)."""
    from dotenv import load_dotenv

    load_dotenv(REPO_ROOT / ".env")


def _new_run_id() -> str:
    """Timestamped id for one run, e.g. 20261024_101530."""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


@dataclass(frozen=True)
class LLMSettings:
    """Where and how to reach the LLM. Build it with `from_env` unless testing."""

    provider: str
    base_url: str
    api_key: str | None
    model: str
    cache_mode: str = "on"
    run_id: str = field(default_factory=_new_run_id)
    results_dir: Path = REPO_ROOT / "results"
    max_retries: int = 6  # Groq free tier: ~7000 input tokens/min, one agent call ~3800
    max_wait_s: float = 60.0

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "LLMSettings":
        """
        Resolve settings from environment variables (call `load_env` first to read `.env`).

        Provider: LLM_PROVIDER (cerebras | groq | openrouter | ollama), default cerebras.
        Base URL: LLM_BASE_URL, else the provider's preset if LLM_PROVIDER is set,
                  else legacy M0 LLM_API_BASE + "/v1", else Cerebras.
        API key:  <PROVIDER>_API_KEY, else LLM_API_KEY (Ollama needs none).
        Model:    <PROVIDER>_MODEL, else LLM_MODEL, else CEREBRAS_MODEL, else llama-3.1-8b.
        Cache:    LLM_CACHE (on | off | refresh), default on. Run id: LLM_RUN_ID.
        """
        env = os.environ if env is None else env
        explicit_provider = env.get("LLM_PROVIDER", "").strip().lower()
        provider = explicit_provider or DEFAULT_PROVIDER

        if env.get("LLM_BASE_URL"):
            base_url = env["LLM_BASE_URL"]
        elif explicit_provider:
            if provider not in PROVIDER_BASE_URLS:
                raise ValueError(f"Unknown LLM_PROVIDER '{provider}'. Use one of {sorted(PROVIDER_BASE_URLS)} or set LLM_BASE_URL.")
            base_url = PROVIDER_BASE_URLS[provider]
        elif env.get("LLM_API_BASE"):
            base_url = env["LLM_API_BASE"].rstrip("/") + "/v1"
        else:
            base_url = PROVIDER_BASE_URLS[DEFAULT_PROVIDER]

        prefix = provider.upper()
        api_key = env.get(f"{prefix}_API_KEY") or env.get("LLM_API_KEY")
        if provider == "ollama" and not api_key:
            api_key = "ollama"
        model = env.get(f"{prefix}_MODEL") or env.get("LLM_MODEL") or env.get("CEREBRAS_MODEL") or DEFAULT_MODEL

        cache_mode = env.get("LLM_CACHE", "on").strip().lower()
        if cache_mode not in CACHE_MODES:
            raise ValueError(f"LLM_CACHE must be one of {CACHE_MODES}, got '{cache_mode}'")

        return cls(
            provider=provider,
            base_url=base_url.rstrip("/"),
            api_key=api_key,
            model=model,
            cache_mode=cache_mode,
            run_id=env.get("LLM_RUN_ID") or _new_run_id(),
        )

    @property
    def chat_url(self) -> str:
        """Full chat-completions endpoint."""
        return f"{self.base_url}/chat/completions"

    @property
    def cache_dir(self) -> Path:
        """One JSON file per cached response."""
        return self.results_dir / "cache"

    @property
    def calls_log(self) -> Path:
        """Per-run log of every LLM call (JSON lines)."""
        return self.results_dir / "runs" / self.run_id / "llm_calls.jsonl"


@dataclass
class LLMStats:
    """Counters for one client. Tokens count only calls that reached the provider (not cache hits)."""

    calls: int = 0
    api_calls: int = 0
    cache_hits: int = 0
    prompt_tokens_spent: int = 0
    completion_tokens_spent: int = 0
    latency_s: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        """Plain dict for JSON summaries."""
        return {**self.__dict__, "latency_s": round(self.latency_s, 2)}


def cache_key(base_url: str, payload: Mapping[str, Any]) -> str:
    """
    SHA-256 of the provider URL and the full request (model, messages, tools, temperature,
    max_tokens). Including the URL means a different provider is really asked, not replayed.
    """
    request = {k: v for k, v in payload.items() if k != "stream"}
    blob = json.dumps({"base_url": base_url, "request": request}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class LLMClient:
    """Sends chat-completion requests with caching, retries and per-call logging."""

    def __init__(self, settings: LLMSettings, sleep: Callable[[float], None] = time.sleep):
        self.settings = settings
        self.stats = LLMStats()
        self._sleep = sleep

    def complete(self, payload: dict[str, Any], timeout: float = 60, tag: str = "") -> dict[str, Any]:
        """
        Return the provider's JSON response for an OpenAI-style chat payload.

        `payload` is sent as given; "model" defaults to the settings' model and "temperature"
        to 0. `timeout` is per HTTP attempt in s. `tag` labels the call in the log
        (e.g. "orchestrator", "agent:dishwasher"). Raises requests.HTTPError when the
        provider refuses after all retries, like the original code expected.
        """
        payload = {"model": self.settings.model, "temperature": 0.0, **payload}
        key = cache_key(self.settings.base_url, payload)
        self.stats.calls += 1

        if self.settings.cache_mode == "on":
            cached = self._read_cache(key)
            if cached is not None:
                self.stats.cache_hits += 1
                self._log(tag, key, payload, cached, cached=True, latency_s=0.0, attempts=0)
                return cached

        start = time.perf_counter()
        try:
            response, attempts = self._post_with_retries(payload, timeout)
        except requests.exceptions.RequestException as e:
            self._log(tag, key, payload, None, cached=False, latency_s=time.perf_counter() - start,
                      attempts=self.settings.max_retries + 1, error=str(e))
            raise
        latency_s = time.perf_counter() - start

        if not response.ok:
            print(f"     ✗ LLM API error {response.status_code}: {response.text[:300]}")
            self._log(tag, key, payload, None, cached=False, latency_s=latency_s, attempts=attempts,
                      error=f"HTTP {response.status_code}: {response.text[:500]}")
            response.raise_for_status()

        result = response.json()
        usage = result.get("usage") or {}
        self.stats.api_calls += 1
        self.stats.prompt_tokens_spent += usage.get("prompt_tokens", 0) or 0
        self.stats.completion_tokens_spent += usage.get("completion_tokens", 0) or 0
        self.stats.latency_s += latency_s
        if self.settings.cache_mode != "off":
            self._write_cache(key, payload, result)
        self._log(tag, key, payload, result, cached=False, latency_s=latency_s, attempts=attempts)
        return result

    def _post_with_retries(self, payload: dict[str, Any], timeout: float) -> tuple[requests.Response, int]:
        """POST, retrying 429/5xx (Retry-After or 5, 10, 20 ... s, max `max_wait_s`) and network drops."""
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self.settings.api_key}"}
        max_retries = self.settings.max_retries
        for attempt in range(max_retries + 1):
            backoff_s = min(5 * 2 ** attempt, self.settings.max_wait_s)
            try:
                response = requests.post(self.settings.chat_url, headers=headers, json=payload, timeout=timeout)
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                if attempt == max_retries:
                    raise
                print(f"     ⏳ Network error ({type(e).__name__}) - retrying in {backoff_s:.0f}s ({attempt + 1}/{max_retries})")
                self._sleep(backoff_s)
                continue
            if response.status_code not in RETRYABLE_STATUS or attempt == max_retries:
                return response, attempt + 1
            wait_s = min(float(response.headers.get("retry-after", backoff_s)), self.settings.max_wait_s)
            reason = "Rate limited" if response.status_code == 429 else f"Provider unavailable ({response.status_code})"
            print(f"     ⏳ {reason} by LLM provider - retrying in {wait_s:.0f}s ({attempt + 1}/{max_retries})")
            self._sleep(wait_s)
        raise AssertionError("unreachable")

    def _read_cache(self, key: str) -> dict[str, Any] | None:
        """Cached response for `key`, or None."""
        path = self.settings.cache_dir / f"{key}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))["response"]

    def _write_cache(self, key: str, payload: Mapping[str, Any], response: Mapping[str, Any]) -> None:
        """Store a successful response (write to a temp file, then rename, so a crash never leaves half a file)."""
        self.settings.cache_dir.mkdir(parents=True, exist_ok=True)
        path = self.settings.cache_dir / f"{key}.json"
        tmp = path.with_suffix(".tmp")
        entry = {
            "created": datetime.now().isoformat(timespec="seconds"),
            "base_url": self.settings.base_url,
            "model": payload.get("model"),
            "response": response,
        }
        tmp.write_text(json.dumps(entry, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)

    def _log(self, tag: str, key: str, payload: Mapping[str, Any], response: Mapping[str, Any] | None, *,
             cached: bool, latency_s: float, attempts: int, error: str | None = None) -> None:
        """Append one call record to the run's llm_calls.jsonl (the API key is never written)."""
        usage = (response or {}).get("usage") or {}
        choices = (response or {}).get("choices") or [{}]
        record = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "tag": tag,
            "provider": self.settings.provider,
            "base_url": self.settings.base_url,
            "model": payload.get("model"),
            "cached": cached,
            "cache_key": key,
            "attempts": attempts,
            "latency_s": round(latency_s, 3),
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "total_tokens": usage.get("total_tokens"),
            "request": payload,
            "response_message": choices[0].get("message"),
            "error": error,
        }
        self.settings.calls_log.parent.mkdir(parents=True, exist_ok=True)
        with self.settings.calls_log.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


_client: LLMClient | None = None


def get_client() -> LLMClient:
    """The process-wide client, created from `.env` on first use (the CLI may install its own)."""
    global _client
    if _client is None:
        load_env()
        _client = LLMClient(LLMSettings.from_env())
    return _client


def set_client(client: LLMClient | None) -> None:
    """Install a client (CLI, tests); None resets to lazy creation from `.env`."""
    global _client
    _client = client


def confirm_budget(estimated_calls: int, limit: int = 500, assume_yes: bool = False,
                   input_fn: Callable[[str], str] = input) -> bool:
    """
    Print the estimated number of LLM calls for an experiment and, above `limit`, ask before
    spending them. Returns True to proceed. (Cached answers cost nothing, so this is an upper bound.)
    """
    print(f"Estimated LLM calls: {estimated_calls} (cached answers are free)")
    if estimated_calls <= limit or assume_yes:
        return True
    answer = input_fn(f"That is more than {limit} calls. Continue? [y/N] ")
    return answer.strip().lower() in {"y", "yes"}
