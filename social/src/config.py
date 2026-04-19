"""Shared configuration loading. Single source of truth — import this, do not duplicate."""

import logging
import os
from pathlib import Path

import yaml
from src.rag.store import RAGStore
from src.bot.brain import Bot

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_config(path: Path | None = None) -> dict:
    """
    Load config.yaml from project root. Falls back to config.example.yaml.
    Returns an empty dict if neither exists — callers must handle missing keys gracefully.
    """
    candidates = [path] if path else [
        PROJECT_ROOT / "config.yaml",
        PROJECT_ROOT / "config.example.yaml",
    ]
    for candidate in candidates:
        if candidate and candidate.exists():
            try:
                with open(candidate) as f:
                    data = yaml.safe_load(f) or {}
                    logger.debug("Loaded config from %s", candidate)
                    return data
            except (yaml.YAMLError, IOError) as e:
                logger.warning("Failed to load config from %s: %s", candidate, e)
    logger.warning("No config file found; using defaults.")
    return {}


def get_rag(config: dict):
    """Build a RAGStore from config."""
    rag_cfg = config.get("rag", {})
    return RAGStore(
        persist_directory=os.path.expanduser(
            rag_cfg.get("persist_directory", "./data/chroma")
        ),
        collection_name=rag_cfg.get("collection_name", "bot_knowledge"),
        embedding_model=rag_cfg.get("embedding_model", "all-MiniLM-L6-v2"),
        top_k=rag_cfg.get("top_k", 4),
    )


def get_bot(config: dict):
    """Build a Bot from config. Reuse across calls where possible."""
    rag = get_rag(config)
    llm_cfg = config.get("llm", {})
    mem_cfg = config.get("memory", {})
    rag_cfg = config.get("rag", {})

    return Bot(
        rag=rag,
        model=llm_cfg.get("model", "openai/gpt-4o-mini"),
        provider=llm_cfg.get("provider", "openrouter"),
        memory_window=mem_cfg.get("window_size", 10),
        top_k=rag_cfg.get("top_k", 4),
    )
