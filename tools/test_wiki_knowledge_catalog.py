#!/usr/bin/env python3
"""Regression checks for the offline Alter Aeon Wiki knowledge catalog."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / "src/mush-z/worlds/plugins/translation_bridge"
DB = BRIDGE / "wiki_knowledge_catalog.sqlite3"
ADDITIONS = ROOT / "tools/reviewed_wiki_ability_additions.json"


def scalar(db: sqlite3.Connection, sql: str, args=()):
    return db.execute(sql, args).fetchone()[0]


def main() -> int:
    assert DB.exists(), DB
    db = sqlite3.connect(DB)
    assert int(scalar(db, "SELECT value FROM metadata WHERE key='ability_count'")) >= 570
    assert scalar(db, "SELECT value FROM metadata WHERE key='priority_rule'") == (
        "reviewed_game_data_over_wiki_over_model"
    )
    glossary = json.loads((BRIDGE / "skill_glossary_zh_tw.json").read_text(encoding="utf-8-sig"))
    additions = json.loads(ADDITIONS.read_text(encoding="utf-8-sig"))
    assert len(additions) == 119
    for english, chinese in additions.items():
        assert glossary.get(english) == chinese
    for english, chinese in glossary.items():
        row = db.execute(
            "SELECT traditional_chinese, translation_reviewed FROM abilities WHERE ability_key=?",
            (english.casefold(),),
        ).fetchone()
        if row:
            assert row == (chinese, 1), (english, row, chinese)

    expected_affects = {
        "HP": "血量", "MANA": "法力", "MOVE": "體力",
        "HP_REGEN": "血量恢復", "HITROLL": "命中加值", "DAMROLL": "傷害加值",
        "ARMOR": "護甲值", "ATTACK_SPEED": "攻擊速度",
    }
    for code, chinese in expected_affects.items():
        assert db.execute(
            "SELECT traditional_chinese FROM item_affects WHERE affect_code=?", (code,)
        ).fetchone() == (chinese,)

    assert db.execute(
        "SELECT required_level, prerequisite_key FROM guild_skill_tree "
        "WHERE guild_name='Rangers Guild' AND ability_key='leathercraft'"
    ).fetchone() == (7, "hunter")
    assert db.execute(
        "SELECT required_level, prerequisite_key FROM guild_skill_tree "
        "WHERE guild_name='Smiths Guild' AND ability_key='forge armor'"
    ).fetchone() == (18, "jewelrysmithing")
    assert scalar(db, "SELECT COUNT(*) FROM classes") == 6
    assert scalar(db, "SELECT COUNT(*) FROM abilities WHERE translation_reviewed=0") == 0
    assert db.execute(
        "SELECT traditional_chinese FROM abilities WHERE ability_key='remise'"
    ).fetchone() == ("格擋後續擊",)
    assert db.execute(
        "SELECT traditional_chinese FROM abilities WHERE ability_key='diamantaire'"
    ).fetchone() == ("鑽石工匠",)
    db.close()
    print("WIKI_KNOWLEDGE_CATALOG_REGRESSION_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
