"""Base platform adapter: browser lifecycle and rate limiting."""

import random
import time
from abc import ABC, abstractmethod
from typing import Any

from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page, Playwright


class PlatformAdapter(ABC):
    """Base class for platform adapters. Subclass and implement login, post, comment, reply."""

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
        time.sleep(random.uniform(self.min_delay, self.max_delay))

    def _launch_browser(self) -> tuple[Playwright, Browser, BrowserContext]:
        self._playwright = sync_playwright().start()
        launch_opts: dict[str, Any] = {"headless": self.headless}
        self._browser = self._playwright.chromium.launch(**launch_opts)
        context_opts: dict[str, Any] = {
            "timezone_id": self.timezone_id,
            "locale": self.locale,
        }
        if self.proxy_url:
            context_opts["proxy"] = {"server": self.proxy_url}
            if self.proxy_username:
                context_opts["proxy"]["username"] = self.proxy_username
            if self.proxy_password:
                context_opts["proxy"]["password"] = self.proxy_password
        self._context = self._browser.new_context(**context_opts)
        return self._playwright, self._browser, self._context

    def _ensure_context(self) -> BrowserContext:
        if self._context is None:
            self._launch_browser()
        assert self._context is not None
        return self._context

    def close(self):
        if self._context:
            self._context.close()
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()
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
        """Log in. Return True on success."""
        pass

    @abstractmethod
    def post(self, subreddit_or_target: str, title: str, body: str = "") -> bool:
        """Create a new post. Return True on success."""
        pass

    @abstractmethod
    def comment(self, post_url: str, text: str) -> bool:
        """Add a top-level comment on a post. Return True on success."""
        pass

    @abstractmethod
    def reply(self, comment_or_post_url: str, text: str) -> bool:
        """Reply to a comment (or post). Return True on success."""
        pass
