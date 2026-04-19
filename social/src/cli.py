"""CLI: ask, chat, teach, queue, run."""

import json
import logging
import os
import sys
from pathlib import Path

import click
from dotenv import load_dotenv
from langchain_community.document_loaders import TextLoader, PyPDFLoader

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(PROJECT_ROOT / ".env")

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "WARNING").upper(),
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)


def _config():
    from src.config import load_config
    return load_config()


def _get_bot():
    from src.config import get_bot
    return get_bot(_config())


def _get_rag():
    from src.config import get_rag
    return get_rag(_config())


# ------------------------------------------------------------------ #
# CLI group
# ------------------------------------------------------------------ #


@click.group()
def main():
    """Social AI Bot — powered by OpenRouter + local RAG."""


@main.command()
@click.argument("message", nargs=-1, required=True)
def ask(message):
    """Ask the bot a question (uses RAG and memory)."""
    text = " ".join(message)
    bot = _get_bot()
    click.echo(bot.ask(text))


@main.command()
def chat():
    """Interactive chat loop. Type 'quit', 'exit', or Ctrl-C to stop. 'clear' resets memory."""
    bot = _get_bot()
    click.echo("Chat with the bot. Type 'quit' or 'exit' to stop, 'clear' to reset memory.")
    while True:
        try:
            user = click.prompt("You", type=str, default="")
            if not user.strip():
                continue
            if user.strip().lower() in ("quit", "exit", "q"):
                break
            if user.strip().lower() == "clear":
                bot.clear_memory()
                click.echo("Memory cleared.")
                continue
            click.echo(bot.ask(user))
        except (EOFError, KeyboardInterrupt, click.exceptions.Abort):
            break


@main.command()
@click.argument("directory", type=click.Path(), default="data/knowledge", required=False)
@click.option(
    "--file",
    "file_path",
    type=click.Path(exists=True, file_okay=True, dir_okay=False, readable=True),
    help="Ingest a single file instead of a directory.",
)
def teach(directory, file_path):
    """Ingest documents into the RAG knowledge base.

    Pass a directory path (default: data/knowledge) or --file for a single file.
    Re-running on the same directory adds to the store — it does not replace.
    To start fresh, delete data/chroma/ and run teach again.
    """
    rag = _get_rag()
    if file_path:
        path = Path(file_path)
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            docs = PyPDFLoader(str(path)).load()
        else:
            docs = TextLoader(str(path)).load()
        rag.add_documents(docs)
        click.echo(f"Ingested: {path}")
    else:
        target = Path(directory)
        if not target.exists():
            raise click.UsageError(f"Directory not found: {target}")
        if not target.is_dir():
            raise click.UsageError(f"Path is not a directory: {target}. Use --file for single files.")
        rag.ingest_directory(target)
        click.echo(f"Ingested directory: {target}")


@main.command()
@click.option(
    "--action",
    type=click.Choice(["post", "comment", "reply"]),
    required=True,
    help="Type of action to queue.",
)
@click.option("--prompt", required=True, help="Prompt for the bot to generate content.")
@click.option("--subreddit", default="test", help="Subreddit name (for post actions).")
@click.option("--title", help="Post title (optional; bot generates one if omitted).")
@click.option("--url", help="Post or comment URL (required for comment/reply actions).")
def queue(action, prompt, subreddit, title, url):
    """Add a post, comment, or reply action to the orchestrator queue."""
    if action in ("comment", "reply") and not (url and url.strip()):
        raise click.UsageError("--url is required for comment and reply actions.")

    queue_path = PROJECT_ROOT / "data" / "queue.json"
    queue_path.parent.mkdir(parents=True, exist_ok=True)

    actions = []
    if queue_path.exists():
        try:
            with open(queue_path) as f:
                actions = json.load(f)
        except (json.JSONDecodeError, IOError):
            pass

    item: dict = {"action": action, "platform": "reddit", "prompt": prompt}
    if action == "post":
        item["subreddit"] = subreddit
        if title:
            item["title"] = title
    if action in ("comment", "reply"):
        item["url"] = url.strip()

    actions.append(item)
    with open(queue_path, "w") as f:
        json.dump(actions, f, indent=2)
    click.echo(f"Queued '{action}'. Total items in queue: {len(actions)}.")


@main.command()
@click.option("--interval", type=int, default=60, help="Seconds between queue checks.")
@click.option("--once", is_flag=True, help="Process one item and exit.")
def run(interval, once):
    """Process the action queue (scheduled loop or single run)."""
    from src.orchestrator import process_queue_once, run_scheduled
    config = _config()
    if once:
        processed = process_queue_once(config)
        click.echo("Processed one item." if processed else "Queue is empty.")
        return
    run_scheduled(config, interval_seconds=interval)


if __name__ == "__main__":
    main()

