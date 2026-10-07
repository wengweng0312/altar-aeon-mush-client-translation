"""Build a privacy-safe Mush-Z Translation Mode release archive."""
import hashlib
import json
import sys
import zipfile
from pathlib import Path


BRIDGE = Path(__file__).resolve().parent
PLUGINS = BRIDGE.parent
MUSHZ = PLUGINS.parent.parent
MODE = "full"
arguments = sys.argv[1:]
if arguments and arguments[0].lower() in {"full", "patch"}:
    MODE = arguments.pop(0).lower()
DEFAULT_OUTPUT = MUSHZ / (
    "Mush-Z_Translation_Mode_Full.zip" if MODE == "full"
    else "Mush-Z_Translation_Mode_Only_Patch.zip"
)
OUTPUT = Path(arguments[0]).resolve() if arguments else DEFAULT_OUTPUT

TOP_FILES = (
    "translation_worker.py",
    "translation_worker.pyw",
    "translation_config.json",
    "cloud_translation_config.txt",
    "cloud_translation_client.py",
    "cloud_translation_probe.py",
    "library_glossary_zh_tw.json",
    "mush_structure_catalog.sqlite3",
    "mush_structure_catalog_report.txt",
    "launch_speech_worker.cmd",
    "nvda_speech_worker.ps1",
    "LMT_Q4_FIRST_RUN.txt",
    "INSTALL_TESTING_zh-TW.txt",
    "TRANSLATION_CACHE_zh-TW.txt",
    "PACKAGE_README_zh-TW.txt",
    "Mush_Client_Translation_Review_v3.nvda-addon",
    "NVDA_TRANSLATION_REVIEW_README_zh-TW.txt",
    "build_translation_package.py",
    "build_translation_package.cmd",
    "build_full_translation_package.cmd",
    "build_only_patch.cmd",
    "ONLY_PATCH_README_zh-TW.txt",
    "update_translation.cmd",
    "update_translation.ps1",
    "translation_version.json",
)
PATCH_FILES = (
    "translation_worker.py",
    "translation_worker.pyw",
    "cloud_translation_client.py",
    "cloud_translation_probe.py",
    "launch_speech_worker.cmd",
    "nvda_speech_worker.ps1",
    "Mush_Client_Translation_Review_v3.nvda-addon",
    "NVDA_TRANSLATION_REVIEW_README_zh-TW.txt",
    "build_translation_package.py",
    "build_translation_package.cmd",
    "build_full_translation_package.cmd",
    "build_only_patch.cmd",
    "ONLY_PATCH_README_zh-TW.txt",
    "update_translation.cmd",
    "update_translation.ps1",
    "translation_version.json",
)
TREE_DIRS = ("runtime", "lmt_runtime")
BANNED_PARTS = (
    "backup_", "__pycache__", "runtime_madlad", "translation_cache.sqlite3",
    "lmt_translation_trace.log", "translation_worker.log", "llama_server.log",
    "accessible_history", "backend_choice.json", "worker.lock", "mush_session_",
    "launch_debug.txt", "translate_api.txt", "cloud_translation_probe_report.json",
)


def archive_name(path):
    if path in {PLUGINS / "Translation_Mode.xml", PLUGINS / "MushReader.xml"}:
        return "worlds/plugins/" + path.name
    if path == MUSHZ / "nvdaControllerClient32.dll":
        return "nvdaControllerClient32.dll"
    return "worlds/plugins/translation_bridge/" + path.relative_to(BRIDGE).as_posix()


def banned(name):
    lowered = name.lower()
    return any(part.lower() in lowered for part in BANNED_PARTS)


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


base_required = [
    PLUGINS / "Translation_Mode.xml",
    PLUGINS / "MushReader.xml",
]
if MODE == "full":
    required = base_required + [MUSHZ / "nvdaControllerClient32.dll"]
    required += [BRIDGE / name for name in TOP_FILES]
else:
    required = base_required + [BRIDGE / name for name in PATCH_FILES]
for path in required:
    if not path.is_file():
        raise SystemExit("Required release file is missing: %s" % path)

files = list(required)
if MODE == "full":
    for directory in TREE_DIRS:
        root = BRIDGE / directory
        if not root.is_dir():
            raise SystemExit("Required runtime directory is missing: %s" % root)
        files.extend(path for path in root.rglob("*") if path.is_file())

