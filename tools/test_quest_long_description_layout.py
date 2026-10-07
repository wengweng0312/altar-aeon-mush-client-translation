"""Fixture regression for semantic quest long-description rows."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "src" / "mush-z" / "worlds" / "plugins" / "Translation_Mode.xml"


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
    print("QUEST_LONG_DESCRIPTION_LAYOUT_OK semantic_rows=3 display_wraps_joined=yes")


if __name__ == "__main__":
    main()
