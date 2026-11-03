"""Settings: admin gate, encrypted key, validation, and demo-mode precedence."""

from __future__ import annotations

import json
import os

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from madira.admin_auth import UNSET_MESSAGE, issue_admin_token, verify_admin_token
from madira.crypto import decrypt_secret, encrypt_secret
from madira.db import SessionLocal, init_db
from madira.llm_runtime import read_stored, resolve_runtime
from madira.llm_validate import set_key_validator, validate_provider_key, validate_provider_key_live
from madira.main import _agent_slot, app, refresh_sommelier_agent
from madira.models import LlmCredential

PASSWORD = "floor-secret"
API_KEY = "sk-settings-unique-key-abcd"
ENV_KEYS = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GOOGLE_API_KEY",
    "MADIRA_API_KEY",
)


def _wipe() -> None:
    init_db()
    session = SessionLocal()
    try:
        row = session.get(LlmCredential, 1)
        if row is not None:
            session.delete(row)
            session.commit()
    finally:
        session.close()


@pytest.fixture(scope="module")
def client():
    tracked = (
        "MADIRA_ADMIN_PASSWORD",
        "MADIRA_SECRET_KEY",
        "MADIRA_LLM_VALIDATOR",
        "MADIRA_DEMO_MODE",
        "MADIRA_LLM_PROVIDER",
        "MADIRA_LLM_MODEL",
        *ENV_KEYS,
    )
    previous = {name: os.environ.get(name) for name in tracked}
    os.environ["MADIRA_ADMIN_PASSWORD"] = PASSWORD
    os.environ["MADIRA_SECRET_KEY"] = Fernet.generate_key().decode()
    os.environ.pop("MADIRA_LLM_VALIDATOR", None)
    os.environ.pop("MADIRA_DEMO_MODE", None)
    os.environ["MADIRA_LLM_PROVIDER"] = "openai"
    os.environ["MADIRA_LLM_MODEL"] = "gpt-4.1-mini"
    for name in ENV_KEYS:
        os.environ[name] = ""
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    monkeypatch.setenv("MADIRA_ADMIN_PASSWORD", PASSWORD)
    monkeypatch.setenv("MADIRA_SECRET_KEY", Fernet.generate_key().decode())
    monkeypatch.delenv("MADIRA_LLM_VALIDATOR", raising=False)
    monkeypatch.delenv("MADIRA_DEMO_MODE", raising=False)
    monkeypatch.setenv("MADIRA_LLM_PROVIDER", "openai")
    monkeypatch.setenv("MADIRA_LLM_MODEL", "gpt-4.1-mini")
    for name in ENV_KEYS:
        monkeypatch.setenv(name, "")
    set_key_validator(lambda provider, api_key, model="": None)
    _wipe()
    yield
    set_key_validator(None)
    _wipe()


def _auth(token: str | None = None) -> dict[str, str]:
    return {"X-Madira-Admin-Token": token or issue_admin_token()}


def _save(client: TestClient, *, provider: str = "openai", model: str = "", api_key: str = API_KEY, token: str | None = None):
    return client.post(
        "/settings/llm",
        headers=_auth(token),
        json={"provider": provider, "model": model, "api_key": api_key},
    )


def test_settings_require_a_token(client: TestClient):
    assert client.get("/settings/llm").status_code == 401
    assert client.post("/settings/llm", json={"provider": "openai", "api_key": API_KEY}).status_code == 401
    assert client.delete("/settings/llm").status_code == 401
    denied = client.get("/settings/llm", headers={"X-Madira-Admin-Token": "not-a-token"})
    assert denied.status_code == 401
    assert API_KEY not in denied.text


def test_wrong_password_is_rejected_without_echoing_it(client: TestClient):
    secret = "not-the-floor-password"
    response = client.post("/settings/session", json={"password": secret})
    assert response.status_code == 401
    assert "Incorrect admin password" in response.json()["detail"]
    assert secret not in response.text


