"""Reddit platform adapter: login, post, comment, reply via Playwright."""

import re
from urllib.parse import urljoin

from playwright.sync_api import Page

from .base import PlatformAdapter


# Reddit's DOM changes frequently; these selectors may need updates.
# Prefer data-testid when available (e.g. new Reddit).
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
        page = self._get_page()
        page.goto(urljoin(REDDIT_BASE, "/login"), wait_until="domcontentloaded")
        self._random_delay()
        try:
            # Reddit login form: username and password
            page.get_by_placeholder("Username").fill(self.username)
            self._random_delay()
            page.get_by_placeholder("Password").fill(self.password)
            self._random_delay()
            page.get_by_role("button", name="Log in").click()
            page.wait_for_url(re.compile(r"reddit\.com/(?!login)", re.I), timeout=15000)
            self._random_delay()
            return True
        except Exception:
            # May need 2FA or captcha; consider saving session state for next time
            return False

    def post(self, subreddit_or_target: str, title: str, body: str = "") -> bool:
        # subreddit_or_target: e.g. "python" or "r/python"
        sub = subreddit_or_target.strip()
        if not sub.startswith("r/"):
            sub = f"r/{sub}"
        page = self._get_page()
        page.goto(urljoin(REDDIT_BASE, f"{sub}/submit"), wait_until="domcontentloaded")
        self._random_delay()
        try:
            page.get_by_placeholder("An interesting title").fill(title)
            self._random_delay()
            if body:
                # Post content / text body
                content = page.get_by_placeholder("What do you want to say?")
                if content.count() > 0:
                    content.first.fill(body)
                self._random_delay()
            page.get_by_role("button", name="Post").click()
            self._random_delay()
            # Success: we're on the new post or back to subreddit
            return True
        except Exception:
            return False

    def comment(self, post_url: str, text: str) -> bool:
        page = self._get_page()
        if not post_url.startswith("http"):
            post_url = urljoin(REDDIT_BASE, post_url)
        page.goto(post_url, wait_until="domcontentloaded")
        self._random_delay()
        try:
            # Comment box: placeholder often "What are your thoughts?"
            box = page.get_by_placeholder("What are your thoughts?")
            if box.count() == 0:
                box = page.locator("[data-testid='comment-submission-form'] textarea")
            box.first.fill(text)
            self._random_delay()
            page.get_by_role("button", name="Comment").click()
            self._random_delay()
            return True
        except Exception:
            return False

    def reply(self, comment_or_post_url: str, text: str) -> bool:
        page = self._get_page()
        if not comment_or_post_url.startswith("http"):
            comment_or_post_url = urljoin(REDDIT_BASE, comment_or_post_url)
        page.goto(comment_or_post_url, wait_until="domcontentloaded")
        self._random_delay()
        try:
            # Click first "Reply" on the page (or a specific one if we had a selector for the comment)
            reply_btn = page.get_by_role("button", name="Reply").first
            reply_btn.click()
            self._random_delay()
            # Reply textarea appears
            box = page.get_by_placeholder("What are your thoughts?")
            if box.count() == 0:
                box = page.locator("form textarea").last
            else:
                box = box.first
            box.fill(text)
            self._random_delay()
            page.get_by_role("button", name="Reply").click()
            self._random_delay()
            return True
        except Exception:
            return False
