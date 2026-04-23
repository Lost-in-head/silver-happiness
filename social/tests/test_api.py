"""Tests for the FastAPI chat API — src/api/app.py and src/api/sessions.py."""

from __future__ import annotations

import sys
import time
import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _stub_heavy_deps() -> None:
    """
    Stub heavy ML/LLM transitive dependencies that may not be installed in the
    test environment.  Matches the pattern used by the existing test suite which
    mocks _build_llm / RAGStore at higher layers.
    """
    stubs = [
        "langchain_community",
        "langchain_community.document_loaders",
        "langchain_community.embeddings",
        "langchain_community.vectorstores",
        "langchain_community.chat_models",
        "langchain_openai",
        "langchain",
        "langchain_core",
        "langchain_core.messages",
        "langchain_core.documents",
        "langchain_text_splitters",
        "chromadb",
        "sentence_transformers",
        "pypdf",
        "unstructured",
        "pyyaml",
    ]
    for stub in stubs:
        if stub not in sys.modules:
            sys.modules[stub] = MagicMock()  # type: ignore[assignment]

    # Prefer the real yaml if present
    try:
        import yaml as _yaml  # noqa: PLC0415
        sys.modules["yaml"] = _yaml
    except ImportError:
        pass


def _fresh_app(api_keys: str = "", cors_origins: str = "*"):
    """
    Return a freshly-imported FastAPI app with the given env overrides.
    Stubs heavy dependencies and purges previously-cached src.* modules so
    each call gets a clean slate.
    """
    _stub_heavy_deps()

    # Purge previously loaded src.* so env patches apply cleanly
    for mod in list(sys.modules.keys()):
        if mod.startswith(("src.api", "src.config", "src.bot", "src.rag")):
            del sys.modules[mod]

    with patch.dict(
        "os.environ",
        {
            "API_KEYS": api_keys,
            "CORS_ORIGINS": cors_origins,
            "RATE_LIMIT_RPM": "999",  # effectively disable rate limiting in tests
            "LOG_LEVEL": "ERROR",
        },
        clear=False,
    ):
        from src.api.app import app as _app  # noqa: PLC0415
        return _app


@pytest.fixture()
def client_no_auth():
    """TestClient with auth disabled and lifespan fully initialised."""
    app = _fresh_app(api_keys="")
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def client_with_auth():
    """TestClient with a single known API key and lifespan fully initialised."""
    app = _fresh_app(api_keys="test-secret-key")
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def mock_bot():
    """Returns a mock Bot whose ask() returns a predictable string."""
    bot = MagicMock()
    bot.ask.return_value = "Hello from the bot!"
    bot.clear_memory.return_value = None
    return bot


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------


class TestHealthEndpoint:
    def test_health_returns_200(self, client_no_auth):
        assert client_no_auth.get("/health").status_code == 200

    def test_health_body(self, client_no_auth):
        data = client_no_auth.get("/health").json()
        assert data["status"] == "ok"
        assert "version" in data

    def test_health_no_auth_required(self, client_with_auth):
        """Health check must not require an API key."""
        assert client_with_auth.get("/health").status_code == 200


# ---------------------------------------------------------------------------
# Chat endpoint — no-auth mode
# ---------------------------------------------------------------------------


class TestChatNoAuth:
    def test_chat_returns_reply(self, client_no_auth, mock_bot):
        with patch("src.api.app.get_bot", return_value=mock_bot):
            resp = client_no_auth.post("/chat", json={"message": "Hello"})
        assert resp.status_code == 200
        assert resp.json()["reply"] == "Hello from the bot!"

    def test_chat_returns_session_id(self, client_no_auth, mock_bot):
        with patch("src.api.app.get_bot", return_value=mock_bot):
            resp = client_no_auth.post("/chat", json={"message": "Hi"})
        assert resp.status_code == 200
        assert len(resp.json()["session_id"]) > 0

    def test_chat_same_session_id_reused(self, client_no_auth, mock_bot):
        with patch("src.api.app.get_bot", return_value=mock_bot):
            r1 = client_no_auth.post("/chat", json={"message": "First"})
            sid = r1.json()["session_id"]
            r2 = client_no_auth.post("/chat", json={"message": "Second", "session_id": sid})
        assert r2.status_code == 200
        assert r2.json()["session_id"] == sid

    def test_chat_empty_message_rejected(self, client_no_auth):
        assert client_no_auth.post("/chat", json={"message": "   "}).status_code == 422

    def test_chat_missing_message_rejected(self, client_no_auth):
        assert client_no_auth.post("/chat", json={}).status_code == 422

    def test_chat_message_too_long_rejected(self, client_no_auth):
        assert client_no_auth.post("/chat", json={"message": "x" * 5000}).status_code == 422

    def test_chat_use_rag_flag_forwarded(self, client_no_auth, mock_bot):
        with patch("src.api.app.get_bot", return_value=mock_bot):
            resp = client_no_auth.post("/chat", json={"message": "Hello", "use_rag": False})
        assert resp.status_code == 200
        # use_rag=False should be passed through to bot.ask
        mock_bot.ask.assert_called_once_with("Hello", use_rag=False)

    def test_chat_bot_error_returns_502(self, client_no_auth):
        failing_bot = MagicMock()
        failing_bot.ask.side_effect = RuntimeError("LLM timeout")
        with patch("src.api.app.get_bot", return_value=failing_bot):
            resp = client_no_auth.post("/chat", json={"message": "Hello"})
        assert resp.status_code == 502

    def test_chat_config_error_returns_503(self, client_no_auth):
        bad_bot = MagicMock()
        bad_bot.ask.side_effect = ValueError("OPENROUTER_API_KEY not set")
        with patch("src.api.app.get_bot", return_value=bad_bot):
            resp = client_no_auth.post("/chat", json={"message": "Hello"})
        assert resp.status_code == 503