names = [archive_name(path) for path in files]
if len(names) != len(set(names)):
    raise SystemExit("Duplicate archive path detected")
bad = [name for name in names if banned(name)]
if bad:
    raise SystemExit("Banned private/generated path selected: %s" % bad[0])

config = json.loads((BRIDGE / "translation_config.json").read_text(encoding="utf-8"))
config["translation_cache_version"] = 13
config.pop("backend", None)
config.pop("scores_tokens_per_second", None)
config_bytes = (json.dumps(config, ensure_ascii=False, indent=2) + "\n").encode("utf-8")

# Never package a user's live API key. Every release archive starts offline and
# asks its recipient to provide their own credentials locally.
cloud_lines = []
for line in (BRIDGE / "cloud_translation_config.txt").read_text(encoding="utf-8-sig").splitlines():
    stripped = line.strip().lower()
    if stripped.startswith("service="):
        cloud_lines.append("service=0")
    elif stripped.startswith(("api_key=", "azure_api_key=", "google_api_key=", "deepl_api_key=")):
        cloud_lines.append(line.split("=", 1)[0] + "=")
    elif stripped.startswith("azure_region="):
        cloud_lines.append("azure_region=global")
    elif stripped.startswith("allow_private_messages="):
        cloud_lines.append("allow_private_messages=0")
    else:
        cloud_lines.append(line)
cloud_config_bytes = ("\n".join(cloud_lines).rstrip() + "\n").encode("utf-8")

glossary_path = BRIDGE / "skill_glossary_zh_tw.json"
if glossary_path.is_file():
    glossary = json.loads(glossary_path.read_text(encoding="utf-8"))
    if not isinstance(glossary, dict):
        raise SystemExit("skill_glossary_zh_tw.json must contain a JSON object")
else:
    glossary = {}
glossary_bytes = (json.dumps(glossary, ensure_ascii=False, indent=2) + "\n").encode("utf-8")

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
manifest = []
with zipfile.ZipFile(OUTPUT, "w", allowZip64=True) as archive:
    for path, name in zip(files, names):
        if path == BRIDGE / "translation_config.json":
            data = config_bytes
            archive.writestr(name, data, compress_type=zipfile.ZIP_DEFLATED)
            digest = hashlib.sha256(data).hexdigest()
        elif path == BRIDGE / "cloud_translation_config.txt":
            data = cloud_config_bytes
            archive.writestr(name, data, compress_type=zipfile.ZIP_DEFLATED)
            digest = hashlib.sha256(data).hexdigest()
        else:
            compression = zipfile.ZIP_STORED if path.suffix.lower() in {".gguf", ".exe", ".dll"} else zipfile.ZIP_DEFLATED
            archive.write(path, name, compress_type=compression)
            digest = sha256_file(path)
        manifest.append("%s  %s" % (digest, name))
    if MODE == "full":
        glossary_name = "worlds/plugins/translation_bridge/skill_glossary_zh_tw.json"
        archive.writestr(glossary_name, glossary_bytes, compress_type=zipfile.ZIP_DEFLATED)
        manifest.append("%s  %s" % (hashlib.sha256(glossary_bytes).hexdigest(), glossary_name))
        for empty in ("inbox/", "outbox/", "speech_inbox/"):
            archive.writestr("worlds/plugins/translation_bridge/" + empty, b"")
    archive.writestr("PACKAGE_MANIFEST_SHA256.txt", "\n".join(manifest) + "\n")

with zipfile.ZipFile(OUTPUT, "r") as archive:
    archived = archive.namelist()
    leaked = [name for name in archived if banned(name)]
    if leaked:
        raise SystemExit("Privacy check failed: %s" % leaked[0])
    if len(archived) != len(set(archived)):
        raise SystemExit("Archive contains duplicate paths")
    if archive.testzip() is not None:
        raise SystemExit("Archive CRC verification failed")

print("PACKAGE_OK=%s" % OUTPUT)
print("MODE=%s" % MODE.upper())
print("FILES=%d" % len(archived))
print("BYTES=%d" % OUTPUT.stat().st_size)
print("SHA256=%s" % sha256_file(OUTPUT))
