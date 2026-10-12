"""Regression checks for fixed Alter Aeon resource and equipment vocabulary."""

from __future__ import annotations

import runpy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "src/mush-z/worlds/plugins/translation_bridge/translation_worker.py"
module = runpy.run_path(str(WORKER), run_name="translation_worker_test")

deterministic = module["deterministic_translate"]
assert deterministic("hp is full.") == "血量已完全恢復。"
assert deterministic("mana is full.") == "法力已完全恢復。"
assert deterministic("hp and movement are full.") == "血量和體力已完全恢復。"
assert deterministic("+62 movement.") == "+62 體力。"
assert deterministic("You'll need about 1 minute and 27 seconds to regen mana.") == (
    "你大約還需要 1 分 27 秒 才能完全恢復法力。"
)
assert deterministic("<718hp 228m 378mv>") == "<血量 718hp 法力 228m 體力 378mv>"
assert deterministic("Stealth mode on.") == "隱密模式已開啟。"
assert deterministic("A shadow decoy melts back into the shadows.") == "影子誘餌融回陰影之中。"
assert module["translate_cached_phrase"]("a crescent-shaped shadow", {}) == "一道新月形影子"
assert module["translate_cached_phrase"]("Dragon Tooth way", {}) == "龍牙之路"
assert module["should_bypass_whole_block_cache"]("a crescent-shaped shadow")

semantic = module["translate_semantic_event_line"]
semantic.__globals__["translate_cached_phrase"] = lambda value, _config: "「%s」" % value
assert semantic("You are carrying the helmet of dreams.", {}) == "你正攜帶著「the helmet of dreams」。"
assert semantic("You are wielding the blade, 'Mischief'.", {}) == "你正裝備著「the blade, 'Mischief'」。"
assert semantic("You are wearing jadite boots.", {}) == "你正穿戴著「jadite boots」。"
assert semantic("You are holding a venomous snake fang.", {}) == "你正拿著「a venomous snake fang」。"
assert semantic("A small troll is DEAD!", {}) == "「A small troll」死了！"
assert semantic("A dwarven sentinel has arrived.", {}) == "「A dwarven sentinel」來了。"
assert semantic("A small troll sniffs the air, as though catching a nearby scent.", {}) == (
    "「A small troll」嗅了嗅空氣，像是聞到附近的氣味。"
)
assert semantic("You throw a crescent-shaped shadow at A small troll!", {}) == (
    "你向「A small troll」投出「a crescent-shaped shadow」！"
)
assert semantic("You see nothing left to loot from the corpse of A trogdolyte.", {}) == (
    "「A trogdolyte」的屍體已經沒有東西可搜刮了。"
)

equipment_source = """You are using:
head - the demon's horn(artifact)
neck - A necklace of Power (glow)
neck - a black wolf talisman(rare)
arms - jadite sleeves
wrist - a jadite bracer
wrist - a legendary dwarven bracelet(artifact) (glow)
hands - emperal gauntlets
finger - a scarlet crystal ring(rare) (glow)
finger - a black opal ring(artifact) (glow)
on body - a purple-blue tunic
about body - an emperal cloak
waist - a burlap belt
legs - jadite leggings
feet - jadite boots
shield -
weapon - the blade, 'Mischief'(relic)"""

assert module["is_equipment_listing"](equipment_source)
equipment = module["translate_equipment_listing"]
equipment.__globals__["reviewed_phrase_translation"] = lambda value: None
equipment.__globals__["cache_get"] = lambda value, _config: None
equipment.__globals__["cache_put"] = lambda value, translated, _config: None
equipment.__globals__["translate_piece"] = (
    lambda value, _config, force_robust=False: "物品「%s」" % value
)
equipment_result = equipment(equipment_source, {})
equipment_lines = equipment_result.splitlines()
assert len(equipment_lines) == len(equipment_source.splitlines()) == 17
assert equipment_lines[0] == "你正在使用："
assert equipment_lines[2].startswith("頸部 - ")
assert equipment_lines[3].startswith("頸部 - ")
assert equipment_lines[5].startswith("手腕 - ")
assert equipment_lines[6].startswith("手腕 - ")
assert equipment_lines[8].startswith("手指 - ")
assert equipment_lines[9].startswith("手指 - ")
assert equipment_lines[15] == "盾牌 -"
assert equipment_lines[16] == "武器 - 物品「the blade, 'Mischief'(relic)」"

inspection_source = """Testperson is short and of slender build, with brown eyes. Their sandy hair
is shoulder length, but unkempt and messy.
They look fairly young and fresh.
You are in excellent condition.
head        - the demon's horn(artifact)
neck        - A necklace of Power (glow)
arms        - jadite sleeves
hands       - emperal gauntlets
on body     - a purple-blue tunic
shield      -
weapon      - the blade, 'Mischief'(relic)
Testperson is obviously carrying:
the sword of mist
a smithy's hammer
a magic mirror"""

assert module["is_character_inspection_listing"](inspection_source)
inspection = module["translate_character_inspection_listing"]
inspection.__globals__["translate_cached_phrase"] = lambda value, _config: "譯「%s」" % value
inspection_result = inspection(inspection_source, {})
inspection_lines = inspection_result.splitlines()
assert inspection_lines[:4] == [
    "譯「Testperson is short and of slender build, with brown eyes.」",
    "譯「Their sandy hair is shoulder length, but unkempt and messy.」",
    "譯「They look fairly young and fresh.」",
    "譯「You are in excellent condition.」",
]
assert inspection_lines[4].startswith("頭部        - 譯「")
assert inspection_lines[9] == "盾牌      -"
assert inspection_lines[10].startswith("武器      - 譯「")
assert inspection_lines[11] == "Testperson 顯然攜帶："
assert inspection_lines[12:] == [
    "譯「the sword of mist」",
    "譯「a smithy's hammer」",
    "譯「a magic mirror」",
]

print("RESOURCE_EQUIPMENT_TEMPLATES_OK")