# ---------------------------------------------------------------------------
# Chat endpoint — auth mode
# ---------------------------------------------------------------------------


class TestChatWithAuth:
    def test_chat_no_key_returns_401(self, client_with_auth, mock_bot):
        with patch("src.api.app.get_bot", return_value=mock_bot):
            resp = client_with_auth.post("/chat", json={"message": "Hello"})
        assert resp.status_code == 401

    def test_chat_wrong_key_returns_401(self, client_with_auth, mock_bot):
        with patch("src.api.app.get_bot", return_value=mock_bot):
            resp = client_with_auth.post(
                "/chat",
                json={"message": "Hello"},
                headers={"X-API-Key": "wrong-key"},
            )
        assert resp.status_code == 401

    def test_chat_correct_key_returns_200(self, client_with_auth, mock_bot):
        with patch("src.api.app.get_bot", return_value=mock_bot):
            resp = client_with_auth.post(
                "/chat",
                json={"message": "Hello"},
                headers={"X-API-Key": "test-secret-key"},
            )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Session management endpoints
# ---------------------------------------------------------------------------


class TestSessionEndpoints:
    def test_clear_nonexistent_session_404(self, client_no_auth):
        resp = client_no_auth.post(f"/sessions/{uuid.uuid4()}/clear")
        assert resp.status_code == 404

    def test_delete_nonexistent_session_404(self, client_no_auth):
        resp = client_no_auth.delete(f"/sessions/{uuid.uuid4()}")
        assert resp.status_code == 404

    def test_clear_existing_session_returns_200(self, client_no_auth, mock_bot):
        with patch("src.api.app.get_bot", return_value=mock_bot):
            r = client_no_auth.post("/chat", json={"message": "Hi"})
            sid = r.json()["session_id"]
            resp = client_no_auth.post(f"/sessions/{sid}/clear")
        assert resp.status_code == 200
        assert resp.json()["cleared"] is True
        assert resp.json()["session_id"] == sid

    def test_delete_existing_session_returns_200(self, client_no_auth, mock_bot):
        with patch("src.api.app.get_bot", return_value=mock_bot):
            r = client_no_auth.post("/chat", json={"message": "Hi"})
            sid = r.json()["session_id"]
            resp = client_no_auth.delete(f"/sessions/{sid}")
        assert resp.status_code == 200
        assert resp.json()["session_id"] == sid

    def test_delete_then_delete_again_returns_404(self, client_no_auth, mock_bot):
        with patch("src.api.app.get_bot", return_value=mock_bot):
            r = client_no_auth.post("/chat", json={"message": "Hi"})
            sid = r.json()["session_id"]
            client_no_auth.delete(f"/sessions/{sid}")
            resp = client_no_auth.delete(f"/sessions/{sid}")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# SessionStore unit tests
# ---------------------------------------------------------------------------


class TestSessionStore:
    def test_get_or_create_new_session(self):
        from src.api.sessions import SessionStore

        store = SessionStore()
        bot = MagicMock()
        sid, returned_bot = store.get_or_create(None, lambda: bot)
        assert sid is not None
        assert returned_bot is bot

    def test_same_session_id_returns_same_bot(self):
        from src.api.sessions import SessionStore

        store = SessionStore()
        bot = MagicMock()
        call_count = {"n": 0}

        def factory():
            call_count["n"] += 1
            return bot

        sid, _ = store.get_or_create(None, factory)
        _, bot2 = store.get_or_create(sid, factory)
        assert call_count["n"] == 1  # factory only called once
        assert bot2 is bot

    def test_len_tracks_sessions(self):
        from src.api.sessions import SessionStore

        store = SessionStore()
        assert len(store) == 0
        store.get_or_create(None, MagicMock)
        assert len(store) == 1

    def test_clear_nonexistent_returns_false(self):
        from src.api.sessions import SessionStore

        store = SessionStore()
        assert store.clear("nonexistent-id") is False

    def test_delete_nonexistent_returns_false(self):
        from src.api.sessions import SessionStore

        store = SessionStore()
        assert store.delete("nonexistent-id") is False

    def test_clear_existing_calls_bot_clear_memory(self):
        from src.api.sessions import SessionStore

        store = SessionStore()
        bot = MagicMock()
        sid, _ = store.get_or_create(None, lambda: bot)
        result = store.clear(sid)
        assert result is True
        bot.clear_memory.assert_called_once()

    def test_ttl_expiry_creates_new_bot(self):
        from src.api.sessions import SessionStore

        store = SessionStore(ttl_seconds=0.01)  # 10ms TTL
        bot1 = MagicMock()
        bot2 = MagicMock()
        bots = iter([bot1, bot2])

        sid, _ = store.get_or_create(None, lambda: next(bots))
        time.sleep(0.02)  # wait for expiry
        _, returned = store.get_or_create(sid, lambda: next(bots))
        # Session expired — a fresh bot should have been created
        assert returned is bot2

    def test_capacity_evicts_lru(self):
        from src.api.sessions import SessionStore

        store = SessionStore(max_sessions=2)
        s1, _ = store.get_or_create(None, MagicMock)
        s2, _ = store.get_or_create(None, MagicMock)
        # Adding a third evicts the LRU (s1)
        s3, _ = store.get_or_create(None, MagicMock)
        assert len(store) == 2
        assert store.delete(s1) is False  # s1 was evicted

    def test_reap_expired_removes_stale(self):
        from src.api.sessions import SessionStore

        store = SessionStore(ttl_seconds=0.01)
        store.get_or_create(None, MagicMock)
        time.sleep(0.02)
        removed = store.reap_expired()
        assert removed == 1
        assert len(store) == 0

