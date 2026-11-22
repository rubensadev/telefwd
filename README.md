# telefwd

`telefwd` is a one-way Telegram-to-IRC bridge. It watches configured Telegram groups, parses Movie and TV release posts, and sends structured announcements to mapped IRC channels. Messages that are not recognized as Movie/TV releases or have no torrent URL are saved as samples but are not announced.

## Requirements

- Python 3.12 or newer
- [uv](https://docs.astral.sh/uv/)
- A Telegram account that can access the source groups
- An IRC server and channels where the bridge account can connect and send messages

## Initialize the project

Clone the repository and enter its directory, then install the project and development dependencies:

```bash
uv sync --extra dev --group dev
```

Create a local environment file from the template:

```bash
cp .env.example .env
```

Edit `.env` and set your Telegram credentials and IRC server details. `.env` and the Telegram session file contain private credentials; do not commit or share them.

### Environment variables

Required Telegram settings:

| Variable | Description |
|---|---|
| `TELEGRAM_API_ID` | Telegram application API ID from [my.telegram.org](https://my.telegram.org). |
| `TELEGRAM_API_HASH` | Telegram application API hash from [my.telegram.org](https://my.telegram.org). |
| `TELEGRAM_PHONE_NUMBER` | Phone number for the Telegram account, including country code. On first run, Telethon may ask for the login code and two-step verification password. |

Telegram session:

| Variable | Description |
|---|---|
| `TELEGRAM_SESSION` | Optional path/name for Telethon's persistent session. Defaults to `session_name2` in the project directory. Keep the resulting session file private. |

IRC settings:

| Variable | Description |
|---|---|
| `IRC_HOST` | IRC server hostname. Required; for example, `irc.example.net`. |
| `IRC_PORT` | TLS listener port; defaults to `6697`. |
| `IRC_NICK` | Bot nickname; defaults to `tg-relay`. |
| `IRC_USER` | IRC username; defaults to `tg-relay`. |
| `IRC_REALNAME` | IRC real name; defaults to `Telegram Relay Bridge`. |
| `IRC_NICKSERV_PASS` | Optional password used for SASL authentication when the server advertises SASL. |
| `IRC_TLS_INSECURE` | Defaults to `true`. When true, skips TLS certificate and hostname verification; set to `false` when the server has a trusted certificate. |

Bridge settings:

| Variable | Description |
|---|---|
| `BRIDGE_CONFIG` | Optional path to the bridge YAML file. Defaults to `config/bridge.yaml`; relative paths are resolved from the current working directory. |

Example `.env` values (replace placeholders with your own):

```dotenv
TELEGRAM_API_ID=123456
TELEGRAM_API_HASH=replace_with_your_api_hash
TELEGRAM_PHONE_NUMBER=+15551234567
TELEGRAM_SESSION=session_name2

IRC_HOST=irc.example.net
IRC_PORT=6697
IRC_NICK=tg-relay
IRC_USER=tg-relay
IRC_REALNAME=Telegram Relay Bridge
IRC_NICKSERV_PASS=
IRC_TLS_INSECURE=false

BRIDGE_CONFIG=config/bridge.yaml
```

## Configure Telegram-to-IRC routes

Edit `config/bridge.yaml`. Each entry connects one Telegram group to an IRC channel and a parser definition:

```yaml
bridges:
  - source_name: movies
    definition: movies
    telegram_group_id: -1001234567890
    irc_channel: "#movies"
  - source_name: tv
    definition: tv
    telegram_group_id: -1009876543210
    irc_channel: "#tv"
```

- `source_name` is a descriptive name. Raw Telegram samples are saved in `mocks/<source_name>/`.
- `definition` is the YAML definition filename, without `.yaml`, under `telefwd/definitions/`.
- `telegram_group_id` must be an integer ID for a group the logged-in Telegram account can access. Do not quote the number.
- `irc_channel` is the destination IRC channel, including its prefix such as `#`.

The repository includes routes and parser definitions for DivTeam Ocio, DivTeam Cultura, Torrentland, and Nobs. Replace their sample IDs/channels or add/remove entries to match your setup. Each Telegram group ID must be unique.

## Configure parser definitions

Create `telefwd/definitions/<definition>.yaml` for each distinct message format and use the same filename stem as `definition` in `bridge.yaml`. Definitions use Python regular expressions; use single-quoted YAML strings to avoid YAML interpreting backslashes.

Supported `parser` fields:

| Field | Purpose |
|---|---|
| `movie_pattern` | Regex matching a Movie post. |
| `series_pattern` | Regex matching a TV/series post. |
| `release_pattern` | Required regex; its first captured group is the release name used to derive the title and quality metadata. |
| `size_pattern` | Optional regex capturing the displayed size. |
| `year_pattern` | Optional regex capturing the release year. If no year is found here, the parser also checks the release name. |
| `audio_pattern` | Optional regex capturing an audio metadata line; language names/codes and supported flag emojis are normalized. |
| `subtitles_pattern` | Optional regex capturing a subtitle metadata line. |

For example, a source with `🎬 Title: Example Film 2025 1080p WEB-DL` and a `📦 Size: 4.2 GB` line could use:

```yaml
parser:
  movie_pattern: '(?im)^Category:\s*Movies?\b'
  series_pattern: '(?im)^Category:\s*TV\b'
  release_pattern: '(?im)^🎬\s*Title:\s*(.+?)\s*$'
  size_pattern: '(?im)^📦\s*Size:\s*([0-9.,]+\s*(?:GiB|GB|MB|KB|B))'
  year_pattern: '\b((?:19|20)\d{2})\b'
  audio_pattern: '(?im)^🔊\s*Audio:\s*(.+?)\s*$'
  subtitles_pattern: '(?im)^💬\s*Subs:\s*(.+?)\s*$'
```

Test a definition against saved sample messages before using it. Sample JSON is written to `mocks/<source_name>/` and is ignored by Git. Run `uv run python -m telefwd.download_messages` to fetch the latest 10 messages from each configured group for inspection.

The parser reads torrent links from Telegram message entities, inline buttons, or URLs in the post text. A post is announced only when its category matches the Movie or series pattern and a torrent URL is found.

## Run the bridge

Start the live Telegram-to-IRC bridge:

```bash
uv run telefwd
```

Alternatively:

```bash
uv run python -m telefwd.main
```

On the first launch, complete Telegram's interactive login if prompted. The saved Telethon session is reused on subsequent starts.

## Fetch or replay recent messages

Fetch the latest 10 messages from each configured Telegram group and save them for parser development, without sending to IRC:

```bash
uv run python -m telefwd.download_messages
```

Replay the latest 10 messages from each group through the normal handler and send eligible Movie/TV posts to IRC:

```bash
uv run python -m telefwd.replay_messages
```

Replay sends messages oldest-to-newest within each group. Both commands are also available as launch configurations in VS Code; choose the appropriate `telefwd:` entry from Run and Debug.

## IRC announcement format

Movie/TV announcements are sent as a single IRC message with fields such as:

```text
[TELEFWD] TYPE=tv NAME="Example Show S01E02 1080p WEB-DL" TITLE="Example Show" YEAR=2025 SEASON=01 EPISODE=02 SIZE="1.4 GiB" URL=https://tracker.example/torrents/123 AUDIO="English, Spanish" QUALITY=1080P SOURCE=WEB-DL CODEC=H264
```

Available fields include `TYPE`, `NAME`, `TITLE`, `YEAR`, `SEASON`, `EPISODE`, `SIZE`, `URL`, `AUDIO`, `SUBS`, `QUALITY`, `SOURCE`, `CODEC`, `IMDB`, and `TMDB`. Fields are omitted when not present in the source message. The IRC client limits messages to the IRC protocol's 512-byte line limit.

## Docker

Build and run with Docker:

```bash
docker build -t telefwd .
docker run --env-file .env telefwd
```

Persist the configured Telegram session path between container recreations, and ensure the container user can write to it.

## Development checks

```bash
uv run ruff check telefwd/ tests/
uv run mypy telefwd/
uv run pytest
```
