"""Regressions derived from the newest translation trace only."""

from pathlib import Path
import runpy


ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "src/mush-z/worlds/plugins/translation_bridge/translation_worker.py"


def main():
    module = runpy.run_path(str(WORKER))
    deterministic = module["deterministic_translate"]
    practice = "You still need 5797172 experience to train a practice. It costs 10000000."
    rendered = deterministic(practice)
    assert rendered == "你還需要 5797172 點經驗值才能獲得一次練習。訓練需要 10000000 點經驗值。", rendered
    assert module["numeric_items_preserved"](practice, rendered)

    source = """A narrow drift
The passage has narrowed to only a few feet across. Hard, dark rock forms
the north wall of the tunnel here. The craggy walls cast deep and complex
shadows in the light from the glass globes hanging from the ceiling.
A deposit of cassiterite has been uncovered and marked here.
A deposit of torbernite ore has been uncovered and marked here.
A deposit of torbernite ore has been uncovered and marked here.
A deposit of torbernite ore has been uncovered and marked here.
A deposit of scapolite has been uncovered and marked here."""
    translate = module["translate_trailing_independent_rows"]
    globals_ = translate.__globals__
    globals_["trailing_independent_row_start"] = lambda _text: 4
    globals_["is_room_prose_candidate"] = lambda _text: True
    globals_["translate_room_prose_cached"] = lambda _text, _config: "窄小的礦道\n礦道兩側是黑暗的岩壁。"
    globals_["cache_get"] = lambda _text, _config: None
    globals_["cache_put"] = lambda *_args: None
    globals_["translate_piece"] = lambda text, _config, **_kwargs: "譯：" + text
    original_sanity = globals_["translation_sanity_ok"]
    globals_["translation_sanity_ok"] = lambda _source, _result: (False, "repeated_source_items_missing")
    try:
        result = translate(source, {})
    finally:
        globals_["translation_sanity_ok"] = original_sanity
    repeated = "譯：A deposit of torbernite ore has been uncovered and marked here."
    assert result.splitlines().count(repeated) == 3, result
    print("RECENT_TRACE_FIXES_OK practice=local repeated_room_rows=preserved")


if __name__ == "__main__":
    main()
