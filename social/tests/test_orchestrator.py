"""Tests for src/orchestrator.py — ActionQueue and process_queue_once."""

import json
import os
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch


# ------------------------------------------------------------------ #
# ActionQueue tests
# ------------------------------------------------------------------ #


class TestActionQueuePushPop:
    def test_empty_queue_pop_returns_none(self, queue):
        assert queue.pop() is None

    def test_push_then_pop_returns_item(self, queue, sample_post_action):
        queue.push(sample_post_action)
        result = queue.pop()
        assert result == sample_post_action

    def test_pop_removes_item_from_queue(self, queue, sample_post_action):
        queue.push(sample_post_action)
        queue.pop()
        assert queue.pop() is None

    def test_fifo_order(self, queue):
        queue.push({"id": 1})
        queue.push({"id": 2})
        queue.push({"id": 3})
        assert queue.pop()["id"] == 1
        assert queue.pop()["id"] == 2
        assert queue.pop()["id"] == 3

    def test_len_reflects_queue_size(self, queue):
        assert len(queue) == 0
        queue.push({"a": 1})
        assert len(queue) == 1
        queue.push({"b": 2})
        assert len(queue) == 2
        queue.pop()
        assert len(queue) == 1


class TestActionQueueAtomicWrite:
    def test_write_creates_file(self, queue, sample_post_action):
        queue.push(sample_post_action)
        assert queue.path.exists()

    def test_write_is_valid_json(self, queue, sample_post_action):
        queue.push(sample_post_action)
        content = json.loads(queue.path.read_text())
        assert isinstance(content, list)
        assert len(content) == 1

    def test_no_tmp_file_left_after_write(self, queue, sample_post_action):
        queue.push(sample_post_action)
        tmp = queue.path.with_suffix(".tmp")
        assert not tmp.exists()

    def test_corrupt_json_returns_empty_list(self, queue):
        queue.path.write_text("not valid json {{{{")
        result = queue.pop()
        assert result is None


class TestActionQueueDeadLetter:
    def test_dead_letter_appends_to_dead_letter_file(self, queue, sample_post_action):
        queue.dead_letter(sample_post_action)
        assert queue.dead_letter_path.exists()
        content = json.loads(queue.dead_letter_path.read_text())
        assert len(content) == 1
        assert content[0] == sample_post_action

    def test_dead_letter_accumulates(self, queue):
        queue.dead_letter({"id": 1})
        queue.dead_letter({"id": 2})
        content = json.loads(queue.dead_letter_path.read_text())
        assert len(content) == 2

    def test_dead_letter_does_not_modify_main_queue(self, queue, sample_post_action):
        queue.push(sample_post_action)
        queue.dead_letter({"bad": "action"})
        assert len(queue) == 1


# ------------------------------------------------------------------ #
# process_queue_once tests
# ------------------------------------------------------------------ #


