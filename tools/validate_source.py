"""Static, offline validation for the publishable source snapshot."""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src"
BRIDGE = SOURCE / "mush-z" / "worlds" / "plugins" / "translation_bridge"

BANNED_NAMES = (
    "translation_cache.sqlite3",
    "lmt_translation_trace.log",
    "translation_worker.log",
    "llama_server.log",
    "backend_choice.json",
    "worker.lock",
    "cloud_translation_config.txt",
)
PUBLISHABLE_CATALOGS = {
    (BRIDGE / "mush_structure_catalog.sqlite3").resolve(),
    (BRIDGE / "wiki_knowledge_catalog.sqlite3").resolve(),
}

SECRET_ASSIGNMENT = re.compile(
    r"(?im)^\s*(?:api_key|azure_api_key|google_api_key|deepl_api_key|token|password)"
    r"[ \t]*=[ \t]*([^\s#]+)"
)


def fail(message: str) -> None:
    raise RuntimeError(message)


def repository_source_paths() -> list[Path]:
    """Return files Git would include, plus non-ignored untracked source files.

    Regression tests import the worker and can create ignored runtime logs in
    ``src``.  Those files are not part of a commit or release checkout and must
    not make a later source validation fail.  Tracked artifacts and unignored
    new files remain visible, so the privacy/generated-file guard stays active.
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", "src"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return sorted(
            ROOT / item.decode("utf-8", errors="surrogateescape")
            for item in result.stdout.split(b"\0")
            if item
        )
    except (OSError, subprocess.SubprocessError):
        # Source archives without .git metadata still receive the conservative
        # filesystem scan used before this Git-aware CI fix.
        return sorted(path for path in SOURCE.rglob("*") if path.is_file())


def validate_names() -> None:
    for path in repository_source_paths():
        lowered = path.name.lower()
        if lowered in BANNED_NAMES:
            fail(f"private/generated file present: {path.relative_to(ROOT)}")
        if path.is_file() and path.resolve() not in PUBLISHABLE_CATALOGS and (
            lowered.endswith(".gguf")
            or lowered.startswith("backup_")
            or lowered.endswith((".sqlite", ".sqlite3", ".log", ".bak"))
        ):
            fail(f"blocked artifact present: {path.relative_to(ROOT)}")


def validate_python() -> None:
    python_files = sorted(SOURCE.rglob("*.py")) + sorted(SOURCE.rglob("*.pyw"))
    for path in python_files:
        ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    py = BRIDGE / "translation_worker.py"
    pyw = BRIDGE / "translation_worker.pyw"
    if py.read_bytes() != pyw.read_bytes():
        fail("translation_worker.py and translation_worker.pyw differ")
    updater = BRIDGE / "update_translation.ps1"
    if not updater.read_bytes().startswith(b"\xef\xbb\xbf"):
        fail("update_translation.ps1 must use UTF-8 BOM for Windows PowerShell 5")
    helper = BRIDGE / "translation_update_helper.ps1"
    if not helper.read_bytes().startswith(b"\xef\xbb\xbf"):
        fail("translation_update_helper.ps1 must use UTF-8 BOM for Windows PowerShell 5")
    checker = BRIDGE / "check_translation_update.ps1"
    if not checker.read_bytes().startswith(b"\xef\xbb\xbf"):
        fail("check_translation_update.ps1 must use UTF-8 BOM for Windows PowerShell 5")


def validate_data() -> None:
    plugins = SOURCE / "mush-z" / "worlds" / "plugins"
    for path in sorted(plugins.glob("*.xml")):
        ET.parse(path)
    for path in sorted(SOURCE.rglob("*.json")):
        json.loads(path.read_text(encoding="utf-8-sig"))


def validate_secrets() -> None:
    for path in repository_source_paths():
        if not path.is_file() or path.suffix.lower() not in {
            ".txt", ".json", ".xml", ".py", ".pyw", ".ps1", ".cmd", ".ini"
        }:
            continue
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        match = SECRET_ASSIGNMENT.search(text)
        if match:
            fail(f"possible credential in {path.relative_to(ROOT)}")


def main() -> int:
    validate_names()
    validate_python()
    validate_data()
    validate_secrets()
    print("SOURCE_VALIDATION_OK")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"SOURCE_VALIDATION_FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1)
