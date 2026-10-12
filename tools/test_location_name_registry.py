"""Regression for the production place-name registry and structured callers."""

import importlib.util
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKER_PATH = ROOT / "src/mush-z/worlds/plugins/translation_bridge/translation_worker.py"
SPEC = importlib.util.spec_from_file_location("location_registry_worker", WORKER_PATH)
worker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(worker)


def main():
    with tempfile.TemporaryDirectory() as directory:
        worker.CACHE_DB = Path(directory) / "cache.sqlite3"
        worker.CACHE_CONNECTION = None
        worker.CACHE_DISABLED = False
        worker.PHRASE_GLOSSARY = None
        calls = []
        translations = {
            "A large wooden cabin": "一座大型木屋",
            "Astraeus": "阿斯特賴俄斯",
            "The Ranger Strag": "遊俠斯特拉格",
        }

        original_translate_piece = worker.translate_piece

        def fake_translate_piece(source, _config, **_kwargs):
            calls.append(source)
            return translations[source]

        worker.translate_piece = fake_translate_piece
        config = {
            "translation_cache_enabled": True,
            "translation_cache_version": 13,
            "source_language": "en",
            "target_language": "zh-TW",
        }
        try:
            # Reviewed Ranger's Guild names bypass every observed model error.
            source = "Fort Ironcliff Ranger's Guild"
            assert worker.translate_place_name(source, config, "where") == "鐵堡壘遊俠公會"
            assert calls == []
            assert worker.translate_place_name(source, config, "room_title") == "鐵堡壘遊俠公會"
            assert calls == []

            # This real LMT failure must always resolve to the reviewed room
            # name, even after the player clears a recently learned name.
            barracks = "Dwarven barracks"
            assert worker.translate_place_name(barracks, config, "room_title") == "矮人兵營"
            assert calls == []

            # An unseen ordinary place is translated once, then shared by
            # where and the later room title.
            cabin = "A large wooden cabin"
            assert worker.translate_place_name(cabin, config, "where") == "一座大型木屋"
            assert worker.translate_place_name(cabin, config, "room_title") == "一座大型木屋"
            assert calls.count(cabin) == 1

            where = "The Ranger Strag -> Fort Ironcliff Ranger's Guild"
            assert worker.is_where_location_row(where)
            assert worker.translate_where_location_row(where, config) == (
                "遊俠斯特拉格 -> 鐵堡壘遊俠公會"
            )

            quest = "Location:    Fort Ironcliff Ranger's Guild"
            assert worker.translate_quest_structured_block(quest, config) == (
                "地點：鐵堡壘遊俠公會"
            )

            # Ctrl+Shift+Delete removes the canonical place implicated by a
            # recent whole-sentence row so the player can choose a new name.
            worker.cache_put(where, "遊俠斯特拉格 -> 鐵堡壘遊俠公會", config)
            assert worker.place_name_get(source) == "鐵堡壘遊俠公會"
            worker.clear_recent_translation_cache(1)
            assert worker.place_name_get(source) is None
            assert worker.translate_place_name(source, config, "room_title") == "鐵堡壘遊俠公會"
            assert calls.count(source) == 0
            assert calls.count(barracks) == 0

            # Ordinary prose is never treated as a where row/place boundary.
            assert not worker.is_where_location_row(
                "The ranger walks past a guild banner while talking about the road."
            )
        finally:
            worker.translate_piece = original_translate_piece
            if worker.CACHE_CONNECTION is not None:
                worker.CACHE_CONNECTION.close()
                worker.CACHE_CONNECTION = None

    print(
        "LOCATION_NAME_REGISTRY_OK where_before_room=yes quest_location=yes "
        "ranger_guild=reviewed clear_recent=yes prose_rejected=yes"
    )


if __name__ == "__main__":
    main()
