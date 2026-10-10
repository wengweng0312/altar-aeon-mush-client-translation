"""Offline regressions for LMT blocks that previously collapsed or truncated."""

from __future__ import annotations

import ast
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "src" / "mush-z" / "worlds" / "plugins" / "translation_bridge" / "translation_worker.py"
NAMES = {
    "PEER_ROOM_PREVIEW", "LEVEL_ADVANCE_LINE", "LEVEL_GAIN_LINE",
    "LEVEL_CHEAPEST_LINE", "LEVEL_CHEAPEST_TIE_LINE", "LEVEL_CLASS_ZH",
}
FUNCTIONS = {
    "is_peer_room_title_preview", "translate_peer_room_title_preview",
    "level_advance_matches", "is_level_advance_block", "translate_level_advance_block",
}


def load_subjects():
    tree = ast.parse(WORKER.read_text(encoding="utf-8-sig"))
    body = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id in NAMES for target in node.targets
        ):
            body.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name in FUNCTIONS:
            body.append(node)
    calls = []
    namespace = {
        "re": re,
        "translate_cached_phrase": lambda value, _config: calls.append(value) or {
            "End of the hallway": "走廊盡頭",
        }.get(value, value),
    }
    exec(compile(ast.Module(body=body, type_ignores=[]), str(WORKER), "exec"), namespace)
    namespace["calls"] = calls
    return namespace


def main():
    module = load_subjects()
    peer = "(you peer out from your hiding place...)\nEnd of the hallway"
    assert module["is_peer_room_title_preview"](peer)
    assert module["translate_peer_room_title_preview"](peer, {}) == (
        "（你從藏身處向外窺視……）\n走廊盡頭"
    )
    assert module["calls"] == ["End of the hallway"]
    assert not module["is_peer_room_title_preview"]("You look around.\nEnd of the hallway")
    assert not module["is_peer_room_title_preview"](
        "(you peer out from your hiding place...)\nEnd of the hallway\nA longer room description."
    )

    mage = "\n".join((
        "CONGRATULATIONS!",
        "You advance another rank closer to level 16 mage!",
        "You gain: 0/718 hit, 0/228 mana, 0/378 movement, 1/3 practices.",
        "Your next cheapest level is a Mage micro for 9000000",
    ))
    mage_zh = module["translate_level_advance_block"](mage)
    assert mage_zh.splitlines() == [
        "恭喜！",
        "你又晉升一個階級，更接近第 16 級法師！",
        "你獲得：血量 0/718、法力 0/228、體力 0/378、練習 1/3。",
        "下一個最便宜的等級是 法師 micro，需要 9000000 點經驗值。",
    ]
    thief = "\n".join((
        "CONGRATULATIONS!",
        "You advance another rank closer to level 33 thief!",
        "You gain: 1/900 hit, 2/300 mana, 3/500 movement, 0/4 practices.",
        "Your next cheapest level is a tie for 12000000",
    ))
    assert module["translate_level_advance_block"](thief).splitlines()[-1] == (
        "下一個最便宜的等級並列，需要 12000000 點經驗值。"
    )
    assert not module["is_level_advance_block"](mage.replace("practices.", "quests."))
    print("LMT_SAFE_UNIT_STRUCTURES_OK peer=1 level_up=2")


if __name__ == "__main__":
    main()
