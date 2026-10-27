"""Tests for b2g.agents.llm_client: settings, cache, retries, logging, budget guard. No network."""

import json

import pytest
import requests

from b2g.agents import llm_client
from b2g.agents.llm_client import LLMClient, LLMSettings, cache_key, confirm_budget

PAYLOAD = {"model": "test-model", "messages": [{"role": "user", "content": "Hi"}], "max_tokens": 5}


def make_response(status: int, body: dict | None = None, headers: dict | None = None) -> requests.Response:
    """A real requests.Response with the given status, JSON body and headers."""
    response = requests.Response()
    response.status_code = status
    response._content = json.dumps(body or {}).encode()
    response.headers.update(headers or {})
    response.url = "https://fake.provider/v1/chat/completions"
    return response


def ok_body(text: str = "OK", prompt_tokens: int = 10, completion_tokens: int = 2) -> dict:
    """OpenAI-style successful completion."""
    return {
        "choices": [{"message": {"role": "assistant", "content": text}}],
        "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
                  "total_tokens": prompt_tokens + completion_tokens},
    }


class FakeProvider:
    """Replaces requests.post: returns queued responses (or raises queued exceptions) and records calls."""

    def __init__(self, *responses):
        self.queue = list(responses)
        self.calls = []

    def __call__(self, url, headers=None, json=None, timeout=None):
        self.calls.append({"url": url, "headers": headers, "json": json})
        item = self.queue.pop(0) if len(self.queue) > 1 else self.queue[0]
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture
def settings(tmp_path):
    return LLMSettings(provider="groq", base_url="https://fake.provider/v1", api_key="secret-key",
                       model="test-model", run_id="test_run", results_dir=tmp_path)


def make_client(settings, monkeypatch, *responses, cache_mode="on"):
    """Client whose HTTP calls go to a FakeProvider and whose sleeps are recorded, not waited."""
    from dataclasses import replace

    fake = FakeProvider(*responses)
    monkeypatch.setattr(llm_client.requests, "post", fake)
    sleeps = []
    client = LLMClient(replace(settings, cache_mode=cache_mode), sleep=sleeps.append)
    return client, fake, sleeps


# --- settings -------------------------------------------------------------------------------

def test_settings_default_is_cerebras():
    s = LLMSettings.from_env({"CEREBRAS_API_KEY": "k"})
    assert (s.provider, s.base_url, s.api_key, s.model) == ("cerebras", "https://api.cerebras.ai/v1", "k", "llama-3.1-8b")


def test_settings_provider_preset_with_own_key_and_model():
    env = {"LLM_PROVIDER": "groq", "GROQ_API_KEY": "g", "GROQ_MODEL": "qwen/qwen3.8-27b",
           "OPENROUTER_API_KEY": "o"}
    s = LLMSettings.from_env(env)
    assert (s.base_url, s.api_key, s.model) == ("https://api.groq.com/openai/v1", "g", "qwen/qwen3.8-27b")
    assert s.chat_url == "https://api.groq.com/openai/v1/chat/completions"


def test_settings_switching_provider_picks_that_providers_key():
    env = {"LLM_PROVIDER": "openrouter", "GROQ_API_KEY": "g", "OPENROUTER_API_KEY": "o"}
    assert LLMSettings.from_env(env).api_key == "o"


def test_settings_legacy_m0_names_still_work():
    env = {"LLM_API_BASE": "https://api.groq.com/openai", "LLM_API_KEY": "k", "CEREBRAS_MODEL": "m"}
    s = LLMSettings.from_env(env)
    assert (s.base_url, s.api_key, s.model) == ("https://api.groq.com/openai/v1", "k", "m")


def test_settings_explicit_base_url_wins():
    s = LLMSettings.from_env({"LLM_PROVIDER": "groq", "LLM_BASE_URL": "http://my.server/v1/"})
    assert s.base_url == "http://my.server/v1"


def test_settings_ollama_needs_no_key():
    s = LLMSettings.from_env({"LLM_PROVIDER": "ollama"})
    assert s.base_url == "http://localhost:11434/v1" and s.api_key == "ollama"


def test_settings_rejects_unknown_provider_and_cache_mode():
    with pytest.raises(ValueError):
        LLMSettings.from_env({"LLM_PROVIDER": "nope"})
    with pytest.raises(ValueError):
        LLMSettings.from_env({"LLM_CACHE": "sometimes"})


# --- cache ----------------------------------------------------------------------------------

def test_cache_hit_makes_no_second_http_call(settings, monkeypatch):
    client, fake, _ = make_client(settings, monkeypatch, make_response(200, ok_body("cached answer")))
    first = client.complete(dict(PAYLOAD))
    second = client.complete(dict(PAYLOAD))
    assert len(fake.calls) == 1
    assert first == second
    assert (client.stats.calls, client.stats.api_calls, client.stats.cache_hits) == (2, 1, 1)
    assert client.stats.prompt_tokens_spent == 10  # cache hits spend nothing


def test_cache_key_changes_with_model_messages_and_provider():
    base = cache_key("https://a/v1", PAYLOAD)
    assert base == cache_key("https://a/v1", dict(PAYLOAD))
    assert base != cache_key("https://a/v1", {**PAYLOAD, "model": "other"})
    assert base != cache_key("https://a/v1", {**PAYLOAD, "messages": [{"role": "user", "content": "Bye"}]})
    assert base != cache_key("https://b/v1", PAYLOAD)


