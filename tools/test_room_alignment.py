"""Offline regression tests for aligned room title/sentence translation."""

from __future__ import annotations

import ast
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "src" / "mush-z" / "worlds" / "plugins" / "translation_bridge" / "translation_worker.py"
FUNCTIONS = {
    "semantic_sentence_chunks",
    "semantic_sentence_chunks_preserving_repeated_rows",
    "room_title_index",
    "room_semantic_chunks",
    "is_room_prose_candidate",
    "parse_numbered_room_translation",
}
CONSTANTS = {
    "ROOM_PREFIX_END",
    "ROOM_SAFE_PREFIX",
    "ROOM_NON_TITLE",
    "ROOM_PERIOD_TITLE_START",
    "ROOM_NON_PROSE_BLOCK",
    "PLACE_URL_SUFFIX",
}


def load_functions() -> dict[str, object]:
    tree = ast.parse(WORKER.read_text(encoding="utf-8-sig"))
    body = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id in (
                {"ROOM_UNIT_MARKER", "ROOM_UNIT_END_MARKER"} | CONSTANTS
            )
            for target in node.targets
        ):
            body.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name in FUNCTIONS:
            body.append(node)
    namespace = {"re": re}
    exec(compile(ast.Module(body=body, type_ignores=[]), str(WORKER), "exec"), namespace)
    return namespace


