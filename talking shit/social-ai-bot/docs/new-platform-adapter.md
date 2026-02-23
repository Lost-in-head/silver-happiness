# Adding a new platform adapter

The bot supports multiple social platforms via **platform adapters**: one class per site that handles login, post, comment, and reply using browser automation (Playwright).

## Pattern

1. **Base adapter** (`src/platforms/base.py`):  
   - Launches browser with optional proxy, timezone, locale.  
   - Provides `_random_delay()`, `_ensure_context()`, `close()`.  
   - Abstract methods: `login()`, `post()`, `comment()`, `reply()`.

2. **Concrete adapter** (e.g. `src/platforms/reddit.py`):  
   - Subclass `PlatformAdapter`, pass credentials and geo options to `super().__init__()`.  
   - In `_launch_browser` the base already uses `proxy_url`, `timezone_id`, `locale` for the browser context.  
   - Implement each action by navigating the site and filling/clicking (selectors).

3. **Factory** (`src/platforms/factory.py`):  
   - Add a `get_<platform>_adapter(config)` that reads config + env (credentials, geo) and returns the adapter instance.

4. **Orchestrator** (`src/orchestrator.py`):  
   - In `process_queue_once()`, branch on `action["platform"]` and call the right factory and adapter methods (e.g. for `platform == "twitter"` use `get_twitter_adapter(config)` and call `post`/`comment`/`reply` as needed).

## Steps to add e.g. Twitter/X

1. **Create `src/platforms/twitter.py`**
   - Subclass `PlatformAdapter`.
   - Implement `login()`: go to login page, fill username/email and password, submit; handle 2FA if required.
   - Implement `post()`: e.g. go to compose, fill text, submit (tweet).
   - Implement `comment()`: open tweet URL, find reply box, fill and submit.
   - Implement `reply()`: open reply context, fill and submit.
   - Use `self._get_page()` (or your own `_get_page()` that uses `_ensure_context()`), and `self._random_delay()` between steps.  
   - **Selectors**: Prefer data-testid or stable IDs; document that selectors may need updates when the site changes.

2. **Config and env**
   - In `config.example.yaml` under `platforms` add e.g. `twitter: { username: "", password: "" }`.
   - In `.env.example` add `TWITTER_USERNAME`, `TWITTER_PASSWORD` (or equivalent).
   - In `src/platforms/factory.py` add `get_twitter_adapter(config)` that reads those and returns `TwitterAdapter(...)` with same geo options (proxy, timezone, locale) as Reddit.

3. **Orchestrator and queue**
   - In `process_queue_once()`, when `action["platform"] == "twitter"`, get the Twitter adapter, login, then call `post`/`comment`/`reply` with the generated text and action params (e.g. tweet URL for comment/reply).
   - CLI `queue` command: extend `--platform` (e.g. `reddit` | `twitter`) and pass through to the queue item so the orchestrator picks the right adapter.

4. **Geolocation**
   - No extra work: the base adapter already applies `proxy_url`, `timezone_id`, and `locale` to the browser context. Your new adapter inherits that.

## Reddit as reference

- See `src/platforms/reddit.py` for full flow (login, post, comment, reply).
- See `src/platforms/factory.py` for `get_reddit_adapter()` (config + env, geo).
- See `src/orchestrator.py` for how the queue action is turned into one adapter call.

## Maintenance

Site layouts change. Plan to update selectors (and possibly flows) when a platform redesigns. Keeping one adapter per file and documenting “likely to break on site changes” in the adapter file helps.