def test_cache_off_always_asks_provider(settings, monkeypatch):
    client, fake, _ = make_client(settings, monkeypatch, make_response(200, ok_body()), cache_mode="off")
    client.complete(dict(PAYLOAD))
    client.complete(dict(PAYLOAD))
    assert len(fake.calls) == 2
    assert not settings.cache_dir.exists()


def test_cache_refresh_asks_provider_and_overwrites(settings, monkeypatch):
    client, _, _ = make_client(settings, monkeypatch, make_response(200, ok_body("old")))
    client.complete(dict(PAYLOAD))
    client, fake, _ = make_client(settings, monkeypatch, make_response(200, ok_body("new")), cache_mode="refresh")
    client.complete(dict(PAYLOAD))
    assert len(fake.calls) == 1
    client, fake, _ = make_client(settings, monkeypatch, make_response(200, ok_body("unused")))
    assert client.complete(dict(PAYLOAD))["choices"][0]["message"]["content"] == "new"
    assert len(fake.calls) == 0


def test_failed_call_is_not_cached(settings, monkeypatch):
    client, _, _ = make_client(settings, monkeypatch, make_response(401, {"error": "bad key"}))
    with pytest.raises(requests.HTTPError):
        client.complete(dict(PAYLOAD))
    assert not settings.cache_dir.exists()


# --- retries --------------------------------------------------------------------------------

def test_retries_rate_limit_and_overload_then_succeeds(settings, monkeypatch):
    client, fake, sleeps = make_client(
        settings, monkeypatch,
        make_response(429, {"error": "rate"}, {"retry-after": "1"}),
        make_response(503, {"error": "over capacity"}),
        make_response(200, ok_body()),
    )
    assert client.complete(dict(PAYLOAD))["choices"][0]["message"]["content"] == "OK"
    assert len(fake.calls) == 3
    assert sleeps == [1.0, 10]  # Retry-After header, then backoff 5 * 2**1 s


def test_retries_network_error(settings, monkeypatch):
    client, fake, sleeps = make_client(settings, monkeypatch,
                                       requests.exceptions.ConnectionError("wifi dropped"),
                                       make_response(200, ok_body()))
    client.complete(dict(PAYLOAD))
    assert len(fake.calls) == 2 and sleeps == [5]


def test_gives_up_after_max_retries(settings, monkeypatch):
    client, fake, sleeps = make_client(settings, monkeypatch, make_response(429, {"error": "rate"}))
    with pytest.raises(requests.HTTPError):
        client.complete(dict(PAYLOAD))
    assert len(fake.calls) == settings.max_retries + 1
    assert max(sleeps) <= settings.max_wait_s


def test_non_retryable_error_fails_immediately(settings, monkeypatch):
    client, fake, sleeps = make_client(settings, monkeypatch, make_response(401, {"error": "bad key"}))
    with pytest.raises(requests.HTTPError) as exc:
        client.complete(dict(PAYLOAD))
    assert exc.value.response.status_code == 401  # the original orchestrator reads e.response
    assert len(fake.calls) == 1 and sleeps == []


# --- request defaults and logging -----------------------------------------------------------

def test_request_uses_settings_url_key_and_defaults(settings, monkeypatch):
    client, fake, _ = make_client(settings, monkeypatch, make_response(200, ok_body()))
    client.complete({"messages": PAYLOAD["messages"]})
    sent = fake.calls[0]
    assert sent["url"] == "https://fake.provider/v1/chat/completions"
    assert sent["headers"]["Authorization"] == "Bearer secret-key"
    assert sent["json"]["model"] == "test-model" and sent["json"]["temperature"] == 0.0


def test_every_call_is_logged_without_the_api_key(settings, monkeypatch):
    client, _, _ = make_client(settings, monkeypatch, make_response(200, ok_body("hello", 7, 3)))
    client.complete(dict(PAYLOAD), tag="orchestrator")
    client.complete(dict(PAYLOAD), tag="orchestrator")
    log_text = settings.calls_log.read_text(encoding="utf-8")
    records = [json.loads(line) for line in log_text.splitlines()]
    assert [r["cached"] for r in records] == [False, True]
    first = records[0]
    assert first["tag"] == "orchestrator" and first["model"] == "test-model"
    assert (first["prompt_tokens"], first["completion_tokens"], first["total_tokens"]) == (7, 3, 10)
    assert first["latency_s"] >= 0 and first["response_message"]["content"] == "hello"
    assert first["request"]["messages"] == PAYLOAD["messages"]
    assert "secret-key" not in log_text


# --- budget guard ---------------------------------------------------------------------------

def test_budget_under_limit_does_not_ask():
    def never_called(prompt):
        raise AssertionError("should not ask")
    assert confirm_budget(120, input_fn=never_called)


@pytest.mark.parametrize("answer, expected", [("y", True), ("yes", True), ("n", False), ("", False)])
def test_budget_over_limit_asks(answer, expected):
    assert confirm_budget(501, input_fn=lambda prompt: answer) is expected


def test_budget_assume_yes_skips_question():
    assert confirm_budget(10_000, assume_yes=True, input_fn=lambda prompt: "n")
