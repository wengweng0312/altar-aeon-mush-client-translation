"""Regressions for deterministic skill/spell help fields and Usage syntax."""

from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "src/mush-z/worlds/plugins/translation_bridge/translation_worker.py"


def main() -> None:
    spec = importlib.util.spec_from_file_location("help_detail_worker_test", WORKER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    source = """Keywords are:  'cleric spell breath of life'
Spell: breath of life           Mana:  25  Wis: 32  Chr: 28  Lvl 31 Cler  (28%)
                                (important)   Requires: major heal
                                Group: Cleric healing spellgroup
Usage:
cast breath of life <character>
This very powerful healing spell can be used on seriously injured targets,
and can sometimes heal the injured completely in one cast.
It generally cannot be cast on targets with only minor injuries."""

    units = module.parse_help_semantic_units(source)
    assert units[:6] == [
        ("help", "Keywords are:  'cleric spell breath of life'"),
        ("help", "Spell: breath of life           Mana:  25  Wis: 32  Chr: 28  Lvl 31 Cler  (28%)"),
        ("help", "(important)   Requires: major heal"),
        ("help", "Group: Cleric healing spellgroup"),
        ("help", "Usage:"),
        ("raw", "cast breath of life <character>"),
    ], units
    assert len(units) == 8, units

    generic_help = """Showing page 1.
Keywords are:  'reboots resets repops'
A reboot is when the mud is shut down and restarted. This takes approximately
15 seconds, after which time you can log back in and play again.
There are 11 other help pages that may be related to your search.
See 'help search reboot' for a list."""
    assert module.is_skill_help_detail(generic_help)
    generic_units = module.parse_help_semantic_units(generic_help)
    assert generic_units[:2] == [
        ("help", "Showing page 1."),
        ("help", "Keywords are:  'reboots resets repops'"),
    ], generic_units
    assert len(generic_units) == 5, generic_units

    quoted_skills = "Thieves start with the 'trip', 'bloodletting stab' and 'dodge' skills."
    protected, occurrences = module.protect_known_entity_names(quoted_skills)
    assert len(occurrences) == 3, occurrences
    assert all(marker in protected for marker, _source, _translated, kind in occurrences if kind == "skill")
    restored = module.restore_known_entity_names(protected, occurrences)
    assert "'絆倒'" in restored and "'放血刺擊'" in restored and "'閃避'" in restored, restored
    assert module.quoted_skill_pairs("Do not trip over the 'unknown phrase'.") == []
    assert module.is_help_usage_command("call list")
    assert module.is_help_usage_command("throw <object> <direction>")
    assert module.is_help_usage_command("'clobber'")
    assert not module.is_help_usage_command("This is ordinary explanatory prose")

    lapidary = """Usage:
lapidary help                  - this screen
lapidary check                 - check stones and gems in your inventory
lapidary list minerals         - list of lapidary minerals you've mined
lapidary create <item> <stone> - start cutting a new stone item or gemstone"""
    woodcraft = """Usage:
woodcraft help                 - this screen
woodcraft list woods           - list the kinds of woods you've gathered
woodcraft create <type> <wood> - craft a new wooden item
woodcraft saw <object>         - saw a wooden object into lumber"""
    for listing, root in ((lapidary, "lapidary"), (woodcraft, "woodcraft")):
        entries = module.parse_command_usage_listing(listing)
        assert entries and len(entries) == 4, entries
        assert all(command.startswith(root + " ") for command, _description in entries), entries
        assert module.is_command_usage_listing(listing)
        assert module.should_bypass_whole_block_cache(listing)

        original_units = module.translate_semantic_units
        module.translate_semantic_units = lambda units, _config, _context: "\n".join(
            "中譯：" + source for _kind, source in units
        )
        try:
            rendered = module.translate_command_usage_listing(listing, {})
        finally:
            module.translate_semantic_units = original_units
        rendered_rows = rendered.splitlines()
        assert len(rendered_rows) == len(listing.splitlines()), rendered_rows
        assert rendered_rows[0] == "用法：", rendered_rows
        assert rendered_rows[1].startswith(root + " help - 中譯："), rendered_rows
        assert "<" in rendered_rows[-1] and " - 中譯：" in rendered_rows[-1], rendered_rows

    assert not module.is_command_usage_listing(
        "Usage:\nlook - inspect something\nsay hello - talk\nget sword - take it\nother help - mixed root"
    )

    extended_cases = {
        "forge": """Usage:
forge help - this screen
forge smelt <ore> - refine metal ingots from ore
forge create <item> <metal> - forge a new item
To get an estimate for creating objects,
add '-cost' at the end of the command.""",
        "leathercraft": """Usage:
leathercraft help - this screen
leathercraft list - list leather item types
leathercraft create <type> <skin> - craft a new leather item
Most leathercrafted items require a hide of double the list size to create.""",
        "skin": """Usage:
skin <corpse> - cut skin from a corpse
Skinning is used to get skins from corpses. The more skilled you are
at skinning, the more intact the corpse will be.""",
    }
    for root, listing in extended_cases.items():
        parts = module._command_usage_parts(listing)
        assert parts, (root, parts)
        entries, trailing = parts
        assert entries[0][0].startswith(root), entries
        assert trailing, (root, trailing)
        assert module.should_bypass_whole_block_cache(listing)

    craftable = """A branch can be crafted into...
 [bowl                ]
 [dish                ]
 [fishing pole        ]
 [mask                ]
 [walking cane        ]
It is flexible. It will be good for crafting bows and crossbows.
Use 'woodcraft create' to start crafting."""
    assert module.is_craftable_material_listing(craftable)
    craft_units = module.craftable_material_units(craftable)
    assert [value for kind, value in craft_units if kind == "keyword"] == [
        "bowl", "dish", "fishing pole", "mask", "walking cane",
    ], craft_units
    assert craft_units[0] == ("translate", "A branch can be crafted into..."), craft_units

    forge_listing = """It would be very easy to forge an ingot of copper into...
 beaker
 bottle
 bowl
 shield rim
 cross guard
 arrowhead"""
    assert module.is_craftable_material_listing(forge_listing)
    forge_units = module.craftable_material_units(forge_listing)
    assert forge_units[0] == ("translate", "It would be very easy to forge an ingot of copper into..."), forge_units
    assert forge_units[1:] == [
        ("keyword", "beaker"), ("keyword", "bottle"), ("keyword", "bowl"),
        ("keyword", "shield rim"), ("keyword", "cross guard"), ("keyword", "arrowhead"),
    ], forge_units
    semantic = module.translate_semantic_units
    semantic_globals = semantic.__globals__
    prefetched = []
    semantic_globals["prefetch_cached_phrases"] = lambda values, _config: prefetched.extend(values)
    semantic_globals["translate_cached_phrase"] = lambda value, _config: "中：" + value
    semantic_globals["cache_get"] = lambda _value, _config: "鍛造標題"
    forge_result = semantic(forge_units, {}, "craftable_material")
    assert forge_result.splitlines() == [
        "鍛造標題", "燒杯 [beaker]", "瓶子 [bottle]", "碗 [bowl]",
        "盾牌邊框 [shield rim]", "十字護手 [cross guard]", "箭頭 [arrowhead]",
    ], forge_result
    assert prefetched == [], prefetched
    assert module.CRAFT_KEYWORD_ZH["cup"] == "杯子"
    assert module.CRAFT_KEYWORD_ZH["dish"] == "盤子"
    assert module.CRAFT_KEYWORD_ZH["flask"] == "燒瓶"
    assert module.CRAFT_KEYWORD_ZH["goblet"] == "高腳杯"
    assert module.CRAFT_KEYWORD_ZH["highball"] == "高球杯"
    assert module.CRAFT_KEYWORD_ZH["jug"] == "壺"
    assert module.CRAFT_KEYWORD_ZH["lowball"] == "矮杯"
    assert craft_units[-1][0] == "translate", craft_units
    assert module.should_bypass_whole_block_cache(craftable)

    forge_catalog = """ [ basin                ] , LIQUID CONTAINER
 [ goblet               ] , LIQUID CONTAINER  , held
 [ helmet               ] , CONTAINER         , head
 [ axe head             ] , PART
 [ bullet               ] , AMMO
 [ crowbar              ] , WEAPON            , one-handed weapon
Use 'forge create <item> <metal>' to start forging a new metal item."""
    assert module.is_forge_catalog_listing(forge_catalog)
    assert module.should_bypass_whole_block_cache(forge_catalog)
    catalog_globals = module.translate_forge_catalog_listing.__globals__
    old_prefetch = catalog_globals["prefetch_cached_phrases"]
    old_translate = catalog_globals["translate_cached_phrase"]
    catalog_globals["prefetch_cached_phrases"] = lambda _values, _config: None
    catalog_globals["translate_cached_phrase"] = lambda value, _config: "中：" + value
    try:
        catalog_result = module.translate_forge_catalog_listing(forge_catalog, {})
    finally:
        catalog_globals["prefetch_cached_phrases"] = old_prefetch
        catalog_globals["translate_cached_phrase"] = old_translate
    assert catalog_result.splitlines() == [
        "盆 [basin]，液體容器",
        "高腳杯 [goblet]，液體容器，手持",
        "中：helmet [helmet]，容器，頭部",
        "斧頭 [axe head]，零件",
        "子彈 [bullet]，彈藥",
        "撬棍 [crowbar]，武器，單手武器",
        "使用 'forge create <item> <metal>' 開始鍛造新的金屬物品。",
    ], catalog_result

    woodcraft_catalog = """[ bowl ] , LIQUID CONTAINER
[ chopsticks ] , TREASURE , head
[ fishing pole ] , FISHPOLE
[ canoe ] , BOAT
[ clogs ] , ARMOR , feet
[ tower shield ] , ARMOR , two-handed shield
[ walking cane ] , FOCUS , held
[ figurehead ] , OTHER
Use 'woodcraft create <item> <wood>' to start making a new woodcrafted item."""
    assert module.is_forge_catalog_listing(woodcraft_catalog)
    woodcraft_result = module.translate_forge_catalog_listing(woodcraft_catalog, {})
    assert woodcraft_result.splitlines() == [
        "碗 [bowl]，液體容器",
        "筷子 [chopsticks]，寶物，頭部",
        "釣魚竿 [fishing pole]，釣魚竿",
        "獨木舟 [canoe]，船隻",
        "木屐 [clogs]，盔甲，腳部",
        "塔盾 [tower shield]，盔甲，雙手盾牌",
        "手杖 [walking cane]，法器，手持",
        "船首像 [figurehead]，其他",
        "使用 'woodcraft create <item> <wood>' 開始製作新的木製物品。",
    ], woodcraft_result

    future_skill_catalog = """[ robe ] , GARMENT , body
[ sash ] , GARMENT , waist
[ cap ] , GARMENT , head
[ glove ] , GARMENT , hands
[ boot ] , GARMENT , feet
Use 'tailoring weave <item> <cloth>' to begin an unfamiliar crafting process."""
    assert module.is_forge_catalog_listing(future_skill_catalog)
    assert module.should_bypass_whole_block_cache(future_skill_catalog)

    forge_recipe = """[ shovel ] , shovel head, haft, mining tool
[ hatchet ] , axe head, handle, one-handed weapon
[ halberd ] , axe head, pole, guard, two-handed weapon
[ thresher ] , mace head, grip, weapon chain, one-handed weapon
[ spear ] , spear head, haft, two-handed weapon"""
    assert module.is_forge_recipe_listing(forge_recipe)
    assert module.should_bypass_whole_block_cache(forge_recipe)
    recipe_result = module.translate_forge_recipe_listing(forge_recipe, {})
    assert recipe_result.splitlines() == [
        "鏟子 [shovel]，鏟頭，長柄，採礦工具",
        "手斧 [hatchet]，斧頭，手柄，單手武器",
        "戟 [halberd]，斧頭，長桿，護手，雙手武器",
        "連枷 [thresher]，釘頭錘頭，握把，武器鏈，單手武器",
        "長矛 [spear]，矛頭，長柄，雙手武器",
    ], recipe_result

    translations = {
        "breath of life": "生命氣息",
        "major heal": "強效治療",
        "Cleric healing spellgroup": "牧師治療法術組",
    }
    original_phrase = module.translate_cached_phrase
    module.translate_cached_phrase = lambda text, _config: translations.get(text, "中譯<%s>" % text)
    try:
        header = module.translate_help_metadata_unit(units[1][1], {})
        requires = module.translate_help_metadata_unit(units[2][1], {})
        group = module.translate_help_metadata_unit(units[3][1], {})
    finally:
        module.translate_cached_phrase = original_phrase
    assert header == "咒語：生命氣息；法力：25；智慧：32；魅力：28；等級：31；職業：牧師（28%）", header
    assert requires == "重要；前置需求：強效治療", requires
    assert group == "分組：牧師治療法術組", group

    class_cases = {
        "Mage": "法師", "Cler": "牧師", "Thie": "盜賊",
        "Warr": "戰士", "Necr": "死靈法師", "Drui": "德魯伊",
    }
    module.translate_cached_phrase = lambda text, _config: "測試技能"
    try:
        for abbreviation, expected in class_cases.items():
            row = "Skill: test skill               Lvl 12 %s  (28%%)" % abbreviation
            result = module.translate_help_metadata_unit(row, {})
            assert "職業：%s（28%%）" % expected in result, (abbreviation, result)
    finally:
        module.translate_cached_phrase = original_phrase

    print("HELP_DETAIL_PIPELINE_OK fields=fixed classes=6 usage=multiword review_units=8")


if __name__ == "__main__":
    main()
