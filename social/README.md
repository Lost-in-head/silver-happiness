# social

A trainable social AI bot with RAG, browser automation for Reddit, and a file-based action queue.

Powered by **OpenRouter** (any LLM, your credits) + **local HuggingFace embeddings** (free, no API key for search).

---

## Quick start

```bash
cd social
cp config.example.yaml config.yaml
cp .env.example .env
# Edit .env — set OPENROUTER_API_KEY (required) and REDDIT_USERNAME/PASSWORD (for posting)

python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/playwright install chromium
```

Use `.venv/bin/python run_cli.py` or activate the venv for all commands below.

---

## Commands

### Ask / chat
```bash
python run_cli.py ask "Your question here"
python run_cli.py chat          # interactive loop; 'clear' resets memory, 'quit' exits
```

### Teach (add knowledge to RAG)
```bash
python run_cli.py teach                          # ingests data/knowledge/ directory
python run_cli.py teach /path/to/folder          # custom directory
python run_cli.py teach --file path/to/notes.md  # single file (.txt, .md, .pdf)
```

Re-running `teach` on the same directory **adds** to the store — it does not replace.
To reset: delete `data/chroma/` and run `teach` again.

### Queue and run (Reddit posting)
```bash
# Queue a post
python run_cli.py queue --action post --prompt "Write a short intro for r/python" --subreddit python

# Queue a comment
python run_cli.py queue --action comment \
  --prompt "Write a helpful comment" \
  --url "https://www.reddit.com/r/python/comments/abc123/"

# Process one item
python run_cli.py run --once

# Scheduled loop (every 5 minutes)
python run_cli.py run --interval 300
```

---

## Config

| File | Purpose |
|------|---------|
| `config.yaml` | LLM model, RAG settings, geolocation, platform creds (prefer `.env`) |
| `.env` | `OPENROUTER_API_KEY`, `REDDIT_USERNAME`, `REDDIT_PASSWORD`, `PROXY_URL` |

### Choosing a model

Set `llm.model` in `config.yaml` to any [OpenRouter model string](https://openrouter.ai/models), e.g.:
- `openai/gpt-4o-mini` (default, cheap)
- `anthropic/claude-3-haiku` 
- `meta-llama/llama-3-8b-instruct:free` (free tier)
- `google/gemini-flash-1.5`

### Using Ollama (local, no API key)
```yaml
llm:
  provider: ollama
  model: llama3
```
Set `OLLAMA_BASE_URL` in `.env` if not running on `localhost:11434`.

---

## Deployment

### Docker
```bash
docker build -t social .
docker run --env-file .env \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/config.yaml:/app/config.yaml \
  social ask "Hello"

docker run --env-file .env \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/config.yaml:/app/config.yaml \
  social run --interval 300
```

### VPS / systemd
Install Python 3.12, Playwright deps, and run as a systemd service or cron job.
Use a geo proxy so traffic appears from the intended region.

---

## Tests

```bash
pip install -r requirements.txt
pytest
```

All tests use mocks — no real API keys, no real browser, no filesystem side effects.

---

## Adding a new platform

See [`docs/new-platform-adapter.md`](docs/new-platform-adapter.md).

---

## ⚠️ Terms of Service

Automating posts and comments on Reddit via browser automation **violates Reddit's User Agreement**.
You are solely responsible for how and where you deploy this bot.
Consider the official [Reddit API + PRAW](https://praw.readthedocs.io/) for ToS-compliant automation.
