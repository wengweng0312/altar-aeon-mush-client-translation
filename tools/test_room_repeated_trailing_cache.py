#!/usr/bin/env python3
"""Regression: repeated room occupants must not defeat semantic caching."""

from pathlib import Path
import runpy


ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "src" / "mush-z" / "worlds" / "plugins" / "translation_bridge" / "translation_worker.py"

SOURCE = """You follow a thin path surrounded by candles.
The Dragon Tooth Waypoint
Set in the ground near two colossal stone towers to the north, the
Dragon Tooth waypoint lies alongside the main thoroughfare through the
town of Dragon Tooth.  A large portal can be seen crackling with
magical energy to the north, while the main road runs east and west
away from the waypoint. To the south, a large wooden cabin stands
there, from which many dwarves go in and out of.
A bone white skeleton spider clatters noisily here.
A crude clay man stands upright here.
A skeletal mage with glowing blue hands paces here.
A robust walking skeleton with a flail paces back and forth.
An animated corpse stands motionless before you.
A bone white skeleton spider clatters noisily here.
A bone white skeleton spider clatters noisily here.
An animated corpse stands motionless before you.
A bone white skeleton spider clatters noisily here.
An animated corpse stands motionless before you.
Beanflicker is here, sound asleep.
Chariot is here.
*Hawana is here.
Hawana is darkened.
A short wooden sign has been stuck in the ground with directions to the local teachers."""


def main():
    module = runpy.run_path(str(WORKER))
    assert module["is_room_prose_candidate"](SOURCE)
    assert module["has_trailing_independent_rows"](SOURCE)
    assert module["has_repeated_source_lines"](SOURCE)

    # Prove the dispatcher chooses the cache-aware room path, not the generic
    # repeated-row path.
    translate = module["translate"]
    globals_ = translate.__globals__
    original_trailing = globals_["translate_trailing_independent_rows"]
    original_repeated = globals_["translate_repeated_line_block"]
    globals_["translate_trailing_independent_rows"] = lambda text, cache: "ROOM_TRAILING"
    globals_["translate_repeated_line_block"] = lambda text, cache: "WRONG_REPEATED"
    try:
        assert translate(SOURCE, {}) == "ROOM_TRAILING"
    finally:
        globals_["translate_trailing_independent_rows"] = original_trailing
        globals_["translate_repeated_line_block"] = original_repeated

    # Exercise the real trailing-row routine with an in-memory cache.  The
    # first visit may translate each unique semantic unit once; the second
    # visit must make no additional model calls, while duplicate NPC rows stay
    # duplicated in the rendered result.
    cache = {}
    model_calls = []
    originals = {name: globals_[name] for name in ("cache_get", "cache_put", "translate_piece", "translate_room_prose_cached")}

    def fake_cache_get(source, _connection):
        return cache.get(source)

    def fake_cache_put(source, translated, _connection):
        cache[source] = translated

    def fake_piece(source, _connection, *args, **kwargs):
        model_calls.append(source)
        return "譯：" + source

    def fake_room(source, _connection):
        cached = cache.get(source)
        if cached is None:
            model_calls.append(source)
            cached = "房間：" + source
            cache[source] = cached
        return cached

    globals_["cache_get"] = fake_cache_get
    globals_["cache_put"] = fake_cache_put
    globals_["translate_piece"] = fake_piece
    globals_["translate_room_prose_cached"] = fake_room
    try:
        first = original_trailing(SOURCE, {})
        first_call_count = len(model_calls)
        second = original_trailing(SOURCE, {})
        assert len(model_calls) == first_call_count, "second visit called the model again"
        assert second == first
        spider = "譯：A bone white skeleton spider clatters noisily here."
        corpse = "譯：An animated corpse stands motionless before you."
        assert first.count(spider) == 4
        assert first.count(corpse) == 3
    finally:
        globals_.update(originals)

    print("room repeated trailing cache regression: PASS")


if __name__ == "__main__":
    main()
