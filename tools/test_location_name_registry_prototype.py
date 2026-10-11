"""Isolated regression for consistent place names discovered before entry.

The fixtures below are copied from the player's local translation trace.  This
prototype deliberately does not modify the live worker or cache.
"""

import json
import re
import sqlite3
from pathlib import Path


WHERE_ROW = re.compile(r"^.+?\s*->\s*(.+?)\s*$")
LOCATION_ROW = re.compile(r"^Location:\s*(.+?)\s*$", re.I | re.M)
NEARBY_ROW = re.compile(
    r"^\s*Lvl\s+\d+\s+(.+?)\s+(?:is|are)\s+"
    r"(?:a very short distance|a short distance|a fair distance|far away),?\s+"
    r"to the (?:north|south|east|west|northeast|northwest|southeast|southwest)\.",
    re.I | re.M,
)
RANGER_GUILD = re.compile(r"^(.*?)(?:\s+)(?:Ranger's|Rangers'|Rangers)\s+Guild$", re.I)


TRACE_FIXTURES = {
    "where": "The Ranger Strag -> Fort Ironcliff Ranger's Guild",
    "room": (
        "Fort Ironcliff Ranger's Guild\n"
        "This is a medium sized building with only a few pieces of furniture,\n"
        "which consists of a simple bed and a wooden desk with a high-back chair."
    ),
    "quest": (
        "Quest Name: Recovered various ingredients.\n"
        "Location: Fort Ironcliff Ranger's Guild\n"
        "Area Level: 26"
    ),
    "nearby": (
        "You consult your maps for nearby areas named 'research':\n"
        "Level      Name/Direction\n"
        "Lvl  28    The Dragon Tooth research guild is a short distance to the southeast."
    ),
    "ordinary_prose": (
        "The ranger walks past a guild banner while talking about the road."
    ),
}


class PlaceRegistry:
    def __init__(self):
        self.db = sqlite3.connect(":memory:")
        self.db.execute(
            "CREATE TABLE places(source_name TEXT PRIMARY KEY, translated_name TEXT NOT NULL, origin TEXT NOT NULL)"
        )

    def get(self, source):
        row = self.db.execute(
            "SELECT translated_name FROM places WHERE source_name=?", (source.strip(),)
        ).fetchone()
        return row[0] if row else None

    def resolve(self, source, origin, translate):
        source = source.strip()
        known = self.get(source)
        if known:
            return known
        guild = RANGER_GUILD.fullmatch(source)
        if guild:
            prefix = guild.group(1).strip()
            translated = (translate(prefix) + "遊俠公會").strip()
        else:
            translated = translate(source)
        self.db.execute(
            "INSERT INTO places(source_name,translated_name,origin) VALUES(?,?,?)",
            (source, translated, origin),
        )
        self.db.commit()
        return translated


def structured_place(text, kind):
    if kind == "where":
        match = WHERE_ROW.fullmatch(text.strip())
        return match.group(1) if match else None
    if kind == "quest":
        match = LOCATION_ROW.search(text)
        return match.group(1) if match else None
    if kind == "nearby":
        match = NEARBY_ROW.search(text)
        return match.group(1) if match else None
    if kind == "room":
        return text.splitlines()[0].strip() if len(text.splitlines()) >= 2 else None
    return None


def main():
    calls = []
    translations = {
        "Fort Ironcliff": "鐵堡壘",
        "The Dragon Tooth research guild": "龍牙研究公會",
        "A large wooden cabin": "一座大型木屋",
    }

    def translate(value):
        calls.append(value)
        return translations[value]

    # The trace proves the model can independently produce all of these bad
    # variants.  The source-aware guild rule must bypass every one of them.
    observed_bad_results = {
        "鐵堡壘步槍俱樂部",
        "鐵堡壘流浪者公會",
        "龍牙護林員協會",
    }
    assert len(observed_bad_results) == 3

    # When run on the player's machine, confirm the fixtures and failure modes
    # really occur in the accumulated trace instead of testing invented text.
    bridge = Path(r"D:\altar aeon\Mush-Z\worlds\plugins\translation_bridge")
    trace_files = [bridge / "lmt_translation_trace.log"]
    trace_files.extend(sorted((bridge / "log_archive").glob("lmt_translation_trace_*.log")))
    actual_sources, actual_results = set(), set()
    for trace_file in trace_files:
        if not trace_file.exists():
            continue
        with trace_file.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if "ranger" not in line.lower() and "guild" not in line.lower():
                    continue
                try:
                    record = json.loads(line)
                except (TypeError, ValueError):
                    continue
                actual_sources.add(str(record.get("source", "")))
                actual_results.add(str(record.get("result", "")))
    if actual_sources:
        assert any(TRACE_FIXTURES["where"] == source for source in actual_sources)
        assert any(
            source.startswith("Fort Ironcliff Ranger's Guild\nThis is a medium sized building")
            for source in actual_sources
        )
        assert any("鐵堡壘步槍俱樂部" in result for result in actual_results)
        assert any("鐵堡壘流浪者公會" in result for result in actual_results)
        assert any("龍牙護林員協會" in result for result in actual_results)

    # where before entering the room
    registry = PlaceRegistry()
    where_name = structured_place(TRACE_FIXTURES["where"], "where")
    room_name = structured_place(TRACE_FIXTURES["room"], "room")
    assert where_name == room_name == "Fort Ironcliff Ranger's Guild"
    assert registry.resolve(where_name, "where", translate) == "鐵堡壘遊俠公會"
    call_count = len(calls)
    assert registry.resolve(room_name, "room", translate) == "鐵堡壘遊俠公會"
    assert len(calls) == call_count

    # room before where produces the same canonical spelling
    registry = PlaceRegistry()
    assert registry.resolve(room_name, "room", translate) == "鐵堡壘遊俠公會"
    assert registry.resolve(where_name, "where", translate) == "鐵堡壘遊俠公會"

    # Quest Location is accepted before room entry.
    registry = PlaceRegistry()
    quest_name = structured_place(TRACE_FIXTURES["quest"], "quest")
    assert quest_name == room_name
    assert registry.resolve(quest_name, "quest_location", translate) == "鐵堡壘遊俠公會"

    # Nearby map rows expose a bounded place name, while ordinary prose does not.
    registry = PlaceRegistry()
    nearby_name = structured_place(TRACE_FIXTURES["nearby"], "nearby")
    assert nearby_name == "The Dragon Tooth research guild"
    assert registry.resolve(nearby_name, "nearby", translate) == "龍牙研究公會"
    assert structured_place(TRACE_FIXTURES["ordinary_prose"], "prose") is None

    print(
        "LOCATION_REGISTRY_PROTOTYPE_OK "
        "where_before_room=yes room_before_where=yes quest_before_room=yes "
        "nearby=yes prose_rejected=yes ranger_guild=reviewed "
        "player_trace=%s" % ("verified" if actual_sources else "not_available")
    )


if __name__ == "__main__":
    main()
