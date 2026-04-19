"""Tests for src/platforms/base.py — PlatformAdapter lifecycle."""

import pytest
import time
from unittest.mock import MagicMock, patch, PropertyMock

from src.platforms.base import PlatformAdapter


# Minimal concrete subclass for testing the abstract base
class DummyAdapter(PlatformAdapter):
    def login(self) -> bool:
        return True

    def post(self, subreddit_or_target, title, body=""):
        return True

    def comment(self, post_url, text):
        return True

    def reply(self, comment_or_post_url, text):
        return True


class TestPlatformAdapterInit:
    def test_defaults(self):
        a = DummyAdapter()
        assert a.username == ""
        assert a.password == ""
        assert a.headless is True
        assert a.timezone_id == "America/New_York"
        assert a.locale == "en-US"
        assert a.min_delay == 2.0
        assert a.max_delay == 6.0
        assert a.proxy_url is None

    def test_custom_values(self):
        a = DummyAdapter(
            username="user",
            password="pass",
            headless=False,
            proxy_url="http://proxy:8080",
            timezone_id="Europe/London",
            locale="en-GB",
            min_delay=0.1,
            max_delay=0.2,
        )
        assert a.username == "user"
        assert a.proxy_url == "http://proxy:8080"
        assert a.timezone_id == "Europe/London"

    def test_none_username_becomes_empty_string(self):
        a = DummyAdapter(username=None)
        assert a.username == ""

    def test_browser_state_starts_none(self):
        a = DummyAdapter()
        assert a._playwright is None
        assert a._browser is None
        assert a._context is None


class TestRandomDelay:
    def test_delay_within_range(self):
        a = DummyAdapter(min_delay=0.01, max_delay=0.02)
        start = time.time()
        a._random_delay()
        elapsed = time.time() - start
        assert 0.01 <= elapsed < 0.5  # generous upper bound for slow CI

    def test_min_equals_max_delays_exactly(self):
        a = DummyAdapter(min_delay=0.01, max_delay=0.01)
        start = time.time()
        a._random_delay()
        elapsed = time.time() - start
        assert elapsed >= 0.01


class TestEnsureContext:
    def test_ensure_context_calls_launch_browser(self):
        a = DummyAdapter()
        mock_ctx = MagicMock()

        def fake_launch():
            a._context = mock_ctx  # simulate what _launch_browser actually does
            return mock_ctx

        with patch.object(a, "_launch_browser", side_effect=fake_launch) as mock_launch:
            result = a._ensure_context()

        mock_launch.assert_called_once()
        assert result is mock_ctx

    def test_ensure_context_reuses_existing_context(self):
        a = DummyAdapter()
        mock_ctx = MagicMock()
        a._context = mock_ctx
        with patch.object(a, "_launch_browser") as mock_launch:
            result = a._ensure_context()
            mock_launch.assert_not_called()
            assert result is mock_ctx


class TestClose:
    def test_close_resets_all_state(self):
        a = DummyAdapter()
        a._context = MagicMock()
        a._browser = MagicMock()
        a._playwright = MagicMock()
        a.close()
        assert a._context is None
        assert a._browser is None
        assert a._playwright is None

    def test_close_calls_playwright_stop(self):
        a = DummyAdapter()
        mock_playwright = MagicMock()
        a._playwright = mock_playwright
        a.close()
        mock_playwright.stop.assert_called_once()

    def test_close_is_idempotent(self):
        a = DummyAdapter()
        a.close()
        a.close()  # should not raise

    def test_close_on_fresh_adapter_is_safe(self):
        a = DummyAdapter()
        a.close()  # no resources allocated yet — should not raise


class TestContextManager:
    def test_enter_calls_ensure_context(self):
        a = DummyAdapter()
        with patch.object(a, "_ensure_context") as mock_ctx, \
             patch.object(a, "close"):
            mock_ctx.return_value = MagicMock()
            with a:
                mock_ctx.assert_called_once()

    def test_exit_calls_close(self):
        a = DummyAdapter()
        with patch.object(a, "_ensure_context", return_value=MagicMock()), \
             patch.object(a, "close") as mock_close:
            with a:
                pass
            mock_close.assert_called_once()

    def test_exit_calls_close_even_on_exception(self):
        a = DummyAdapter()
        with patch.object(a, "_ensure_context", return_value=MagicMock()), \
             patch.object(a, "close") as mock_close:
            try:
                with a:
                    raise ValueError("boom")
            except ValueError:
                pass
            mock_close.assert_called_once()


class TestLaunchBrowserProxy:
    def test_proxy_passed_to_context_when_set(self):
        a = DummyAdapter(proxy_url="http://proxy:8080")
        mock_pw = MagicMock()
        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_pw.chromium.launch.return_value = mock_browser
        mock_browser.new_context.return_value = mock_context

        with patch("src.platforms.base.sync_playwright") as mock_sync:
            mock_sync.return_value.__enter__ = lambda s: mock_pw
            mock_sync.return_value.start.return_value = mock_pw
            a._launch_browser()

        ctx_kwargs = mock_browser.new_context.call_args[1]
        assert "proxy" in ctx_kwargs
        assert ctx_kwargs["proxy"]["server"] == "http://proxy:8080"

    def test_no_proxy_key_when_not_set(self):
        a = DummyAdapter(proxy_url=None)
        mock_pw = MagicMock()
        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_pw.chromium.launch.return_value = mock_browser
        mock_browser.new_context.return_value = mock_context

        with patch("src.platforms.base.sync_playwright") as mock_sync:
            mock_sync.return_value.start.return_value = mock_pw
            a._launch_browser()

        ctx_kwargs = mock_browser.new_context.call_args[1]
        assert "proxy" not in ctx_kwargs