def test_missing_admin_password_refuses_settings(client: TestClient, monkeypatch):
    monkeypatch.delenv("MADIRA_ADMIN_PASSWORD", raising=False)
    for method, kwargs in (
        ("get", {}),
        ("post", {"json": {"provider": "openai", "api_key": API_KEY}}),
        ("delete", {}),
    ):
        response = getattr(client, method)("/settings/llm", **kwargs)
        assert response.status_code == 403
        assert response.json()["detail"] == UNSET_MESSAGE
    session = client.post("/settings/session", json={"password": PASSWORD})
    assert session.status_code == 403
    assert session.json()["detail"] == UNSET_MESSAGE


def test_session_token_expires_and_dies_when_the_password_changes(monkeypatch):
    token = issue_admin_token(ttl_seconds=-5)
    assert verify_admin_token(token) is False
    fresh = issue_admin_token()
    assert verify_admin_token(fresh) is True
    monkeypatch.setenv("MADIRA_ADMIN_PASSWORD", "a-different-password")
    assert verify_admin_token(fresh) is False


def test_save_validates_stores_ciphertext_and_hides_the_key(client: TestClient, monkeypatch):
    seen: list[tuple[str, str, str]] = []

    def record(provider: str, api_key: str, model: str = "") -> None:
        seen.append((provider, api_key, model))

    set_key_validator(record)
    calls: list[str] = []
    monkeypatch.setattr("madira.main.refresh_sommelier_agent", lambda: calls.append("refresh"))

    response = _save(client, provider="Anthropic", model="claude-haiku-4-5-20251001")
    assert response.status_code == 200
    body = response.json()
    assert body["configured"] is True
    assert body["provider"] == "anthropic"
    assert body["model"] == "claude-haiku-4-5-20251001"
    assert body["key_hint"] == "abcd"
    assert body["demo_mode"] is False
    assert body["source"] == "settings"
    assert "api_key" not in body
    assert "ciphertext" not in body
    assert API_KEY not in response.text
    assert seen == [("anthropic", API_KEY, "claude-haiku-4-5-20251001")]
    assert calls == ["refresh"]

    stored = read_stored()
    assert stored is not None
    assert stored.ciphertext != API_KEY
    assert API_KEY not in stored.ciphertext
    assert decrypt_secret(stored.ciphertext) == API_KEY

    listed = client.get("/settings/llm", headers=_auth())
    assert listed.status_code == 200
    assert API_KEY not in listed.text
    assert listed.json()["key_hint"] == "abcd"

    public = client.get("/status")
    assert public.json()["demo_mode"] is False
    assert public.json()["llm_source"] == "settings"
    assert public.json()["llm_provider"] == "anthropic"
    assert API_KEY not in public.text
    assert "abcd" not in public.text


def test_rejected_key_is_not_stored(client: TestClient, monkeypatch):
    def reject(provider: str, api_key: str, model: str = "") -> None:
        raise ValueError(f"OpenAI rejected the API key (401). bad {api_key}")

    set_key_validator(reject)
    calls: list[str] = []
    monkeypatch.setattr("madira.main.refresh_sommelier_agent", lambda: calls.append("refresh"))
    response = _save(client)
    assert response.status_code == 400
    assert "rejected" in response.json()["detail"]
    assert API_KEY not in response.text
    assert calls == []
    assert read_stored() is None
    assert client.get("/status").json()["demo_mode"] is True


def test_failed_rebuild_rolls_back_the_new_key(client: TestClient, monkeypatch):
    def boom():
        raise RuntimeError("rebuild failed")

    monkeypatch.setattr("madira.main.refresh_sommelier_agent", boom)
    response = _save(client)
    assert response.status_code == 500
    assert "rebuild failed" in response.json()["detail"]
    assert API_KEY not in response.text
    assert read_stored() is None
    assert resolve_runtime().demo_mode is True


def test_delete_falls_back_to_demo(client: TestClient, monkeypatch):
    monkeypatch.setattr("madira.main.refresh_sommelier_agent", lambda: None)
    assert _save(client).status_code == 200
    response = client.delete("/settings/llm", headers=_auth())
    assert response.status_code == 200
    body = response.json()
    assert body["configured"] is False
    assert body["key_hint"] is None
    assert body["demo_mode"] is True
    assert body["source"] == "demo"
    assert API_KEY not in response.text
    assert read_stored() is None
    assert "DEMO MODE" in client.get("/status").json()["label"]


