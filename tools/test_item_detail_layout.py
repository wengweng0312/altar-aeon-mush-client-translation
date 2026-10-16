"""Regression fixture for dense item-identification field layout."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "src/mush-z/worlds/plugins/translation_bridge/translation_worker.py"
PLUGIN = ROOT / "src/mush-z/worlds/plugins/Translation_Mode.xml"
BOUNDARY = re.compile(
    r",\s*(?=(?:Level|Comp|Type|Weight|Damage|Speed|Damage Type|Quality):"
    r"|\d+\s+wield strength(?:\b|$)|(?:HIT_POINTS|MANA|MOVE)\s+by\b)",
    re.I,
)


def main() -> None:
    source = (
        "nightslayer, Level: 28, Comp: BASE METAL, METAL, Type: WEAPON, "
        "Weight: 8 ARTIFACT LIGHT GLOW , Damage: 6d7, Speed: slow, "
        "Damage Type: nonorm slice, 17 wield strength, HIT_POINTS by 20, "
        "MANA by 20, MOVE by 20, Quality: WELL CRAFTED"
    )
    fields = [part.strip(" ,") for part in BOUNDARY.split(source) if part.strip(" ,")]
    assert len(fields) == 13, fields
    assert fields[0] == "nightslayer"
    assert fields[2] == "Comp: BASE METAL, METAL"
    assert fields[6] == "Speed: slow"
    assert fields[7] == "Damage Type: nonorm slice"
    assert fields[-1] == "Quality: WELL CRAFTED"
    numbers = re.findall(r"\d+(?:d\d+)?", source)
    assert all(number in "\n".join(fields) for number in numbers)

    armor = (
        "the helmet of dreams, Level: 28, Comp: BASE METAL, SILVER, Type: ARMOR, "
        "Weight: 1 ARTIFACT GLOW QUEST_ITEM, AC: 7, HEAD, MANA_REGEN by 3.0, "
        "WIS by 1, INT by 1, MANA by 8, Quality: WELL CRAFTED, "
        "This item is bound to your account."
    )
    armor_fields = [part.strip(" ,") for part in BOUNDARY.split(armor) if part.strip(" ,")]
    # The production boundary also includes every affect and wear-location
    # code. Static checks below ensure those reviewed groups remain enabled.
    assert "MANA_REGEN by 3.0" in armor

    worker = WORKER.read_text(encoding="utf-8")
    plugin = PLUGIN.read_text(encoding="utf-8-sig")
    assert "split_item_detail_fields" in worker
    assert '"MANA_REGEN": "法力恢復"' in (
        ROOT / "src/mush-z/worlds/plugins/translation_bridge/build_mush_structure_catalog.py"
    ).read_text(encoding="utf-8")
    assert '"You are full.": "你完全恢復了。"' in worker
    assert '"MANA_REGEN", "ALIGNMENT"' in worker
    assert "item_detail_semantic_source_lines" in plugin

    spec = importlib.util.spec_from_file_location("item_detail_worker_test", WORKER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    icebringer = (
        "Icebringer, Level: 27, Comp: NON-SOLID, ICE, Type: WEAPON, "
        "Weight: 32 ARTIFACT GLOW, 2_WIELD, Damage: 6d11, Speed: slowest, "
        "Damage Type: ice slash, 25 wield strength, DAMROLL by 9, HITROLL by 9, "
        "SAVING_FIRE by 25%, HIT_POINTS by 20, MOVE by 20, MANA by 20, "
        "Quality: WELL CRAFTED, This item is bound to your account."
    )
    rendered = icebringer.replace("2_WIELD", "雙手持握")
    assert (module.Decimal("2"), False) not in module.numeric_values(icebringer)
    assert module.numeric_items_preserved(icebringer, rendered)
    total_levels = (
        "a cloak of concealment, Total levels: 61 (and 20 thief), "
        "Comp: TEXTILE, FABRIC, Type: ARMOR, Weight: 12 RARE ANTI_GOOD THIEF, "
        "AC: 2, ABOUT_BODY, HIDE by 1, DAMROLL by 2, THIEF_SKILL_LEVEL by 1, "
        "Quality: WELL CRAFTED, This item is bound to you."
    )
    assert module.is_numeric_report_block(total_levels)
    total_fields = module.split_item_detail_fields(total_levels)
    assert total_fields and total_fields[1] == "Total levels: 61 (and 20 thief)", total_fields
    assert module.translate_item_detail_field(total_fields[1], {}) == "總等級：61（另含 20 級盜賊）"
    module.cache_get = lambda source, config: None
    module.cache_put = lambda source, translated, config: None
    module.translate_piece = lambda source, config, **kwargs: "譯：" + source
    translated_total = module.translate_item_detail_line(total_levels, {})
    assert translated_total and len(translated_total.splitlines()) >= 10, translated_total
    assert "總等級：61（另含 20 級盜賊）" in translated_total
    assert module.numeric_items_preserved(total_levels, translated_total)

    carrying = (
        "a huge two handed spiked club, Total levels: 73, Comp: BASE METAL, IRON, "
        "Type: WEAPON, Weight: 40, 2_WIELD, Damage: 3d15, Speed: slow, "
        "Damage Type: crush, 27 wield strength, DAMROLL by 14, ARMOR by 14, "
        "HIT_POINTS by 50, Quality: WELL CRAFTED "
        "You are carrying a huge two handed spiked club."
    )
    translated_carrying = module.translate_item_detail_line(carrying, {})
    assert translated_carrying, translated_carrying
    carrying_rows = translated_carrying.splitlines()
    assert carrying_rows[-2] == "品質：工藝精良", carrying_rows
    assert carrying_rows[-1].startswith("你正攜帶著"), carrying_rows
    assert len(carrying_rows) == len(module.split_item_detail_fields(
        carrying[:carrying.index(" You are carrying")]
    )) + 1, carrying_rows

    assert '(value:find(", Level:", 1, true) or value:find(", Total levels:", 1, true))' in plugin
    assert 'value:gsub("%s+(You are carrying .+)$", "\\n%1")' in plugin
    assert '{"Total levels", "Level", "Comp", "Yield", "Type", "Weight", "Purity"' in plugin

    # Real Total-level equipment must yield exactly the same number of source
    # semantic rows as the worker emits, or NVDA history safely falls back to
    # one large bilingual row.
    warhammer = (
        "an apple-handled copper warhammer, Total levels: 113 , "
        "Comp: BASE METAL, COPPER, Type: WEAPON, Weight: 31 REMARKABLE , "
        "Damage: 4d18, Speed: very slow, Damage Type: crush, "
        "29 wield strength, SAVING_ZAP by 25%, HITROLL by 2, DAMROLL by 8, "
        "INT by 2, MANA_REGEN by 1.5, Quality: EXPERTLY CRAFTED\n"
        "You are carrying an apple-handled copper warhammer."
    )
    translated_warhammer = module.translate_item_detail_line(warhammer, {})
    assert translated_warhammer is not None
    assert len(translated_warhammer.splitlines()) == 16
    assert "總等級：113" in translated_warhammer
    assert "法力恢復：增加 1.5" in translated_warhammer

    ore = (
        "iodargyrite ore, Comp: MINERAL, ROCK, Yield: SILVER, Type: ORE, "
        "Weight: 4 , more pure ore\nYou are carrying iodargyrite ore."
    )
    assert module.is_numeric_report_block(ore)
    ore_fields = module.split_item_detail_fields(ore.splitlines()[0])
    assert ore_fields == [
        "iodargyrite ore", "Comp: MINERAL, ROCK", "Yield: SILVER",
        "Type: ORE", "Weight: 4", "Purity: more pure ore",
    ], ore_fields
    translated_ore = module.translate_numeric_report_block(ore, {})
    ore_rows = translated_ore.splitlines()
    assert len(ore_rows) == 7, ore_rows
    assert ore_rows[1] == "材質：礦物、岩石", ore_rows
    assert ore_rows[2] == "產出：銀", ore_rows
    assert ore_rows[3] == "類型：礦石", ore_rows
    assert ore_rows[4] == "重量：4", ore_rows
    assert ore_rows[5] == "礦石純度：較高", ore_rows
    assert ore_rows[6].startswith("你正攜帶著"), ore_rows

    least_pure_ore = (
        "malachite ore, Comp: MINERAL, MALACHITE, Yield: COPPER, Type: ORE, "
        "Weight: 4 , least pure ore\nYou are carrying malachite ore."
    )
    least_fields = module.split_item_detail_fields(least_pure_ore.splitlines()[0])
    assert least_fields[-2:] == ["Weight: 4", "Purity: least pure ore"], least_fields
    translated_least = module.translate_numeric_report_block(least_pure_ore, {})
    least_rows = translated_least.splitlines()
    assert len(least_rows) == 7, least_rows
    assert least_rows[4] == "重量：4", least_rows
    assert least_rows[5] == "礦石純度：最低", least_rows
    assert module.translate_item_detail_field("Yield: LEAD", {}) == "產出：鉛"
    assert module.translate_item_detail_field("Yield: COPPER", {}) == "產出：銅"
    assert module.translate_item_detail_field("Yield: PLATINUM", {}) == "產出：鉑"
    assert module.translate_item_detail_field("Yield: CADMIUM", {}) == "產出：鎘"
    assert module.translate_item_detail_field("Yield: ADAMANTIUM", {}) == "產出：精金"
    assert module.translate_item_detail_field("Yield: MITHRIL", {}) == "產出：秘銀"
    assert module.translate_item_detail_field("Yield: ORICHALCUM", {}) == "產出：山銅"
    assert module.translate_item_detail_field("Yield: SKY IRON", {}) == "產出：天鐵"
    assert module.translate_item_detail_field("Yield: ARJALE", {}) == "產出：阿爾賈爾（Arjale）"
    assert module.translate_item_detail_field("Yield: ZIFF", {}) == "產出：齊夫（Ziff）"
    assert module.translate_item_detail_field("Yield: UNKNOWNIUM", {}) == "產出：UNKNOWNIUM"
    assert module.translate_item_detail_field("malachite ore", {}) == "孔雀石礦石"
    assert module.translate_item_detail_field("heartstone ore", {}) == "心石礦石"
    assert module.translate_item_detail_field("galena ore", {}) == "方鉛礦"
    assert module.translate_item_detail_field("unobtainium ore", {}) == "unobtainium ore"
    assert module.translate_item_detail_field("Comp: MINERAL, MALACHITE", {}) == "材質：礦物、孔雀石"
    assert module.STRUCTURED_FIELD_CACHE_VERSION >= 4
    assert 'value:find(", Yield:", 1, true)' in plugin
    assert '"Comp", "Yield", "Type", "Weight", "Purity"' in plugin
    print("ITEM_DETAIL_LAYOUT_OK fields=13 total_levels=yes carrying=separate internal_component_comma=preserved")


if __name__ == "__main__":
    main()
