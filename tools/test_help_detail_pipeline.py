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
