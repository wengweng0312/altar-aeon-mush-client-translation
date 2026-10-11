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
    assert [value for kind, value in craft_units if kind == "raw"] == [
        "[bowl]", "[dish]", "[fishing pole]", "[mask]", "[walking cane]",
    ], craft_units
    assert craft_units[0] == ("translate", "A branch can be crafted into..."), craft_units
    assert craft_units[-1][0] == "translate", craft_units
    assert module.should_bypass_whole_block_cache(craftable)

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