class TestProcessQueueOnce:
    def _make_mock_adapter(self, login_ok=True, action_ok=True):
        adapter = MagicMock()
        adapter.login.return_value = login_ok
        adapter.post.return_value = action_ok
        adapter.comment.return_value = action_ok
        adapter.reply.return_value = action_ok
        return adapter

    def test_returns_false_when_queue_empty(self, tmp_path):
        from src.orchestrator import process_queue_once

        result = process_queue_once(queue_path=str(tmp_path / "queue.json"))
        assert result is False

    def test_returns_true_when_action_processed(self, tmp_path, sample_post_action):
        from src.orchestrator import process_queue_once, ActionQueue

        q = ActionQueue(path=tmp_path / "queue.json")
        q.push(sample_post_action)

        mock_bot = MagicMock()
        mock_bot.ask.return_value = "Generated post text."
        mock_adapter = self._make_mock_adapter()

        with patch("src.orchestrator.get_reddit_adapter", return_value=mock_adapter), \
             patch("src.orchestrator._get_bot_from_config", return_value=mock_bot):
            result = process_queue_once(queue_path=str(tmp_path / "queue.json"))

        assert result is True

    def test_drops_unsupported_platform(self, tmp_path):
        from src.orchestrator import process_queue_once, ActionQueue

        q = ActionQueue(path=tmp_path / "queue.json")
        q.push({"action": "post", "platform": "twitter", "prompt": "hi"})

        result = process_queue_once(queue_path=str(tmp_path / "queue.json"))
        assert result is True
        assert len(q) == 0  # consumed, not re-queued

    def test_drops_action_with_no_prompt(self, tmp_path):
        from src.orchestrator import process_queue_once, ActionQueue

        q = ActionQueue(path=tmp_path / "queue.json")
        q.push({"action": "post", "platform": "reddit", "prompt": ""})

        result = process_queue_once(queue_path=str(tmp_path / "queue.json"))
        assert result is True
        assert len(q) == 0

    def test_drops_comment_missing_url(self, tmp_path):
        from src.orchestrator import process_queue_once, ActionQueue

        q = ActionQueue(path=tmp_path / "queue.json")
        q.push({"action": "comment", "platform": "reddit", "prompt": "say hi", "url": ""})

        result = process_queue_once(queue_path=str(tmp_path / "queue.json"))
        assert result is True
        assert len(q) == 0

    def test_login_failure_requeues_with_retry_count(self, tmp_path, sample_post_action):
        from src.orchestrator import process_queue_once, ActionQueue

        q = ActionQueue(path=tmp_path / "queue.json")
        q.push(sample_post_action)

        mock_bot = MagicMock()
        mock_bot.ask.return_value = "text"
        mock_adapter = self._make_mock_adapter(login_ok=False)

        with patch("src.orchestrator.get_reddit_adapter", return_value=mock_adapter), \
             patch("src.orchestrator._get_bot_from_config", return_value=mock_bot):
            process_queue_once(queue_path=str(tmp_path / "queue.json"))

        requeued = q.pop()
        assert requeued is not None
        assert requeued["_retry_count"] == 1

    def test_exceeding_max_retries_sends_to_dead_letter(self, tmp_path, sample_post_action):
        from src.orchestrator import process_queue_once, ActionQueue, MAX_RETRIES

        dl_path = tmp_path / "dl.json"
        q = ActionQueue(path=tmp_path / "queue.json", dead_letter_path=dl_path)
        action = {**sample_post_action, "_retry_count": MAX_RETRIES}
        q.push(action)

        mock_bot = MagicMock()
        mock_bot.ask.return_value = "text"
        mock_adapter = self._make_mock_adapter(login_ok=False)

        with patch("src.orchestrator.get_reddit_adapter", return_value=mock_adapter), \
             patch("src.orchestrator._get_bot_from_config", return_value=mock_bot):
            process_queue_once(
                queue_path=str(tmp_path / "queue.json"),
                dead_letter_path=str(dl_path),
            )

        # Queue should be empty
        assert len(q) == 0
        # Dead letter should have the action
        dl_content = json.loads(dl_path.read_text())
        assert len(dl_content) == 1

    def test_post_action_calls_adapter_post(self, tmp_path, sample_post_action):
        from src.orchestrator import process_queue_once, ActionQueue

        q = ActionQueue(path=tmp_path / "queue.json")
        q.push({**sample_post_action, "subreddit": "python"})

        mock_bot = MagicMock()
        mock_bot.ask.return_value = "Generated text."
        mock_adapter = self._make_mock_adapter()

        with patch("src.orchestrator.get_reddit_adapter", return_value=mock_adapter), \
             patch("src.orchestrator._get_bot_from_config", return_value=mock_bot):
            process_queue_once(queue_path=str(tmp_path / "queue.json"))

        mock_adapter.post.assert_called_once()
        call_args = mock_adapter.post.call_args[0]
        assert call_args[0] == "python"

    def test_comment_action_calls_adapter_comment(self, tmp_path, sample_comment_action):
        from src.orchestrator import process_queue_once, ActionQueue

        q = ActionQueue(path=tmp_path / "queue.json")
        q.push(sample_comment_action)

        mock_bot = MagicMock()
        mock_bot.ask.return_value = "A comment."
        mock_adapter = self._make_mock_adapter()

        with patch("src.orchestrator.get_reddit_adapter", return_value=mock_adapter), \
             patch("src.orchestrator._get_bot_from_config", return_value=mock_bot):
            process_queue_once(queue_path=str(tmp_path / "queue.json"))

        mock_adapter.comment.assert_called_once_with(
            sample_comment_action["url"], "A comment."
        )

    def test_provided_bot_is_used_instead_of_creating_new(self, tmp_path, sample_post_action):
        from src.orchestrator import process_queue_once, ActionQueue

        q = ActionQueue(path=tmp_path / "queue.json")
        q.push(sample_post_action)

        mock_bot = MagicMock()
        mock_bot.ask.return_value = "text"
        mock_adapter = self._make_mock_adapter()

        with patch("src.orchestrator.get_reddit_adapter", return_value=mock_adapter), \
             patch("src.orchestrator._get_bot_from_config") as mock_factory:
            process_queue_once(
                queue_path=str(tmp_path / "queue.json"), bot=mock_bot
            )
            # Should NOT call the factory when bot is provided
            mock_factory.assert_not_called()

    def test_adapter_is_always_closed(self, tmp_path, sample_post_action):
        from src.orchestrator import process_queue_once, ActionQueue

        q = ActionQueue(path=tmp_path / "queue.json")
        q.push(sample_post_action)

        mock_bot = MagicMock()
        mock_bot.ask.return_value = "text"
        mock_adapter = self._make_mock_adapter()

        with patch("src.orchestrator.get_reddit_adapter", return_value=mock_adapter), \
             patch("src.orchestrator._get_bot_from_config", return_value=mock_bot):
            process_queue_once(queue_path=str(tmp_path / "queue.json"))

        mock_adapter.close.assert_called_once()
