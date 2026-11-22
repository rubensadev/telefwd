import asyncio
import logging
import os
from pathlib import Path

from telefwd.bridge_config import load_bridges
from telefwd.broadcaster import get_broadcaster
from telefwd.telegram import get_telegram_client, replay_latest_messages

logger = logging.getLogger(__name__)


async def run() -> None:
    config_path = Path(os.getenv("BRIDGE_CONFIG", "config/bridge.yaml"))
    definitions_dir = Path(__file__).parent / "definitions"
    bridges = load_bridges(config_path, definitions_dir)
    client, phone = get_telegram_client()
    broadcaster = await get_broadcaster(bridges)

    try:
        logger.info("Connecting to Telegram to replay recent messages to IRC...")
        await client.start(phone=phone)
        delivered_count = await replay_latest_messages(
            client,
            bridges,
            broadcaster,
        )
        logger.info(
            "Replayed %d recent Movie/TV message(s) to IRC",
            delivered_count,
        )
    finally:
        await client.disconnect()
        await broadcaster.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())


if __name__ == "__main__":
    main()
