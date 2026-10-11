"""Regression checks for structured Alter Aeon news output."""

from __future__ import annotations

import runpy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "src/mush-z/worlds/plugins/translation_bridge/translation_worker.py"
module = runpy.run_path(str(WORKER), run_name="news_report_test")

source = (
    "ALTER AEON NEWS\n"
    "TODAY'S HEADLINE:\n"
    "The 'ate the kitten' quest is not going to work until we get anothre\n"
    "reboot, nothing to worry about, Draak figured out the problem.\n"
    "Happy Halloween! Watch for carveable pumpkins when foraging!\n"
    "Alter Aeon was last booted:  Sat Oct  3 17:58:32 2026\n"
    "(Type 'changes' to see recent updates to the game's codebase.)\n"
    "Got Their Freak On: Shadowheart, soulsteal, level: 60.\n"
    "Catch of the Day: a wahoo, 127 lbs. - caught by Ozhka\n"
    "New and recently updated areas:\n"
    "Date         Level      [     X,     Y] Name                                             Creators\n"
    "Aug 26 2026  Lvl  27    [   -3929,     56 ] Tyranid caves                                    alf duncan osprey morpheus seren\n"
    "Jul 29 2026  Lvl  32    [     -32,   -409 ] An Abandoned Citadel                             bloodlust morpheus virgo seren\n"
    "Jul 14 2026  Tot 189    [    -526,    561 ] The Cirustal Coast                               morpheus draak"
)

cache = {}
globals_ = module["translate_news_report"].__globals__
globals_["cache_get"] = lambda key, _config: cache.get(key)
globals_["cache_put"] = lambda key, value, _config: cache.__setitem__(key, value)
globals_["cloud_translate_many"] = lambda fields: ["中文段落 %d。" % index for index, _ in enumerate(fields, 1)]
globals_["translate_place_name"] = lambda name, _config, _origin: {
    "Tyranid caves": "泰倫蟲族洞穴",
    "An Abandoned Citadel": "廢棄城堡",
    "The Cirustal Coast": "西魯斯塔爾海岸",
}[name]

assert module["is_news_report"](source)
result = module["translate_news_report"](source, {})
lines = result.splitlines()
assert lines[0] == "ALTER AEON 新聞", lines
assert lines[1] == "今日頭條：", lines
assert any(line.startswith("Alter Aeon 上次重啟時間：") for line in lines), lines
assert any("127 磅" in line and "Ozhka" in line for line in lines), lines
assert any("-3929、56" in line and "泰倫蟲族洞穴" in line for line in lines), lines
assert any("-32、-409" in line and "廢棄城堡" in line for line in lines), lines
assert any("-526、561" in line and "西魯斯塔爾海岸" in line for line in lines), lines
assert max(map(len, lines)) < 300, max(map(len, lines))
assert globals_["should_bypass_whole_block_cache"](source)

print("NEWS_REPORT_OK structured=yes dynamic_numbers=preserved long_single_line=no")
