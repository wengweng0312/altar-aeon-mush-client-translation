"""Fill missing official skill names with the packaged LMT runtime."""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import time
from pathlib import Path


def load_worker(path: Path):
    spec = importlib.util.spec_from_file_location("skill_catalog_worker", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def acceptable(source: str, translated: str) -> bool:
    value = translated.strip()
    if not value or "\n" in value or len(value) > 40:
        return False
    if not re.search(r"[\u3400-\u9fff]", value):
        return False
    lowered = value.lower()
    if any(marker in lowered for marker in ("translation:", "中文：", "翻譯：", "english:")):
        return False
    if len(value) >= 8 and value[: len(value) // 2] == value[len(value) // 2 :]:
        return False
    return source.strip().lower() != lowered


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--glossary", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    args = parser.parse_args()

    catalog = json.loads(args.catalog.read_text(encoding="utf-8-sig"))
    glossary = json.loads(args.glossary.read_text(encoding="utf-8-sig"))
    glossary = {str(key).strip().lower(): str(value).strip() for key, value in glossary.items()}
    checkpoint = {}
    if args.checkpoint.exists():
        checkpoint = json.loads(args.checkpoint.read_text(encoding="utf-8-sig"))

    worker = load_worker(args.worker.resolve())
    accepted = rejected = 0
    worker.start_server()
    try:
        missing = [row for row in catalog["entries"] if row["english"] not in glossary]
        total = len(missing)
        for index, row in enumerate(missing, 1):
            name = row["english"]
            translated = checkpoint.get(name, "")
            if not translated:
                context = ", ".join(row.get("classes") or [])
                ability_type = "/".join(row.get("types") or ["ability"])
                groups = "; ".join(row.get("groups") or [])
                prompt = (
                    "Translate this fantasy RPG ability name into Traditional Chinese. "
                    "Use its game meaning, not an unrelated everyday meaning. "
                    "Output only the translated ability name and no explanation.\n"
                    "Class: " + context + "\nType: " + ability_type + "\nGroup: " + groups +
                    "\nEnglish ability name: " + name + "\nTraditional Chinese name:"
                )
                response = worker.http_post("/completion", {
                    "prompt": prompt, "n_predict": 48, "temperature": 0.0,
                    "repeat_penalty": 1.1, "repeat_last_n": 64, "stream": False,
                }, 25)
                translated = worker.to_traditional_characters((response.get("content") or "").strip())
                checkpoint[name] = translated
                if index % 10 == 0:
                    args.checkpoint.write_text(
                        json.dumps(checkpoint, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
                    )
            if acceptable(name, translated):
                glossary[name] = translated
                accepted += 1
            else:
                rejected += 1
            if index % 50 == 0:
                print("SKILL_LMT_PROGRESS %d/%d" % (index, total), flush=True)
        args.checkpoint.write_text(
            json.dumps(checkpoint, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        args.glossary.write_text(
            json.dumps(dict(sorted(glossary.items())), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    finally:
        if worker.SERVER_PROCESS is not None:
            try:
                worker.SERVER_PROCESS.terminate()
                worker.SERVER_PROCESS.wait(timeout=5)
            except Exception:
                try:
                    worker.SERVER_PROCESS.kill()
                except Exception:
                    pass
        time.sleep(0.1)
    print("SKILL_LMT_OK accepted=%d rejected=%d total_glossary=%d" % (
        accepted, rejected, len(glossary)
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
