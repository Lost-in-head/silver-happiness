"""Tests for src/bot/prompt.py"""

from src.bot.prompt import build_system_prompt, SYSTEM_PROMPT


class TestSystemPrompt:
    def test_base_prompt_is_non_empty(self):
        assert SYSTEM_PROMPT.strip()

    def test_base_prompt_contains_core_rules(self):
        assert "Do not make up facts" in SYSTEM_PROMPT
        assert "retrieved knowledge" in SYSTEM_PROMPT

    def test_no_context_returns_base_prompt(self):
        result = build_system_prompt()
        assert result == SYSTEM_PROMPT

    def test_none_context_returns_base_prompt(self):
        result = build_system_prompt(None)
        assert result == SYSTEM_PROMPT

    def test_empty_string_context_returns_base_prompt(self):
        result = build_system_prompt("")
        assert result == SYSTEM_PROMPT

    def test_whitespace_only_context_returns_base_prompt(self):
        result = build_system_prompt("   \n  ")
        assert result == SYSTEM_PROMPT

    def test_context_is_appended(self):
        ctx = "The sky is blue."
        result = build_system_prompt(ctx)
        assert SYSTEM_PROMPT in result
        assert ctx in result
        assert "Relevant knowledge:" in result

    def test_context_appears_after_base_prompt(self):
        ctx = "Custom knowledge here."
        result = build_system_prompt(ctx)
        base_pos = result.index(SYSTEM_PROMPT)
        ctx_pos = result.index(ctx)
        assert ctx_pos > base_pos
