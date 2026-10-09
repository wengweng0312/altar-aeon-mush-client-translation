"""Updater must use the latest Release asset, not GitHub Raw's stale CDN path."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / "src/mush-z/worlds/plugins/translation_bridge"
for name in ("check_translation_update.ps1", "update_translation.ps1"):
    text = (BRIDGE / name).read_text(encoding="utf-8-sig")
    assert 'Join-Path $PSScriptRoot "release_repository.txt"' in text, name
    assert 'releases/latest/download/update_manifest.json' in text, name
    assert "raw.githubusercontent.com" not in text, name

repository = (BRIDGE / "release_repository.txt").read_text(encoding="utf-8").strip()
assert repository == "wengweng0312/altar-aeon-mush-client-translation"

print("UPDATE_MANIFEST_ENDPOINT_OK latest_release_asset=yes")
