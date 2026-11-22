# telefwd

## What the project does

`telefwd` is a one-way Telegram-to-IRC bridge built with Telethon and Python 3.12+. It loads parser definitions for configured Telegram groups, converts messages into structured fields, and posts formatted messages to mapped IRC channels.

## Configuration

Install dependencies with uv:

```bash
uv sync
uv sync --extra dev --group dev
```

Set these environment variables:

- `TELEGRAM_API_ID` — Telegram API ID
- `TELEGRAM_API_HASH` — Telegram API hash
- `TELEGRAM_PHONE_NUMBER` — phone number used by the Telethon client
- `TELEGRAM_SESSION` — optional Telethon session-file path; defaults to `session_name2`
- `IRC_HOST` — IRC server hostname;
- `IRC_PORT` — optional IRC port; defaults to `6697`
- `IRC_NICK` — optional IRC nickname; defaults to `tg-relay`
- `IRC_USER` — optional IRC username; defaults to `tg-relay`
- `IRC_REALNAME` — optional IRC real name; defaults to `Telegram Relay Bridge`
- `IRC_NICKSERV_PASS` — optional NickServ IDENTIFY password
- `IRC_TLS_INSECURE` — allow unverified TLS certificates; defaults to `true` for private/self-signed IRC certificates. This disables certificate and hostname verification.
- `BRIDGE_CONFIG` — optional bridge YAML path; defaults to `config/bridge.yaml`

Configure routes in the `bridges` list in `config/bridge.yaml`. Each route specifies:

```yaml
bridges:
  - source_name: divteam
    definition: divteam
    telegram_group_id: -1001234567890
    irc_channel: "#divteam"
```

`definition` selects `telefwd/definitions/<definition>.yaml`. Replace the sample group ID and channel with values for your setup. Keep credentials and Telethon session files out of version control.

## Running and development

Run locally with `uv run python -u telefwd/main.py` or `uv run telefwd`.
Copy `.env.example` to `.env` and set your Telegram credentials and optional NickServ password.
To download the latest 10 messages from each configured Telegram group into `mocks/<source_name>/` for analysis, run `uv run python -m telefwd.download_messages` or select the matching launch configuration in VS Code.
To replay the latest 10 messages from each configured group through the same message handler and send eligible Movie/TV announcements to IRC, run `uv run python -m telefwd.replay_messages` or select `telefwd: replay latest Telegram messages to IRC` in VS Code. Replay sends oldest-to-newest within each group.

Build and run with Docker:

```bash
docker build -t telefwd .
docker run --env-file .env telefwd
```

Development checks:

```bash
uv run ruff check telefwd/ tests/
uv run mypy telefwd/
uv run pytest
uv run pytest tests/test_parser.py::test_divteam_parser_extracts_series_fields
```

## Runtime flow

Startup loads environment values and YAML routes, validates the referenced definition files, connects to IRC and joins configured channels, then starts Telethon and verifies access to configured Telegram groups. Each incoming message is saved under `mocks/<source_name>/`, then routed through its source-specific parser. Movie and TV releases with a detected torrent URL are announced as a single IRC line with stable fields: `TYPE`, `TITLE`, `YEAR`, `SEASON`, `EPISODE`, `SIZE`, `URL`, `AUDIO`, `SUBS`, `QUALITY`, `SOURCE`, `CODEC`, `IMDB`, and `TMDB`. Non-movie/TV posts are retained as raw JSON samples but are not announced.
