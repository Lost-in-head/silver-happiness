#!/usr/bin/env python3
"""Entry point: start the FastAPI chatbot API server with uvicorn.

Usage:
    python serve.py                        # default: 0.0.0.0:8000
    python serve.py --host 127.0.0.1 --port 8080
    python serve.py --reload               # dev hot-reload
    python serve.py --workers 4            # production multi-worker

Environment variables (see .env.example for the full list):
    OPENROUTER_API_KEY  – Required for the openrouter LLM provider.
    API_KEYS            – Comma-separated valid API keys (auth disabled if empty).
    CORS_ORIGINS        – Comma-separated allowed origins (default: *).
    LOG_LEVEL           – DEBUG | INFO | WARNING | ERROR (default: WARNING).
"""

import sys
from pathlib import Path

# Make src/ importable when running as a script from the social/ directory.
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import click
import uvicorn


@click.command()
@click.option("--host", default="0.0.0.0", show_default=True, help="Bind address.")
@click.option("--port", default=8000, show_default=True, type=int, help="TCP port.")
@click.option("--reload", is_flag=True, default=False, help="Enable hot-reload (dev only).")
@click.option(
    "--workers",
    default=1,
    show_default=True,
    type=int,
    help="Number of worker processes (>1 disables --reload).",
)
@click.option("--log-level", default="warning", show_default=True, help="Uvicorn log level.")
def serve(host: str, port: int, reload: bool, workers: int, log_level: str):
    """Run the Social AI Bot HTTP API server."""
    if workers > 1 and reload:
        click.echo("Warning: --reload is ignored when --workers > 1.", err=True)
        reload = False

    uvicorn.run(
        "src.api.app:app",
        host=host,
        port=port,
        reload=reload,
        workers=workers if not reload else 1,
        log_level=log_level,
    )


if __name__ == "__main__":
    serve()
