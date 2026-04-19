"""Base platform adapter: browser lifecycle, rate limiting, and geo config."""

import logging
import random
import time
from abc import ABC, abstractmethod
from typing import Any

from playwright.sync_api import sync_playwright, Browser, BrowserContext, Playwright

logger = logging.getLogger(__name__)


class PlatformAdapter(ABC):
    """
    Base class for platform adapters.
    Subclass and implement: login, post, comment, reply.

    Browser context is lazy — created on first _ensure_context() call.
    Always call close() or use as a context manager to release resources.
    """

    def __init__(
        self,
        username: str = "",
        password: str = "",
        headless: bool = True,
        proxy_url: str | None = None,
        proxy_username: str | None = None,
        proxy_password: str | None = None,
        timezone_id: str | None = None,
        locale: str | None = None,
        min_delay: float = 2.0,
        max_delay: float = 6.0,
    ):
        self.username = username or ""
        self.password = password or ""
        self.headless = headless
        self.proxy_url = proxy_url
        self.proxy_username = proxy_username
        self.proxy_password = proxy_password
        self.timezone_id = timezone_id or "America/New_York"
        self.locale = locale or "en-US"
        self.min_delay = min_delay
        self.max_delay = max_delay
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None

    def _random_delay(self):
        delay = random.uniform(self.min_delay, self.max_delay)
        logger.debug("Sleeping %.2fs (rate limiting)", delay)
        time.sleep(delay)

    def _launch_browser(self) -> BrowserContext:
        self._playwright = sync_playwright().start()
        launch_opts: dict[str, Any] = {"headless": self.headless}
        self._browser = self._playwright.chromium.launch(**launch_opts)

        # Proxy is set at context level — Playwright applies it per-request.
        context_opts: dict[str, Any] = {
            "timezone_id": self.timezone_id,
            "locale": self.locale,
        }
        if self.proxy_url:
            proxy: dict[str, str] = {"server": self.proxy_url}
            if self.proxy_username:
                proxy["username"] = self.proxy_username
            if self.proxy_password:
                proxy["password"] = self.proxy_password
            context_opts["proxy"] = proxy
            logger.debug("Browser context using proxy: %s", self.proxy_url)

        self._context = self._browser.new_context(**context_opts)
        logger.debug(
            "Browser launched (headless=%s, tz=%s, locale=%s)",
            self.headless, self.timezone_id, self.locale,
        )
        return self._context

    def _ensure_context(self) -> BrowserContext:
        if self._context is None:
            self._launch_browser()
        assert self._context is not None
        return self._context

    def close(self):
        """Release all Playwright resources. Safe to call multiple times."""
        try:
            if self._context:
                self._context.close()
            if self._browser:
                self._browser.close()
            if self._playwright:
                self._playwright.stop()
        except Exception as e:
            logger.warning("Error during adapter close: %s", e)
        finally:
            self._context = None
            self._browser = None
            self._playwright = None

    def __enter__(self):
        self._ensure_context()
        return self

    def __exit__(self, *args):
        self.close()

    @abstractmethod
    def login(self) -> bool:
        """Log in. Return True on success, False on failure."""

    @abstractmethod
    def post(self, subreddit_or_target: str, title: str, body: str = "") -> bool:
        """Create a new post. Return True on success."""

    @abstractmethod
    def comment(self, post_url: str, text: str) -> bool:
        """Add a top-level comment on a post. Return True on success."""

    @abstractmethod
    def reply(self, comment_or_post_url: str, text: str) -> bool:
        """Reply to a comment (or post). Return True on success."""
