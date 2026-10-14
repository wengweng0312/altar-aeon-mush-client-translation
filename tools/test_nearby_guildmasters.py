"""Regression for the directional nearby-guildmaster table."""

from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "src" / "mush-z" / "worlds" / "plugins" / "translation_bridge" / "translation_worker.py"


def main() -> None:
    spec = importlib.util.spec_from_file_location("nearby_guildmasters_worker_test", WORKER)
    worker = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(worker)

    source = """Dir  Nearby Guildmasters
W    Larry the Leatherworker          -> The Ralnoth Rangers Guild Leather Shop,
SW   Alderius the map maker           -> The Official Ralnoth Cartographers' Office
E    Mondel the Tailor                -> The Ralnoth Boutique and Bespoke Livery"""
    assert worker.is_nearby_direction_listing(source)

    worker.translate_cached_phrase = lambda value, _config: "人物：" + value
    worker.translate_place_name = lambda value, _config, origin: "地點：" + value
    result = worker.translate_nearby_direction_listing(source, {})
    rows = result.splitlines()
    assert len(rows) == len(source.splitlines()), rows
    assert rows[0] == "方向　附近公會導師", rows
    assert rows[1].startswith("西　人物：Larry the Leatherworker"), rows
    assert "-> 地點：The Ralnoth Rangers Guild Leather Shop," in rows[1], rows
    assert rows[2].startswith("西南　人物：Alderius the map maker"), rows
    assert rows[3].startswith("東　人物：Mondel the Tailor"), rows
    assert worker.translate(source, {}) == result
    print("NEARBY_GUILDMASTERS_OK rows=4 fields=protected")


if __name__ == "__main__":
    main()
