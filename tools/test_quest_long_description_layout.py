"""Fixture regression for semantic quest long-description rows."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "src" / "mush-z" / "worlds" / "plugins" / "Translation_Mode.xml"
WORKER = ROOT / "src" / "mush-z" / "worlds" / "plugins" / "translation_bridge" / "translation_worker.py"


def semantic_long_rows(lines: list[str]) -> list[str]:
    output, current = [], []
    for line in lines:
        value = line.strip()
        if not value:
            continue
        current.append(value)
        if re.search(r"[.!?][\"']?$", value):
            output.append(" ".join(current))
            current = []
    if current:
        output.append(" ".join(current))
    return output


def main() -> None:
    source = [
        "Sovison the dream alchemist says, 'Now that you have helped to make the",
        "dream nectar it's time to enter each of the monks dreams to find out what",
        "is preventing them from waking. Head south from my office and just use the",
        "potion on the sleeping form of the monk you wish to help, you should",
        "probably start with Koron or Tenzani first and leave Calaell for last since",
        "they seem to be in a much deeper sleep.",
        "Good luck and may the gods watch over you.'",
        "Sovison the dream alchemist goes back to his work.",
    ]
    rows = semantic_long_rows(source)
    assert len(rows) == 3, rows
    assert rows[0].startswith("Sovison the dream alchemist says")
    assert rows[0].endswith("deeper sleep.")
    assert rows[1] == "Good luck and may the gods watch over you.'"
    assert rows[2] == "Sovison the dream alchemist goes back to his work."

    plugin = PLUGIN.read_text(encoding="utf-8-sig")
    assert 'value:match("^Current goal long description:%s*")' in plugin
    assert 'value:match("^Previous goal long description:%s*")' in plugin
    assert "split_long_field and value:match" in plugin

    spec = importlib.util.spec_from_file_location("quest_layout_worker_test", WORKER)
    worker = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(worker)
    dialogue_quest = """Quest Name: Give a troll a chance.
Location: Dream realm 2
Area Level: 28
Previous goal long description:
A bridge troll says, 'No attack Bob. Go get me bear and I will remove rock.'
Current goal long description:
Mongo says, 'Search every room. I wish you luck.'"""
    assert worker.is_quest_structured_block(dialogue_quest)
    assert worker.is_wrapped_dialogue_block(dialogue_quest)
    worker.translate_quest_structured_block = lambda text, config: "QUEST_STRUCTURED"
    worker.translate_wrapped_dialogue_block = lambda text, config: "WRAPPED_DIALOGUE"
    assert worker.translate(dialogue_quest, {}) == "QUEST_STRUCTURED"
    print("QUEST_LONG_DESCRIPTION_LAYOUT_OK semantic_rows=3 display_wraps_joined=yes")


if __name__ == "__main__":
    main()
