import asyncio
import base64
import logging
import os
import re
import ssl

from telefwd.bridge_config import Bridge
from telefwd.internal_types import IRCMessage

logger = logging.getLogger(__name__)
MAX_IRC_LINE_BYTES = 512


class MessageBroadcaster:
    def __init__(
        self,
        host: str,
        port: int = 6697,
        nick: str = "tg-relay",
        username: str = "tg-relay",
        realname: str = "Telegram Relay Bridge",
        nickserv_password: str = "",
        server_password: str | None = None,
        use_tls: bool = True,
        tls_insecure: bool = False,
        registration_timeout: float = 30,
    ):
        self.host = host
        self.port = port
        self.nick = nick
        self.username = username
        self.realname = realname
        self.nickserv_password = nickserv_password
        self.use_tls = use_tls
        self.tls_insecure = tls_insecure
        self.registration_timeout = registration_timeout
        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None
        self.channels: set[str] = set()
        self._registration_replies: list[str] = []
        self._connected = False
        self._reader_task: asyncio.Task[None] | None = None
        self._connect_lock = asyncio.Lock()
        self._write_lock = asyncio.Lock()
        self.server_password: str | None = None

    async def connect(self, channels: set[str]) -> None:
        self.channels = set(channels)
        async with self._connect_lock:
            if self._is_connected():
                return
            await self._disconnect_unlocked()
            await self._connect_unlocked()

    async def close(self) -> None:
        async with self._connect_lock:
            await self._disconnect_unlocked()

    async def broadcast(self, channel: str, message: IRCMessage) -> None:
        text = format_message(message)
        if not text:
            return

        prefix = f"PRIVMSG {channel} :"
        prefix_size = len(prefix.encode("utf-8"))
        max_text_size = MAX_IRC_LINE_BYTES - 2 - prefix_size
        if max_text_size <= 0:
            raise ValueError(f"IRC channel name is too long: {channel}")
        encoded_text = text.encode("utf-8")[:max_text_size]
        text = encoded_text.decode("utf-8", errors="ignore")
        line = f"{prefix}{text}"

        for attempt in range(2):
            try:
                await self._ensure_connected()
                await self._send_raw(line)
                return
            except (ConnectionError, OSError, TimeoutError):
                async with self._connect_lock:
                    await self._disconnect_unlocked()
                if attempt:
                    raise
                logger.warning("IRC delivery failed; reconnecting before retry")
        raise RuntimeError("IRC delivery failed without an error")

    async def _ensure_connected(self) -> None:
        async with self._connect_lock:
            if self._is_connected():
                return
            await self._disconnect_unlocked()
            await self._connect_unlocked()

    def _is_connected(self) -> bool:
        return (
            self._connected
            and self.writer is not None
            and not self.writer.is_closing()
            and self._reader_task is not None
            and not self._reader_task.done()
        )

    async def _connect_unlocked(self) -> None:
        context = None
        if self.use_tls:
            context = ssl.create_default_context()
            if self.tls_insecure:
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
        try:
            self.reader, self.writer = await asyncio.open_connection(
                self.host,
                self.port,
                ssl=context,
            )
            if self.server_password:
                await self._send_raw(f"PASS {self.server_password}")
            await self._send_raw("CAP LS 302")
            self._registration_replies.clear()
            try:
                await asyncio.wait_for(
                    self._wait_for_registration(),
                    timeout=self.registration_timeout,
                )
            except TimeoutError:
                replies = "; ".join(self._registration_replies)
                detail = (
                    f" Last server replies: {replies}"
                    if replies
                    else " No server replies received."
                )
                raise TimeoutError(
                    f"IRC server {self.host}:{self.port} did not send welcome numeric 001 "
                    f"within {self.registration_timeout:g} seconds.{detail}"
                ) from None
            for channel in sorted(self.channels):
                await self._send_raw(f"JOIN {channel}")
            self._connected = True
            self._reader_task = asyncio.create_task(self._read_loop())
        except BaseException:
            await self._disconnect_unlocked()
            raise

    async def _send_identity_and_end_cap(self) -> None:
        await self._send_raw(f"NICK {self.nick}")
        await self._send_raw(f"USER {self.username} 0 * :{self.realname}")
        await self._send_raw("CAP END")

    async def _wait_for_registration(self) -> None:
        if self.reader is None:
            raise ConnectionError("IRC reader is not connected")
        sasl_sent = False
        while True:
            data = await self.reader.readline()
            if not data:
                raise ConnectionError("IRC server closed the connection during registration")
            line = data.decode("utf-8", errors="replace").rstrip("\r\n")
            if len(self._registration_replies) < 10:
                self._registration_replies.append(line[:300])

            if line.startswith("PING "):
                await self._send_raw(f"PONG {line[5:]}")
            elif " CAP " in line and " LS " in line:
                if self.nickserv_password and "sasl" in line.lower() and not sasl_sent:
                    await self._send_raw("CAP REQ :sasl")
                else:
                    await self._send_identity_and_end_cap()
            elif " CAP " in line and " ACK " in line and "sasl" in line.lower():
                await self._send_raw("AUTHENTICATE PLAIN")
            elif line.startswith("AUTHENTICATE +"):
                token = base64.b64encode(
                    f"\0{self.nick}\0{self.nickserv_password}".encode()
                ).decode("ascii")
                await self._send_raw(f"AUTHENTICATE {token}")
                sasl_sent = True
            elif " 903 " in line:
                await self._send_identity_and_end_cap()
            elif " 904 " in line or " 905 " in line:
                raise ConnectionError(f"SASL authentication failed: {line}")
            elif " 001 " in line:
                return
            elif line.startswith("ERROR "):
                raise ConnectionError(f"IRC registration failed: {line}")

    async def _read_loop(self) -> None:
        if self.reader is None:
            raise ConnectionError("IRC reader is not connected")
        reader = self.reader
        try:
            while True:
                data = await reader.readline()
                if not data:
                    raise ConnectionError("IRC server closed the connection")
                line = data.decode("utf-8", errors="replace").rstrip("\r\n")
                if line.startswith("PING "):
                    await self._send_raw(f"PONG {line[5:]}")
        except asyncio.CancelledError:
            raise
        except (ConnectionError, OSError):
            logger.warning("IRC connection was closed")
        finally:
            self._connected = False

    async def _send_raw(self, line: str) -> None:
        if "\r" in line or "\n" in line:
            raise ValueError("IRC commands cannot contain line breaks")
        if len(line.encode("utf-8")) + 2 > MAX_IRC_LINE_BYTES:
            raise ValueError("IRC command exceeds the protocol line limit")
        async with self._write_lock:
            writer = self.writer
            if writer is None or writer.is_closing():
                raise ConnectionError("IRC writer is not connected")
            writer.write(f"{line}\r\n".encode())
            await writer.drain()

    async def _disconnect_unlocked(self) -> None:
        self._connected = False
        task = self._reader_task
        self._reader_task = None
        if task is not None and task is not asyncio.current_task() and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        writer = self.writer
        self.reader = None
        self.writer = None
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                logger.debug("Error while closing IRC connection", exc_info=True)


