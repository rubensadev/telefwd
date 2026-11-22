import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from telefwd.parser import DefinitionParser

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Bridge:
    source_name: str
    telegram_group_id: int
    irc_channel: str
    parser: DefinitionParser


def load_bridges(
    config_path: Path,
    definitions_dir: Path,
) -> list[Bridge]:
    if not config_path.is_file():
        raise FileNotFoundError(f"Bridge configuration does not exist: {config_path}")

    with config_path.open(encoding="utf-8") as config_file:
        config: Any = yaml.safe_load(config_file)
    if not isinstance(config, dict) or not isinstance(config.get("bridges"), list):
        raise TypeError(f"Bridge configuration must contain a 'bridges' list: {config_path}")
    if not config["bridges"]:
        raise ValueError(f"Bridge configuration has no entries: {config_path}")

    bridges: list[Bridge] = []
    seen_group_ids: set[int] = set()
    parsers: dict[str, DefinitionParser] = {}
    for index, entry in enumerate(config["bridges"]):
        try:
            if not isinstance(entry, dict):
                raise TypeError(f"Bridge entry {index} must be a mapping")
    
            source_name = _required_string(entry, "source_name", index)
            definition = _required_string(entry, "definition", index)
            irc_channel = _required_string(entry, "irc_channel", index)
            group_id = entry.get("telegram_group_id")
            if isinstance(group_id, bool) or not isinstance(group_id, int):
                raise TypeError(f"Bridge entry {index} must have an integer telegram_group_id")
            if group_id in seen_group_ids:
                raise ValueError(f"Duplicate telegram_group_id in bridge configuration: {group_id}")
            if not definition.replace("_", "").replace("-", "").isalnum():
                raise ValueError(f"Invalid parser definition name in bridge entry {index}: {definition}")
            if not irc_channel.startswith(("#", "&", "+", "!")) or any(
                character in irc_channel for character in " ,\r\n"
            ):
                raise ValueError(f"Invalid IRC channel in bridge entry {index}: {irc_channel}")
    
            parser = parsers.get(definition)
            if parser is None:
                definition_path = definitions_dir / f"{definition}.yaml"
                parser = DefinitionParser(definition_path)
                parsers[definition] = parser
            bridges.append(
                Bridge(
                    source_name=source_name,
                    telegram_group_id=group_id,
                    irc_channel=irc_channel,
                    parser=parser,
                )
            )
            seen_group_ids.add(group_id)
        except Exception:
            logger.exception("Error loading bridge entry %d from configuration: %s", index, config_path)
            raise

    return bridges


def _required_string(entry: dict[str, Any], key: str, index: int) -> str:
    value = entry.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Bridge entry {index} must have a non-empty {key}")
    return value.strip()
