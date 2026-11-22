import asyncio
import inspect
import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Protocol

from telethon import TelegramClient

from telefwd.bridge_config import Bridge
from telefwd.broadcaster import MessageBroadcaster

logger = logging.getLogger(__name__)
MOCKS_ROOT = Path(__file__).resolve().parent.parent / "mocks"
ENABLE_TELEGRAM_MOCKS = os.getenv("ENABLE_TELEGRAM_MOCKS", "false").lower() in {"1", "true", "yes"}

class TelegramEvent(Protocol):
    @property
    def chat_id(self) -> int: ...

    @property
    def message(self) -> Any: ...


@dataclass(frozen=True)
class _HistoryEvent:
    chat_id: int
    message: Any


def _to_json_safe(obj: Any, seen: set[int] | None = None) -> Any:
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj

    if isinstance(obj, (datetime, date)):
        return obj.isoformat()

    if isinstance(obj, bytes):
        try:
            return obj.decode("utf-8")
        except UnicodeDecodeError:
            return obj.hex()

    if isinstance(obj, Enum):
        return obj.value

    if isinstance(obj, (list, tuple, set)):
        return [_to_json_safe(item, seen) for item in obj]

    if isinstance(obj, dict):
        return {str(key): _to_json_safe(value, seen) for key, value in obj.items()}

    if seen is None:
        seen = set()

    obj_id = id(obj)
    if obj_id in seen:
        return f"<circular:{type(obj).__name__}>"
    seen.add(obj_id)

    try:
        if hasattr(obj, "to_dict") and callable(obj.to_dict):
            return _to_json_safe(obj.to_dict(), seen)

        if hasattr(obj, "__dict__"):
            data = {
                key: value
                for key, value in vars(obj).items()
                if not key.startswith("_") and not callable(value)
            }
            return _to_json_safe(data, seen)

        attributes = {}
        for name, value in inspect.getmembers(obj):
            if name.startswith("_") or callable(value):
                continue
            attributes[name] = value
        if attributes:
            return _to_json_safe(attributes, seen)

        return repr(obj)
    finally:
        seen.discard(obj_id)


def _write_mock_message(
    bridge: Bridge, message_id: int | str, message_obj: Any
) -> Path:
    safe_source_name = re.sub(
        r"[^A-Za-z0-9_-]+", "_", bridge.source_name
    ).strip("_")
    if not safe_source_name:
        raise ValueError(f"Bridge source name cannot be used as a file name: {bridge.source_name!r}")

    safe_msg_id = re.sub(r"[^A-Za-z0-9_-]+", "_", str(message_id))
    chat_id = getattr(message_obj, "chat_id", None)
    if chat_id is not None:
        safe_msg_id = f"{chat_id}_{safe_msg_id}"

    target_dir = MOCKS_ROOT / safe_source_name
    target_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "message_id": message_id,
        "chat_id": chat_id,
        "raw_object": _to_json_safe(message_obj),
    }

    json_file = target_dir / f"{safe_msg_id}.json"
    json_file.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return json_file


async def handle_message(
    event: TelegramEvent,
    bridges: dict[int, Bridge],
    broadcaster: MessageBroadcaster,
) -> bool:
    logger.info(
        "Received message from Telegram group %s: %s",
        event.chat_id,
        getattr(event.message, "text", "<no text>"),
    )
    bridge = bridges.get(event.chat_id)
    if bridge is None:
        return False

    telegram_message = (
        event.message if getattr(event, "message", None) is not None else event
    )
    message_id = getattr(telegram_message, "id", None)
    if not isinstance(message_id, (int, str)):
        message_id = getattr(event, "id", None)
    if not isinstance(message_id, (int, str)):
        raise TypeError("Telegram event has no valid message ID")
    
    if ENABLE_TELEGRAM_MOCKS:
        saved_path = await asyncio.to_thread(
            _write_mock_message, bridge, message_id, telegram_message
        )
        logger.info("Stored mock message at %s", saved_path)

    text = getattr(telegram_message, "message", None) or getattr(
        telegram_message, "text", ""
    )
    if not isinstance(text, str) or not text.strip():
        return False

    parsed_message = bridge.parser.parse(text, telegram_message)
    if parsed_message.category not in {"Movie", "Serie"}:
        logger.debug(
            "Ignoring non-movie/TV Telegram message %s from %s",
            message_id,
            bridge.source_name,
        )
        return False
    if not parsed_message.torrent:
        logger.warning(
            "Skipping %s message %s from %s: no torrent URL found",
            parsed_message.category,
            message_id,
            bridge.source_name,
        )
        return False

    await broadcaster.broadcast(bridge.irc_channel, parsed_message)
    return True


