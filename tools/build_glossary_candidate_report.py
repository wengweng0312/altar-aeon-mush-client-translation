"""Mine local traces for reviewable public game-term glossary candidates.

This never promotes model output automatically.  It excludes chat/dialogue and
reports aggregate recurring UI phrases, inconsistent translations, and item
attribute codes for human review.
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path


PRIVATE_OR_DIALOGUE = re.compile(
    r"^(?:\[[^]]+\]|\([^)]*notify[^)]*\))|\b(?:says?|tells?|asks?|replies?|shouts?|whispers?)\b|['\"]",
    re.I,
)
ITEM_CODE = re.compile(r"\b[A-Z][A-Z_]{1,30}\b")


def safe_game_line(value: str) -> bool:
    value = value.strip()
    return bool(value and len(value) <= 160 and re.search(r"[A-Za-z]", value)
                and not PRIVATE_OR_DIALOGUE.search(value))


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    pairs: dict[str, collections.Counter[str]] = collections.defaultdict(collections.Counter)
    codes: collections.Counter[str] = collections.Counter()
    records = 0
    for path in args.paths:
        if not path.is_file():
            continue
        for raw in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            try:
                record = json.loads(raw)
            except (ValueError, TypeError):
                continue
            records += 1
            source_lines = str(record.get("source", "")).replace("\r", "").split("\n")
            result_lines = str(record.get("result", "")).replace("\r", "").split("\n")
            for source in source_lines:
                if ", Level:" in source or "Affects:" in source:
                    codes.update(ITEM_CODE.findall(source))
            if len(source_lines) != len(result_lines):
                continue
            for source, result in zip(source_lines, result_lines):
                source, result = source.strip(), result.strip()
                if safe_game_line(source) and result:
                    pairs[source][result] += 1

    candidates = []
    for source, translations in pairs.items():
        count = sum(translations.values())
        if count < 2:
            continue
        variants = [{"translation": value, "count": n}
                    for value, n in translations.most_common(8)]
        candidates.append({
            "source": source,
            "occurrences": count,
            "translation_variant_count": len(translations),
            "translations": variants,
        })
    candidates.sort(key=lambda row: (-row["translation_variant_count"], -row["occurrences"], row["source"].lower()))
    report = {
        "schema_version": 1,
        "trace_records_scanned": records,
        "policy": "Candidates only; never auto-promote model translations. Chat/dialogue excluded.",
        "recurring_line_candidates": candidates,
        "item_attribute_codes": [{"code": code, "occurrences": count} for code, count in codes.most_common()],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("GLOSSARY_CANDIDATES_OK records=%d recurring=%d codes=%d" % (records, len(candidates), len(codes)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
