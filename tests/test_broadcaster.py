import asyncio

import pytest

from telefwd.broadcaster import MessageBroadcaster, format_message
from telefwd.internal_types import IRCMessage


def test_format_message_includes_parsed_fields() -> None:
    message = IRCMessage(
        category="Serie",
        title="Pluribus",
        season=1,
        episode="S01E07",
        name="Pluribus S01E07",
        torrent="https://example.com/torrent",
    )

    assert format_message(message) == (
        '[TELEFWD] TYPE=tv TITLE="Pluribus" SEASON=01 EPISODE=07 '
        "URL=https://example.com/torrent"
    )


def test_format_message_collapses_whitespace() -> None:
    message = IRCMessage(category="Movie", title="Example\nTitle", name="  Release\tName  ")

    assert format_message(message) == "[Movie] Example Title - Release Name"


def test_format_message_includes_autobrr_metadata_fields() -> None:
    message = IRCMessage(
        category="Movie",
        title='La película "Especial"',
        year=2026,
        size="5.18 GiB",
        quality="1080P",
        source="WEB-DL",
        codec="AVC",
        audio_languages=["English", "Spanish"],
        torrent="https://example.com/torrents/1",
        imdb="https://www.imdb.com/title/tt1234567",
        tmdb="https://www.themoviedb.org/movie/123",
    )

    assert format_message(message) == (
        '[TELEFWD] TYPE=movie TITLE="La película \\"Especial\\"" YEAR=2026 '
        'SIZE="5.18 GiB" URL=https://example.com/torrents/1 '
        'AUDIO="English, Spanish" QUALITY=1080P SOURCE=WEB-DL CODEC=AVC '
        "IMDB=https://www.imdb.com/title/tt1234567 "
        "TMDB=https://www.themoviedb.org/movie/123"
    )


@pytest.mark.asyncio
async def test_broadcaster_registers_joins_and_sends_privmsg() -> None:
    received: asyncio.Queue[str] = asyncio.Queue()

    async def handle_client(
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        try:
            while line := await reader.readline():
                command = line.decode().rstrip("\r\n")
                await received.put(command)
                if command == "CAP LS 302":
                    writer.write(b":irc.test CAP * LS :\r\n")
                    await writer.drain()
                elif command.startswith("USER "):
                    writer.write(b":irc.test 001 bot :Welcome\r\n")
                    await writer.drain()
                elif command.startswith("JOIN "):
                    writer.write(b"PING :keepalive\r\n")
                    await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_server(handle_client, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    broadcaster = MessageBroadcaster(
        host="127.0.0.1",
        port=port,
        nick="bot",
        username="relay-user",
        realname="Relay Service",
        use_tls=False,
    )
    try:
        await broadcaster.connect({"#sample"})
        await broadcaster.broadcast(
            "#sample",
            IRCMessage(category="Movie", title="Example", year=2024),
        )

        commands = [await asyncio.wait_for(received.get(), timeout=1) for _ in range(7)]
        assert commands[:5] == [
            "CAP LS 302",
            "NICK bot",
            "USER relay-user 0 * :Relay Service",
            "CAP END",
            "JOIN #sample",
        ]
        assert "PONG :keepalive" in commands
        assert "PRIVMSG #sample :[Movie] Example 2024" in commands
    finally:
        await broadcaster.close()
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_broadcaster_truncates_to_irc_protocol_limit() -> None:
    received: asyncio.Queue[str] = asyncio.Queue()

    async def handle_client(
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        try:
            while line := await reader.readline():
                command = line.decode().rstrip("\r\n")
                await received.put(command)
                if command == "CAP LS 302":
                    writer.write(b":irc.test CAP * LS :\r\n")
                    await writer.drain()
                elif command.startswith("USER "):
                    writer.write(b":irc.test 001 bot :Welcome\r\n")
                    await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_server(handle_client, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    broadcaster = MessageBroadcaster(host="127.0.0.1", port=port, use_tls=False)
    try:
        await broadcaster.connect(set())
        await broadcaster.broadcast(
            "#sample",
            IRCMessage(category="Unknown", title="é" * 1000),
        )

        commands = [await asyncio.wait_for(received.get(), timeout=1) for _ in range(5)]
        message_line = next(command for command in commands if command.startswith("PRIVMSG "))
        assert len(message_line.encode("utf-8")) + 2 <= 512
        message_line.encode("utf-8").decode("utf-8")
    finally:
        await broadcaster.close()
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_broadcaster_reconnects_after_server_disconnect() -> None:
    received: asyncio.Queue[str] = asyncio.Queue()
    connection_count = 0

    async def handle_client(
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        nonlocal connection_count
        connection_count += 1
        current_connection = connection_count
        try:
            while line := await reader.readline():
                command = line.decode().rstrip("\r\n")
                await received.put(command)
                if command == "CAP LS 302":
                    writer.write(b":irc.test CAP * LS :\r\n")
                    await writer.drain()
                elif command.startswith("USER "):
                    writer.write(b":irc.test 001 bot :Welcome\r\n")
                    await writer.drain()
                elif command.startswith("JOIN ") and current_connection == 1:
                    writer.close()
                    await writer.wait_closed()
                    return
        finally:
            if not writer.is_closing():
                writer.close()
                await writer.wait_closed()

    server = await asyncio.start_server(handle_client, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    broadcaster = MessageBroadcaster(
        host="127.0.0.1",
        port=port,
        nick="bot",
        use_tls=False,
    )
    try:
        await broadcaster.connect({"#sample"})
        for _ in range(5):
            await asyncio.wait_for(received.get(), timeout=1)
        for _ in range(100):
            if not broadcaster._connected:
                break
            await asyncio.sleep(0.01)
        assert not broadcaster._connected

        await broadcaster.broadcast(
            "#sample",
            IRCMessage(category="Movie", title="Reconnect"),
        )

        commands = []
        while not any(command.startswith("PRIVMSG ") for command in commands):
            commands.append(await asyncio.wait_for(received.get(), timeout=1))
        assert connection_count == 2
        assert "PRIVMSG #sample :[Movie] Reconnect" in commands
    finally:
        await broadcaster.close()
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_registration_timeout_includes_server_replies() -> None:
    async def handle_client(
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        try:
            await reader.readline()
            writer.write(b":irc.test CAP * LS :sasl\r\n")
            await writer.drain()
            await asyncio.sleep(1)
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_server(handle_client, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    broadcaster = MessageBroadcaster(
        host="127.0.0.1",
        port=port,
        use_tls=False,
        registration_timeout=0.01,
    )
    try:
        with pytest.raises(TimeoutError, match=r"CAP \* LS :sasl") as error:
            await broadcaster.connect(set())
        assert "CAP * LS :sasl" in str(error.value)
    finally:
        await broadcaster.close()
        server.close()
        await server.wait_closed()
