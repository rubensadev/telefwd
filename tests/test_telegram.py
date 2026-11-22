import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from telefwd import telegram
from telefwd.bridge_config import Bridge
from telefwd.parser import DefinitionParser


def _bridge(group_id: int, source_name: str) -> Bridge:
    parser = DefinitionParser(Path("telefwd/definitions/divteam.yaml"))
    return Bridge(
        source_name=source_name,
        telegram_group_id=group_id,
        irc_channel=f"#{source_name}",
        parser=parser,
    )


@pytest.mark.asyncio
async def test_download_latest_messages_saves_ten_per_configured_group(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(telegram, "MOCKS_ROOT", tmp_path)
    bridges = [_bridge(-1001, "one"), _bridge(-1002, "two")]
    requested: list[tuple[int, int]] = []

    class FakeClient:
        async def get_dialogs(self):
            return [
                SimpleNamespace(id=bridge.telegram_group_id, entity=bridge.telegram_group_id)
                for bridge in bridges
            ]

        def iter_messages(self, entity: int, limit: int):
            requested.append((entity, limit))

            async def messages():
                for message_id in range(1, 11):
                    yield SimpleNamespace(
                        id=message_id,
                        chat_id=entity,
                        message=f"message {message_id}",
                    )

            return messages()

    saved_count = await telegram.download_latest_messages(FakeClient(), bridges)

    assert saved_count == 20
    assert requested == [(-1001, 10), (-1002, 10)]
    saved_file = tmp_path / "one" / "-1001_1.json"
    payload = json.loads(saved_file.read_text(encoding="utf-8"))
    assert payload["message_id"] == 1
    assert payload["chat_id"] == -1001
    assert payload["raw_object"]["message"] == "message 1"
    assert (tmp_path / "two" / "-1002_1.json").is_file()


@pytest.mark.asyncio
async def test_download_latest_messages_fails_for_unavailable_group(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(telegram, "MOCKS_ROOT", tmp_path)

    class FakeClient:
        async def get_dialogs(self):
            return []

    with pytest.raises(RuntimeError, match=r"\[-1001\]"):
        await telegram.download_latest_messages(
            FakeClient(), [_bridge(-1001, "one")]
        )


@pytest.mark.asyncio
async def test_handle_message_broadcasts_parsed_movie(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(telegram, "MOCKS_ROOT", tmp_path)
    bridge = Bridge(
        source_name="nobs",
        telegram_group_id=-1001,
        irc_channel="#movies",
        parser=DefinitionParser(Path("telefwd/definitions/nobs.yaml")),
    )
    telegram_message = SimpleNamespace(
        id=42,
        chat_id=-1001,
        message="""🎬 Example Movie 2026 1080p WEB-DL ENG-ESP
📂 Categoría: Movies
💾 Tamaño: 5.18 GiB
🔊 Audio: 🇬🇧 🇪🇸""",
        reply_markup={
            "rows": [
                {
                    "buttons": [
                        {
                            "type": {
                                "url": "https://nobs.example/torrents/42"
                            }
                        }
                    ]
                }
            ]
        },
    )
    telegram_message.to_dict = lambda: vars(telegram_message)

    class FakeBroadcaster:
        def __init__(self) -> None:
            self.broadcasts: list[tuple[str, Any]] = []

        async def broadcast(self, channel: str, message: Any) -> None:
            self.broadcasts.append((channel, message))

    broadcaster = FakeBroadcaster()
    event = SimpleNamespace(chat_id=-1001, message=telegram_message)

    await telegram.handle_message(event, {-1001: bridge}, broadcaster)

    assert len(broadcaster.broadcasts) == 1
    channel, parsed_message = broadcaster.broadcasts[0]
    assert channel == "#movies"
    assert parsed_message.category == "Movie"
    assert parsed_message.title == "Example Movie"
    assert parsed_message.torrent == "https://nobs.example/torrents/42"


@pytest.mark.asyncio
async def test_replay_latest_messages_uses_handler_in_oldest_first_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(telegram, "MOCKS_ROOT", tmp_path)
    bridge = Bridge(
        source_name="nobs",
        telegram_group_id=-1001,
        irc_channel="#movies",
        parser=DefinitionParser(Path("telefwd/definitions/nobs.yaml")),
    )

    class FakeMessage:
        def __init__(self, message_id: int) -> None:
            self.id = message_id
            self.chat_id = -1001
            self.message = (
                f"🎬 Movie {message_id} 2026 1080p WEB-DL\n"
                "📂 Categoría: Movies\n"
                "💾 Tamaño: 1.5 GiB"
            )
            self.reply_markup = {
                "rows": [
                    {
                        "buttons": [
                            {
                                "type": {
                                    "url": f"https://nobs.example/torrents/{message_id}"
                                }
                            }
                        ]
                    }
                ]
            }

        def to_dict(self) -> dict[str, Any]:
            return {
                "id": self.id,
                "chat_id": self.chat_id,
                "message": self.message,
                "reply_markup": self.reply_markup,
            }

    class FakeClient:
        def __init__(self) -> None:
            self.requested_limit: int | None = None

        async def get_dialogs(self):
            return [SimpleNamespace(id=-1001, entity="nobs-entity")]

        def iter_messages(self, entity: str, limit: int):
            assert entity == "nobs-entity"
            self.requested_limit = limit

            async def messages():
                for message_id in (3, 2, 1):
                    yield FakeMessage(message_id)

            return messages()

    class FakeBroadcaster:
        def __init__(self) -> None:
            self.broadcasts: list[tuple[str, Any]] = []

        async def broadcast(self, channel: str, message: Any) -> None:
            self.broadcasts.append((channel, message))

    client = FakeClient()
    broadcaster = FakeBroadcaster()

    delivered_count = await telegram.replay_latest_messages(
        client, [bridge], broadcaster
    )

    assert delivered_count == 3
    assert client.requested_limit == 10
    assert [message.title for _, message in broadcaster.broadcasts] == [
        "Movie 1",
        "Movie 2",
        "Movie 3",
    ]
    assert all(channel == "#movies" for channel, _ in broadcaster.broadcasts)
    assert (tmp_path / "nobs" / "-1001_1.json").is_file()
