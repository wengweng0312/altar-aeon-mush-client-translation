"""Regression for deterministic no-match Help suggestions."""

from __future__ import annotations

import runpy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "src/mush-z/worlds/plugins/translation_bridge/translation_worker.py"
module = runpy.run_path(str(WORKER), run_name="help_search_suggestion_test")

source = """Sorry, no help matches that.  Perhaps you meant:
    races
    group rank grouprank rankings ratings rate
    bane weapon quarry race
    object flag artifact rare unique epic remarkable antique relic exceptional
    cleric petition celestials audience angels glory repentance
    warrior skill bloodrage blood rage
    druid skill birdcalls call birds flock songbirds magpie raven bald eagle falcon
    druid skill call legendary raptor roc phoenix thunderbird
    druid call list animals porcupine coyote boar hyena winter wolf stag black brown polar bear baboon elk ape mountain lion panther moose swarm rats bats viper
    druid salve insect repellent"""

assert module["is_help_search_listing"](source)
assert module["should_bypass_whole_block_cache"](source)
translated = module["translate_help_search_listing"](source, {})
source_lines = source.splitlines()
translated_lines = translated.splitlines()
assert len(translated_lines) == len(source_lines)
assert translated_lines[0] == "抱歉，找不到符合的說明。你可能是指："
assert translated_lines[1:] == source_lines[1:]
assert not module["is_help_search_listing"](
    "Sorry, no help matches that.  Perhaps you meant:\nThis is ordinary prose!"
)

print("HELP_SEARCH_SUGGESTIONS_OK keywords=preserved line_count=preserved")