async def replay_latest_messages(
    client: TelegramClient,
    bridges: list[Bridge],
    broadcaster: MessageBroadcaster,
    limit: int = 10,
) -> int:
    if limit < 1:
        raise ValueError("Message replay limit must be at least 1")

    dialogs = await client.get_dialogs()
    dialogs_by_id = {dialog.id: dialog for dialog in dialogs}
    missing_ids = sorted(
        {bridge.telegram_group_id for bridge in bridges} - dialogs_by_id.keys()
    )
    if missing_ids:
        raise RuntimeError(f"Telegram groups are not reachable: {missing_ids}")

    bridges_by_id = {bridge.telegram_group_id: bridge for bridge in bridges}
    delivered_count = 0
    for bridge in bridges:
        dialog = dialogs_by_id[bridge.telegram_group_id]
        group_delivered_count = 0
        recent_messages = [
            message
            async for message in client.iter_messages(dialog.entity, limit=limit)
        ]
        for message in reversed(recent_messages):
            event = _HistoryEvent(
                chat_id=bridge.telegram_group_id,
                message=message,
            )
            if await handle_message(event, bridges_by_id, broadcaster):
                delivered_count += 1
                group_delivered_count += 1

        logger.info(
            "Replayed %d of the latest %d message(s) from Telegram group %s",
            group_delivered_count,
            len(recent_messages),
            bridge.telegram_group_id,
        )

    return delivered_count


async def download_latest_messages(
    client: TelegramClient, bridges: list[Bridge]
) -> int:
    dialogs = await client.get_dialogs()
    dialogs_by_id = {dialog.id: dialog for dialog in dialogs}
    missing_ids = sorted(
        {bridge.telegram_group_id for bridge in bridges} - dialogs_by_id.keys()
    )
    if missing_ids:
        raise RuntimeError(f"Telegram groups are not reachable: {missing_ids}")

    saved_count = 0
    for bridge in bridges:
        dialog = dialogs_by_id[bridge.telegram_group_id]
        group_count = 0
        async for message in client.iter_messages(dialog.entity, limit=10):
            message_id = getattr(message, "id", None)
            if not isinstance(message_id, (int, str)):
                raise TypeError(
                    f"Telegram message in group {bridge.telegram_group_id} has no ID"
                )
            if ENABLE_TELEGRAM_MOCKS:
                await asyncio.to_thread(
                    _write_mock_message, bridge, message_id, message
                )
            group_count += 1
            saved_count += 1

        logger.info(
            "Downloaded %d recent message(s) from Telegram group %s",
            group_count,
            bridge.telegram_group_id,
        )

    return saved_count


def get_telegram_client() -> tuple[TelegramClient, str]:
    logger.info("Initializing Telegram client...")
    api_id = int(_required_env("TELEGRAM_API_ID"))
    api_hash = _required_env("TELEGRAM_API_HASH")
    phone = _required_env("TELEGRAM_PHONE_NUMBER")
    session_path = os.getenv("TELEGRAM_SESSION", "session_name2").strip()
    if not session_path:
        raise ValueError("TELEGRAM_SESSION must not be empty")

    resolved_session = Path(session_path)
    if not resolved_session.is_absolute():
        resolved_session = Path(__file__).resolve().parent.parent / resolved_session
    resolved_session.parent.mkdir(parents=True, exist_ok=True)

    return TelegramClient(str(resolved_session), api_id, api_hash), phone


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        raise ValueError(f"Required environment variable is missing: {name}")
    return value.strip()