import re
import unicodedata


def _slugify_release_part(value: str) -> str:
    # Normalize accents (e.g., "Resurrección" -> "Resurreccion") and keep ASCII alphanumerics/dots
    normalized = unicodedata.normalize("NFKD", value)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^A-Za-z0-9]+", ".", ascii_only).strip(".")
    return re.sub(r"\.+", ".", cleaned)


def _build_release_name(message: IRCMessage, media_type: str) -> str:
    tokens: list[str] = []

    if message.title:
        title_part = _slugify_release_part(message.title)
        if title_part:
            tokens.append(title_part)

    if message.year is not None:
        tokens.append(str(message.year))

    if media_type == "tv":
        season_str = f"S{message.season:02d}" if message.season is not None else None
        episode_match = re.search(r"(?i)E(\d{1,3})", message.episode or "")
        episode_str = f"E{int(episode_match.group(1)):02d}" if episode_match else None
        if season_str and episode_str:
            tokens.append(f"{season_str}{episode_str}")
        elif season_str:
            tokens.append(season_str)
        elif episode_str:
            tokens.append(episode_str)

    if message.quality:
        tokens.append(_slugify_release_part(message.quality.lower()))

    if message.source:
        tokens.append(_slugify_release_part(message.source))

    if message.codec:
        tokens.append(_slugify_release_part(message.codec))

    if message.audio_languages:
        audio_tokens = [
            _slugify_release_part(lang)
            for lang in message.audio_languages
            if _slugify_release_part(lang)
        ]
        if audio_tokens:
            tokens.extend(audio_tokens)

    return ".".join(tokens)


