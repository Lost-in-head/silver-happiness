"""Shared fixtures and path setup for all tests."""

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure src/ is importable regardless of how pytest is invoked
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ------------------------------------------------------------------ #
# Environment fixtures
# ------------------------------------------------------------------ #


@pytest.fixture(autouse=True)
def clear_env(monkeypatch):
    """
    Strip real API keys from environment for every test.
    Tests that need them must set them explicitly.
    """
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("REDDIT_USERNAME", raising=False)
    monkeypatch.delenv("REDDIT_PASSWORD", raising=False)
    monkeypatch.delenv("PROXY_URL", raising=False)


@pytest.fixture
def openrouter_key(monkeypatch):
    """Set a fake OpenRouter API key for tests that need it."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test-fake-key-1234")
    return "sk-or-test-fake-key-1234"


@pytest.fixture
def reddit_creds(monkeypatch):
    """Set fake Reddit credentials."""
    monkeypatch.setenv("REDDIT_USERNAME", "test_user")
    monkeypatch.setenv("REDDIT_PASSWORD", "test_pass")


# ------------------------------------------------------------------ #
# Config fixtures
# ------------------------------------------------------------------ #


@pytest.fixture
def sample_config():
    return {
        "llm": {"provider": "openrouter", "model": "openai/gpt-4o-mini"},
        "rag": {
            "persist_directory": "./data/chroma",
            "collection_name": "test_knowledge",
            "embedding_model": "all-MiniLM-L6-v2",
            "top_k": 4,
        },
        "memory": {"window_size": 5},
        "platforms": {
            "reddit": {"username": "cfg_user", "password": "cfg_pass"}
        },
        "geolocation": {
            "timezone_id": "America/New_York",
            "locale": "en-US",
        },
    }


@pytest.fixture
def config_file(tmp_path, sample_config):
    """Write a config.yaml to a temp dir and return its path."""
    import yaml

    path = tmp_path / "config.yaml"
    path.write_text(yaml.dump(sample_config))
    return path


# ------------------------------------------------------------------ #
# Mock bot / rag fixtures
# ------------------------------------------------------------------ #


@pytest.fixture
def mock_rag():
    """A RAGStore mock that returns predictable results."""
    rag = MagicMock()
    rag.retrieve.return_value = "Relevant context from knowledge base."
    rag.add_documents.return_value = None
    rag.add_texts.return_value = None
    rag.ingest_directory.return_value = None
    return rag


@pytest.fixture
def mock_llm_response():
    """Fake LangChain message response."""
    msg = MagicMock()
    msg.content = "This is a bot response."
    return msg


@pytest.fixture
def mock_bot(mock_rag, mock_llm_response):
    """A Bot instance with mocked LLM and RAG."""
    from src.bot.brain import Bot

    with patch("src.bot.brain._build_llm") as mock_build:
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = mock_llm_response
        mock_build.return_value = mock_llm
        bot = Bot(rag=mock_rag, provider="openrouter", model="openai/gpt-4o-mini")
        bot._llm_mock = mock_llm  # expose for assertions
        return bot


# ------------------------------------------------------------------ #
# Queue fixture
# ------------------------------------------------------------------ #


@pytest.fixture
def queue(tmp_path):
    """An ActionQueue backed by a temp directory."""
    from src.orchestrator import ActionQueue

    return ActionQueue(
        path=tmp_path / "queue.json",
        dead_letter_path=tmp_path / "dead_letter.json",
    )


@pytest.fixture
def sample_post_action():
    return {
        "action": "post",
        "platform": "reddit",
        "prompt": "Write a short intro post.",
        "subreddit": "test",
    }


@pytest.fixture
def sample_comment_action():
    return {
        "action": "comment",
        "platform": "reddit",
        "prompt": "Write a comment.",
        "url": "https://www.reddit.com/r/test/comments/abc123/",
    }
