"""Report observed dense-item field values missing from the reviewed catalog."""

from __future__ import annotations

import argparse
import collections
import json
import re
import runpy
import sys
from pathlib import Path


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", type=Path, required=True)
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args()
    module = runpy.run_path(str(args.worker), run_name="item_glossary_audit")
    module["load_deterministic_templates"]()
    split_fields = module["split_item_detail_fields"]
    lookup = module["item_glossary_value"]
    affect_codes = set(module["ITEM_AFFECT_CODES"])
    wear_codes = set(module["ITEM_WEAR_CODES"])
    missing: collections.Counter[tuple[str, str]] = collections.Counter()
    observed: collections.Counter[tuple[str, str]] = collections.Counter()
    for path in args.paths:
        if not path.is_file():
            continue
        for raw in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            try:
                source = str(json.loads(raw).get("source", ""))
            except (ValueError, TypeError):
                continue
            for line in source.replace("\r", "").split("\n"):
                fields = split_fields(line)
                if not fields:
                    continue
                for field in fields:
                    label = re.fullmatch(r"([A-Za-z ]+):\s*(.*)", field)
                    values = []
                    if label and label.group(1).lower() == "comp":
                        values = [("composition", token.strip()) for token in label.group(2).split(",")]
                    elif label and label.group(1).lower() in {"type", "speed", "quality"}:
                        values = [(label.group(1).lower().replace("type", "item_type"), label.group(2).strip())]
                    elif label and label.group(1).lower() == "weight":
                        tail = re.sub(r"^[-+]?\d+(?:\.\d+)?\s*", "", label.group(2))
                        values = [("flag", token) for token in tail.split()]
                    else:
                        affect = re.fullmatch(r"([A-Z_]+)\s+by\s+(?:minus\s+)?[-+]?\d+(?:\.\d+)?%?", field, re.I)
                        if affect and affect.group(1).upper() in affect_codes:
                            values = [("affect", affect.group(1))]
                        elif field.upper() in wear_codes:
                            values = [("wear", field)]
                    for category, value in values:
                        key = (category, value.upper())
                        observed[key] += 1
                        if lookup(category, value) is None:
                            missing[key] += 1
    total = sum(observed.values())
    missing_total = sum(missing.values())
    print("ITEM_FIELD_GLOSSARY_AUDIT observed=%d missing=%d coverage=%.1f%%" % (
        total, missing_total, 100.0 * (total - missing_total) / total if total else 100.0,
    ))
    for (category, value), count in missing.most_common():
        print("%4d | %-12s | %s" % (count, category, value))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
