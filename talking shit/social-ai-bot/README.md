# Social AI Bot

Trainable chatbot with RAG, optional browser automation for social platforms (Reddit first), geolocation support, and a file-based action queue for posting/commenting/replying.

## Quick start

1. **Setup**
   ```bash
   cd social-ai-bot
   cp config.example.yaml config.yaml
   cp .env.example .env
   # Edit .env: set OPENAI_API_KEY (required)
   python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
   .venv/bin/playwright install chromium
   ```
   Use `.venv/bin/python run_cli.py` (or activate the venv) for all commands below.

2. **Teach the bot** (add your or other-AI knowledge)
   ```bash
   python run_cli.py teach
   # Or: python run_cli.py teach --file path/to/notes.md
   ```

3. **Ask / chat**
   ```bash
   python run_cli.py ask "Your question here"
   python run_cli.py chat
   ```

4. **Reddit (optional)**  
   Set `REDDIT_USERNAME`, `REDDIT_PASSWORD` in `.env`. Queue an action and run:
   ```bash
   python run_cli.py queue --action post --prompt "Write a short intro post for r/test" --subreddit test
   python run_cli.py run --once
   ```

5. **Geolocation**  
   Set `PROXY_URL` in `.env` (e.g. `http://user:pass@geo-proxy.example.com:8080`) and `timezone_id` / `locale` in `config.yaml` under `geolocation`. The Reddit adapter uses these when launching the browser.

## Deployment (VPS / Docker)

- **Docker**
  ```bash
  docker build -t social-ai-bot .
  docker run --env-file .env -v $(pwd)/data:/app/data -it social-ai-bot ask "Hello"
  docker run --env-file .env -v $(pwd)/data:/app/data social-ai-bot run --interval 300
  ```
- **VPS**: Install Python 3.12, Playwright, deps; run with `systemd` or cron. Use a geo proxy so traffic appears from the desired region.

See **docs/** for:
- **Teaching data**: how to add knowledge (folder, files, formats).
- **New platform adapter**: how to add another site (e.g. Twitter) using the same pattern.

## Config

- `config.yaml`: LLM model, RAG path, memory size, platform credentials (or use env), geolocation (timezone, locale, optional proxy).
- `.env`: `OPENAI_API_KEY`, `REDDIT_USERNAME`, `REDDIT_PASSWORD`, `PROXY_URL`.

## Caveats

Automating posting/commenting on major social platforms may violate their Terms of Service. You are responsible for how and where you use this bot.
