"""Isolated integration tests for the Windows Translation Mode updater."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UPDATER = ROOT / "src/mush-z/worlds/plugins/translation_bridge/update_translation.ps1"
HELPER = ROOT / "src/mush-z/worlds/plugins/translation_bridge/translation_update_helper.ps1"
POWERSHELL = Path(r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe")


def write(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def build_patch(path: Path, version: str, complete: bool = True, conflict: bool = False) -> None:
    entries = {
        "worlds/plugins/Translation_Mode.xml": "new translation mode",
        "worlds/plugins/translation_bridge/translation_worker.py": "new worker",
        "worlds/plugins/translation_bridge/translation_worker.pyw": "new workerw",
        "worlds/plugins/translation_bridge/translation_version.json": json.dumps({"version": version}),
        "worlds/plugins/translation_bridge/Mush_Client_Translation_Review_v3.nvda-addon": "addon",
        # These must never replace a user's values.
        "worlds/plugins/translation_bridge/cloud_translation_config.txt": "SECRET=overwritten",
        "worlds/plugins/translation_bridge/translation_config.json": "{}",
        "PACKAGE_MANIFEST_SHA256.txt": "fixture",
    }
    if not complete:
        entries.pop("worlds/plugins/translation_bridge/translation_worker.pyw")
    if conflict:
        entries["worlds/plugins/zz_conflict/child.txt"] = "must fail"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, value in entries.items():
            archive.writestr(name, value)


def invoke(root: Path, patch: Path, manifest: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            str(POWERSHELL), "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", str(UPDATER),
            "-ManifestFile", str(manifest),
            "-PatchFile", str(patch),
            "-MushZRoot", str(root),
            "-SkipMushClientCheck", "-SkipAddonLaunch",
        ],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=30,
    )


def manifest_for(path: Path, patch: Path, version: str, digest: str | None = None) -> None:
    sha = digest or hashlib.sha256(patch.read_bytes()).hexdigest()
    write(path, json.dumps({
        "schema_version": 1,
        "published": True,
        "version": version,
        "patch_url": "https://invalid.test/fixture.zip",
        "sha256": sha,
    }))


def seed(root: Path) -> Path:
    bridge = root / "worlds/plugins/translation_bridge"
    write(root / "worlds/plugins/Translation_Mode.xml", "old translation mode")
    write(bridge / "translation_worker.py", "old worker")
    write(bridge / "translation_worker.pyw", "old workerw")
    write(bridge / "translation_version.json", json.dumps({"version": "1.0.0"}))
    write(bridge / "cloud_translation_config.txt", "SECRET=user-key")
    write(bridge / "translation_config.json", '{"user": true}')
    write(bridge / "translation_cache.sqlite3", "cache")
    return bridge


def main() -> None:
    sandbox = Path(tempfile.mkdtemp(prefix="mushz_update_test_"))
    try:
        # Successful update, including preservation of every protected file.
        root = sandbox / "success"
        bridge = seed(root)
        patch = sandbox / "success.zip"
        manifest = sandbox / "success.json"
        build_patch(patch, "1.1.0")
        manifest_for(manifest, patch, "1.1.0")
        result = invoke(root, patch, manifest)
        assert result.returncode == 0, result.stdout + result.stderr
        assert (root / "worlds/plugins/Translation_Mode.xml").read_text(encoding="utf-8") == "new translation mode"
        assert (bridge / "translation_worker.py").read_text(encoding="utf-8") == "new worker"
        assert json.loads((bridge / "translation_version.json").read_text(encoding="utf-8"))["version"] == "1.1.0"
        assert (bridge / "cloud_translation_config.txt").read_text(encoding="utf-8") == "SECRET=user-key"
        assert (bridge / "translation_config.json").read_text(encoding="utf-8") == '{"user": true}'
        assert (bridge / "translation_cache.sqlite3").read_text(encoding="utf-8") == "cache"

        # Re-running the same version is safe and reaches the addon-launch step.
        result = invoke(root, patch, manifest)
        assert result.returncode == 0, result.stdout + result.stderr
        log = (bridge / "translation_update.log").read_text(encoding="utf-8-sig")
        assert "The installed version is already current: 1.1.0" in log
        assert "skipped the NVDA add-on installer" in log

        # A bad hash must leave the existing installation untouched.
        root = sandbox / "bad_hash"
        bridge = seed(root)
        patch = sandbox / "bad_hash.zip"
        manifest = sandbox / "bad_hash.json"
        build_patch(patch, "1.1.0")
        manifest_for(manifest, patch, "1.1.0", "0" * 64)
        result = invoke(root, patch, manifest)
        assert result.returncode != 0
        assert (bridge / "translation_worker.py").read_text(encoding="utf-8") == "old worker"
        assert json.loads((bridge / "translation_version.json").read_text(encoding="utf-8"))["version"] == "1.0.0"

        # A structurally incomplete archive must also leave the old files intact.
        root = sandbox / "incomplete"
        bridge = seed(root)
        patch = sandbox / "incomplete.zip"
        manifest = sandbox / "incomplete.json"
        build_patch(patch, "1.1.0", complete=False)
        manifest_for(manifest, patch, "1.1.0")
        result = invoke(root, patch, manifest)
        assert result.returncode != 0
        assert (bridge / "translation_worker.py").read_text(encoding="utf-8") == "old worker"
        assert (root / "worlds/plugins/Translation_Mode.xml").read_text(encoding="utf-8") == "old translation mode"

        # A failure after copying begins must restore files already replaced.
        root = sandbox / "rollback"
        bridge = seed(root)
        write(root / "worlds/plugins/zz_conflict", "parent is deliberately a file")
        patch = sandbox / "rollback.zip"
        manifest = sandbox / "rollback.json"
        build_patch(patch, "1.1.0", conflict=True)
        manifest_for(manifest, patch, "1.1.0")
        result = invoke(root, patch, manifest)
        assert result.returncode != 0
        assert (bridge / "translation_worker.py").read_text(encoding="utf-8") == "old worker"
        assert (root / "worlds/plugins/Translation_Mode.xml").read_text(encoding="utf-8") == "old translation mode"

        # The bootstrap helper must time out safely if MUSHclient did not close.
        fake_mush = sandbox / "MUSHclient.exe"
        shutil.copy2(Path(r"C:\Windows\System32\cmd.exe"), fake_mush)
        # Use a local timer rather than ping: restricted test environments may
        # reject even loopback traffic and let the fake client exit early.
        blocker = subprocess.Popen([
            str(fake_mush), "/c",
            "powershell.exe -NoLogo -NoProfile -Command Start-Sleep -Seconds 8",
        ])
        try:
            helper_log = sandbox / "helper.log"
            helper = subprocess.run(
                [
                    str(POWERSHELL), "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass",
                    "-File", str(HELPER), "-CloseTimeoutSeconds", "1",
                    "-StatusLogPath", str(helper_log), "-SuppressDialogs",
                ],
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                timeout=10,
            )
            assert helper.returncode != 0
            helper_text = helper_log.read_text(encoding="utf-8-sig")
            assert "no files were changed" in helper_text, helper_text
        finally:
            blocker.terminate()
            blocker.wait(timeout=5)

        print("AUTOMATIC_UPDATE_ISOLATION_OK success=yes protected=yes repeat=yes bad_hash_safe=yes incomplete_safe=yes rollback=yes close_timeout_safe=yes")
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)


if __name__ == "__main__":
    main()
