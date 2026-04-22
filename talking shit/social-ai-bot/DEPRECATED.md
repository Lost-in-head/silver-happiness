# ⚠️ DEPRECATED — This folder is no longer maintained

> **Use [`social/`](../social/) instead.**  
> All active development, bug fixes, and features happen in `social/`.

This directory (`talking shit/social-ai-bot/`) was the original prototype.  
It is kept only to preserve git history and **must not be deployed**.

## Differences from the active codebase (`social/`)

| Feature | `social/` (active) | `talking shit/social-ai-bot/` (archived) |
|---------|-------------------|------------------------------------------|
| LLM backend | OpenRouter (any model) | OpenAI API only |
| Test suite | ✅ Full unit tests | ❌ None |
| Web API | ✅ FastAPI (`serve.py`) | ❌ CLI only |
| Docker | ✅ Production Dockerfile | Basic |
| Dead-letter queue | ✅ Retry + DLQ | ❌ |

## Migration

If you have `config.yaml` or `data/` from this prototype:

1. Copy `config.yaml` → `social/config.yaml` and update `llm.provider` to `openrouter`.
2. Copy `data/chroma/` → `social/data/chroma/` (vector store is compatible).
3. Follow the Quick Start in [`social/README.md`](../social/README.md).
