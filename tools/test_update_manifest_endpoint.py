"""Updater must use the latest Release asset, not GitHub Raw's stale CDN path."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / "src/mush-z/worlds/plugins/translation_bridge"
ENDPOINT = (
    "https://github.com/wengweng0312/altar-aeon-mush-client-translation/"
    "releases/latest/download/update_manifest.json"
)

for name in ("check_translation_update.ps1", "update_translation.ps1"):
    text = (BRIDGE / name).read_text(encoding="utf-8-sig")
    assert ENDPOINT in text, name
    assert "raw.githubusercontent.com" not in text, name

print("UPDATE_MANIFEST_ENDPOINT_OK latest_release_asset=yes")
