"""Regression test for lossless local log rotation."""
from __future__ import annotations
import ast
import os
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "src" / "mush-z" / "worlds" / "plugins" / "translation_bridge" / "translation_worker.py"

def main() -> None:
    tree = ast.parse(WORKER.read_text(encoding="utf-8-sig"))
    node = next(item for item in tree.body if isinstance(item, ast.FunctionDef) and item.name == "rotate_log_if_needed")
    namespace = {"os": os, "time": time, "LOG_ARCHIVE": None}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(WORKER), "exec"), namespace)
    rotate = namespace["rotate_log_if_needed"]
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder); archive = root / "log_archive"; namespace["LOG_ARCHIVE"] = archive
        path = root / "trace.log"; original = "珍貴的實戰紀錄\n" * 20
        path.write_text(original, encoding="utf-8")
        assert rotate(path, path.stat().st_size + 1) is None
        destination = rotate(path, 1)
        assert destination and destination.is_file() and not path.exists()
        assert destination.read_text(encoding="utf-8") == original
    print("LOG_ROTATION_OK lossless=yes deletion_policy=none")

if __name__ == "__main__":
    main()
