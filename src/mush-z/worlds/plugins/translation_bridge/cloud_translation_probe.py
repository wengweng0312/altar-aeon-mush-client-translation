"""Opt-in, isolated smoke test for Azure, Google and DeepL translation APIs."""
import argparse
import importlib.util
import json
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


worker_path = ROOT / "translation_worker.py"
if not worker_path.is_file():
    worker_path = ROOT / "translation_worker_candidate.py"
worker = load_module("translation_worker_probe", worker_path)
client = load_module("cloud_translation_client_probe", ROOT / "cloud_translation_client.py")

FIXTURES = [
    "A quiet stone hallway leads north toward the city gate.",
    "The wooden chest contains 3 silver rings and 12 gold coins.",
    "Find the Trogdolyte caves and return the gray spotted mushroom.",
    "A strange dwarf stands behind a counter, selling herbs.",
    "The path continues southeast beneath several enormous oak trees.",
]


def main():
    parser = argparse.ArgumentParser(description="Isolated Mush-Z cloud translation test")
    parser.add_argument("--live", action="store_true", help="make limited live API requests")
    args = parser.parse_args()
    settings = worker.cloud_translation_config()
    candidates = worker.cloud_translation_candidates("")
    selected = candidates[0][0] if candidates else 0
    provider = client.SERVICE_NAMES.get(selected, "offline")
    public_settings = {
        "service": settings["service"], "provider": provider,
        "azure_region": settings["azure_region"],
        "timeout_seconds": settings["timeout_seconds"],
        "allow_private_messages": settings["allow_private_messages"],
        "configured_providers": [client.SERVICE_NAMES[service]
                                 for service in (1, 2, 3)
                                 if settings["api_keys"].get(service)],
    }
    if not args.live:
        print(json.dumps({"status": "DRY_RUN", "settings": public_settings}, ensure_ascii=False))
        return
    if not candidates:
        raise SystemExit("OFFLINE_OR_KEY_MISSING")

    service, api_key, settings = candidates[0]

    rows = []
    started = time.perf_counter()
    try:
        translations = client.translate_many(
            service, FIXTURES, api_key,
            settings["azure_region"], settings["timeout_seconds"],
        )
        elapsed = time.perf_counter() - started
        for source, translated in zip(FIXTURES, translations):
            has_cjk = any("\u3400" <= char <= "\u9fff" for char in translated)
            numbers_ok = worker.numeric_items_preserved(source, translated)
            sane, reason = worker.translation_sanity_ok(source, translated)
            valid = bool(translated and has_cjk and numbers_ok and sane)
            rows.append({
                "source": source, "translated": translated,
                "batch_elapsed_seconds": round(elapsed, 3), "valid": valid,
                "reason": "" if valid else (reason or "no_cjk_or_numbers"),
            })
    except Exception as error:
        for source in FIXTURES:
            rows.append({
                "source": source, "translated": "", "batch_elapsed_seconds": round(time.perf_counter() - started, 3),
                "valid": False, "reason": str(error),
            })
    report = {
        "status": "PASS" if all(row["valid"] for row in rows) else "FAIL",
        "settings": public_settings, "fixture_count": len(rows), "rows": rows,
    }
    (ROOT / "cloud_translation_probe_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({
        "status": report["status"], "provider": provider,
        "passed": sum(row["valid"] for row in rows), "total": len(rows),
    }, ensure_ascii=False))
    if report["status"] != "PASS":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
