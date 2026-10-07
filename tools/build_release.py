"""Build a validated Only Patch and updater manifest for a GitHub Release."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / "src" / "mush-z" / "worlds" / "plugins" / "translation_bridge"
ADDON_SOURCE = ROOT / "src" / "nvda-addon"
DIST = ROOT / "dist"
REPOSITORY = "wengweng0312/altar-aeon-mush-client-translation"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    version = args.version.strip().removeprefix("v")
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?", version):
        raise SystemExit("version must look like 1.2.3 or 1.2.3-beta.1")

    subprocess.run([sys.executable, str(ROOT / "tools" / "validate_source.py")], check=True)
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir()

    addon = BRIDGE / "Mush_Client_Translation_Review_v3.nvda-addon"
    with zipfile.ZipFile(addon, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(ADDON_SOURCE.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                archive.write(path, path.relative_to(ADDON_SOURCE).as_posix())

    version_path = BRIDGE / "translation_version.json"
    channel = "beta" if "-" in version else "stable"
    version_path.write_text(
        json.dumps({"version": version, "channel": channel}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    asset_name = f"Mush-Z_Translation_Mode_Only_Patch_v{version}.zip"
    asset = DIST / asset_name
    subprocess.run(
        [sys.executable, str(BRIDGE / "build_translation_package.py"), "patch", str(asset)],
        check=True,
    )
    digest = sha256(asset)
    (DIST / f"{asset_name}.sha256.txt").write_text(
        f"{digest}  {asset_name}\n", encoding="ascii"
    )
    manifest = {
        "schema_version": 1,
        "published": True,
        "version": version,
        "patch_url": f"https://github.com/{REPOSITORY}/releases/download/v{version}/{asset_name}",
        "sha256": digest,
        "release_notes_url": f"https://github.com/{REPOSITORY}/releases/tag/v{version}",
    }
    (DIST / "update_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"RELEASE_BUILD_OK={asset}")
    print(f"SHA256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
