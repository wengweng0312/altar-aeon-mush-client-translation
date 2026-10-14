"""Regression fixture for dialogue with leading and trailing actions."""

from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "src/mush-z/worlds/plugins/translation_bridge/translation_worker.py"


def load_worker():
    spec = importlib.util.spec_from_file_location("translation_worker_test", WORKER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def main() -> None:
    worker = load_worker()
    source = """You try to talk to Calaell the monk...
Calaell the monk says, 'Oh! I didn't even see you there. Maybe you can
help me that metal thing off in the distance is full of half creature
half metal things. Please go talk with them and help them if you can.'
Calaell the monk goes back to staring at the metal building off in the
distance."""
    units = worker.parse_wrapped_dialogue_units(source)
    assert len(units) == 3, units
    assert units[0][1] == "You try to talk to Calaell the monk..."
    assert units[1][1].startswith("Calaell the monk says")
    assert units[1][1].endswith("help them if you can.'")
    assert units[2][1].endswith("distance.")
    assert worker.is_wrapped_dialogue_block(source)
    tarot = """You pay 100 gold coins for a reading.
Madam Kezila shuffles the deck, then lays the top four cards face-up before her:
  The Highwayman, the Blade's noble bringer of woe.
  The Kornbocke, the Grove's common bringer of woe.
  The Gravedigger, the Skull's common bringer of weal and woe.
  The Void, the Universe's cosmic bringer of woe.
Madam Kezila tells you, 'The cards say that treachery will influence your destiny.'
You feel a subtle shift in the strands of fate.
You have got a tarot reading. 2 more tasks to go!"""
    tarot_units = worker.parse_wrapped_dialogue_units(tarot)
    assert len(tarot_units) == 9, tarot_units
    assert tarot_units[1][1].endswith("before her:"), tarot_units
    assert tarot_units[2][1].startswith("The Highwayman"), tarot_units
    assert tarot_units[5][1].startswith("The Void"), tarot_units
    assert tarot_units[-1][1] == "You have got a tarot reading. 2 more tasks to go!"
    globals_ = worker.translate_semantic_units.__globals__
    old_cloud = globals_["cloud_translate_many"]
    old_cache = globals_["cache_get"]
    globals_["cloud_translate_many"] = lambda _values: (_ for _ in ()).throw(
        AssertionError("fixed task progress must not call a provider")
    )
    globals_["cache_get"] = lambda _source, _config: None
    try:
        progress = worker.translate_semantic_units([tarot_units[-1]], {}, "wrapped_dialogue")
    finally:
        globals_["cloud_translate_many"] = old_cloud
        globals_["cache_get"] = old_cache
    assert progress == "你已完成一次塔羅牌占卜。還有 2 個任務！", progress
    print("WRAPPED_DIALOGUE_LAYOUT_OK units=3 speech_wraps=joined")


if __name__ == "__main__":
    main()
