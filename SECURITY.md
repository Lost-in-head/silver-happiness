# Security Policy

## Supported Versions

Only the latest release in the `main` branch is actively supported.

| Version / Branch | Supported |
|-----------------|-----------|
| `main` (latest) | ✅ |
| Older commits   | ❌ |

The legacy `talking shit/social-ai-bot/` directory is **archived and unsupported**.

---

## Reporting a Vulnerability

Please **do not** open a public GitHub issue for security vulnerabilities.

Report security issues privately by emailing the repository owner or by using
[GitHub's private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing/privately-reporting-a-security-vulnerability)
on this repository.

Include:
- A description of the vulnerability and its potential impact.
- Steps to reproduce or a minimal proof-of-concept.
- The affected component(s) and version/commit.

You can expect an acknowledgement within **72 hours** and a status update within **7 days**.

---

## Security Considerations for Operators

### API keys
- Set `API_KEYS` in your `.env` file before any public deployment.
- Rotate keys immediately if they are exposed.
- Never commit `.env` to version control (it is in `.gitignore`).

### CORS
- Change `CORS_ORIGINS=*` to your exact website origin(s) in production.

### LLM credentials
- `OPENROUTER_API_KEY` is a billing credential. Treat it like a password.
- Set spending limits in your OpenRouter dashboard.

### Reddit credentials
- Reddit browser automation violates Reddit's ToS.
- If used, `REDDIT_PASSWORD` should be for a **dedicated bot account**, not your personal account.

### Rate limiting
- The default limit (30 req/min/IP) is a baseline. Adjust `RATE_LIMIT_RPM` based on your traffic.

### Dependencies
- Keep dependencies updated. Run `pip install -r requirements.txt --upgrade` regularly.
- Review [GitHub's Dependabot alerts](../../security/dependabot) for this repository.

