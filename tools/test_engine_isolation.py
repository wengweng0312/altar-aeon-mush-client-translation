"""Log-derived isolation tests for cloud units and LMT fallback boundaries."""
from __future__ import annotations
import ast
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "src" / "mush-z" / "worlds" / "plugins" / "translation_bridge" / "translation_worker.py"

def load_functions():
    tree = ast.parse(WORKER.read_text(encoding="utf-8-sig"))
    nodes = [item for item in tree.body if isinstance(item, ast.FunctionDef) and item.name in {
        "cloud_translate_many_partial", "translate_room_prose_cached"
    }]
    namespace = {}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(WORKER), "exec"), namespace)
    return namespace

def main() -> None:
    module = load_functions()
    cloud_partial = module["cloud_translate_many_partial"]
    translate_room = module["translate_room_prose_cached"]
    # Sanitized from actual Dragon Tooth Waypoint trace rows. No private text.
    chunks = [
        "The Dragon Tooth Waypoint",
        "Set in the ground near two colossal stone towers to the north.",
        "Hawana is here.",
        "A short wooden sign has directions to the local teachers.",
    ]
    calls = []
    def provider(service, values, _key, _region, _timeout):
        calls.append((service, list(values)))
        if service == 1:
            return ["The Dragon Tooth Waypoint", "它位於北方兩座巨大石塔附近。",
                    "Hawana 在這裡。", "一塊木製短告示牌標示著當地教師的方向。"]
        assert values == ["The Dragon Tooth Waypoint"]
        return ["龍牙傳送點"]
    def validate(_source, result):
        if not any("\u3400" <= char <= "\u9fff" for char in result):
            raise RuntimeError("CLOUD_NO_CHINESE")
        return result
    settings = {"azure_region": "global", "timeout_seconds": 1.5}
    cloud_partial.__globals__.update({
        "cloud_translation_candidates": lambda _text: [(1, "azure", settings), (3, "deepl", settings)],
        "cloud_translation_client": SimpleNamespace(SERVICE_NAMES={1: "azure", 3: "deepl"},
            translate_many=provider, is_session_blocking_error=lambda _error: False),
        "validate_cloud_translation": validate, "mark_translation_engine": lambda _name: None,
        "CLOUD_FAILURE_COUNT": {}, "CLOUD_FAILURE_LIMIT": 3,
        "CLOUD_DISABLED_FOR_SESSION": set(), "CLOUD_DISABLED_UNTIL": {},
        "CLOUD_COOLDOWN_SECONDS": 30, "time": SimpleNamespace(monotonic=lambda: 0),
        "log": lambda *_args, **_kwargs: None,
    })
    results = cloud_partial(chunks)
    assert results == ["龍牙傳送點", "它位於北方兩座巨大石塔附近。", "Hawana 在這裡。",
                       "一塊木製短告示牌標示著當地教師的方向。"], results
    assert calls == [(1, chunks), (3, ["The Dragon Tooth Waypoint"])], calls

    cache, local_calls = {}, []
    translate_room.__globals__.update({
        "room_semantic_chunks": lambda _text: chunks,
        "cache_get": lambda key, _config: cache.get(key),
        "cache_put": lambda key, value, _config: cache.__setitem__(key, value),
        "cloud_translate_many_partial": lambda _values: [None, "它位於北方兩座巨大石塔附近。",
            "Hawana 在這裡。", "一塊木製短告示牌標示著當地教師的方向。"],
        "translate_room_units_once": lambda values, _config: (local_calls.append(list(values)) or ["龍牙傳送點"]),
        "translation_sanity_ok": lambda _source, _result: (True, ""),
        "translate_piece": lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("whole-room fallback ran")),
        "log": lambda *_args, **_kwargs: None,
    })
    assert translate_room("ignored", {}).splitlines()[0] == "龍牙傳送點"
    assert local_calls == [["The Dragon Tooth Waypoint"]], local_calls

    cache.clear(); offline_calls = []
    translate_room.__globals__["cloud_translate_many_partial"] = lambda _values: None
    translate_room.__globals__["translate_room_units_once"] = lambda values, _config: (
        offline_calls.append(list(values)) or ["離線翻譯"] * len(values))
    translate_room("ignored", {})
    assert offline_calls == [chunks], offline_calls
    print("ENGINE_ISOLATION_OK azure=4 deepl=1 lmt_partial=1 offline_lmt=4")

if __name__ == "__main__":
    main()
