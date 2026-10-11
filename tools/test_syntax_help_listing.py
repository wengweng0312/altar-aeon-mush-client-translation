"""Regression for line-preserving Syntax command tables."""

from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "src/mush-z/worlds/plugins/translation_bridge/translation_worker.py"


def main() -> None:
    spec = importlib.util.spec_from_file_location("syntax_help_worker_test", WORKER)
    worker = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(worker)
    source = """Syntax:
friends               - show logged in friends and recent activity
friend on/off         - turn on/off your friends channel
friend replay [name]  - see what your friends have done recently
friend remove all     - remove everyone from your friends list
What do you want to do with your friends list?"""
    translations = {
        "show logged in friends and recent activity": "顯示已登入的朋友與近期活動",
        "turn on/off your friends channel": "開啟或關閉朋友頻道",
        "see what your friends have done recently": "查看朋友最近做過什麼",
        "remove everyone from your friends list": "移除朋友清單中的所有人",
        "What do you want to do with your friends list?": "你想如何處理朋友清單？",
    }
    worker.prefetch_cached_phrases = lambda values, config: None
    worker.translate_cached_phrase = lambda text, config: translations[text]
    assert worker.is_syntax_help_block(source)
    result = worker.translate_syntax_help_block(source, {})
    lines = result.splitlines()
    assert len(lines) == 6, lines
    assert lines[0] == "語法："
    assert lines[1] == "friends - 顯示已登入的朋友與近期活動"
    assert lines[2] == "friend on/off - 開啟或關閉朋友頻道"
    assert lines[3] == "friend replay [name] - 查看朋友最近做過什麼"
    assert lines[4] == "friend remove all - 移除朋友清單中的所有人"
    assert lines[5] == "你想如何處理朋友清單？"
    assert all(command in result for command in (
        "friends", "friend on/off", "friend replay [name]", "friend remove all",
    ))
    print("SYNTAX_HELP_LISTING_OK rows=6 commands=preserved review_pairing=exact")


if __name__ == "__main__":
    main()
