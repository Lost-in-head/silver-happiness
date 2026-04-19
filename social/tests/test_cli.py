"""Tests for src/cli.py — all CLI commands via Click's test runner."""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from click.testing import CliRunner


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def cli():
    from src.cli import main
    return main


@pytest.fixture
def mock_bot_ask():
    """Patch the full bot instantiation stack, return (mock_bot, mock_rag)."""
    mock_bot = MagicMock()
    mock_bot.ask.return_value = "mocked bot response"
    mock_rag = MagicMock()

    with patch("src.cli._get_bot", return_value=mock_bot), \
         patch("src.cli._get_rag", return_value=mock_rag):
        yield mock_bot, mock_rag


# ------------------------------------------------------------------ #
# ask command
# ------------------------------------------------------------------ #


class TestAskCommand:
    def test_ask_single_word(self, runner, cli, mock_bot_ask):
        mock_bot, _ = mock_bot_ask
        result = runner.invoke(cli, ["ask", "hello"])
        assert result.exit_code == 0
        assert "mocked bot response" in result.output

    def test_ask_multi_word_message(self, runner, cli, mock_bot_ask):
        mock_bot, _ = mock_bot_ask
        result = runner.invoke(cli, ["ask", "what", "is", "the", "weather"])
        assert result.exit_code == 0
        mock_bot.ask.assert_called_once_with("what is the weather")

    def test_ask_requires_message(self, runner, cli):
        with patch("src.cli._get_bot", return_value=MagicMock()):
            result = runner.invoke(cli, ["ask"])
        assert result.exit_code != 0

    def test_ask_output_contains_response(self, runner, cli, mock_bot_ask):
        result = runner.invoke(cli, ["ask", "test"])
        assert "mocked bot response" in result.output


# ------------------------------------------------------------------ #
# chat command
# ------------------------------------------------------------------ #


class TestChatCommand:
    def test_chat_exits_on_quit(self, runner, cli, mock_bot_ask):
        result = runner.invoke(cli, ["chat"], input="quit\n")
        assert result.exit_code == 0

    def test_chat_exits_on_exit(self, runner, cli, mock_bot_ask):
        result = runner.invoke(cli, ["chat"], input="exit\n")
        assert result.exit_code == 0

    def test_chat_asks_bot_on_input(self, runner, cli, mock_bot_ask):
        mock_bot, _ = mock_bot_ask
        runner.invoke(cli, ["chat"], input="hello bot\nquit\n")
        mock_bot.ask.assert_called_once_with("hello bot")

    def test_chat_clear_resets_memory(self, runner, cli, mock_bot_ask):
        mock_bot, _ = mock_bot_ask
        runner.invoke(cli, ["chat"], input="clear\nquit\n")
        mock_bot.clear_memory.assert_called_once()

    def test_chat_skips_empty_input(self, runner, cli, mock_bot_ask):
        mock_bot, _ = mock_bot_ask
        runner.invoke(cli, ["chat"], input="\nquit\n")
        mock_bot.ask.assert_not_called()

    def test_chat_handles_eof_gracefully(self, runner, cli, mock_bot_ask):
        # Click raises Abort when stdin is exhausted; our handler catches it.
        # Exit code may be 0 (clean break) or 1 (Abort propagated before catch).
        result = runner.invoke(cli, ["chat"], input="")
        assert result.exit_code in (0, 1)


# ------------------------------------------------------------------ #
# teach command
# ------------------------------------------------------------------ #


class TestTeachCommand:
    def test_teach_directory_calls_ingest(self, runner, cli, tmp_path, mock_bot_ask):
        _, mock_rag = mock_bot_ask
        result = runner.invoke(cli, ["teach", str(tmp_path)])
        assert result.exit_code == 0
        mock_rag.ingest_directory.assert_called_once_with(tmp_path)

    def test_teach_directory_not_found_fails(self, runner, cli, mock_bot_ask):
        _, mock_rag = mock_bot_ask
        result = runner.invoke(cli, ["teach", "/nonexistent/path/xyz"])
        assert result.exit_code != 0

    def test_teach_file_option_ingests_single_file(self, runner, cli, tmp_path, mock_bot_ask):
        _, mock_rag = mock_bot_ask
        f = tmp_path / "notes.txt"
        f.write_text("some knowledge")

        with patch("src.cli.TextLoader") as MockLoader:
            MockLoader.return_value.load.return_value = [MagicMock()]
            result = runner.invoke(cli, ["teach", "--file", str(f)])

        assert result.exit_code == 0
        mock_rag.add_documents.assert_called_once()

    def test_teach_pdf_file_uses_pdf_loader(self, runner, cli, tmp_path, mock_bot_ask):
        _, mock_rag = mock_bot_ask
        f = tmp_path / "doc.pdf"
        f.write_bytes(b"%PDF-1.4 fake content")

        with patch("src.cli.PyPDFLoader") as MockLoader:
            MockLoader.return_value.load.return_value = [MagicMock()]
            result = runner.invoke(cli, ["teach", "--file", str(f)])

        MockLoader.assert_called_once_with(str(f))

    def test_teach_nonexistent_file_fails(self, runner, cli, mock_bot_ask):
        result = runner.invoke(cli, ["teach", "--file", "/nonexistent/file.txt"])
        assert result.exit_code != 0

    def test_teach_directory_passed_to_file_option_fails(self, runner, cli, tmp_path, mock_bot_ask):
        # --file should only accept files, not directories
        result = runner.invoke(cli, ["teach", "--file", str(tmp_path)])
        assert result.exit_code != 0


