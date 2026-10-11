#!/usr/bin/env python3
"""Export Wiki help summaries for abilities not yet in the reviewed glossary."""

from __future__ import annotations

import argparse
import html
import json
import re
import sqlite3
import ssl
import urllib.parse
import urllib.request
from pathlib import Path


API = "https://wiki.alteraeon.com/api.php"
HELP = "https://alteraeon.com:8081/help?helpfile="


def query(params):
    request = urllib.request.Request(
        API + "?" + urllib.parse.urlencode({"format": "json", **params}),
        headers={"User-Agent": "Mush-Z-Translation-Catalog/1.0"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def official_help(name: str) -> str:
    request = urllib.request.Request(
        HELP + urllib.parse.quote(name),
        headers={"User-Agent": "Mush-Z-Translation-Catalog/1.0"},
    )
    # The legacy official help endpoint does not present a chain accepted by
    # every bundled Python CA store.  This exporter only reads public text.
    context = ssl._create_unverified_context()
    with urllib.request.urlopen(request, timeout=30, context=context) as response:
        raw = response.read().decode("utf-8", "replace")
    text = html.unescape(re.sub(r"<[^>]+>", " ", raw))
    text = re.sub(r"\s+", " ", text).strip()
    marker = "Keywords are:"
    if marker in text:
        text = marker + text.split(marker, 1)[1]
    return text[:2400]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    db = sqlite3.connect(args.catalog)
    names = [row[0] for row in db.execute(
        "SELECT english_name FROM abilities WHERE translation_reviewed=0 ORDER BY ability_key"
    )]
    db.close()
    output = []
    for offset in range(0, len(names), 20):
        payload = query({
            "action": "query", "prop": "extracts|categories", "explaintext": "1",
            "exintro": "1", "exsectionformat": "plain", "cllimit": "500",
            "redirects": "1", "titles": "|".join(names[offset:offset + 20]),
        })
        for page in payload["query"]["pages"].values():
            extract = re.sub(r"\s+", " ", page.get("extract", "")).strip()
            output.append({
                "english": page.get("title", ""),
                "summary": extract[:1200],
                "categories": sorted(
                    row["title"].removeprefix("Category:") for row in page.get("categories", [])
                ),
            })
    for row in output:
        row["official_help"] = official_help(row["english"])
    output.sort(key=lambda row: row["english"].casefold())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("WIKI_HELP_EXPORT_OK entries=%d" % len(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
