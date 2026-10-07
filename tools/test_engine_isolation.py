"""Prove cloud success never enters the LMT-only room translation path."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "src" / "mush-z" / "worlds" / "plugins" / "translation_bridge" / "translation_worker.py"


def load_room_function():
    tree = ast.parse(WORKER.read_text(encoding="utf-8-sig"))
    node = next(
        item for item in tree.body
        if isinstance(item, ast.FunctionDef) and item.name == "translate_room_prose_cached"
    )
    namespace = {}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(WORKER), "exec"), namespace)
    return namespace["translate_room_prose_cached"]


def main() -> None:
    translate_room = load_room_function()
    chunks = ["Room title", "A complete room sentence."]
    cache = {}
    calls = {"cloud": 0, "local": 0}

    def cloud(values):
        calls["cloud"] += 1
        assert values == chunks
        return ["房間名稱", "完整的房間句子。"]

    def local(_values, _config):
        calls["local"] += 1
        raise AssertionError("LMT path ran after successful cloud translation")

    translate_room.__globals__.update({
        "room_semantic_chunks": lambda _text: chunks,
        "cache_get": lambda key, _config: cache.get(key),
        "cache_put": lambda key, value, _config: cache.__setitem__(key, value),
        "cloud_translate_many": cloud,
        "translate_room_units_once": local,
        "translation_sanity_ok": lambda _source, _result: (True, ""),
        "translate_piece": lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("whole-room fallback unexpectedly ran")
        ),
        "log": lambda *_args, **_kwargs: None,
    })
    result = translate_room("ignored", {})
    assert result == "房間名稱\n完整的房間句子。", result
    assert calls == {"cloud": 1, "local": 0}, calls

    cache.clear()
    calls = {"cloud": 0, "local": 0}
    translate_room.__globals__["cloud_translate_many"] = lambda _values: None
    translate_room.__globals__["translate_room_units_once"] = lambda values, _config: (
        calls.__setitem__("local", calls["local"] + 1) or ["房間名稱", "完整的房間句子。"]
    )
    translate_room("ignored", {})
    assert calls["local"] == 1, calls
    print("ENGINE_ISOLATION_OK cloud_success_lmt_calls=0 cloud_failure_lmt_calls=1")


if __name__ == "__main__":
    main()
