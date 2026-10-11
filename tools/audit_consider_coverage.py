"""Replay consider reports from traces without calling a translation engine."""

from __future__ import annotations

import argparse
import json
import runpy
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "src/mush-z/worlds/plugins/translation_bridge/translation_worker.py"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    module = runpy.run_path(str(WORKER), run_name="consider_coverage_audit")
    unknown: list[str] = []
    module["translate_consider_line"].__globals__["translate_cached_phrase"] = lambda value, _config: value
    module["translate_consider_line"].__globals__["translate_piece"] = (
        lambda value, *_args, **_kwargs: unknown.append(value) or ("未知：" + value)
    )
    sources: set[str] = set()
    for path in sorted(args.path.rglob("*translation_trace*.log")):
        with path.open("r", encoding="utf-8-sig", errors="replace") as handle:
            for raw in handle:
                try:
                    record = json.loads(raw)
                except Exception:
                    continue
                source = str(record.get("source", ""))
                if source and module["is_consider_report"](source):
                    sources.add(source)
    line_total = 0
    for source in sources:
        before = len(unknown)
        result = module["translate_consider_report"](source, {})
        source_lines = source.replace("\r", "").split("\n")
        result_lines = result.split("\n")
        assert len(source_lines) == len(result_lines), (source, result)
        line_total += sum(bool(line.strip()) for line in source_lines)
        assert len(unknown) >= before
    counts = Counter(unknown)
    print("CONSIDER_REPORTS=%d" % len(sources))
    print("CONSIDER_LINES=%d" % line_total)
    print("ENGINE_FALLBACK_LINES=%d" % len(unknown))
    print("ENGINE_FALLBACK_UNIQUE=%d" % len(counts))
    for value, count in counts.most_common():
        print("%4d  %s" % (count, value))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
