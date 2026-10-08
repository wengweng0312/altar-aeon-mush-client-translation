"""Regression fixture for dialogue with leading and trailing actions."""

from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "src/mush-z/worlds/plugins/translation_bridge/translation_worker.py"


def load_worker():
    spec = importlib.util.spec_from_file_location("translation_worker_test", WORKER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def main() -> None:
    worker = load_worker()
    source = """You try to talk to Calaell the monk...
Calaell the monk says, 'Oh! I didn't even see you there. Maybe you can
help me that metal thing off in the distance is full of half creature
half metal things. Please go talk with them and help them if you can.'
Calaell the monk goes back to staring at the metal building off in the
distance."""
    units = worker.parse_wrapped_dialogue_units(source)
    assert len(units) == 3, units
    assert units[0][1] == "You try to talk to Calaell the monk..."
    assert units[1][1].startswith("Calaell the monk says")
    assert units[1][1].endswith("help them if you can.'")
    assert units[2][1].endswith("distance.")
    assert worker.is_wrapped_dialogue_block(source)
    print("WRAPPED_DIALOGUE_LAYOUT_OK units=3 speech_wraps=joined")


if __name__ == "__main__":
    main()
