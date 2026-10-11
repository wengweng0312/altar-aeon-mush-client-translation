"""Regression checks for line-safe Alter Aeon consider reports."""

from __future__ import annotations

import runpy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "src/mush-z/worlds/plugins/translation_bridge/translation_worker.py"
module = runpy.run_path(str(WORKER), run_name="consider_report_test")

source = (
    "it's a     1.\n"
    "Do you feel lucky, punk?\n"
    "Mother Fairy's medium armor is somewhat effective against your weaponry.\n"
    "Mother Fairy is flying and is wide open to ranged attacks such as sling bullets, arrows and crossbow bolts.\n"
    "Your armor would be no defense against Mother Fairy's attacks.\n"
    "You are capable of dishing out more damage than Mother Fairy.\n"
    "You use your knowledge of monster lore:\n"
    "Mother Fairy...\n"
    " Might be somewhat resistant to breath damage."
)

assert module["is_consider_report"](source)
module["translate_consider_line"].__globals__["translate_cached_phrase"] = lambda value, _config: "母親仙女"
module["translate_consider_line"].__globals__["translate_piece"] = lambda *_args, **_kwargs: (_ for _ in ()).throw(
    AssertionError("known consider rows must not call a translation engine")
)
result = module["translate_consider_report"](source, {})
lines = result.splitlines()
assert len(lines) == len(source.splitlines()) == 9, lines
assert lines[0] == "這是 1。", lines
assert lines[2].startswith("母親仙女的中甲"), lines
assert lines[3].startswith("母親仙女正在飛行"), lines
assert lines[6] == "你運用怪物知識進行判斷：", lines
assert lines[7] == "母親仙女……", lines
assert lines[8].endswith("吐息傷害具有一定程度抗性。"), lines

older = (
    "it's a 0.\n"
    "The perfect match! Don't try it twice in a row...\n"
    "Your attacks would be mostly absorbed by A kobold war leader's medium armor.\n"
    "Your armor would be no defense against A kobold war leader's attacks.\n"
    "A kobold war leader's ability to do damage far exceeds yours.\n"
    "A kobold war leader would not hesitate to come after you."
)
assert module["is_consider_report"](older)
assert len(module["translate_consider_report"](older, {}).splitlines()) == 6

print("CONSIDER_REPORT_OK lines_preserved=yes engine_calls_for_known_rows=zero")