def main() -> None:
    module = load_functions()
    chunks = module["room_semantic_chunks"](
        "Three way intersection in the cave\n"
        "This direction changes again, and goes to the west and to the north.\n"
        "The path is clear of any big rocks or boulders but the ground is sandy\n"
        "and is mixed with pebbles.\n"
        "There are unclear markings in the dirt but it is clear there are things\n"
        "living in this cave."
    )
    assert chunks == [
        "Three way intersection in the cave",
        "This direction changes again, and goes to the west and to the north.",
        "The path is clear of any big rocks or boulders but the ground is sandy and is mixed with pebbles.",
        "There are unclear markings in the dirt but it is clear there are things living in this cave.",
    ], chunks

    cellar = (
        "You make your way down the steep steps into the gloom.\n"
        "Cellar\n"
        "A dark and damp cellar filled with barrels and crates. Along one wall a\n"
        "pile of straw has been fashioned into a bed and there is a very strong\n"
        "smell of alcohol in the air, tinged with an unpleasant aroma of waste which\n"
        "seems to be coming from a bucket in one corner."
    )
    cellar_chunks = module["room_semantic_chunks"](cellar)
    assert cellar_chunks[0] == "You make your way down the steep steps into the gloom."
    assert cellar_chunks[1] == "Cellar"
    assert len(cellar_chunks) == 4, cellar_chunks
    assert module["is_room_prose_candidate"](cellar)

    repeated_entry = (
        "East Thalenwood Forest\n"
        "You enter the East Thalenwood Forest\n"
        "You enter the East Thalenwood Forest\n"
        "Entrance to the old ancient forest\n"
        "You are standing near an old trail leading into a dense ancient forest.\n"
        "The trees grow close together and their branches block most of the sky.\n"
        "A disheveled halfling camps out near the trail."
    )
    repeated_chunks = module["room_semantic_chunks"](repeated_entry)
    assert repeated_chunks.count("You enter the East Thalenwood Forest") == 2, repeated_chunks
    assert repeated_chunks[0] == "East Thalenwood Forest", repeated_chunks
    assert (
        "Entrance to the old ancient forest You are standing near an old trail leading into a dense ancient forest."
        in repeated_chunks
    ), repeated_chunks

    period_title = (
        "Near the middle of a clearing.\n"
        "You are now walking almost exclusively on rocks. Some of them are quite\n"
        "smooth, almost polished, while others are jagged shards that seem to have\n"
        "been crudely smashed from their source. Directly to the south of you is a\n"
        "huge stump, and these rocks now make your going so difficult."
    )
    assert module["room_title_index"](period_title.splitlines()) == 0
    assert module["is_room_prose_candidate"](period_title)
    assert module["room_semantic_chunks"](period_title)[0] == "Near the middle of a clearing."

    short_period_name = period_title.replace(
        "Near the middle of a clearing.", "Moss Ave."
    )
    assert module["room_title_index"](short_period_name.splitlines()) == 0
    assert module["is_room_prose_candidate"](short_period_name)

    body_starts_its_a = (
        "Inside a dwarven house\n"
        "It's a pretty dwarven house, with three beds lined up against the southern\n"
        "wall. A colorful carpet covers part of the floor behind a wooden table,\n"
        "and a metal cauldron rests in one corner beside several dirty dishes."
    )
    assert module["is_room_prose_candidate"](body_starts_its_a)

    shop_url = (
        "A Twinkle in Her Eye Jewelry and Lapidary - http://alteraeon.com:8080/shops/53467\n"
        "This small shop's walls are covered with simple linen drapes. There are\n"
        "marble-topped counters by the east and west walls, with velvet-lined trays\n"
        "that bear various pieces of jewelry. A lantern fills the room with light."
    )
    assert module["room_title_index"](shop_url.splitlines()) == 0
    assert module["room_semantic_chunks"](shop_url)[0].endswith("/shops/53467")

    longer_period_name = period_title.replace(
        "Near the middle of a clearing.",
        "A narrow crevice that makes a good hiding place.",
    )
    assert module["room_title_index"](longer_period_name.splitlines()) == 0
    assert module["is_room_prose_candidate"](longer_period_name)

    prefixed = (
        "You bend low and crawl into the cave.\n"
        "A small cave.\n"
        "The cramped stone passage presses close on every side, and cold water runs\n"
        "down the uneven walls. A narrow opening continues farther north into the\n"
        "darkness, while scattered pebbles cover most of the sandy ground."
    )
    assert module["room_title_index"](prefixed.splitlines()) == 1
    assert module["is_room_prose_candidate"](prefixed)
    assert module["room_semantic_chunks"](prefixed)[:2] == [
        "You bend low and crawl into the cave.", "A small cave."
    ]

    status_prefixed = prefixed.replace(
        "You bend low and crawl into the cave.", "You slip from the shadows."
    )
    assert module["is_room_prose_candidate"](status_prefixed)

    preview_prefixed = (
        "In the next room you see:\n"
        "A Webby Passage\n"
        "The tunnel twists and turns so quickly here that keeping your balance is\n"
        "difficult, and thick white webbing covers the rough walls on either side. "
        "You hold your light close to the ground and watch strange shadows dance\n"
        "across the ceiling while the narrow passage continues farther north."
    )
    assert module["room_title_index"](preview_prefixed.splitlines()) == 1
    assert module["is_room_prose_candidate"](preview_prefixed)

    combat_retreat_prefixed = (
        "A larger troll screams a blood-chilling roar at you!\n"
        "You turn and run like a yellow-bellied coward!\n"
        "You flee from something...\n"
        "A forked passage\n"
        "One can wander for many hours inside these dark labyrinthine chambers\n"
        "without finding a way out. In one corner is a pool of dark, foul-smelling\n"
        "water that sensible travelers should probably avoid whenever possible."
    )
    assert module["room_title_index"](combat_retreat_prefixed.splitlines()) == 3
    assert module["is_room_prose_candidate"](combat_retreat_prefixed)

    false_blocks = [
        "You have 9 practices left.\nMage elemental cold spellgroup\n"
        "-------- Int Wis Chr Lvl --------\nchill touch moderate 15 11 3 mag\n"
        "shower of sparks very good 14 11 1 mag",
        "Keywords are: 'thief skill throwing'\nSkill: knife throwing Lvl 15 Thie\n"
        "Usage:\nthrow <object>\nThis skill allows a thief to throw an object at\n"
        "a distant target during combat and then retreat.",
        "You strike a spider guard!\nA shadow decoy melts back into the shadows.\n"
        "The spider guard attacks again and again until the target falls.\n"
        "A shadow decoy avoids the attack and moves away from danger.",
        "You open a chest.\non ground contains:\na silver spoon\na black potion\n"
        "a polished stone\na wooden sign",
        "Quest Name: Find the lost bear.\nLocation: Dream realm 2\n"
        "Current goal long description:\nSearch every room in the village and\n"
        "return the bear to its owner before nightfall.",
        "it's a unknown.\nYou get a very, very bad feeling about this. Something\n"
        "is not right here. The creature's armor is effective against your weapon,\n"
        "and its ability to do damage far exceeds yours. Attack at your own risk.",
    ]
    for false_block in false_blocks:
        assert not module["is_room_prose_candidate"](false_block), false_block

    parsed = module["parse_numbered_room_translation"](
        "[[ROOM_0]] 洞穴中的三叉路口\n"
        "[[ROOM_1]] 這個方向又發生了變化。\n"
        "[[ROOM_2]] 道路沒有大石頭的阻擋。\n"
        "[[ROOM_3]] 泥土上有一些不清楚的標記。",
        4,
    )
    assert parsed == [
        "洞穴中的三叉路口",
        "這個方向又發生了變化。",
        "道路沒有大石頭的阻擋。",
        "泥土上有一些不清楚的標記。",
    ], parsed
    translated_markers = module["parse_numbered_room_translation"](
        "【房间 0】洞穴中的三岔路口 【房间 1】方向改變。 "
        "【房间 2】道路暢通。 【房间 3】洞穴裡有生物。 【房间结束】",
        4,
    )
    assert translated_markers == [
        "洞穴中的三岔路口", "方向改變。", "道路暢通。", "洞穴裡有生物。"
    ], translated_markers
    assert module["parse_numbered_room_translation"](
        "[[ROOM_0]] 標題\n[[ROOM_2]] 少了一段", 3
    ) is None
    worker_source = WORKER.read_text(encoding="utf-8-sig")
    assert "LMT does not reliably retain markers" in worker_source
    assert "for source in chunks:" in worker_source
    assert "unique_missing_sources = list(dict.fromkeys(missing_sources))" in worker_source
    assert 'output.append("\\n".join(repaired))' in worker_source
    assert 'output = [" ".join(prefix_translation.splitlines()).strip()]' not in worker_source
    assert "output = [line.strip() for line in prefix_translation.splitlines() if line.strip()]" in worker_source
    print("ROOM_ALIGNMENT_OK units=4 malformed_marker_safe=yes")


if __name__ == "__main__":
    main()
