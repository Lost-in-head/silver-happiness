"""Reddit platform adapter: login, post, comment, reply via Playwright.

NOTE: Reddit selectors change without warning on redeployments.
      Prefer data-testid or aria roles over CSS classes. Document breakage here.
      Last verified: April 2026 (new Reddit UI).
"""

import logging
import re
from urllib.parse import urljoin

from playwright.sync_api import Page

from .base import PlatformAdapter

logger = logging.getLogger(__name__)

REDDIT_BASE = "https://www.reddit.com"


class RedditAdapter(PlatformAdapter):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._page: Page | None = None

    def _get_page(self) -> Page:
        ctx = self._ensure_context()
        if self._page is None or self._page.is_closed():
            self._page = ctx.new_page()
        return self._page

    def login(self) -> bool:
        if not self.username or not self.password:
            logger.error("Reddit login failed: username or password is empty.")
            return False

        page = self._get_page()
        try:
            page.goto(urljoin(REDDIT_BASE, "/login"), wait_until="domcontentloaded")
            self._random_delay()
            page.get_by_placeholder("Username").fill(self.username)
            self._random_delay()
            page.get_by_placeholder("Password").fill(self.password)
            self._random_delay()
            page.get_by_role("button", name="Log in").click()
            page.wait_for_url(
                re.compile(r"reddit\.com/(?!login)", re.I), timeout=15_000
            )
            self._random_delay()
            logger.info("Reddit login succeeded for user: %s", self.username)
            return True
        except Exception as e:
            logger.exception(
                "Reddit login failed for user %s: %s. "
                "Possible causes: wrong credentials, CAPTCHA, 2FA, or selector change.",
                self.username, e,
            )
            return False

    def post(self, subreddit_or_target: str, title: str, body: str = "") -> bool:
        sub = subreddit_or_target.strip()
        if not sub.startswith("r/"):
            sub = f"r/{sub}"
        page = self._get_page()
        try:
            page.goto(
                urljoin(REDDIT_BASE, f"{sub}/submit"), wait_until="domcontentloaded"
            )
            self._random_delay()
            page.get_by_placeholder("An interesting title").fill(title)
            self._random_delay()
            if body:
                content = page.get_by_placeholder("What do you want to say?")
                if content.count() > 0:
                    content.first.fill(body)
                self._random_delay()
            page.get_by_role("button", name="Post").click()
            self._random_delay()
            logger.info("Reddit post submitted to %s", sub)
            return True
        except Exception as e:
            logger.exception("Reddit post to %s failed: %s", sub, e)
            return False

    def comment(self, post_url: str, text: str) -> bool:
        if not post_url.startswith("http"):
            post_url = urljoin(REDDIT_BASE, post_url)
        page = self._get_page()
        try:
            page.goto(post_url, wait_until="domcontentloaded")
            self._random_delay()
            box = page.get_by_placeholder("What are your thoughts?")
            if box.count() == 0:
                box = page.locator("[data-testid='comment-submission-form'] textarea")
            box.first.fill(text)
            self._random_delay()
            page.get_by_role("button", name="Comment").click()
            self._random_delay()
            logger.info("Reddit comment submitted on: %s", post_url)
            return True
        except Exception as e:
            logger.exception("Reddit comment on %s failed: %s", post_url, e)
            return False

    def reply(self, comment_or_post_url: str, text: str) -> bool:
        if not comment_or_post_url.startswith("http"):
            comment_or_post_url = urljoin(REDDIT_BASE, comment_or_post_url)
        page = self._get_page()
        try:
            page.goto(comment_or_post_url, wait_until="domcontentloaded")
            self._random_delay()
            reply_btn = page.get_by_role("button", name="Reply").first
            reply_btn.click()
            self._random_delay()
            box = page.get_by_placeholder("What are your thoughts?")
            box = box.first if box.count() > 0 else page.locator("form textarea").last
            box.fill(text)
            self._random_delay()
            page.get_by_role("button", name="Reply").click()
            self._random_delay()
            logger.info("Reddit reply submitted on: %s", comment_or_post_url)
            return True
        except Exception as e:
            logger.exception("Reddit reply on %s failed: %s", comment_or_post_url, e)
            return False
