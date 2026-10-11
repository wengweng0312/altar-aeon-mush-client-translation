"""Regression checks for Usage rows containing command-line style options."""

from __future__ import annotations

import runpy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "src/mush-z/worlds/plugins/translation_bridge/translation_worker.py"
module = runpy.run_path(str(WORKER), run_name="command_usage_options_test")

source = """Usage:
scan help            - this page
scan                 - scan in all directions
scan [direction]     - scan only in the designated direction
scan -dclient [args] - look before scanning"""

globals_ = module["translate_command_usage_listing"].__globals__
cache = {}
globals_["cache_get"] = lambda key, _config: cache.get(key)
globals_["cache_put"] = lambda key, value, _config: cache.__setitem__(key, value)
globals_["cloud_translate_many"] = lambda fields: [
    "此頁面",
    "向所有方向掃描",
    "只向指定方向掃描",
    "掃描前查看",
]

assert module["is_help_usage_command"]("scan -dclient [args]")
assert module["is_help_usage_command"]("forge smelt <ore> -cost")
assert module["is_command_usage_listing"](source)
result = module["translate_command_usage_listing"](source, {})
assert result.splitlines() == [
    "用法：",
    "scan help - 此頁面",
    "scan - 向所有方向掃描",
    "scan [direction] - 只向指定方向掃描",
    "scan -dclient [args] - 掃描前查看",
], result

print("COMMAND_USAGE_OPTIONS_OK option_preserved=yes rows=5")
