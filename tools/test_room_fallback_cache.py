#!/usr/bin/env python3
"""A safe whole-room fallback must become instant on the second look."""

from pathlib import Path
import runpy


ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "src" / "mush-z" / "worlds" / "plugins" / "translation_bridge" / "translation_worker.py"

SOURCE = """Entrance hall of the Djinni School
After climbing through the awkwardly placed gate, solid ground becomes a
constant companion. The halls are long and narrow, and the walls are
covered in strange text that does not seem so easily deciphered. A large
plaque sits at the entrance of the school, and in bold letters are the
words 'School of the Djinni'. Climbing downwards allows one to hop back
into the awkward space that was midair, and further travel south appears to
be more hallways. There is an additional flight of stairs that head up, and
the steps themselves seem to be considerably cleaner due to the slightly
lighter hue of the material in comparison to the walls of the first floor."""


def main():
    module = runpy.run_path(str(WORKER))
    function = module["translate_room_prose_cached"]
    globals_ = function.__globals__
    originals = {
        name: globals_[name]
        for name in (
            "cache_get", "cache_put", "place_name_get",
            "cloud_translate_many_partial", "translate_room_units_once",
            "translate_piece",
        )
    }
    cache = {}
    model_calls = []

    def key(source, config):
        return (int(config.get("translation_cache_version", 12)), source)

    globals_["cache_get"] = lambda source, config: cache.get(key(source, config))
    globals_["cache_put"] = lambda source, translated, config: cache.__setitem__(key(source, config), translated)
    globals_["place_name_get"] = lambda source: None
    globals_["cloud_translate_many_partial"] = lambda sources: None

    def reject_units(sources, config):
        raise RuntimeError("ROOM_UNIT_SANITY_low_length_ratio")

    def whole_fallback(source, config, *args, **kwargs):
        model_calls.append(source)
        return "精靈學校入口大廳。這是一段已通過整體安全檢查的完整房間翻譯。"

    globals_["translate_room_units_once"] = reject_units
    globals_["translate_piece"] = whole_fallback
    config = {
        "translation_cache_version": 13,
        "translation_cache_enabled": True,
        "source_language": "en",
        "target_language": "zh",
    }
    try:
        first = function(SOURCE, config)
        assert len(model_calls) == 1
        second = function(SOURCE, config)
        assert second == first
        assert len(model_calls) == 1, "second look called the model again"
        fallback_version = module["room_fallback_cache_config"](config)["translation_cache_version"]
        assert fallback_version != config["translation_cache_version"]
        assert (fallback_version, SOURCE) in cache
    finally:
        globals_.update(originals)

    print("ROOM_FALLBACK_CACHE_OK first=model second=cache namespace=isolated")


if __name__ == "__main__":
    main()
