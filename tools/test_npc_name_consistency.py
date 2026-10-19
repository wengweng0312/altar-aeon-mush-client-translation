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
        assert module.translate_cached_phrase("A kobold druid", config) == "一名狗頭人德魯伊"
        assert module.translate_cached_phrase("A kobold warrior", config) == "一名狗頭人戰士"
        assert module.translate_cached_phrase("A kobold mage", config) == "一名狗頭人法師"
        assert module.translate_cached_phrase("A kobold cleric", config) == "一名狗頭人牧師"
        assert module.translate_cached_phrase("A kobold thief", config) == "一名狗頭人盜賊"
        assert module.translate_cached_phrase("A kobold necromancer", config) == "一名狗頭人死靈法師"
        assert module.translate_cached_phrase("kobold warrior", config) == "狗頭人戰士"
        assert module.translate_cached_phrase("A kobold war leader", config) == "一名狗頭人戰爭領袖"

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

        linkas_source = (
            "You try to talk to Linkas...\n"
            "Linkas starts following you.\n"
            "You add Linkas to your group.\n"
            "Linkas has become a member of the group."
        )
        linkas_result = module.normalize_npc_names(
            linkas_source,
            "你試著和林卡斯說話……\n"
            "鏈接開始跟隨你。\n"
            "你將鏈接加入隊伍。\n"
            "鏈接加入了隊伍。",
        )
        assert linkas_result.splitlines() == [
            "你試著和林卡斯說話……",
            "林卡斯開始跟隨你。",
            "你將林卡斯加入隊伍。",
            "林卡斯加入了隊伍。",
        ], linkas_result

        # Generic creatures use their own table but share the exact same
        # protection/restoration path once a reliable actor sentence teaches
        # the first local spelling.
        spider_source = "A spider guard attacks you."
        spider_first = module.normalize_npc_names(spider_source, "一名蜘蛛守衛攻擊你。")
        assert spider_first == "一名蜘蛛守衛攻擊你。", spider_first
        spider_second = module.normalize_npc_names(
            "A spider guard leaves north.", "一隻蜘蛛警衛離開前往北方。"
        )
        assert spider_second == "一隻蜘蛛守衛離開前往北方。", spider_second
        protected, occurrences = module.protect_known_entity_names(
            "A spider guard attacks Gimthen."
        )
        assert protected.count("ZXQNPC") == 2 and len(occurrences) == 2, (protected, occurrences)
        restored = module.restore_known_entity_names(
            protected.replace(" attacks ", "攻擊"), occurrences
        )
        assert "蜘蛛守衛" in restored and "吉姆森" in restored, restored

        # A source article belongs to the generic mob phrase, not to the
        # translated output. This covers room corpses, combat and sacrifice.
        corpse_protected, corpse_occurrences = module.protect_known_entity_names(
            "The corpse of A spider guard is lying here."
        )
        assert "of ZXQNPC" in corpse_protected and "of A ZXQNPC" not in corpse_protected
        corpse_restored = module.restore_known_entity_names(
            "這裡躺著 " + corpse_protected.split("of ", 1)[1].split(" is", 1)[0] + " 的屍體。",
            corpse_occurrences,
        )
        assert "A " not in corpse_restored and "蜘蛛守衛" in corpse_restored, corpse_restored

        old_cached_article = module.normalize_npc_names(
            "The corpse of A spider guard is lying here.",
            "A 蜘蛛守衛的屍體躺在這裡。",
        )
        assert old_cached_article == "蜘蛛守衛的屍體躺在這裡。", old_cached_article

        # Accuracy is deliberately not a promotion requirement: the player's
        # first accepted wording remains stable until recent-cache reset.
        wrong_but_stable = module.normalize_npc_names(
            "A pixie thief attacks you.", "一名精靈小偷攻擊你。"
        )
        assert "精靈小偷" in wrong_but_stable
        stable_again = module.normalize_npc_names(
            "A pixie thief leaves east.", "一名皮克西盜賊離開向東。"
        )
        assert "精靈小偷" in stable_again and "皮克西盜賊" not in stable_again

        # A learned short alias may be contained inside the canonical name.
        # Never expand the already-correct canonical spelling a second time.
        wisp_source = "A will-o-the-wisp misses someone."
        wisp_first = module.normalize_npc_names(wisp_source, "幻影之火沒有擊中某人。")
        assert wisp_first == "幻影之火沒有擊中某人。", wisp_first
        wisp_alias = module.normalize_npc_names(
            "A will-o-the-wisp dodges someone's attack.",
            "幻影閃避了某人的攻擊。",
        )
        assert wisp_alias == "幻影之火閃避了某人的攻擊。", wisp_alias
        wisp_death = module.normalize_npc_names(
            "A will-o-the-wisp is DEAD!", "幻影之火之火死了！"
        )
        assert wisp_death == "幻影之火死了！", wisp_death

        # Movement sentences are unsafe training examples: the translated
        # direction must never become part of the persistent creature name.
        movement = module.normalize_npc_names(
            "A swamp fang leaves up.", "沼澤之牙往上方離開。"
        )
        assert movement == "沼澤之牙往上方離開。", movement
        db = module.cache_connection()
        assert db.execute(
            "SELECT translated_name FROM mob_types WHERE source_name='swamp fang'"
        ).fetchone() is None

        # A later reliable combat sentence may teach the clean local spelling.
        learned = module.normalize_npc_names(
            "A swamp fang misses you.", "沼澤之牙沒有擊中你。"
        )
        assert learned == "沼澤之牙沒有擊中你。", learned
        assert db.execute(
            "SELECT translated_name FROM mob_types WHERE source_name='swamp fang'"
        ).fetchone()[0] == "沼澤之牙"

        # Existing installations are repaired narrowly: remove the polluted
        # mob name and only cache entries that mention that English identity.
        db.execute(
            "UPDATE mob_types SET translated_name=? WHERE source_name='swamp fang'",
            ("沼澤之牙往上方",),
        )
        module.cache_put(
            "Shift appreciates your sacrifice of the corpse of A swamp fang.",
            "你將沼澤之牙往上方往上方的屍體奉獻給切換。",
            config,
        )
        module.cache_put("An unrelated sentence.", "一個無關句子。", config)
        module.ensure_npc_name_tables(db)
        assert db.execute(
            "SELECT translated_name FROM mob_types WHERE source_name='swamp fang'"
        ).fetchone() is None
        assert module.cache_get(
            "Shift appreciates your sacrifice of the corpse of A swamp fang.", config
        ) is None
        assert module.cache_get("An unrelated sentence.", config) == "一個無關句子。"

        # Number words are prose, never entity identities. Repair an old
        # polluted installation and invalidate only affected translations.
        db.execute(
            "INSERT OR REPLACE INTO mob_types(source_name,translated_name,updated_at) VALUES(?,?,?)",
            ("two", "東面", 1),
        )
        db.execute(
            "INSERT OR REPLACE INTO mob_type_aliases(source_name,alias_name) VALUES(?,?)",
            ("two", "東面"),
        )
        module.cache_put(
            "It forms a series of two-inch tall waterfalls.",
            "它形成一系列東面英寸高的瀑布。", config,
        )
        module.ensure_npc_name_tables(db)
        assert db.execute("SELECT 1 FROM mob_types WHERE source_name='two'").fetchone() is None
        assert module.cache_get(
            "It forms a series of two-inch tall waterfalls.", config
        ) is None
        protected, occurrences = module.protect_known_entity_names(
            "It forms a series of two-inch tall waterfalls."
        )
        assert protected == "It forms a series of two-inch tall waterfalls."
        assert occurrences == []

        # Observation/posture sentences have an ambiguous Chinese verb
        # boundary and must not teach an adverb as part of the creature name.
        watched = module.normalize_npc_names(
            "A sewer rat watches you intently.",
            "一條下水道老鼠正專注地看著你。",
        )
        assert watched == "一條下水道老鼠正專注地看著你。"
        assert db.execute(
            "SELECT 1 FROM mob_types WHERE source_name='sewer rat'"
        ).fetchone() is None

        # Repair the exact old contamination and invalidate only translations
        # that contain this English creature identity.
        db.execute(
            "INSERT OR REPLACE INTO mob_types(source_name,translated_name,updated_at) VALUES(?,?,?)",
            ("sewer rat", "下水道老鼠正專注地", 1),
        )
        module.cache_put(
            "A sewer rat leaves west.", "下水道老鼠正專注地往西方離開。", config,
        )
        module.ensure_npc_name_tables(db)
        assert db.execute(
            "SELECT 1 FROM mob_types WHERE source_name='sewer rat'"
        ).fetchone() is None
        assert module.cache_get("A sewer rat leaves west.", config) is None

        module.CACHE_CONNECTION.close()
        module.CACHE_CONNECTION = None

    print("NPC_NAME_CONSISTENCY_OK proper=locked mob_type=locked old_cache=normalized recent_reset=yes")


if __name__ == "__main__":
    main()
