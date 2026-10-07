"""Regression checks for display-wrapped Tip blocks."""

from __future__ import annotations

import ast
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "src" / "mush-z" / "worlds" / "plugins" / "translation_bridge" / "translation_worker.py"


def load_functions() -> dict[str, object]:
    wanted = {"semantic_display_chunks", "is_tip_block", "has_embedded_tip_block"}
    tree = ast.parse(WORKER.read_text(encoding="utf-8-sig"))
    body = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in wanted]
    namespace: dict[str, object] = {"re": re}
    exec(compile(ast.Module(body=body, type_ignores=[]), str(WORKER), "exec"), namespace)
    return namespace


def main() -> None:
    module = load_functions()
    source = (
        "Hawana's coat of crystal scales suddenly shatters in a chain reaction!\n"
        "Tip:\n"
        "Use the 'check' command to see what important things you might be\n"
        "missing for your character."
    )
    assert module["has_embedded_tip_block"](source)
    tip = "\n".join(source.splitlines()[1:])
    assert module["is_tip_block"](tip)
    assert module["semantic_display_chunks"]("\n".join(source.splitlines()[2:])) == [
        "Use the 'check' command to see what important things you might be missing for your character."
    ]
    worker_source = WORKER.read_text(encoding="utf-8-sig")
    assert "if has_embedded_tip_block(text):\n        return translate_embedded_tip_block(text, c)" in worker_source
    print("WRAPPED_TIP_OK joined_sentence=yes embedded_tip=yes")


if __name__ == "__main__":
    main()
