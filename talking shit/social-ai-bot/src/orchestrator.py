"""Orchestrator: decide when to post/reply and call platform adapters."""

import json
import os
import time
from pathlib import Path
from typing import Any

from .bot.brain import Bot
from .rag.store import RAGStore
from .platforms.factory import get_reddit_adapter


def _load_config() -> dict:
    import yaml
    root = Path(__file__).resolve().parent.parent
    path = root / "config.yaml"
    if not path.exists():
        path = root / "config.example.yaml"
    if not path.exists():
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


def _get_bot(config: dict) -> Bot:
    rag_cfg = config.get("rag", {})
    root = Path(__file__).resolve().parent.parent
    rag = RAGStore(
        persist_directory=os.path.expanduser(rag_cfg.get("persist_directory", "./data/chroma")),
        collection_name=rag_cfg.get("collection_name", "bot_knowledge"),
        embedding_model=rag_cfg.get("embedding_model", "text-embedding-3-small"),
    )
    llm_cfg = config.get("llm", {})
    mem_cfg = config.get("memory", {})
    return Bot(
        rag=rag,
        model=llm_cfg.get("model", "gpt-4o-mini"),
        memory_window=mem_cfg.get("window_size", 10),
    )


class ActionQueue:
    """Simple file-based queue of actions (post, comment, reply) for the orchestrator."""

    def __init__(self, path: str | Path = "data/queue.json"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def push(self, action: dict[str, Any]):
        actions = self._read()
        actions.append(action)
        self._write(actions)

    def pop(self) -> dict[str, Any] | None:
        actions = self._read()
        if not actions:
            return None
        action = actions.pop(0)
        self._write(actions)
        return action

    def _read(self) -> list:
        if not self.path.exists():
            return []
        try:
            with open(self.path) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []

    def _write(self, actions: list):
        with open(self.path, "w") as f:
            json.dump(actions, f, indent=2)


def process_queue_once(config: dict | None = None, queue_path: str = "data/queue.json") -> bool:
    """
    Process one action from the queue: generate content with the bot and run the platform action.
    Returns True if an action was processed.
    """
    config = config or _load_config()
    queue = ActionQueue(queue_path)
    action = queue.pop()
    if not action:
        return False

    kind = action.get("action")  # "post" | "comment" | "reply"
    platform = action.get("platform", "reddit")
    if platform != "reddit" or kind not in ("post", "comment", "reply"):
        return False
    if kind in ("comment", "reply") and not (action.get("url") or "").strip():
        queue.push(action)  # put back so user can fix queue and add --url
        return False

    bot = _get_bot(config)
    prompt = action.get("prompt", "")
    if not prompt:
        return False

    # Generate content with the bot (no RAG for action text unless prompt asks for it)
    text = bot.ask(prompt, use_rag=True)

    adapter = get_reddit_adapter(config, headless=True)
    try:
        adapter._ensure_context()
        if not adapter.login():
            queue.push(action)  # re-queue on login failure
            return False
        if kind == "post":
            sub = action.get("subreddit", "test")
            title = action.get("title") or text[:300]
            body = action.get("body", "") if action.get("title") else text
            success = adapter.post(sub, title, body)
        elif kind == "comment":
            success = adapter.comment(action.get("url", ""), text)
        else:
            success = adapter.reply(action.get("url", ""), text)
        return success
    finally:
        adapter.close()


def run_scheduled(config: dict | None = None, interval_seconds: int = 60):
    """Process queue every interval_seconds until interrupted."""
    config = config or _load_config()
    while True:
        process_queue_once(config)
        time.sleep(interval_seconds)