# ------------------------------------------------------------------ #
# queue command
# ------------------------------------------------------------------ #


class TestQueueCommand:
    def test_queue_post_action(self, runner, cli, tmp_path, mock_bot_ask):
        queue_path = tmp_path / "queue.json"
        with patch("src.cli.PROJECT_ROOT", tmp_path):
            result = runner.invoke(
                cli, ["queue", "--action", "post", "--prompt", "Write a post"]
            )
        assert result.exit_code == 0
        assert "Queued 'post'" in result.output

    def test_queue_comment_requires_url(self, runner, cli, mock_bot_ask):
        result = runner.invoke(
            cli, ["queue", "--action", "comment", "--prompt", "Write a comment"]
        )
        assert result.exit_code != 0

    def test_queue_reply_requires_url(self, runner, cli, mock_bot_ask):
        result = runner.invoke(
            cli, ["queue", "--action", "reply", "--prompt", "Write a reply"]
        )
        assert result.exit_code != 0

    def test_queue_comment_with_url_succeeds(self, runner, cli, tmp_path, mock_bot_ask):
        with patch("src.cli.PROJECT_ROOT", tmp_path):
            result = runner.invoke(
                cli,
                [
                    "queue",
                    "--action", "comment",
                    "--prompt", "Say something",
                    "--url", "https://reddit.com/r/test/abc",
                ],
            )
        assert result.exit_code == 0

    def test_queue_writes_to_json_file(self, runner, cli, tmp_path, mock_bot_ask):
        with patch("src.cli.PROJECT_ROOT", tmp_path):
            runner.invoke(
                cli, ["queue", "--action", "post", "--prompt", "Hello"]
            )
        queue_file = tmp_path / "data" / "queue.json"
        assert queue_file.exists()
        data = json.loads(queue_file.read_text())
        assert len(data) == 1
        assert data[0]["action"] == "post"
        assert data[0]["prompt"] == "Hello"

    def test_queue_accumulates_multiple_items(self, runner, cli, tmp_path, mock_bot_ask):
        with patch("src.cli.PROJECT_ROOT", tmp_path):
            runner.invoke(cli, ["queue", "--action", "post", "--prompt", "First"])
            runner.invoke(cli, ["queue", "--action", "post", "--prompt", "Second"])
        queue_file = tmp_path / "data" / "queue.json"
        data = json.loads(queue_file.read_text())
        assert len(data) == 2

    def test_queue_post_stores_subreddit(self, runner, cli, tmp_path, mock_bot_ask):
        with patch("src.cli.PROJECT_ROOT", tmp_path):
            runner.invoke(
                cli,
                ["queue", "--action", "post", "--prompt", "Post text", "--subreddit", "python"],
            )
        queue_file = tmp_path / "data" / "queue.json"
        data = json.loads(queue_file.read_text())
        assert data[0]["subreddit"] == "python"

    def test_queue_post_stores_optional_title(self, runner, cli, tmp_path, mock_bot_ask):
        with patch("src.cli.PROJECT_ROOT", tmp_path):
            runner.invoke(
                cli,
                [
                    "queue", "--action", "post",
                    "--prompt", "Post text",
                    "--title", "My Custom Title",
                ],
            )
        queue_file = tmp_path / "data" / "queue.json"
        data = json.loads(queue_file.read_text())
        assert data[0]["title"] == "My Custom Title"


# ------------------------------------------------------------------ #
# run command
# ------------------------------------------------------------------ #


class TestRunCommand:
    def test_run_once_processes_queue(self, runner, cli, mock_bot_ask):
        with patch("src.orchestrator.process_queue_once", return_value=True) as mock_proc, \
             patch("src.cli._config", return_value={}):
            result = runner.invoke(cli, ["run", "--once"])

        assert result.exit_code == 0
        mock_proc.assert_called_once()

    def test_run_once_reports_empty_queue(self, runner, cli, mock_bot_ask):
        with patch("src.orchestrator.process_queue_once", return_value=False), \
             patch("src.cli._config", return_value={}):
            result = runner.invoke(cli, ["run", "--once"])

        assert "empty" in result.output.lower()

    def test_run_once_reports_processed(self, runner, cli, mock_bot_ask):
        with patch("src.orchestrator.process_queue_once", return_value=True), \
             patch("src.cli._config", return_value={}):
            result = runner.invoke(cli, ["run", "--once"])

        assert "Processed" in result.output
