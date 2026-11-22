from pathlib import Path

import pytest

from telefwd.bridge_config import load_bridges


def test_load_bridges_loads_definition_and_routes(tmp_path: Path) -> None:
    definitions = tmp_path / "definitions"
    definitions.mkdir()
    (definitions / "sample.yaml").write_text(
        """parser:
  release_pattern: 'Title: (.+)'
""",
        encoding="utf-8",
    )
    config = tmp_path / "bridge.yaml"
    config.write_text(
        """bridges:
  - source_name: sample
    definition: sample
    telegram_group_id: -100123
    irc_channel: "#sample"
""",
        encoding="utf-8",
    )

    bridges = load_bridges(config, definitions)

    assert len(bridges) == 1
    assert bridges[0].source_name == "sample"
    assert bridges[0].telegram_group_id == -100123
    assert bridges[0].irc_channel == "#sample"


def test_load_bridges_rejects_duplicate_telegram_ids(tmp_path: Path) -> None:
    definitions = tmp_path / "definitions"
    definitions.mkdir()
    (definitions / "sample.yaml").write_text(
        """parser:
  release_pattern: '(.*)'
""",
        encoding="utf-8",
    )
    config = tmp_path / "bridge.yaml"
    config.write_text(
        """bridges:
  - source_name: one
    definition: sample
    telegram_group_id: 123
    irc_channel: "#one"
  - source_name: two
    definition: sample
    telegram_group_id: 123
    irc_channel: "#two"
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Duplicate telegram_group_id"):
        load_bridges(config, definitions)
