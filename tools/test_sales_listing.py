"""Regression for the numeric-safe credit sale listing."""

from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "src/mush-z/worlds/plugins/translation_bridge/translation_worker.py"


def main() -> None:
    spec = importlib.util.spec_from_file_location("sales_listing_worker_test", WORKER)
    worker = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(worker)
    source = """There are the following sales running:
 5% extra! - weightless expansions
40% off!   - detect and protect spells   - now   15 credits!
20% off!   - get out of death cards      - now  159 credits!
15% off!   - unbind an item              - now 1699 credits!
Use the 'credit buy' command to take advantage of these deals."""
    worker.reviewed_phrase_translation = lambda text: None
    worker.cache_get = lambda source, config: None
    worker.cache_put = lambda source, translated, config: None
    worker.translate_piece = lambda text, config, **kwargs: "譯：" + text
    assert worker.is_sales_listing(source)
    result = worker.translate_sales_listing(source, {})
    lines = result.splitlines()
    assert len(lines) == 6, lines
    assert lines[0] == "目前有以下促銷活動："
    assert lines[1] == " 額外 5%！ - 譯：weightless expansions"
    assert lines[2] == "優惠 40%！ - 譯：detect and protect spells - 現在 15 credits！"
    assert lines[-1] == "請使用 'credit buy' 指令購買這些優惠。"
    assert worker.numeric_items_preserved(source, result)
    assert worker.translate(source, {}) == result
    malformed = source.replace("40% off!", "forty percent off!")
    assert not worker.is_sales_listing(malformed)
    print("SALES_LISTING_OK rows=6 numbers=preserved provider_neutral=yes")


if __name__ == "__main__":
    main()
