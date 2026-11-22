import asyncio
import logging
import os
from functools import partial
from pathlib import Path

from telethon import events

from telefwd.bridge_config import Bridge, load_bridges
from telefwd.broadcaster import get_broadcaster
from telefwd.telegram import get_telegram_client, handle_message

logger = logging.getLogger(__name__)


def load_configured_bridges() -> list[Bridge]:
    logger.info("Loading bridge configuration...")
    config_path = Path(os.getenv("BRIDGE_CONFIG", "config/bridge.yaml"))
    definitions_dir = Path(__file__).parent / "definitions"
    configured_bridges = load_bridges(config_path, definitions_dir)
    return configured_bridges


async def run() -> None:
    configured_bridges = load_configured_bridges()
    bridges = {bridge.telegram_group_id: bridge for bridge in configured_bridges}
    
    broadcaster = await get_broadcaster(configured_bridges)
    client, phone = get_telegram_client()

    try:
        logger.info("Connecting to Telegram...")
        await client.start(phone=phone)
        dialogs = await client.get_dialogs()
        available_group_ids = {dialog.id for dialog in dialogs}
        missing_ids = sorted(set(bridges) - available_group_ids)
        if missing_ids:
            raise RuntimeError(f"Telegram groups are not reachable: {missing_ids}")

        client.add_event_handler(
            partial(handle_message, bridges=bridges, broadcaster=broadcaster),
            events.NewMessage(chats=list(bridges)),
        )
        logger.info("Bridge started for %d Telegram source(s)", len(bridges))
        await client.run_until_disconnected()
    finally:
        await client.disconnect()
        await broadcaster.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())


if __name__ == "__main__":
    main()
