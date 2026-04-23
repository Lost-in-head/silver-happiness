"""Thread-safe in-memory session store with TTL expiry and capacity cap.

Each session owns one Bot instance so conversation memory is isolated.
Expired or excess sessions are evicted lazily on access and proactively
by the background reaper thread started in ``lifespan``.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from collections import OrderedDict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.bot.brain import Bot

logger = logging.getLogger(__name__)

_SESSION_TTL_SECONDS = 1800   # 30 minutes idle timeout
_MAX_SESSIONS = 1000          # hard cap to prevent memory exhaustion
_REAP_INTERVAL_SECONDS = 300  # background sweep every 5 minutes


class _SessionEntry:
    __slots__ = ("bot", "last_active")

    def __init__(self, bot: "Bot") -> None:
        self.bot = bot
        self.last_active: float = time.monotonic()

    def touch(self) -> None:
        self.last_active = time.monotonic()

    def is_expired(self, ttl: float) -> bool:
        return (time.monotonic() - self.last_active) > ttl


class SessionStore:
    """
    Manages per-user Bot instances keyed by session UUID strings.

    Thread-safety: all public methods hold a reentrant lock.
    Eviction policy:
      1. TTL-based: sessions idle for more than ``ttl_seconds`` are dropped.
      2. Capacity-based: when ``max_sessions`` is reached, the least recently
         active session is evicted before a new one is created.
    """

    def __init__(
        self,
        ttl_seconds: float = _SESSION_TTL_SECONDS,
        max_sessions: int = _MAX_SESSIONS,
    ) -> None:
        self._ttl = ttl_seconds
        self._max = max_sessions
        # OrderedDict gives O(1) move_to_end + popitem(last=False) for LRU
        self._sessions: OrderedDict[str, _SessionEntry] = OrderedDict()
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def get_or_create(self, session_id: str | None, bot_factory) -> tuple[str, "Bot"]:
        """
        Return (session_id, bot) for the given ID, creating one if needed.

        ``bot_factory`` is called with no arguments to produce a new Bot.
        """
        with self._lock:
            if session_id:
                entry = self._sessions.get(session_id)
                if entry is not None and not entry.is_expired(self._ttl):
                    entry.touch()
                    self._sessions.move_to_end(session_id)
                    return session_id, entry.bot
                # expired or unknown — create fresh
                if session_id in self._sessions:
                    del self._sessions[session_id]

            new_id = session_id or str(uuid.uuid4())
            self._evict_if_needed()
            new_bot = bot_factory()
            self._sessions[new_id] = _SessionEntry(new_bot)
            logger.debug("Session created: %s (total=%d)", new_id, len(self._sessions))
            return new_id, new_bot

    def clear(self, session_id: str) -> bool:
        """Clear conversation memory for a session. Returns True if found."""
        with self._lock:
            entry = self._sessions.get(session_id)
            if entry is None or entry.is_expired(self._ttl):
                if session_id in self._sessions:
                    del self._sessions[session_id]
                return False
            entry.bot.clear_memory()
            entry.touch()
            logger.debug("Session memory cleared: %s", session_id)
            return True

    def delete(self, session_id: str) -> bool:
        """Remove a session entirely. Returns True if it existed."""
        with self._lock:
            existed = session_id in self._sessions
            self._sessions.pop(session_id, None)
            if existed:
                logger.debug("Session deleted: %s", session_id)
            return existed

    def reap_expired(self) -> int:
        """Remove all expired sessions. Returns the count removed."""
        with self._lock:
            expired = [sid for sid, e in self._sessions.items() if e.is_expired(self._ttl)]
            for sid in expired:
                del self._sessions[sid]
            if expired:
                logger.info("Reaped %d expired session(s).", len(expired))
            return len(expired)

    def __len__(self) -> int:
        with self._lock:
            return len(self._sessions)

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _evict_if_needed(self) -> None:
        """Evict the LRU entry when at capacity. Called with lock held."""
        if len(self._sessions) >= self._max:
            evicted_id, _ = self._sessions.popitem(last=False)
            logger.warning(
                "Session store at capacity (%d). Evicted LRU session: %s",
                self._max,
                evicted_id,
            )


# ------------------------------------------------------------------ #
# Background reaper thread
# ------------------------------------------------------------------ #

def start_reaper(store: SessionStore, interval: float = _REAP_INTERVAL_SECONDS) -> threading.Event:
    """
    Start a daemon thread that periodically calls ``store.reap_expired()``.

    Returns the ``threading.Event`` that can be set to stop the thread
    gracefully during application shutdown.
    """
    stop = threading.Event()

    def _run() -> None:
        while not stop.wait(timeout=interval):
            try:
                store.reap_expired()
            except Exception:
                logger.exception("Session reaper error.")

    t = threading.Thread(target=_run, daemon=True, name="session-reaper")
    t.start()
    logger.info("Session reaper started (interval=%ss, ttl=%ss).", interval, store._ttl)
    return stop
