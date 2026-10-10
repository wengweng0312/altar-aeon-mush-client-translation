"""Regression test for field-level caching in dynamic practice tables."""

from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "src/mush-z/worlds/plugins/translation_bridge/translation_worker.py"
PLUGIN = ROOT / "src/mush-z/worlds/plugins/Translation_Mode.xml"


def main() -> None:
    spec = importlib.util.spec_from_file_location("practice_cache_worker_test", WORKER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    source = """You have 4 practices left.
Warcries
------------------------------------------------ Int Wis Chr Lvl ---
        enrage                      not learned               24 war
(If you run out, you can buy extra practices using the 'credit buy' command.)"""
    cached = []
    module.translate_skill_names = lambda names, config: ["激怒"]
    module.translate_cached_phrase = lambda text, config: cached.append(text) or ("快取：「%s」" % text)
    module.translate_piece = lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("practice prose bypassed the field cache")
    )

    result = module.translate_practice_table(source, {})
    assert cached == ["(If you run out, you can buy extra practices using the 'credit buy' command.)"], cached
    assert "你還剩 4 次練習。" in result
    assert "激怒" in result and "24 war" in result
    assert "戰吼" in result
    assert len(module.PRACTICE_FIXED_PROSE) >= 39

    singular_source = source.replace("You have 4 practices left.", "You have one practice left.")
    assert module.is_practice_table(singular_source)
    assert module.should_bypass_whole_block_cache(singular_source)
    singular_result = module.translate_practice_table(singular_source, {})
    assert "你還剩 1 次練習。" in singular_result
    prefixed_source = "You slip from the shadows.\n" + singular_source
    assert module.is_practice_table(prefixed_source)
    assert module.should_bypass_whole_block_cache(prefixed_source)
    prefixed_result = module.translate_practice_table(prefixed_source, {})
    assert prefixed_result.splitlines()[0].startswith("快取：")
    assert "你還剩 1 次練習。" in prefixed_result

    plugin = PLUGIN.read_text(encoding="utf-8-sig")
    footer = "to find a teacher or guildmaster to learn less common abilities."
    assert ('if line == "' + footer + '" then') in plugin
    assert "flush_pending()" in plugin
    assert plugin.count("You have%s+one%s+practice%s+left") == 2
    print(
        "PRACTICE_TABLE_CACHE_OK dynamic_fields=local fixed_headings=local "
        "repeated_prose=cached immediate_footer_flush=yes"
    )


if __name__ == "__main__":
    main()
