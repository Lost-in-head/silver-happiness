"""FastAPI application — HTTP wrapper around the chatbot brain.

Environment variables (all optional unless noted):
  OPENROUTER_API_KEY  – Required when provider=openrouter (set in .env)
  API_KEYS            – Comma-separated list of valid bearer/header keys.
                        If empty, authentication is DISABLED (dev-only).
  CORS_ORIGINS        – Comma-separated list of allowed origins (default: *).
                        Use explicit origins in production.
  RATE_LIMIT_RPM      – Max requests per minute per IP (default: 30).
  SESSION_TTL_SECONDS – Idle session expiry in seconds (default: 1800).
  MAX_SESSIONS        – Hard cap on concurrent sessions (default: 1000).
  LOG_LEVEL           – DEBUG | INFO | WARNING | ERROR (default: WARNING).
"""

from __future__ import annotations

import logging
import os
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Security, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security.api_key import APIKeyHeader

from src.config import get_bot, load_config
from .models import ChatRequest, ChatResponse, ClearResponse, HealthResponse
from .sessions import SessionStore, start_reaper

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "WARNING").upper(),
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration helpers (read once at import time)
# ---------------------------------------------------------------------------

load_dotenv()

_RAW_API_KEYS: list[str] = [
    k.strip() for k in os.environ.get("API_KEYS", "").split(",") if k.strip()
]
_AUTH_ENABLED: bool = bool(_RAW_API_KEYS)

_CORS_ORIGINS: list[str] = [
    o.strip() for o in os.environ.get("CORS_ORIGINS", "*").split(",") if o.strip()
] or ["*"]

_RATE_LIMIT_RPM: int = int(os.environ.get("RATE_LIMIT_RPM", "30"))

_SESSION_TTL: int = int(os.environ.get("SESSION_TTL_SECONDS", "1800"))
_MAX_SESSIONS: int = int(os.environ.get("MAX_SESSIONS", "1000"))

# ---------------------------------------------------------------------------
# Application lifespan — initialise shared resources once
# ---------------------------------------------------------------------------

_session_store: SessionStore | None = None
_shared_config: dict[str, Any] | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _session_store, _shared_config
    _shared_config = load_config()
    _session_store = SessionStore(ttl_seconds=_SESSION_TTL, max_sessions=_MAX_SESSIONS)
    start_reaper(_session_store)
    if not _AUTH_ENABLED:
        logger.warning(
            "API_KEYS is not set — authentication is DISABLED. "
            "Set API_KEYS in your .env for production deployments."
        )
    logger.info(
        "API started (auth=%s, cors_origins=%s, rate_limit=%d rpm).",
        _AUTH_ENABLED,
        _CORS_ORIGINS,
        _RATE_LIMIT_RPM,
    )
    yield
    # Cleanup (if any) on shutdown goes here


# ---------------------------------------------------------------------------
# App instance
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Social AI Bot API",
    description=(
        "HTTP API for the Social AI Bot. "
        "Send chat messages and receive AI-generated replies backed by RAG."
    ),
    version="1.0.0",
    lifespan=lifespan,
    # Disable /docs and /redoc in production by setting DOCS_DISABLED=1
    docs_url=None if os.environ.get("DOCS_DISABLED") else "/docs",
    redoc_url=None if os.environ.get("DOCS_DISABLED") else "/redoc",
)

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", "X-API-Key"],
)

# ---------------------------------------------------------------------------
# Rate limiting — sliding window per IP address
# ---------------------------------------------------------------------------

# {ip: [(timestamp, ...), ...]}
_rate_windows: dict[str, list[float]] = defaultdict(list)


def _check_rate_limit(ip: str) -> None:
    """Raise 429 if IP exceeds RATE_LIMIT_RPM requests in the last 60 seconds."""
    now = time.monotonic()
    window = _rate_windows[ip]
    # Purge timestamps older than 60 s
    cutoff = now - 60.0
    _rate_windows[ip] = [t for t in window if t > cutoff]
    if len(_rate_windows[ip]) >= _RATE_LIMIT_RPM:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please slow down.",
        )
    _rate_windows[ip].append(now)


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def _require_api_key(api_key: str | None = Security(_api_key_header)) -> str | None:
    """Validate the X-API-Key header when auth is enabled."""
    if not _AUTH_ENABLED:
        return None
    if not api_key or api_key not in _RAW_API_KEYS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key.",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    return api_key


# ---------------------------------------------------------------------------
# Helper to access the session store safely
# ---------------------------------------------------------------------------

def _get_store() -> SessionStore:
    if _session_store is None:
        raise RuntimeError("Session store not initialised.")
    return _session_store


def _get_config() -> dict[str, Any]:
    if _shared_config is None:
        raise RuntimeError("Config not initialised.")
    return _shared_config


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    tags=["meta"],
)
async def health():
    """Returns 200 OK when the service is up. No authentication required."""
    return HealthResponse()


@app.post(
    "/chat",
    response_model=ChatResponse,
    summary="Send a chat message",
    tags=["chat"],
)
async def chat(
    body: ChatRequest,
    request: Request,
    _key: str | None = Security(_require_api_key),
):
    """
    Send a message to the bot and receive a reply.

    - Supply a ``session_id`` from a previous response to continue a conversation.
    - Omit ``session_id`` (or pass ``null``) to start a fresh session.
    - The response always includes the ``session_id`` to use on the next request.
    """
    ip = request.client.host if request.client else "unknown"
    _check_rate_limit(ip)

    store = _get_store()
    config = _get_config()

    def _make_bot():
        return get_bot(config)

    try:
        session_id, bot = store.get_or_create(body.session_id, _make_bot)
    except Exception as exc:
        logger.exception("Failed to get/create session: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not initialise bot session.",
        ) from exc

    try:
        reply = bot.ask(body.message, use_rag=body.use_rag)
    except ValueError as exc:
        # e.g. missing API key
        logger.error("Bot configuration error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Bot.ask raised an unexpected error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The AI backend returned an error. Please try again.",
        ) from exc

    return ChatResponse(reply=reply, session_id=session_id)


@app.post(
    "/sessions/{session_id}/clear",
    response_model=ClearResponse,
    summary="Clear session memory",
    tags=["sessions"],
)
async def clear_session(
    session_id: str,
    _key: str | None = Security(_require_api_key),
):
    """Reset the conversation history for the given session without deleting it."""
    store = _get_store()
    found = store.clear(session_id)
    if not found:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found or expired.",
        )
    return ClearResponse(session_id=session_id)


@app.delete(
    "/sessions/{session_id}",
    response_model=ClearResponse,
    summary="Delete a session",
    tags=["sessions"],
)
async def delete_session(
    session_id: str,
    _key: str | None = Security(_require_api_key),
):
    """Remove a session and its memory entirely."""
    store = _get_store()
    existed = store.delete(session_id)
    if not existed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found or already expired.",
        )
    return ClearResponse(session_id=session_id)


# ---------------------------------------------------------------------------
# Global exception handler — never leak internal tracebacks
# ---------------------------------------------------------------------------

@app.exception_handler(Exception)
async def _global_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An unexpected internal error occurred."},
    )
