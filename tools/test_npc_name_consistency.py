"""Regression tests for player-local NPC name consistency and reset."""

from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "src/mush-z/worlds/plugins/translation_bridge/translation_worker.py"


def main() -> None:
    spec = importlib.util.spec_from_file_location("npc_name_worker_test", WORKER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    with tempfile.TemporaryDirectory() as folder:
        module.CACHE_DB = Path(folder) / "cache.sqlite3"
        module.LOG = Path(folder) / "translation_worker.log"
        module.CACHE_CONNECTION = None
        module.CACHE_DISABLED = False
        config = {
            "translation_cache_enabled": True,
            "translation_cache_version": 13,
            "source_language": "en",
            "target_language": "zh-TW",
        }

        first_source = "Gimthen says, 'Welcome to me shop.'"
        first = module.normalize_npc_names(first_source, "金騰說：「歡迎來到我的店。」")
        assert first.startswith("金騰說"), first

        second_source = "Gimthen says, 'Bring the parts to me.'"
        second = module.normalize_npc_names(second_source, "吉姆森說：「把零件帶給我。」")
        assert second.startswith("金騰說"), second

        action_source = "Gimthen gives you a little wink and goes back to his work."
        action = module.normalize_npc_names(action_source, "金森將眨了眨眼，然後繼續工作。")
        assert action.startswith("金騰將"), action

        # Old cache text is normalized lazily once its alias has been seen.
        mention_source = "Kempf says, 'You should talk to Gimthen.'"
        mention = module.normalize_npc_names(mention_source, "肯普夫說：「你應該去找吉姆森。」")
        assert "金騰" in mention and "吉姆森" not in mention, mention

        module.cache_put(first_source, first, config)
        module.cache_put(second_source, second, config)
        module.cache_put(action_source, action, config)
        removed = module.clear_recent_translation_cache(1)
        assert removed == 1
        db = module.cache_connection()
        assert db.execute("SELECT translated_name FROM npc_names WHERE source_name='gimthen'").fetchone() is None
        assert module.cache_get(first_source, config) is None
        assert module.cache_get(second_source, config) is None

        # After Ctrl+Shift+Delete, the next observed spelling becomes the new
        # local choice and all following dialogue uses it.
        reset = module.normalize_npc_names(first_source, "吉姆森說：「歡迎來到我的店。」")
        assert reset.startswith("吉姆森說"), reset
        stable = module.normalize_npc_names(second_source, "金騰說：「把零件帶給我。」")
        assert stable.startswith("吉姆森說"), stable

        module.CACHE_CONNECTION.close()
        module.CACHE_CONNECTION = None

    print("NPC_NAME_CONSISTENCY_OK first_seen=locked old_cache=normalized recent_reset=yes")


if __name__ == "__main__":
    main()
