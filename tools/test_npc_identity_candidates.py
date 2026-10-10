"""Isolation regressions for automatic NPC identity discovery."""

from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUBJECT = ROOT / "tools" / "audit_npc_identity_candidates.py"


def load_subject():
    spec = importlib.util.spec_from_file_location("npc_identity_candidates", SUBJECT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def main():
    module = load_subject()
    fixtures = {
        "You try to talk to Belnar, the town mayor...": "Belnar",
        "Belnar, the town mayor says, 'Hello.'": "Belnar",
        "Standir the dwarf assists Belnar, the town mayor!": "Standir",
        "Torngar the dwarf's kick devastates a shadow decoy!": "Torngar",
        "Lady Kindri -> Court meeting room": "Kindri",
        "Dractoz Clawheart says in an irritated voice, 'Stop.'": "Dractoz Clawheart",
    }
    confirmed = set()
    for source, expected in fixtures.items():
        found = list(module.evidence_from_line(source))
        identities = {identity for identity, _variant, _reason in found}
        assert expected in identities, (source, identities, expected)
        confirmed.update(identity.lower() for identity in identities)

    # Once confirmed, no knowledge of "somersaults" or "polishes" is needed.
    assert list(module.confirmed_name_mentions(
        "Belnar somersaults angrily across the battlefield!", confirmed,
    )) == ["belnar"]
    assert list(module.confirmed_name_mentions(
        "Torngar polishes an unfamiliar contraption.", confirmed,
    )) == ["torngar"]

    false_cases = (
        "You throw a crescent-shaped shadow at A husker!",
        "The Tyranid warrior is DEAD!",
        "A kobold war leader tries to trip you.",
        "North end of Miner's End",
    )
    for source in false_cases:
        assert not list(module.evidence_from_line(source)), source
    print("NPC_IDENTITY_CANDIDATES_OK confirmed=%d unknown_verbs=2 false_cases=%d" % (
        len(confirmed), len(false_cases),
    ))


if __name__ == "__main__":
    main()
