"""Tests for src/platforms/reddit.py — RedditAdapter actions via mocked Playwright."""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from src.platforms.reddit import RedditAdapter, REDDIT_BASE


def make_adapter(**kwargs):
    defaults = dict(username="user", password="pass", min_delay=0, max_delay=0)
    defaults.update(kwargs)
    return RedditAdapter(**defaults)


def mock_page():
    """Build a minimal mock Playwright Page."""
    page = MagicMock()
    # get_by_placeholder returns a locator mock
    loc = MagicMock()
    loc.count.return_value = 1
    loc.first = MagicMock()
    loc.last = MagicMock()
    page.get_by_placeholder.return_value = loc
    page.get_by_role.return_value = loc
    page.locator.return_value = loc
    page.is_closed.return_value = False
    return page


class TestRedditAdapterLogin:
    def test_login_returns_false_with_empty_username(self):
        adapter = make_adapter(username="", password="pass")
        result = adapter.login()
        assert result is False

    def test_login_returns_false_with_empty_password(self):
        adapter = make_adapter(username="user", password="")
        result = adapter.login()
        assert result is False

    def test_login_success_path(self):
        adapter = make_adapter()
        page = mock_page()
        page.wait_for_url = MagicMock()  # simulate successful redirect

        with patch.object(adapter, "_get_page", return_value=page), \
             patch.object(adapter, "_random_delay"):
            result = adapter.login()

        assert result is True
        page.goto.assert_called_once()
        assert "/login" in page.goto.call_args[0][0]

    def test_login_fills_username_and_password(self):
        adapter = make_adapter(username="myuser", password="mypass")

        # Each placeholder needs a distinct locator so fills don't overwrite each other
        username_loc = MagicMock()
        password_loc = MagicMock()
        button_loc = MagicMock()

        def by_placeholder(name):
            return username_loc if name == "Username" else password_loc

        page = MagicMock()
        page.get_by_placeholder.side_effect = by_placeholder
        page.get_by_role.return_value = button_loc
        page.is_closed.return_value = False

        with patch.object(adapter, "_get_page", return_value=page), \
             patch.object(adapter, "_random_delay"):
            adapter.login()

        username_loc.fill.assert_called_with("myuser")
        password_loc.fill.assert_called_with("mypass")

    def test_login_returns_false_on_timeout(self):
        adapter = make_adapter()
        page = mock_page()
        page.wait_for_url.side_effect = Exception("Timeout waiting for navigation")

        with patch.object(adapter, "_get_page", return_value=page), \
             patch.object(adapter, "_random_delay"):
            result = adapter.login()

        assert result is False

    def test_login_logs_exception_on_failure(self, caplog):
        import logging
        adapter = make_adapter()
        page = mock_page()
        page.wait_for_url.side_effect = Exception("network error")

        with patch.object(adapter, "_get_page", return_value=page), \
             patch.object(adapter, "_random_delay"), \
             caplog.at_level(logging.ERROR, logger="src.platforms.reddit"):
            adapter.login()

        assert caplog.records  # something was logged


class TestRedditAdapterPost:
    def test_post_returns_true_on_success(self):
        adapter = make_adapter()
        page = mock_page()

        with patch.object(adapter, "_get_page", return_value=page), \
             patch.object(adapter, "_random_delay"):
            result = adapter.post("python", "My Title", "My body text")

        assert result is True

    def test_post_navigates_to_subreddit_submit(self):
        adapter = make_adapter()
        page = mock_page()

        with patch.object(adapter, "_get_page", return_value=page), \
             patch.object(adapter, "_random_delay"):
            adapter.post("python", "Title")

        goto_url = page.goto.call_args[0][0]
        assert "r/python/submit" in goto_url

    def test_post_prepends_r_slash_to_subreddit(self):
        adapter = make_adapter()
        page = mock_page()

        with patch.object(adapter, "_get_page", return_value=page), \
             patch.object(adapter, "_random_delay"):
            adapter.post("learnpython", "Title")

        goto_url = page.goto.call_args[0][0]
        assert "r/learnpython" in goto_url

    def test_post_with_r_prefix_not_doubled(self):
        adapter = make_adapter()
        page = mock_page()

        with patch.object(adapter, "_get_page", return_value=page), \
             patch.object(adapter, "_random_delay"):
            adapter.post("r/learnpython", "Title")

        goto_url = page.goto.call_args[0][0]
        assert "r/r/" not in goto_url

    def test_post_fills_title(self):
        adapter = make_adapter()
        page = mock_page()

        with patch.object(adapter, "_get_page", return_value=page), \
             patch.object(adapter, "_random_delay"):
            adapter.post("test", "My Post Title")

        page.get_by_placeholder("An interesting title").fill.assert_called_with("My Post Title")

    def test_post_returns_false_on_exception(self):
        adapter = make_adapter()
        page = mock_page()
        page.goto.side_effect = Exception("Navigation failed")

        with patch.object(adapter, "_get_page", return_value=page), \
             patch.object(adapter, "_random_delay"):
            result = adapter.post("test", "Title")

        assert result is False

    def test_post_logs_exception_on_failure(self, caplog):
        import logging
        adapter = make_adapter()
        page = mock_page()
        page.goto.side_effect = Exception("network failure")

        with patch.object(adapter, "_get_page", return_value=page), \
             patch.object(adapter, "_random_delay"), \
             caplog.at_level(logging.ERROR, logger="src.platforms.reddit"):
            adapter.post("test", "Title")

        assert caplog.records


