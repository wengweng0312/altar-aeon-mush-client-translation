"""Regression checks for structured Alter Aeon change logs."""

from __future__ import annotations

import runpy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "src/mush-z/worlds/plugins/translation_bridge/translation_worker.py"
module = runpy.run_path(str(WORKER), run_name="changes_report_test")

source = """[3417] ---- Oct 3, 26
From Draak:
Fixed pose so it actually displays the strings.
[3415] ---- XXX XX, 26
From Draak:
You can no longer cast dancing lights in recalls. Multiple dancing
lights cast in or into the same room will merge, similar to continual
light.
Group zone mobs should be adjusting appropriately again. Please let
Draak know if there are still issues, preferrrably by mudmail.
The 'pose' command should now accept a class name. Note that you
will not be able to pose as a designated class unless you have some
levels in it.
[3413] ---- Sep 20, 26
From Draak:
Mobs should no longer bleed to death, to prevent exp loss.
Most recent 3 entries displayed.
To see recent area additions, use the 'area new' command."""

globals_ = module["translate_changes_report"].__globals__
cache = {}
globals_["cache_get"] = lambda key, _config: cache.get(key)
globals_["cache_put"] = lambda key, value, _config: cache.__setitem__(key, value)
globals_["cloud_translate_many"] = lambda fields: ["中文更新內容 %d。" % index for index, _ in enumerate(fields, 1)]

assert module["is_changes_report"](source)
semantic = module["semantic_display_chunks"](
    "Casting detect poison makes the effect stronger. (Morpheus)\n"
    "Mobs should no longer bleed to death. (Simo)\n"
    "Non-aggressive animals should be more receptive to being touched."
)
assert len(semantic) == 3, semantic
result = module["translate_changes_report"](source, {})
lines = result.splitlines()
assert [line for line in lines if line.startswith("[")] == [
    "[3417] ---- Oct 3, 26",
    "[3415] ---- XXX XX, 26",
    "[3413] ---- Sep 20, 26",
], lines
assert lines.count("來自 Draak：") == 3, lines
assert "目前顯示最近 3 筆更新。" in lines, lines
assert "若要查看最近新增的區域，請使用 area new 指令。" in lines, lines
assert globals_["should_bypass_whole_block_cache"](source)

# One failed semantic unit must remain visible in English instead of making the
# entire report disappear.  The deterministic headers still remain intact.
globals_["cloud_translate_many"] = lambda fields: None
globals_["translate_piece"] = lambda value, *_args, **_kwargs: (
    (_ for _ in ()).throw(RuntimeError("simulated unit failure"))
    if "Group zone mobs" in value else "中文更新。"
)
cache.clear()
partial = module["translate_changes_report"](source, {})
assert "Group zone mobs should be adjusting appropriately again." in partial, partial
assert "[3417] ---- Oct 3, 26" in partial and "[3413] ---- Sep 20, 26" in partial

print("CHANGES_REPORT_OK headers=preserved whole_block_fallback=no partial_unit_fallback=yes")
