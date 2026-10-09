"""Regression test for caching channel history independently of its age."""

from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "src/mush-z/worlds/plugins/translation_bridge/translation_worker.py"


def main() -> None:
    spec = importlib.util.spec_from_file_location("relative_history_worker_test", WORKER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    requested = []
    module.translate_cached_phrase = lambda text, config: requested.append(text) or "健二說：請安心享受。"
    first = " Kenji says, 'Please be at ease and enjoy your time with us.' 27 seconds ago"
    second = " Kenji says, 'Please be at ease and enjoy your time with us.' 45 seconds ago"
    assert module.translate_relative_history_timestamp(first, {}) == " 健二說：請安心享受。 27 秒前"
    assert module.translate_relative_history_timestamp(second, {}) == " 健二說：請安心享受。 45 秒前"
    assert requested[0] == requested[1]
    assert module.translate_relative_history_timestamp("You receive 27 experience.", {}) is None
    assert module.translate_relative_history_timestamp("A path continues south.", {}) is None
    print("RELATIVE_HISTORY_TIMESTAMP_OK stable_message=cached dynamic_age=local")


if __name__ == "__main__":
    main()