class TestRedditAdapterComment:
    def test_comment_returns_true_on_success(self):
        adapter = make_adapter()
        page = mock_page()

        with patch.object(adapter, "_get_page", return_value=page), \
             patch.object(adapter, "_random_delay"):
            result = adapter.comment("https://reddit.com/r/test/abc", "My comment")

        assert result is True

    def test_comment_navigates_to_post_url(self):
        adapter = make_adapter()
        page = mock_page()
        url = "https://reddit.com/r/test/comments/abc123/"

        with patch.object(adapter, "_get_page", return_value=page), \
             patch.object(adapter, "_random_delay"):
            adapter.comment(url, "text")

        page.goto.assert_called_with(url, wait_until="domcontentloaded")

    def test_comment_prepends_base_url_to_relative_path(self):
        adapter = make_adapter()
        page = mock_page()

        with patch.object(adapter, "_get_page", return_value=page), \
             patch.object(adapter, "_random_delay"):
            adapter.comment("/r/test/comments/abc", "text")

        goto_url = page.goto.call_args[0][0]
        assert goto_url.startswith(REDDIT_BASE)

    def test_comment_returns_false_on_exception(self):
        adapter = make_adapter()
        page = mock_page()
        page.goto.side_effect = Exception("error")

        with patch.object(adapter, "_get_page", return_value=page), \
             patch.object(adapter, "_random_delay"):
            result = adapter.comment("https://reddit.com/r/test/abc", "text")

        assert result is False

    def test_comment_logs_on_failure(self, caplog):
        import logging
        adapter = make_adapter()
        page = mock_page()
        page.goto.side_effect = Exception("timeout")

        with patch.object(adapter, "_get_page", return_value=page), \
             patch.object(adapter, "_random_delay"), \
             caplog.at_level(logging.ERROR, logger="src.platforms.reddit"):
            adapter.comment("https://reddit.com/r/test", "hi")

        assert caplog.records


class TestRedditAdapterReply:
    def test_reply_returns_true_on_success(self):
        adapter = make_adapter()
        page = mock_page()

        with patch.object(adapter, "_get_page", return_value=page), \
             patch.object(adapter, "_random_delay"):
            result = adapter.reply("https://reddit.com/r/test/abc", "My reply")

        assert result is True

    def test_reply_navigates_to_url(self):
        adapter = make_adapter()
        page = mock_page()
        url = "https://reddit.com/r/test/comments/abc123/comment/xyz/"

        with patch.object(adapter, "_get_page", return_value=page), \
             patch.object(adapter, "_random_delay"):
            adapter.reply(url, "reply text")

        page.goto.assert_called_with(url, wait_until="domcontentloaded")

    def test_reply_prepends_base_url_to_relative(self):
        adapter = make_adapter()
        page = mock_page()

        with patch.object(adapter, "_get_page", return_value=page), \
             patch.object(adapter, "_random_delay"):
            adapter.reply("/r/test/comments/abc", "text")

        goto_url = page.goto.call_args[0][0]
        assert goto_url.startswith(REDDIT_BASE)

    def test_reply_returns_false_on_exception(self):
        adapter = make_adapter()
        page = mock_page()
        page.goto.side_effect = Exception("failed")

        with patch.object(adapter, "_get_page", return_value=page), \
             patch.object(adapter, "_random_delay"):
            result = adapter.reply("https://reddit.com/r/test", "text")

        assert result is False

    def test_reply_logs_on_failure(self, caplog):
        import logging
        adapter = make_adapter()
        page = mock_page()
        page.goto.side_effect = Exception("browser crashed")

        with patch.object(adapter, "_get_page", return_value=page), \
             patch.object(adapter, "_random_delay"), \
             caplog.at_level(logging.ERROR, logger="src.platforms.reddit"):
            adapter.reply("https://reddit.com/r/test", "text")

        assert caplog.records


class TestRedditAdapterPageReuse:
    def test_get_page_creates_new_page_if_none(self):
        adapter = make_adapter()
        mock_ctx = MagicMock()
        mock_ctx.new_page.return_value = mock_page()
        adapter._context = mock_ctx
        adapter._page = None

        p = adapter._get_page()

        mock_ctx.new_page.assert_called_once()
        assert p is not None

    def test_get_page_reuses_open_page(self):
        adapter = make_adapter()
        existing_page = mock_page()
        existing_page.is_closed.return_value = False
        adapter._page = existing_page
        adapter._context = MagicMock()

        p = adapter._get_page()

        assert p is existing_page
        adapter._context.new_page.assert_not_called()

    def test_get_page_creates_new_if_closed(self):
        adapter = make_adapter()
        closed_page = mock_page()
        closed_page.is_closed.return_value = True

        new_pg = mock_page()
        mock_ctx = MagicMock()
        mock_ctx.new_page.return_value = new_pg

        adapter._page = closed_page
        adapter._context = mock_ctx

        p = adapter._get_page()
        assert p is new_pg
