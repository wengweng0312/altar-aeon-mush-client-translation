"""Regression checks for dynamic Current Event Information bulletins."""

from __future__ import annotations

import runpy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "src" / "mush-z" / "worlds" / "plugins" / "translation_bridge" / "translation_worker.py"
FIXTURE = ROOT / "tools" / "fixtures" / "current_event_information.txt"
module = runpy.run_path(str(WORKER), run_name="current_event_report_test")

source = FIXTURE.read_text(encoding="utf-8").rstrip()

units = module["current_event_semantic_units"](source)
assert module["is_current_event_report"](source)
assert units[0] == ("fixed", "目前活動資訊"), units
assert any(value == "Our Halloween Havoc has begun And will end sometime on Monday, November 2." for _kind, value in units), units
assert any(value == "Please note:" for _kind, value in units), units
assert any(value == "Thanks and we hope you have fun, The AA team." for _kind, value in units), units
assert units[-2][1] == "(see 'show schedule' for a schedule of events)", units
assert len(units) > 20, units

globals_ = module["translate_current_event_report"].__globals__
cache = {}
globals_["cache_get"] = lambda key, _config: cache.get(key)
globals_["cache_put"] = lambda key, value, _config: cache.__setitem__(key, value)
globals_["cloud_translate_many"] = lambda fields: ["中文：" + value for value in fields]
result = module["translate_current_event_report"](source, {})
assert len(result.splitlines()) == len(units), result
assert result.splitlines()[0] == "目前活動資訊", result
assert module["should_bypass_whole_block_cache"](source)

print("CURRENT_EVENT_REPORT_OK semantic_rows=%d cache_bypass=yes" % len(units))
