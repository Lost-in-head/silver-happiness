"""CLI: ask, teach, and run bot."""

import json
import os
import sys
from pathlib import Path

import click
from dotenv import load_dotenv

# Add project root so config and data paths work
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(PROJECT_ROOT / ".env")


def _load_config():
    import yaml
    config_path = PROJECT_ROOT / "config.yaml"
    if not config_path.exists():
        config_path = PROJECT_ROOT / "config.example.yaml"
    if not config_path.exists():
        return {}
    with open(config_path) as f:
        return yaml.safe_load(f) or {}


def _get_rag():
    cfg = _load_config()
    rag_cfg = cfg.get("rag", {})
    from src.rag.store import RAGStore
    return RAGStore(
        persist_directory=os.path.expanduser(rag_cfg.get("persist_directory", "./data/chroma")),
        collection_name=rag_cfg.get("collection_name", "bot_knowledge"),
        embedding_model=rag_cfg.get("embedding_model", "text-embedding-3-small"),
    )


def _get_bot():
    cfg = _load_config()
    rag = _get_rag()
    llm_cfg = cfg.get("llm", {})
    mem_cfg = cfg.get("memory", {})
    from src.bot.brain import Bot
    return Bot(
        rag=rag,
        model=llm_cfg.get("model", "gpt-4o-mini"),
        memory_window=mem_cfg.get("window_size", 10),
    )


@click.group()
def main():
    """Social AI Bot: ask, teach, and run."""
    pass


@main.command()
@click.argument("message", nargs=-1, required=True)
def ask(message):
    """Ask the bot (uses RAG and memory)."""
    text = " ".join(message)
    bot = _get_bot()
    click.echo(bot.ask(text))


@main.command()
@click.argument("path", type=click.Path(exists=True), default="data/knowledge")
@click.option("--file", "file_path", type=click.Path(exists=True), help="Ingest a single file instead of directory.")
def teach(path, file_path):
    """Ingest documents from a directory or file into the knowledge base."""
    rag = _get_rag()
    if file_path:
        path = Path(file_path)
        if path.is_dir():
            rag.ingest_directory(path)
        else:
            from langchain_community.document_loaders import TextLoader
            from langchain_community.document_loaders import PyPDFLoader
            suffix = path.suffix.lower()
            if suffix == ".pdf":
                docs = PyPDFLoader(str(path)).load()
            else:
                docs = TextLoader(str(path)).load()
            rag.add_documents(docs)
        click.echo(f"Ingested: {path}")
    else:
        rag.ingest_directory(path)
        click.echo(f"Ingested directory: {path}")


@main.command()
def chat():
    """Interactive chat with the bot (ask in a loop)."""
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
        except (EOFError, KeyboardInterrupt):
            break


@main.command()
@click.option("--action", type=click.Choice(["post", "comment", "reply"]), required=True)
@click.option("--prompt", required=True, help="Prompt for the bot to generate content.")
@click.option("--subreddit", default="test", help="For post: subreddit name.")
@click.option("--title", help="For post: optional title (else from prompt).")
@click.option("--url", help="For comment/reply: post or comment URL.")
def queue(action, prompt, subreddit, title, url):
    """Add a post/comment/reply action to the orchestrator queue."""
    root = PROJECT_ROOT / "data"
    root.mkdir(parents=True, exist_ok=True)
    queue_path = root / "queue.json"
    actions = []
    if queue_path.exists():
        try:
            with open(queue_path) as f:
                actions = json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    if action in ("comment", "reply") and not (url and url.strip()):
        raise click.UsageError("--url is required for comment and reply actions.")
    item = {"action": action, "platform": "reddit", "prompt": prompt}
    if action == "post":
        item["subreddit"] = subreddit
        if title:
            item["title"] = title
    if action in ("comment", "reply"):
        item["url"] = url.strip()
    actions.append(item)
    with open(queue_path, "w") as f:
        json.dump(actions, f, indent=2)
    click.echo(f"Queued {action}. Total items: {len(actions)}.")


@main.command()
@click.option("--interval", type=int, default=60, help="Seconds between queue processing.")
@click.option("--once", is_flag=True, help="Process one item and exit.")
def run(interval, once):
    """Process the action queue (scheduled or once)."""
    from src.orchestrator import process_queue_once, run_scheduled, _load_config
    config = _load_config()
    if once:
        process_queue_once(config)
        return
    run_scheduled(config, interval_seconds=interval)


if __name__ == "__main__":
    main()
