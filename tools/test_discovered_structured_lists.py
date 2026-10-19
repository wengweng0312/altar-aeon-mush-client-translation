"""Regression coverage for table shapes discovered by the trace auditor."""

from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "src/mush-z/worlds/plugins/translation_bridge/translation_worker.py"


spec = importlib.util.spec_from_file_location("discovered_structured_worker", WORKER)
worker = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(worker)

worker.translate_cached_phrase = lambda value, _config: "中：" + value
worker.translate_place_name = lambda value, _config, _origin: "地：" + value
worker.translate_library_titles = lambda names, _config: ["書：" + name for name in names]

alias_source = "'kk' is aliased to:\nfeint\nstab\ndirt\ncrip\nflour"
assert worker.is_alias_listing(alias_source)
alias_result = worker.translate(alias_source, {})
assert alias_result.splitlines()[1:] == alias_source.splitlines()[1:]
assert len(alias_result.splitlines()) == len(alias_source.splitlines())

guild_source = """Listing Guildmasters in The Smiths Guild:
Rodnar the Redsmith            - Novice       -               - Town of Vemarken
Pegad the Armorer              - Apprentice   -               - The Town of Indira
Spike the dwarven craftsman    - Journeyman   -               - The Town of Dragon Tooth
Henry the Weaponsmith          - Expert       -               - The City of Ralnoth"""
assert worker.is_guildmaster_listing(guild_source)
guild_result = worker.translate(guild_source, {})
guild_rows = guild_result.splitlines()
assert len(guild_rows) == len(guild_source.splitlines())
assert "新手" in guild_rows[1] and "地：Town of Vemarken" in guild_rows[1]
assert "學徒" in guild_rows[2] and "熟練工" in guild_rows[3]

service_source = """Dir  Nearby Service Providers
S    a bronzesmith                    -> Naphtali Bronzeworks -- Arms and Armor for Warriors
SW   Kazon the Tattooist              -> Stone Dragon Tattoos
SE   Madam Kezila                     -> Naphtali Tarot Reading"""
assert worker.is_nearby_direction_listing(service_source)
service_result = worker.translate(service_source, {})
service_rows = service_result.splitlines()
assert len(service_rows) == len(service_source.splitlines())
assert service_rows[0] == "方向　附近服務提供者"
assert service_rows[1].startswith("南　中：a bronzesmith")
assert "-> 地：Naphtali Bronzeworks -- Arms and Armor for Warriors" in service_rows[1]

book_source = """Books matching your search 'ore'
 5197 - a book titled 'Primitive Stone Tools'
 5303 - a small journal
10223 - the Dogma of Ducttapology
10588 - a book titled, 'Artifacts Captured During the Great Wars'"""
assert worker.is_library_catalog(book_source)
book_result = worker.translate(book_source, {})
book_rows = book_result.splitlines()
assert len(book_rows) == len(book_source.splitlines())
assert book_rows[0] == "符合搜尋「ore」的書籍"
assert book_rows[1].startswith(" 5197 - 書：")
assert [row.strip().split(" ", 1)[0] for row in book_rows[1:]] == ["5197", "5303", "10223", "10588"]

short_book_source = """Books with names matching 'mine'
48802 - a book titled, "Where To Find Rocks and Minerals"
49888 - a Miner's Guide to Prospecting"""
assert worker.is_library_catalog(short_book_source)
short_book_result = worker.translate(short_book_source, {})
assert len(short_book_result.splitlines()) == 3
assert short_book_result.splitlines()[0] == "符合搜尋「mine」的書籍"
assert short_book_result.splitlines()[1].startswith("48802 - 書：")
assert short_book_result.splitlines()[2].startswith("49888 - 書：")

area_source = """Realm - The Mainland of Atmir
The birch and aspen forest
This is a level 30 area.
You have 0 out of 8 possible explorer points for this area.
You have acquired none of the fame in this area.
Players that are nearby
          Wengweng      -> In the deep, dark forest
          Areidon       -> A small campfire in the woods."""
assert worker.is_area_overview_report(area_source)
area_result = worker.translate(area_source, {})
area_rows = area_result.splitlines()
assert len(area_rows) == len(area_source.splitlines()), area_rows
assert area_rows[0] == "領域 - 地：The Mainland of Atmir"
assert area_rows[2] == "這是等級 30 的區域。"
assert area_rows[3] == "此區域探索點：0／8。"
assert area_rows[5] == "附近玩家："
assert area_rows[6] == "Wengweng -> 地：In the deep, dark forest"
assert area_rows[7] == "Areidon -> 地：A small campfire in the woods."

# Old one-line cache values must be rejected so the structured renderer can
# rebuild them after an update.
for source in (alias_source, guild_source, service_source, book_source, short_book_source, area_source):
    ok, reason = worker.translation_sanity_ok(source, "錯誤地全部黏成一行")
    assert not ok, (reason, source)

print("DISCOVERED_STRUCTURED_LISTS_OK alias=yes guildmasters=yes services=yes books=yes area=yes")