def test_saved_key_overrides_env_then_delete_uses_env(client: TestClient, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env-key-zzzz")
    monkeypatch.setenv("MADIRA_LLM_PROVIDER", "openai")
    monkeypatch.setenv("MADIRA_LLM_MODEL", "gpt-4.1-mini")
    monkeypatch.setattr("madira.main.refresh_sommelier_agent", lambda: None)

    before = resolve_runtime()
    assert before.source == "env"
    assert before.demo_mode is False
    assert before.api_key == "sk-env-key-zzzz"
    assert client.get("/status").json()["llm_source"] == "env"

    saved = _save(client, provider="anthropic", model="claude-haiku-4-5-20251001", api_key=API_KEY)
    assert saved.status_code == 200
    current = resolve_runtime()
    assert current.source == "settings"
    assert current.provider == "anthropic"
    assert current.api_key == API_KEY
    assert current.demo_mode is False

    deleted = client.delete("/settings/llm", headers=_auth())
    assert deleted.status_code == 200
    restored = resolve_runtime()
    assert restored.source == "env"
    assert restored.provider == "openai"
    assert restored.api_key == "sk-env-key-zzzz"
    assert restored.demo_mode is False

    monkeypatch.setenv("OPENAI_API_KEY", "")
    assert resolve_runtime().source == "demo"
    assert resolve_runtime().demo_mode is True


def test_demo_mode_flag_forces_fixtures_even_with_a_saved_key(client: TestClient, monkeypatch):
    monkeypatch.setenv("MADIRA_DEMO_MODE", "true")
    monkeypatch.setattr("madira.main.refresh_sommelier_agent", lambda: None)
    response = _save(client)
    assert response.status_code == 200
    body = response.json()
    assert body["configured"] is True
    assert body["demo_mode"] is True
    assert body["demo_forced"] is True
    assert body["source"] == "forced-demo"
    status = client.get("/status").json()
    assert status["demo_mode"] is True
    assert "DEMO MODE" in status["label"]
    from madira.agents.orchestrator import specialist_specs

    assert specialist_specs()[0]["model"].__class__.__name__ == "DemoChatModel"


def test_save_rebuilds_the_agent_with_the_saved_key(client: TestClient, monkeypatch):
    from madira.agents.demo_model import DemoChatModel

    seen: list[tuple[str, str | None]] = []

    def fake_init(model, **kwargs):
        seen.append((model, kwargs.get("api_key")))
        return DemoChatModel(role="settings-test")

    monkeypatch.setattr("langchain.chat_models.init_chat_model", fake_init)
    response = _save(client, provider="openai", model="gpt-4.1-mini")
    assert response.status_code == 200
    assert seen
    assert all(api_key == API_KEY for _, api_key in seen)
    assert all(model == "openai:gpt-4.1-mini" for model, _ in seen)
    agent = _agent_slot.get("agent")
    assert agent is not None
    assert agent.graph is not None

    seen.clear()
    deleted = client.delete("/settings/llm", headers=_auth())
    assert deleted.status_code == 200
    assert seen == []
    assert resolve_runtime().demo_mode is True


def test_refresh_swaps_the_mounted_graph(monkeypatch):
    class Agent:
        def __init__(self):
            self.graph = "old"
            self.subgraphs = {"stale"}

    class Graph:
        def __init__(self):
            self.nodes = {"menu": type("Node", (), {"bound": object()})()}

    agent = Agent()
    previous = _agent_slot.get("agent")
    _agent_slot["agent"] = agent
    monkeypatch.setattr("madira.agents.orchestrator.build_head_sommelier", lambda: Graph())
    try:
        refresh_sommelier_agent()
        assert isinstance(agent.graph, Graph)
        assert agent.subgraphs == set()
    finally:
        _agent_slot["agent"] = previous


def test_live_validator_checks_each_provider_and_hides_the_key(monkeypatch):
    calls: list[dict] = []

    class Response:
        def __init__(self, status_code: int, text: str):
            self.status_code = status_code
            self.text = text

    def fake_get(url, headers=None, params=None, timeout=None):
        calls.append({"url": url, "headers": headers or {}, "params": params or {}})
        return Response(200, "ok")

    monkeypatch.setattr("madira.llm_validate.httpx.get", fake_get)
    validate_provider_key_live("openai", API_KEY, "gpt-4.1-mini")
    validate_provider_key_live("anthropic", API_KEY, "")
    validate_provider_key_live("google_genai", API_KEY, "")
    assert calls[0]["url"] == "https://api.openai.com/v1/models"
    assert calls[0]["headers"]["Authorization"] == f"Bearer {API_KEY}"
    assert calls[1]["url"] == "https://api.anthropic.com/v1/models"
    assert calls[1]["headers"]["x-api-key"] == API_KEY
    assert calls[2]["url"] == "https://generativelanguage.googleapis.com/v1beta/models"
    assert calls[2]["params"]["key"] == API_KEY

    monkeypatch.setattr(
        "madira.llm_validate.httpx.get",
        lambda *args, **kwargs: Response(401, f"invalid {API_KEY}"),
    )
    with pytest.raises(ValueError, match="rejected") as raised:
        validate_provider_key_live("openai", API_KEY, "")
    assert API_KEY not in str(raised.value)


def test_accept_mode_skips_the_network(monkeypatch):
    monkeypatch.setenv("MADIRA_LLM_VALIDATOR", "accept")
    set_key_validator(None)

    def boom(*args, **kwargs):
        raise AssertionError("network")

    monkeypatch.setattr("madira.llm_validate.httpx.get", boom)
    validate_provider_key("openai", API_KEY, "")


def test_secret_roundtrip_and_dev_fallback(monkeypatch, tmp_path):
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("MADIRA_SECRET_KEY", key)
    token = encrypt_secret("sk-roundtrip")
    assert decrypt_secret(token) == "sk-roundtrip"
    monkeypatch.setenv("MADIRA_SECRET_KEY", "a-passphrase-not-a-fernet-key")
    with pytest.raises(RuntimeError, match="MADIRA_SECRET_KEY"):
        decrypt_secret(token)

    monkeypatch.delenv("MADIRA_SECRET_KEY", raising=False)
    secret_file = tmp_path / ".madira_secret"
    monkeypatch.setattr("madira.crypto.SECRET_FILE", secret_file)
    first = encrypt_secret("sk-dev")
    assert secret_file.is_file()
    assert decrypt_secret(first) == "sk-dev"


def test_blank_model_uses_the_provider_default(client: TestClient, monkeypatch):
    monkeypatch.setattr("madira.main.refresh_sommelier_agent", lambda: None)
    response = _save(client, provider="google", model="")
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "google_genai"
    assert body["model"] == "gemini-3.5-flash"
    assert resolve_runtime().model == "gemini-3.5-flash"


def test_unreadable_ciphertext_can_be_removed(client: TestClient, monkeypatch):
    monkeypatch.setattr("madira.main.refresh_sommelier_agent", lambda: None)
    assert _save(client).status_code == 200
    monkeypatch.setenv("MADIRA_SECRET_KEY", Fernet.generate_key().decode())
    listed = client.get("/settings/llm", headers=_auth())
    assert listed.status_code == 200
    body = listed.json()
    assert body["configured"] is False
    assert body["stored"] is True
    assert "MADIRA_SECRET_KEY" in body["warning"]
    assert API_KEY not in listed.text
    assert client.get("/status").json()["demo_mode"] is True
    deleted = client.delete("/settings/llm", headers=_auth())
    assert deleted.status_code == 200
    assert read_stored() is None


def test_status_shape_stays_demo_without_a_key(client: TestClient):
    payload = client.get("/status").json()
    assert payload["demo_mode"] is True
    assert payload["llm_model"] == "madira-demo-fixtures"
    assert payload["llm_source"] == "demo"
    assert payload["label"].startswith("DEMO MODE")
    health = client.get("/health").json()
    assert health["demo_mode"] is True
    assert json.dumps(health).find("sk-") == -1
