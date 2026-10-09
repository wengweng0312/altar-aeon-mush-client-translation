"""Static safety regression for the public one-click release publisher."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
publisher = (ROOT / "tools/publish_release.ps1").read_text(encoding="utf-8-sig")
launcher = (ROOT / "publish.cmd").read_text(encoding="utf-8-sig")
workflow = (ROOT / ".github/workflows/release-patch.yml").read_text(encoding="utf-8")

assert "tools\\publish_release.ps1" in launcher
assert "git -C $Root remote get-url origin" in publisher
assert "gh api user --jq .login" in publisher
assert "Publish to this repository?" in publisher
assert "Commit and publish exactly these files?" in publisher
assert "DRY RUN PASSED" in publisher
assert publisher.index("if ($DryRun)") < publisher.index("WriteAllText($repositoryFile")
assert "release-patch.yml" in publisher
assert "gh run watch" in publisher
assert "function Invoke-GhCaptured" in publisher
assert "release not found|HTTP 404" in publisher
assert "SysWOW64\\WindowsPowerShell" in publisher
assert "RELEASE COMPLETED AND PLAYER UPDATE CHECK PASSED" in publisher
assert "wengweng0312" not in publisher  # destination comes from origin

assert "python tools/build_release.py" in workflow
assert '--repository "${{ github.repository }}"' in workflow
assert 'Copy-Item -LiteralPath "dist\\update_manifest.json" -Destination "update\\latest.json"' in workflow
assert "Player-facing update verification failed" in workflow
assert "raw.githubusercontent.com" not in workflow

print("RELEASE_PUBLISHER_OK generic_origin=yes dry_run=yes player_check=yes")
