"""Regression tests for level-up skill tables and embedded nearby previews."""

from __future__ import annotations

import runpy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "src/mush-z/worlds/plugins/translation_bridge/translation_worker.py"
PLUGIN = ROOT / "src/mush-z/worlds/plugins/Translation_Mode.xml"
module = runpy.run_path(str(WORKER), run_name="skills_preview_test")

skills = """Available spells and skills at level 16
General      - cobbler                              -(guild)
Mage         - potion lore                          -(helpful)
Mage         - darken                               -(important)
Mage         - crystal coat                         -(important)
Mage         - diffraction                          -(obscure)
Cleric       - sunbeam                              -(helpful)
Cleric       - charm person                         -(obscure)
Cleric       - noxious cloud                        -(helpful)
Thief        - steal                                -(important)
Thief        - poison weapon                        -(helpful)
Warrior      - rally                                -(important)
Warrior      - moulinet                             -(helpful)
Warrior      - attract                              -(helpful)
Necromancer  - harvest bone                         -(obscure)
Necromancer  - skeletal warrior                     -(critical)
Druid        - reduce decoction                     -(helpful)
Druid        - tempest                              -(critical)"""

assert module["is_available_level_skills_block"](skills)
translated = module["translate_available_level_skills_block"](skills, {})
source_lines = skills.splitlines()
translated_lines = translated.splitlines()
assert len(translated_lines) == len(source_lines) == 18
assert translated_lines[0] == "第 16 級可用的法術與技能："
assert translated_lines[1] == "通用 - 修鞋匠（公會）"
assert "法師 - 黑暗化（重要）" in translated_lines
assert "牧師 - 魅惑人類（冷門）" in translated_lines
assert "死靈法師 - 收集骨骸（冷門）" in translated_lines
assert translated_lines[-1] == "德魯伊 - 暴風雨（關鍵）"

preview = """You see the entrance to a large cave, made of stones and boulders piled up.
Nearby you see:
A stealthy spider guard
A stealthy spider guard"""
assert module["is_room_preview_block"](preview)
units = module["parse_room_preview_units"](preview)
assert units == [
    ("translate", "You see the entrance to a large cave, made of stones and boulders piled up."),
    ("fixed", "在附近你可以看到："),
    ("translate", "A stealthy spider guard"),
    ("translate", "A stealthy spider guard"),
]

plugin = PLUGIN.read_text(encoding="utf-8-sig")
assert "local header_index = nil" in plugin
assert "for i = 1, header_index - 1" in plugin
print("AVAILABLE_SKILLS_EMBEDDED_PREVIEW_OK skills=18 preview=4")
