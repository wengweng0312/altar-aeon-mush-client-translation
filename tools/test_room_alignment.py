"""Offline regression tests for aligned room title/sentence translation."""

from __future__ import annotations

import ast
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "src" / "mush-z" / "worlds" / "plugins" / "translation_bridge" / "translation_worker.py"
FUNCTIONS = {
    "semantic_sentence_chunks",
    "room_semantic_chunks",
    "parse_numbered_room_translation",
}


def load_functions() -> dict[str, object]:
    tree = ast.parse(WORKER.read_text(encoding="utf-8-sig"))
    body = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id in {"ROOM_UNIT_MARKER", "ROOM_UNIT_END_MARKER"}
            for target in node.targets
        ):
            body.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name in FUNCTIONS:
            body.append(node)
    namespace = {"re": re}
    exec(compile(ast.Module(body=body, type_ignores=[]), str(WORKER), "exec"), namespace)
    return namespace


def main() -> None:
    module = load_functions()
    chunks = module["room_semantic_chunks"](
        "Three way intersection in the cave\n"
        "This direction changes again, and goes to the west and to the north.\n"
        "The path is clear of any big rocks or boulders but the ground is sandy\n"
        "and is mixed with pebbles.\n"
        "There are unclear markings in the dirt but it is clear there are things\n"
        "living in this cave."
    )
    assert chunks == [
        "Three way intersection in the cave",
        "This direction changes again, and goes to the west and to the north.",
        "The path is clear of any big rocks or boulders but the ground is sandy and is mixed with pebbles.",
        "There are unclear markings in the dirt but it is clear there are things living in this cave.",
    ], chunks

    parsed = module["parse_numbered_room_translation"](
        "[[ROOM_0]] 洞穴中的三叉路口\n"
        "[[ROOM_1]] 這個方向又發生了變化。\n"
        "[[ROOM_2]] 道路沒有大石頭的阻擋。\n"
        "[[ROOM_3]] 泥土上有一些不清楚的標記。",
        4,
    )
    assert parsed == [
        "洞穴中的三叉路口",
        "這個方向又發生了變化。",
        "道路沒有大石頭的阻擋。",
        "泥土上有一些不清楚的標記。",
    ], parsed
    translated_markers = module["parse_numbered_room_translation"](
        "【房间 0】洞穴中的三岔路口 【房间 1】方向改變。 "
        "【房间 2】道路暢通。 【房间 3】洞穴裡有生物。 【房间结束】",
        4,
    )
    assert translated_markers == [
        "洞穴中的三岔路口", "方向改變。", "道路暢通。", "洞穴裡有生物。"
    ], translated_markers
    assert module["parse_numbered_room_translation"](
        "[[ROOM_0]] 標題\n[[ROOM_2]] 少了一段", 3
    ) is None
    worker_source = WORKER.read_text(encoding="utf-8-sig")
    assert 'output = [" ".join(prefix_translation.splitlines()).strip()]' not in worker_source
    assert "output = [line.strip() for line in prefix_translation.splitlines() if line.strip()]" in worker_source
    print("ROOM_ALIGNMENT_OK units=4 malformed_marker_safe=yes")


if __name__ == "__main__":
    main()
