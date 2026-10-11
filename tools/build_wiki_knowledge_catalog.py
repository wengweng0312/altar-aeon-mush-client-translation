#!/usr/bin/env python3
"""Build a privacy-safe offline knowledge catalog from Alter Aeon Wiki.

The Wiki supplements gaps in the official class catalog.  It never overrides
reviewed translations, and the generated database contains no player data.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


API = "https://wiki.alteraeon.com/api.php"
WIKI = "https://wiki.alteraeon.com/index.php/"
ABILITY_CATEGORY = "Category:Skills and Spells"

CLASSES = {
    "mage": ("法師", "mag"),
    "cleric": ("牧師", "cler"),
    "thief": ("盜賊", "thi"),
    "warrior": ("戰士", "war"),
    "necromancer": ("死靈法師", "necr"),
    "druid": ("德魯伊", "dru"),
}

# Reviewed, finite trees published on the individual guild pages.  Keeping
# these explicit makes changes reviewable instead of silently trusting prose.
GUILD_TREES = {
    "Rangers Guild": [
        ("hunter", 1, ""), ("leathercraft", 7, "hunter"),
        ("tanner", 10, "leathercraft"), ("cobbler", 16, "tanner"),
        ("furrier", 22, "cobbler"), ("shellcraft", 30, "furrier"),
        ("flay animental", 33, "shellcraft"),
    ],
    "Smiths Guild": [
        ("metallurgy", 10, ""), ("forge simple weapon", 13, "metallurgy"),
        ("jewelrysmithing", 15, "forge simple weapon"),
        ("forge armor", 18, "jewelrysmithing"),
        ("forge blade", 23, "forge armor"),
        ("reinforce armor", 31, "forge blade"),
        ("forge kozane and nihonto", 34, "reinforce armor"),
    ],
    "Haberdashers Guild": [
        ("hatmaking", 5, ""), ("tailoring", 10, "hatmaking"),
        ("kiltmaking", 15, "tailoring"), ("livery", 18, "kiltmaking"),
        ("haute couture", 25, "livery"), ("shabby chic", 29, "haute couture"),
        ("orphrey", 34, "shabby chic"),
    ],
}

ITEM_AFFECTS = {
    "HP": "血量", "MANA": "法力", "MOVE": "體力",
    "HP_REGEN": "血量恢復", "MANA_REGEN": "法力恢復",
    "MOVE_REGEN": "體力恢復", "STR": "力量", "INT": "智力",
    "WIS": "智慧", "DEX": "敏捷", "CON": "體質", "CHR": "魅力",
    "WARRIOR_SKILL_LEVEL": "戰士技能等級", "THIEF_SKILL_LEVEL": "盜賊技能等級",
    "MAGE_CAST_LEVEL": "法師施法等級", "CLERIC_CAST_LEVEL": "牧師施法等級",
    "NECR_CAST_LEVEL": "死靈法師施法等級", "HITROLL": "命中加值",
    "DAMROLL": "傷害加值", "ATTACK_SPEED": "攻擊速度", "ARMOR": "護甲值",
    "LUCK": "幸運", "CAST_ABILITY": "施法能力", "SNEAK": "潛行",
    "HIDE": "隱藏", "PARRY": "招架", "DODGE": "閃避",
}


def api_query(params: dict[str, str]) -> dict:
    query = urllib.parse.urlencode({"format": "json", **params})
    request = urllib.request.Request(
        API + "?" + query, headers={"User-Agent": "Mush-Z-Translation-Catalog/1.0"}
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def category_pages(category: str) -> list[str]:
    rows: list[str] = []
    continuation: dict[str, str] = {}
    while True:
        payload = api_query({
            "action": "query", "list": "categorymembers", "cmtitle": category,
            "cmtype": "page", "cmlimit": "500", **continuation,
        })
        rows.extend(item["title"] for item in payload["query"]["categorymembers"])
        continuation = payload.get("continue", {})
        if not continuation:
            return rows


def page_categories(titles: list[str]) -> dict[str, list[str]]:
    output: dict[str, list[str]] = {}
    for offset in range(0, len(titles), 50):
        batch = titles[offset:offset + 50]
        continuation: dict[str, str] = {}
        while True:
            payload = api_query({
                "action": "query", "prop": "categories", "cllimit": "500",
                "titles": "|".join(batch), **continuation,
            })
            for page in payload["query"]["pages"].values():
                output.setdefault(page["title"], []).extend(
                    row["title"].removeprefix("Category:") for row in page.get("categories", [])
                )
            continuation = payload.get("continue", {})
            if not continuation:
                break
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--glossary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--snapshot-output", type=Path)
    args = parser.parse_args()

    glossary = json.loads(args.glossary.read_text(encoding="utf-8-sig"))
    glossary = {str(k).strip().lower(): str(v).strip() for k, v in glossary.items()}
    titles = sorted(set(category_pages(ABILITY_CATEGORY)), key=str.casefold)
    categories = page_categories(titles)
    rows = []
    for title in titles:
        key = title.casefold()
        cats = sorted(set(categories.get(title, [])), key=str.casefold)
        rows.append({
            "english": title, "key": key, "traditional_chinese": glossary.get(key, ""),
            "reviewed": int(key in glossary), "categories": cats,
            "source_url": WIKI + urllib.parse.quote(title.replace(" ", "_")),
        })

    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        args.output.unlink()
    db = sqlite3.connect(args.output)
    db.executescript("""
      PRAGMA journal_mode=DELETE;
      CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
      CREATE TABLE abilities (
        ability_key TEXT PRIMARY KEY, english_name TEXT UNIQUE NOT NULL,
        traditional_chinese TEXT NOT NULL, translation_reviewed INTEGER NOT NULL,
        source_url TEXT NOT NULL
      );
      CREATE TABLE ability_categories (
        ability_key TEXT NOT NULL REFERENCES abilities(ability_key),
        category TEXT NOT NULL, PRIMARY KEY(ability_key, category)
      );
      CREATE TABLE classes (
        class_key TEXT PRIMARY KEY, english_name TEXT NOT NULL,
        traditional_chinese TEXT NOT NULL, abbreviation TEXT UNIQUE NOT NULL
      );
      CREATE TABLE guild_skill_tree (
        guild_name TEXT NOT NULL, ability_key TEXT NOT NULL, required_level INTEGER NOT NULL,
        prerequisite_key TEXT NOT NULL, source_url TEXT NOT NULL,
        PRIMARY KEY(guild_name, ability_key)
      );
      CREATE TABLE item_affects (
        affect_code TEXT PRIMARY KEY, traditional_chinese TEXT NOT NULL,
        source_url TEXT NOT NULL
      );
      CREATE INDEX idx_ability_reviewed ON abilities(translation_reviewed, ability_key);
      CREATE INDEX idx_ability_category ON ability_categories(category, ability_key);
    """)
    metadata = {
        "schema_version": "1", "generated_utc": datetime.now(timezone.utc).isoformat(),
        "source": "Alter Aeon Wiki plus reviewed project glossary",
        "priority_rule": "reviewed_game_data_over_wiki_over_model",
        "privacy": "public_game_data_only_no_player_text",
        "ability_count": str(len(rows)),
        "reviewed_translation_count": str(sum(row["reviewed"] for row in rows)),
    }
    db.executemany("INSERT INTO metadata VALUES (?,?)", metadata.items())
    db.executemany(
        "INSERT INTO abilities VALUES (?,?,?,?,?)",
        ((r["key"], r["english"], r["traditional_chinese"], r["reviewed"], r["source_url"]) for r in rows),
    )
    db.executemany(
        "INSERT INTO ability_categories VALUES (?,?)",
        ((r["key"], category) for r in rows for category in r["categories"]),
    )
    db.executemany(
        "INSERT INTO classes VALUES (?,?,?,?)",
        ((key, key.title(), zh, abbreviation) for key, (zh, abbreviation) in CLASSES.items()),
    )
    for guild, tree in GUILD_TREES.items():
        source_url = WIKI + urllib.parse.quote(("The " + guild).replace(" ", "_"))
        db.executemany(
            "INSERT INTO guild_skill_tree VALUES (?,?,?,?,?)",
            ((guild, ability, level, prerequisite, source_url)
             for ability, level, prerequisite in tree),
        )
    affect_url = WIKI + "Category%3AItem_Affect"
    db.executemany(
        "INSERT INTO item_affects VALUES (?,?,?)",
        ((code, zh, affect_url) for code, zh in ITEM_AFFECTS.items()),
    )
    db.commit()
    db.close()

    if args.snapshot_output:
        args.snapshot_output.parent.mkdir(parents=True, exist_ok=True)
        snapshot = {
            "schema_version": 1, "ability_count": len(rows),
            "reviewed_translation_count": sum(row["reviewed"] for row in rows),
            "abilities": rows,
        }
        args.snapshot_output.write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print("WIKI_CATALOG_OK abilities=%d reviewed=%d missing=%d" % (
        len(rows), sum(row["reviewed"] for row in rows),
        len(rows) - sum(row["reviewed"] for row in rows),
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
