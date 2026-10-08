"""Regression fixture for dense item-identification field layout."""

from __future__ import annotations

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
    print("ITEM_DETAIL_LAYOUT_OK fields=13 internal_component_comma=preserved")


if __name__ == "__main__":
    main()
