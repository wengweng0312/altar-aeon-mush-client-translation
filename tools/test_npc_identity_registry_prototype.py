"""Isolation tests for automatic NPC identity persistence and protection."""

from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUBJECT = ROOT / "tools" / "npc_identity_registry_prototype.py"


def load_subject():
    spec = importlib.util.spec_from_file_location("npc_identity_registry", SUBJECT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def main():
    module = load_subject()
    with tempfile.TemporaryDirectory(dir=ROOT / ".test-tmp") as folder:
        registry = module.IdentityRegistry(Path(folder) / "identities.sqlite3")
        try:
            registry.observe("belnar", "Belnar, the town mayor", strong=True)
            # Candidates never affect source text before their Chinese name is
            # explicitly confirmed from an aligned, validated translation.
            untouched, pending = registry.protect("Belnar somersaults angrily!")
            assert untouched == "Belnar somersaults angrily!" and pending == []

            registry.confirm(
                "belnar", "貝爾納",
                variants=("Belnar", "Mayor Belnar", "Belnar, the town mayor"),
            )
            source = (
                "Mayor Belnar somersaults angrily across the battlefield!\n"
                "Standir assists Belnar, the town mayor.\n"
                "Belnar's weapon flashes."
            )
            protected, occurrences = registry.protect(source)
            assert len(occurrences) == 3, (protected, occurrences)
            assert "Belnar" not in protected and "Mayor" not in protected
            # Simulate a provider translating every word except the opaque marker.
            translated = protected.replace(" somersaults angrily across the battlefield!", " 憤怒地翻越戰場！")
            translated = translated.replace("Standir assists ", "Standir 協助了")
            translated = translated.replace("'s weapon flashes.", "的武器閃閃發光。")
            restored = registry.restore(translated, occurrences)
            assert restored.count("貝爾納") == 3 and "ZXQNPC" not in restored

            # Missing, duplicated or invented markers must fail closed so the
            # caller can return original English rather than a corrupted name.
            for broken in (
                translated.replace("ZXQNPC0000QXZ", ""),
                translated + " ZXQNPC0000QXZ",
                translated + " ZXQNPC9999QXZ",
            ):
                try:
                    registry.restore(broken, occurrences)
                except RuntimeError:
                    pass
                else:
                    raise AssertionError("broken marker accepted: " + broken)
        finally:
            registry.close()
    print("NPC_IDENTITY_REGISTRY_OK candidate_safe=yes unknown_grammar=yes marker_fail_closed=yes")


if __name__ == "__main__":
    main()
