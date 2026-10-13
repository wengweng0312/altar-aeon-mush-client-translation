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
assert "function Write-WorkflowFailureDiagnostics" in publisher
assert '"--log-failed"' in publisher
assert "mush-release-run-$RunId-failed.log" in publisher
assert "GITHUB ACTIONS FAILURE DETAILS" in publisher
assert "Source commit  : already pushed" in publisher
assert "the same version may be retried" in publisher
assert publisher.index("gh run watch") < publisher.index("Write-WorkflowFailureDiagnostics $RunId")
assert "release not found|HTTP 404" in publisher
assert "SysWOW64\\WindowsPowerShell" in publisher
assert "RELEASE COMPLETED AND PLAYER UPDATE CHECK PASSED" in publisher
assert "wengweng0312" not in publisher  # destination comes from origin
assert "function Assert-RemoteBranchContained" in publisher
assert "git -C $Root fetch origin $BranchName" in publisher
assert 'merge-base --is-ancestor "origin/$BranchName" HEAD' in publisher
assert "Assert-RemoteBranchContained $Branch" in publisher
assert publisher.index("Assert-RemoteBranchContained $Branch") < publisher.index("WriteAllText($repositoryFile")
assert "force-with-lease" not in publisher
assert "force push" in publisher

# Tests intentionally run before build_release. The Git-aware validator must
# ignore their ignored runtime logs while retaining the source safety scan.
validator = (ROOT / "tools/validate_source.py").read_text(encoding="utf-8-sig")
assert '"ls-files", "-z", "--cached", "--others", "--exclude-standard"' in validator
assert "BANNED_NAMES" in validator and "validate_names()" in validator

assert "python tools/build_release.py" in workflow
assert '--repository "${{ github.repository }}"' in workflow
assert 'Copy-Item -LiteralPath "dist\\update_manifest.json" -Destination "update\\latest.json"' in workflow
assert "Player-facing update verification failed" in workflow
assert "raw.githubusercontent.com" not in workflow
assert "shell: powershell" not in workflow
assert workflow.count("shell: pwsh") == 4

print("RELEASE_PUBLISHER_OK generic_origin=yes dry_run=yes player_check=yes")
