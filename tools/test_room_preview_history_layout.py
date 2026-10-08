"""Regression fixture for bilingual history of room-preview blocks."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "src" / "mush-z" / "worlds" / "plugins" / "Translation_Mode.xml"


def complete(line: str) -> bool:
    value = line.strip()
    return len(value) >= 12 and re.search(r"[.!?][\"')\]]*$", value) is not None


def trailing_row_start(lines: list[str]) -> int | None:
    if len(lines) < 2:
        return None
    start = len(lines)
    for index in range(len(lines) - 1, 0, -1):
        if not complete(lines[index]) or not complete(lines[index - 1]):
            break
        start = index
    return start if start < len(lines) else None


def main() -> None:
    source = [
        "In the next room you see:",
        "Just inside the cave",
        "Deep gouges cover most of the ground and the dark colored stone walls",
        "of this massive cave. Large piles of what looks to be bat guano lie",
        "scattered about the ground as well. The cave continues on to the north",
        "and looking up one can see another chamber shrouded in darkness.",
        "The shadow of a crescent-shaped blade is projected by nothing.",
        "The shadow of a crescent-shaped blade is projected by nothing.",
        "A vampire bat flies about the cave.",
        "A vampire bat flies about the cave in circles.",
        "The bleaching skeleton of a vampire bat is lying here.",
        "The shadow of a crescent-shaped blade is projected by nothing.",
        "The shadow of a crescent-shaped blade is projected by nothing.",
        "The shadow of a crescent-shaped blade is projected by nothing.",
        "The shadow of a crescent-shaped blade is projected by nothing.",
    ]
    payload = source[2:]
    start = trailing_row_start(payload)
    assert start == 4, start
    prose = " ".join(payload[:start])
    trailing = payload[start:]
    rebuilt = [source[0], source[1], prose, *trailing]
    assert len(rebuilt) == 12, rebuilt
    assert len(trailing) == 9
    assert sum("crescent-shaped blade" in row for row in trailing) == 6
    assert rebuilt[-1] == source[-1]

    plugin = PLUGIN.read_text(encoding="utf-8-sig")
    assert "room_preview_semantic_source_lines" in plugin
    assert '["In the next room you see:"] = true' in plugin
    assert '["Nearby you see:"] = true' in plugin
    assert 'table.concat(prose, " ")' in plugin
    print("ROOM_PREVIEW_HISTORY_LAYOUT_OK rows=12 trailing=9 duplicates=preserved")


if __name__ == "__main__":
    main()
