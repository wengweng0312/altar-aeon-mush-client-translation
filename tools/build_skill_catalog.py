"""Build a public Alter Aeon skill catalog from the official class lists.

The generated catalog contains no player data. Existing reviewed Traditional
Chinese names always win; missing translations remain blank for later review.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


CLASSES = ("mage", "cleric", "thief", "warrior", "necromancer", "druid")
BASE_URL = "https://alteraeon.com:8081/spells/"
GROUP_RE = re.compile(r'<font color="ffff00">(.*?)</font>', re.I | re.S)
ABILITY_RE = re.compile(
    r'<a href="([^"]*help\?helpfile=[^"]+)">([^<]+)</a>\s*([^\r\n<]*)',
    re.I,
)
LEVEL_RE = re.compile(r"(\d+)\s+(mag|cle|thi|war|nec|dru)\b", re.I)


def fetch(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "Mush-Z-Translation-Catalog/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", "replace")


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", value))).strip()


def parse_class(class_name: str, document: str) -> list[dict]:
    groups = [(match.start(), clean(match.group(1))) for match in GROUP_RE.finditer(document)]
    output = []
    for match in ABILITY_RE.finditer(document):
        level = LEVEL_RE.search(clean(match.group(3)))
        if not level:
            continue
        group = ""
        for position, candidate in groups:
            if position > match.start():
                break
            group = candidate
        name = clean(match.group(2)).lower()
        output.append({
            "name": name,
            "class": class_name,
            "level": int(level.group(1)),
            "ability_type": "spell" if "spellgroup" in group.lower() else "skill",
            "group": group,
            "help_url": urllib.parse.urljoin(BASE_URL + class_name, html.unescape(match.group(1))),
        })
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--existing-glossary", type=Path, required=True)
    parser.add_argument("--reviewed-additions", type=Path)
    parser.add_argument("--source-dir", type=Path)
    parser.add_argument("--catalog-output", type=Path, required=True)
    parser.add_argument("--glossary-output", type=Path, required=True)
    args = parser.parse_args()

    reviewed = json.loads(args.existing_glossary.read_text(encoding="utf-8-sig"))
    reviewed = {str(key).strip().lower(): str(value).strip() for key, value in reviewed.items()}
    original_reviewed = dict(reviewed)
    additions = {}
    if args.reviewed_additions:
        additions = json.loads(args.reviewed_additions.read_text(encoding="utf-8-sig"))
        additions = {str(key).strip().lower(): str(value).strip() for key, value in additions.items()}
        overlap = sorted(set(reviewed) & set(additions))
        if overlap:
            raise RuntimeError("reviewed additions duplicate existing keys: %s" % ", ".join(overlap))
        reviewed.update(additions)
    entries = []
    for class_name in CLASSES:
        source_file = args.source_dir / (class_name + ".html") if args.source_dir else None
        document = source_file.read_text(encoding="utf-8-sig") if source_file else fetch(BASE_URL + class_name)
        parsed = parse_class(class_name, document)
        if len(parsed) < 40:
            raise RuntimeError("official %s list unexpectedly short: %d" % (class_name, len(parsed)))
        entries.extend(parsed)

    by_name: dict[str, dict] = {}
    for entry in entries:
        current = by_name.setdefault(entry["name"], {
            "english": entry["name"], "traditional_chinese": reviewed.get(entry["name"], ""),
            "classes": [], "levels": {}, "types": [], "groups": [], "help_urls": [],
        })
        current["classes"].append(entry["class"])
        current["levels"][entry["class"]] = entry["level"]
        if entry["ability_type"] not in current["types"]:
            current["types"].append(entry["ability_type"])
        if entry["group"] and entry["group"] not in current["groups"]:
            current["groups"].append(entry["group"])
        if entry["help_url"] not in current["help_urls"]:
            current["help_urls"].append(entry["help_url"])

    unknown_additions = sorted(set(additions) - set(by_name))
    if unknown_additions:
        raise RuntimeError("reviewed additions not found in official catalog: %s" % ", ".join(unknown_additions))
    changed_existing = [key for key, value in original_reviewed.items() if reviewed.get(key) != value]
    if changed_existing:
        raise RuntimeError("existing reviewed translations changed unexpectedly")

    catalog = {
        "schema_version": 1,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "source": "Official Alter Aeon class spell and skill lists",
        "source_base_url": BASE_URL,
        "entry_count": len(by_name),
        "reviewed_translation_count": sum(bool(row["traditional_chinese"]) for row in by_name.values()),
        "entries": [by_name[name] for name in sorted(by_name)],
    }
    args.catalog_output.parent.mkdir(parents=True, exist_ok=True)
    args.catalog_output.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # Runtime glossary deliberately contains reviewed translations only.
    # This means a newly discovered official skill safely follows the existing
    # LMT learner until its Chinese name is reviewed and promoted here.
    merged = dict(reviewed)
    args.glossary_output.write_text(
        json.dumps(dict(sorted(merged.items())), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("SKILL_CATALOG_OK entries=%d reviewed=%d missing=%d" % (
        len(by_name), catalog["reviewed_translation_count"],
        len(by_name) - catalog["reviewed_translation_count"],
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