def format_message(message: IRCMessage) -> str:
    if message.torrent and message.category in {"Movie", "Serie", "TV"}:
        media_type = "movie" if message.category == "Movie" else "tv"
        parts = [
            "[TELEFWD]",
            f"TYPE={media_type}",
        ]

        release_name = _build_release_name(message, media_type)
        if release_name:
            parts.append(f'NAME="{_quote_field(release_name)}"')

        if message.title:
            parts.append(f'TITLE="{_quote_field(message.title)}"')
        if message.year is not None:
            parts.append(f"YEAR={message.year}")
        if message.season is not None:
            parts.append(f"SEASON={message.season:02d}")
        if message.episode:
            episode_match = re.search(r"(?i)E(\d{1,3})", message.episode)
            if episode_match:
                parts.append(f"EPISODE={int(episode_match.group(1)):02d}")
        if message.size:
            parts.append(f'SIZE="{_quote_field(message.size)}"')

        parts.append(f"URL={message.torrent}")

        if message.audio_languages:
            parts.append(
                f'AUDIO="{_quote_field(", ".join(message.audio_languages))}"'
            )

        if message.subtitle_languages:
            # Cap subtitle list length so long multi-language sub lists don't push the IRC line over limit
            subs_preview = message.subtitle_languages[:6]
            if len(message.subtitle_languages) > 6:
                subs_preview.append(f"+{len(message.subtitle_languages) - 6}more")
            parts.append(
                f'SUBS="{_quote_field(", ".join(subs_preview))}"'
            )

        for key, value in (
            ("QUALITY", message.quality),
            ("SOURCE", message.source),
            ("CODEC", message.codec),
            ("IMDB", message.imdb),
            ("TMDB", message.tmdb),
        ):
            if value:
                parts.append(f"{key}={value}")

        line = " ".join(parts)
        # Keep a single IRC message within ~420 bytes if possible to avoid server line-splitting
        if len(line.encode("utf-8")) > 420 and message.subtitle_languages:
            parts = [p for p in parts if not p.startswith("SUBS=")]
            line = " ".join(parts)

        return line
    parts = [f"[{_clean_text(message.category)}]"]
    if message.title:
        parts.append(_clean_text(message.title))
    if message.episode:
        parts.append(_clean_text(message.episode))
    if message.year is not None:
        parts.append(str(message.year))
    if message.name:
        parts.append(f"- {_clean_text(message.name)}")
    if message.torrent:
        parts.append(_clean_text(message.torrent))
    return " ".join(parts)


def _clean_text(value: str) -> str:
    return " ".join(value.replace("\x00", "").split())


def _quote_field(value: str) -> str:
    return _clean_text(value).replace("\\", "\\\\").replace('"', '\\"')


def _parse_bool(value: str, name: str) -> bool:
    normalized = value.lower()
    if normalized not in ("true", "false"):
        raise ValueError(f"{name} must be 'true' or 'false'")
    return normalized == "true"

async def get_broadcaster(configured_bridges: list[Bridge]) -> MessageBroadcaster:
    logger.info("Connecting to IRC server...")
    irc_host = os.getenv("IRC_HOST")
    irc_port = int(os.getenv("IRC_PORT", "6697"))
    irc_nick = os.getenv("IRC_NICK", "tg-relay")
    irc_user = os.getenv("IRC_USER", "tg-relay")
    irc_realname = os.getenv("IRC_REALNAME", "Telegram Relay Bridge")
    irc_nickserv_password = os.getenv("IRC_NICKSERV_PASS", "")
    irc_tls_insecure = _parse_bool(
        os.getenv("IRC_TLS_INSECURE", "true"),
        "IRC_TLS_INSECURE",
    )
    if not 1 <= irc_port <= 65535:
        raise ValueError("IRC_PORT must be between 1 and 65535")
    if not irc_host.strip():
        raise ValueError("IRC_HOST must not be empty")

    broadcaster = MessageBroadcaster(
        host=irc_host,
        port=irc_port,
        nick=irc_nick,
        username=irc_user,
        realname=irc_realname,
        nickserv_password=irc_nickserv_password,
        use_tls=True,
        tls_insecure=irc_tls_insecure,
    )
    
    channels = {bridge.irc_channel for bridge in configured_bridges}
    await broadcaster.connect(channels)
    return broadcaster
