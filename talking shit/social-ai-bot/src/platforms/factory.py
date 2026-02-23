"""Build platform adapters from config and env (including geolocation)."""

import os
from typing import Any

from .reddit import RedditAdapter


def get_reddit_adapter(config: dict[str, Any] | None = None, headless: bool = True) -> RedditAdapter:
    """Build RedditAdapter with credentials and geolocation from config and env."""
    config = config or {}
    platforms = config.get("platforms", {})
    reddit_cfg = platforms.get("reddit", {})
    geo = config.get("geolocation", {})

    username = os.environ.get("REDDIT_USERNAME") or reddit_cfg.get("username") or ""
    password = os.environ.get("REDDIT_PASSWORD") or reddit_cfg.get("password") or ""
    proxy_url = os.environ.get("PROXY_URL") or geo.get("proxy_url")
    proxy_username = os.environ.get("PROXY_USERNAME") or geo.get("proxy_username")
    proxy_password = os.environ.get("PROXY_PASSWORD") or geo.get("proxy_password")
    timezone_id = geo.get("timezone_id", "America/New_York")
    locale = geo.get("locale", "en-US")

    return RedditAdapter(
        username=username,
        password=password,
        headless=headless,
        proxy_url=proxy_url,
        proxy_username=proxy_username,
        proxy_password=proxy_password,
        timezone_id=timezone_id,
        locale=locale,
    )
