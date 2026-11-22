import asyncio
import logging
import os
from pathlib import Path

from telefwd.bridge_config import load_bridges
from telefwd.telegram import download_latest_messages, get_telegram_client

logger = logging.getLogger(__name__)


async def run() -> None:
    config_path = Path(os.getenv("BRIDGE_CONFIG", "config/bridge.yaml"))
    definitions_dir = Path(__file__).parent / "definitions"
    bridges = load_bridges(config_path, definitions_dir)
    client, phone = get_telegram_client()

    try:
        logger.info("Connecting to Telegram to download recent messages...")
        await client.start(phone=phone)
        saved_count = await download_latest_messages(client, bridges)
        logger.info("Saved %d Telegram message(s) for analysis", saved_count)
    finally:
        await client.disconnect()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())


if __name__ == "__main__":
    main()
