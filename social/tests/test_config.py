"""Tests for src/config.py"""

import yaml
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


class TestLoadConfig:
    def test_returns_empty_dict_when_no_file(self, tmp_path):
        from src.config import load_config

        # Point to a dir with no yaml files
        result = load_config(path=tmp_path / "nonexistent.yaml")
        assert result == {}

    def test_reads_yaml_from_explicit_path(self, tmp_path):
        from src.config import load_config

        cfg = {"llm": {"model": "openai/gpt-4o-mini"}}
        path = tmp_path / "config.yaml"
        path.write_text(yaml.dump(cfg))

        result = load_config(path=path)
        assert result["llm"]["model"] == "openai/gpt-4o-mini"

    def test_returns_empty_on_invalid_yaml(self, tmp_path):
        from src.config import load_config

        path = tmp_path / "config.yaml"
        path.write_text(": invalid: [yaml")

        result = load_config(path=path)
        assert result == {}

    def test_returns_empty_on_empty_yaml_file(self, tmp_path):
        from src.config import load_config

        path = tmp_path / "config.yaml"
        path.write_text("")

        result = load_config(path=path)
        assert result == {}

    def test_nested_config_fully_parsed(self, config_file):
        from src.config import load_config

        result = load_config(path=config_file)
        assert result["rag"]["top_k"] == 4
        assert result["geolocation"]["timezone_id"] == "America/New_York"
        assert result["memory"]["window_size"] == 5


class TestGetRag:
    def test_get_rag_returns_ragstore(self, sample_config):
        from src.config import get_rag
        import src.config as cfg_module

        with patch.object(cfg_module, "RAGStore") as MockRAG:
            MockRAG.return_value = MagicMock()
            rag = get_rag(sample_config)
            MockRAG.assert_called_once()
            call_kwargs = MockRAG.call_args[1]
            assert call_kwargs["collection_name"] == "test_knowledge"
            assert call_kwargs["top_k"] == 4

    def test_get_rag_uses_defaults_on_empty_config(self):
        from src.config import get_rag
        import src.config as cfg_module

        with patch.object(cfg_module, "RAGStore") as MockRAG:
            MockRAG.return_value = MagicMock()
            get_rag({})
            call_kwargs = MockRAG.call_args[1]
            assert call_kwargs["collection_name"] == "bot_knowledge"
            assert call_kwargs["top_k"] == 4


class TestGetBot:
    def test_get_bot_returns_bot(self, sample_config, openrouter_key):
        from src.config import get_bot
        import src.config as cfg_module

        with patch.object(cfg_module, "get_rag") as mock_get_rag, \
             patch.object(cfg_module, "Bot") as MockBot:
            mock_get_rag.return_value = MagicMock()
            MockBot.return_value = MagicMock()
            bot = get_bot(sample_config)
            MockBot.assert_called_once()
            call_kwargs = MockBot.call_args[1]
            assert call_kwargs["model"] == "openai/gpt-4o-mini"
            assert call_kwargs["provider"] == "openrouter"
            assert call_kwargs["memory_window"] == 5
            assert call_kwargs["top_k"] == 4
