"""List equipment/status sentence families found in local translation traces."""

from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path


PATTERNS = (
    re.compile(r"^You are (?:wearing|holding|wielding|carrying)\b.*[.:]$", re.I),
    re.compile(r"^You (?:wear|hold|wield|carry|remove|stop using|start using)\b.*[.:]$", re.I),
)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args()
    pairs: collections.Counter[tuple[str, str]] = collections.Counter()
    for path in args.paths:
        if not path.is_file():
            continue
        for raw in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            try:
                record = json.loads(raw)
            except (ValueError, TypeError):
                continue
            sources = str(record.get("source", "")).replace("\r", "").split("\n")
            results = str(record.get("result", "")).replace("\r", "").split("\n")
            for index, source in enumerate(sources):
                source = source.strip()
                if any(pattern.match(source) for pattern in PATTERNS):
                    result = results[index].strip() if index < len(results) else "<line alignment lost>"
                    pairs[(source, result)] += 1
    families = collections.Counter()
    for (source, _result), count in pairs.items():
        match = re.match(r"^You (?:are )?([A-Za-z ]+?)\b(?:\s+the|\s+a|\s+an|:|\.)", source, re.I)
        families[(match.group(1).lower() if match else "other")] += count
    print("FAMILIES")
    for family, count in families.most_common():
        print("%4d | %s" % (count, family))
    print("PAIRS")
    for (source, result), count in sorted(pairs.items(), key=lambda item: (-item[1], item[0][0].lower())):
        print("%4d | %s | %s" % (count, source, result))
    print("UNIQUE_PAIRS=%d TOTAL_MATCHES=%d" % (len(pairs), sum(pairs.values())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
