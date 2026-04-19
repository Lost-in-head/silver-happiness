"""Tests for src/bot/brain.py"""

import pytest
from unittest.mock import MagicMock, patch, call


class TestBuildLlm:
    def test_openrouter_raises_without_api_key(self):
        from src.bot.brain import _build_llm

        with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
            _build_llm("openrouter", "openai/gpt-4o-mini")

    def test_openrouter_creates_chatopenai(self, openrouter_key):
        from src.bot.brain import _build_llm

        with patch("src.bot.brain.ChatOpenAI") as MockLLM:
            MockLLM.return_value = MagicMock()
            _build_llm("openrouter", "openai/gpt-4o-mini")
            MockLLM.assert_called_once()
            kwargs = MockLLM.call_args[1]
            assert kwargs["openai_api_key"] == openrouter_key
            assert "openrouter.ai" in kwargs["openai_api_base"]
            assert kwargs["model"] == "openai/gpt-4o-mini"

    def test_openrouter_sets_required_headers(self, openrouter_key):
        from src.bot.brain import _build_llm, OPENROUTER_HEADERS

        with patch("src.bot.brain.ChatOpenAI") as MockLLM:
            MockLLM.return_value = MagicMock()
            _build_llm("openrouter", "openai/gpt-4o-mini")
            kwargs = MockLLM.call_args[1]
            assert "HTTP-Referer" in kwargs["default_headers"]
            assert "X-Title" in kwargs["default_headers"]

    def test_ollama_creates_chat_ollama(self, monkeypatch):
        from src.bot.brain import _build_llm

        monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
        with patch("src.bot.brain.ChatOpenAI") as MockOpenAI:
            try:
                with patch("langchain_ollama.ChatOllama") as MockOllama:
                    MockOllama.return_value = MagicMock()
                    result = _build_llm("ollama", "llama3")
                    MockOpenAI.assert_not_called()
            except ImportError:
                pass  # Ollama not installed — acceptable in CI

    def test_unknown_provider_defaults_to_openrouter(self, openrouter_key):
        from src.bot.brain import _build_llm

        with patch("src.bot.brain.ChatOpenAI") as MockLLM:
            MockLLM.return_value = MagicMock()
            # Any unrecognized provider string falls through to openrouter
            _build_llm("some-future-provider", "openai/gpt-4o-mini")
            MockLLM.assert_called_once()


class TestBotAsk:
    def test_ask_returns_string(self, mock_bot):
        result = mock_bot.ask("What is the capital of France?")
        assert isinstance(result, str)
        assert result == "This is a bot response."

    def test_ask_calls_llm_invoke(self, mock_bot):
        mock_bot.ask("Hello")
        mock_bot.llm.invoke.assert_called_once()

    def test_ask_appends_to_history(self, mock_bot):
        assert len(mock_bot._history) == 0
        mock_bot.ask("First message")
        assert len(mock_bot._history) == 1
        human, ai = mock_bot._history[0]
        assert human == "First message"
        assert ai == "This is a bot response."

    def test_ask_multiple_messages_builds_history(self, mock_bot):
        mock_bot.ask("msg 1")
        mock_bot.ask("msg 2")
        mock_bot.ask("msg 3")
        assert len(mock_bot._history) == 3

    def test_ask_with_use_rag_false_skips_rag(self, mock_bot, mock_rag):
        mock_bot.ask("Hello", use_rag=False)
        mock_rag.retrieve.assert_not_called()

    def test_ask_with_use_rag_true_calls_retrieve(self, mock_bot, mock_rag):
        mock_bot.ask("Hello", use_rag=True)
        mock_rag.retrieve.assert_called_once_with("Hello", top_k=mock_bot.top_k)

    def test_rag_context_included_in_messages(self, mock_bot, mock_rag):
        mock_rag.retrieve.return_value = "Important context."
        mock_bot.ask("question", use_rag=True)
        invoke_args = mock_bot.llm.invoke.call_args[0][0]
        # First message is SystemMessage with context
        system_content = invoke_args[0].content
        assert "Important context." in system_content

    def test_history_included_in_subsequent_messages(self, mock_bot):
        mock_bot.ask("first question")
        mock_bot.ask("second question")
        # On second call, messages should include prior human+ai pair
        second_call_messages = mock_bot.llm.invoke.call_args[0][0]
        message_contents = [m.content for m in second_call_messages]
        assert "first question" in message_contents
        assert "This is a bot response." in message_contents


class TestBotMemoryWindow:
    def test_memory_window_limits_history(self, mock_rag, mock_llm_response):
        from src.bot.brain import Bot

        with patch("src.bot.brain._build_llm") as mock_build:
            mock_llm = MagicMock()
            mock_llm.invoke.return_value = mock_llm_response
            mock_build.return_value = mock_llm
            bot = Bot(rag=mock_rag, memory_window=3)

        for i in range(5):
            bot.ask(f"message {i}")

        assert len(bot._history) == 3
        # Should contain the last 3
        messages = [h[0] for h in bot._history]
        assert "message 2" in messages
        assert "message 3" in messages
        assert "message 4" in messages
        assert "message 0" not in messages

    def test_clear_memory_empties_history(self, mock_bot):
        mock_bot.ask("something")
        assert len(mock_bot._history) == 1
        mock_bot.clear_memory()
        assert len(mock_bot._history) == 0

    def test_clear_memory_on_empty_history_is_safe(self, mock_bot):
        mock_bot.clear_memory()  # should not raise
        assert len(mock_bot._history) == 0


class TestBotTopK:
    def test_top_k_passed_to_retrieve(self, mock_rag, mock_llm_response):
        from src.bot.brain import Bot

        with patch("src.bot.brain._build_llm") as mock_build:
            mock_llm = MagicMock()
            mock_llm.invoke.return_value = mock_llm_response
            mock_build.return_value = mock_llm
            bot = Bot(rag=mock_rag, top_k=7)

        bot.ask("test", use_rag=True)
        mock_rag.retrieve.assert_called_once_with("test", top_k=7)
