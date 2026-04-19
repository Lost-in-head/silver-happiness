"""Orchestrator: action queue processing and scheduled execution.

Fixes from code review:
- Shared config via src.config (no duplication)
- Bot instantiated once per run_scheduled loop, not per queue item
- Atomic queue writes via os.replace()
- Max retry logic — actions exceeding MAX_RETRIES go to dead-letter log
- All exceptions logged with full tracebacks
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

from src.config import load_config, get_bot as _get_bot_from_config
from src.platforms.factory import get_reddit_adapter

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
DEFAULT_QUEUE_PATH = "data/queue.json"
DEFAULT_DEAD_LETTER_PATH = "data/dead_letter.json"


class ActionQueue:
    """
    File-based FIFO queue for platform actions.
    Writes are atomic (temp file + os.replace) to prevent corruption on concurrent access.
    """

    def __init__(
        self,
        path: str | Path = DEFAULT_QUEUE_PATH,
        dead_letter_path: str | Path = DEFAULT_DEAD_LETTER_PATH,
    ):
        self.path = Path(path)
        self.dead_letter_path = Path(dead_letter_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def push(self, action: dict[str, Any]):
        """Append an action to the queue."""
        actions = self._read(self.path)
        actions.append(action)
        self._write(self.path, actions)

    def pop(self) -> dict[str, Any] | None:
        """Remove and return the first action, or None if the queue is empty."""
        actions = self._read(self.path)
        if not actions:
            return None
        action = actions.pop(0)
        self._write(self.path, actions)
        return action

    def dead_letter(self, action: dict[str, Any]):
        """Move a permanently failed action to the dead-letter log."""
        actions = self._read(self.dead_letter_path)
        actions.append(action)
        self._write(self.dead_letter_path, actions)
        logger.warning(
            "Action moved to dead letter (exceeded MAX_RETRIES=%d): %s",
            MAX_RETRIES, action,
        )

    def __len__(self) -> int:
        return len(self._read(self.path))

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _read(path: Path) -> list:
        if not path.exists():
            return []
        try:
            with open(path) as f:
                return json.load(f) or []
        except (json.JSONDecodeError, IOError) as e:
            logger.warning("Queue read error (%s): %s — treating as empty.", path, e)
            return []

    @staticmethod
    def _write(path: Path, actions: list):
        """Atomic write: write to temp file then rename."""
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        try:
            with open(tmp, "w") as f:
                json.dump(actions, f, indent=2)
            os.replace(tmp, path)  # atomic on POSIX; near-atomic on Windows
        except Exception as e:
            logger.exception("Queue write failed to %s: %s", path, e)
            if tmp.exists():
                tmp.unlink(missing_ok=True)
            raise


# ------------------------------------------------------------------ #
# Queue processing
# ------------------------------------------------------------------ #


def process_queue_once(
    config: dict | None = None,
    queue_path: str = DEFAULT_QUEUE_PATH,
    dead_letter_path: str = DEFAULT_DEAD_LETTER_PATH,
    bot=None,
) -> bool:
    """
    Process one action from the queue.
    - Generates content with the bot.
    - Dispatches to the correct platform adapter.
    - Handles retry counting and dead-lettering.
    Returns True if an action was processed (even if it failed).
    """
    config = config or load_config()
    queue = ActionQueue(queue_path, dead_letter_path=dead_letter_path)
    action = queue.pop()
    if not action:
        return False

    kind = action.get("action")
    platform = action.get("platform", "reddit")
    retry_count = action.get("_retry_count", 0)

    # Validate platform and action type
    if platform != "reddit" or kind not in ("post", "comment", "reply"):
        logger.warning("Unsupported platform/action: %s/%s — dropping.", platform, kind)
        return True  # consumed but not re-queued

    # comment/reply require a URL
    if kind in ("comment", "reply") and not (action.get("url") or "").strip():
        logger.error("Action %s requires a URL but none provided — dropping.", kind)
        return True

    prompt = action.get("prompt", "").strip()
    if not prompt:
        logger.error("Action has no prompt — dropping.")
        return True

    # Generate content
    _bot = bot or _get_bot_from_config(config)
    try:
        text = _bot.ask(prompt, use_rag=True)
    except Exception as e:
        logger.exception("Bot failed to generate content: %s", e)
        _requeue_or_dead_letter(queue, action, retry_count)
        return True

    # Dispatch to adapter
    adapter = get_reddit_adapter(config, headless=True)
    try:
        adapter._ensure_context()
        if not adapter.login():
            logger.warning("Reddit login failed — re-queuing action.")
            _requeue_or_dead_letter(queue, action, retry_count)
            return True

        if kind == "post":
            sub = action.get("subreddit", "test")
            title = action.get("title") or text[:300]
            body = action.get("body", "") if action.get("title") else text
            success = adapter.post(sub, title, body)
        elif kind == "comment":
            success = adapter.comment(action["url"], text)
        else:
            success = adapter.reply(action["url"], text)

        if not success:
            logger.warning("Platform action returned False — re-queuing.")
            _requeue_or_dead_letter(queue, action, retry_count)

        return True

    except Exception as e:
        logger.exception("Unexpected error processing action: %s", e)
        _requeue_or_dead_letter(queue, action, retry_count)
        return True
    finally:
        adapter.close()


def _requeue_or_dead_letter(queue: ActionQueue, action: dict, retry_count: int):
    if retry_count >= MAX_RETRIES:
        queue.dead_letter(action)
    else:
        action["_retry_count"] = retry_count + 1
        queue.push(action)
        logger.info("Action re-queued (attempt %d/%d).", retry_count + 1, MAX_RETRIES)


def run_scheduled(config: dict | None = None, interval_seconds: int = 60):
    """
    Process queue on a fixed interval. Bot is instantiated once and reused.
    Runs until interrupted (KeyboardInterrupt).
    """
    config = config or load_config()
    bot = _get_bot_from_config(config)  # once — not per iteration
    logger.info("Scheduler started (interval=%ds).", interval_seconds)
    while True:
        try:
            process_queue_once(config, bot=bot)
        except Exception as e:
            logger.exception("Scheduler iteration error: %s", e)
        time.sleep(interval_seconds)
