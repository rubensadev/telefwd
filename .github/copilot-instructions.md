# Repository Guidelines

## Stack and commands

- Python 3.12+; use `uv` for dependencies and commands. The distribution is named `telewd`; the import package and command are `telefwd`.
- Install runtime and development dependencies with `uv sync --extra dev --group dev`.
- Run locally with `uv run python -u telefwd/main.py` or `uv run telefwd`.
- Lint with `uv run ruff check telefwd/ tests/`; type-check with `uv run mypy telefwd/`; run tests with `uv run pytest`.
- Run one test file with `uv run pytest tests/test_parser.py` or one test with `uv run pytest tests/test_parser.py::test_divteam_parser_extracts_series_fields`.
- Build/run the container with `docker build -t telefwd .` and `docker run --env-file .env telefwd`.

## Configuration

`telefwd/main.py` reads `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `TELEGRAM_PHONE_NUMBER`, optional `TELEGRAM_SESSION` (defaults to `session_name2`), `IRC_HOST`, and optional `IRC_PORT`, `IRC_NICK`, `IRC_USER`, `IRC_REALNAME`, `IRC_NICKSERV_PASS`, and `IRC_TLS_INSECURE`. Defaults are `6697`, `tg-relay`, `tg-relay`, `Telegram Relay Bridge`, empty, and `true`. `IRC_NICKSERV_PASS` is sent in a NickServ `IDENTIFY` message after registration. `IRC_TLS_INSECURE=true` disables certificate and hostname verification; only use it for the intended private/self-signed IRC server. `BRIDGE_CONFIG` optionally overrides the default `config/bridge.yaml`. Use `.env.example` as the environment template.

Each item in the YAML `bridges` list has `source_name`, `definition`, `telegram_group_id`, and `irc_channel`. The `definition` value selects `telefwd/definitions/<definition>.yaml`. Keep credentials and Telethon session files out of commits.

## Architecture and conventions

- Startup loads and validates bridge/parser configuration, connects to IRC, then starts Telethon and verifies configured Telegram group IDs.
- `telefwd/bridge_config.py` constructs one route and preloaded parser per Telegram group. `telefwd/main.py` routes each new message by `event.chat_id`.
- `telefwd/parser.py` loads source-specific regex YAML definitions and returns the shared `IRCMessage` dataclass from `telefwd/internal_types.py`. Parsers consume message text and Telegram metadata so they can extract both release details and inline-button/entity URLs.
- `telefwd/telegram.py` saves raw messages to `mocks/<source_name>/` and broadcasts parsed Movie/TV releases only when a torrent URL is found.
- `telefwd/broadcaster.py` owns IRC registration, joins, PING/PONG, reconnect-on-delivery, and formatting parsed fields as `PRIVMSG`. Autobrr announcements use `TYPE=movie|tv`, `TITLE`, and optional metadata fields including `YEAR`, `SEASON`, `EPISODE`, `SIZE`, `URL`, `AUDIO`, `SUBS`, `QUALITY`, `SOURCE`, `CODEC`, `IMDB`, and `TMDB`. It applies IRC's 512-byte line limit including CRLF.
- Delivery is one-way from configured Telegram groups to IRC channels. Keep parsing independent of IRC formatting and transport.
- `AGENT.md` contains project setup details; update it when changing documented configuration or workflow.
