import importlib.util
import json
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKER_PATH = ROOT / "src/mush-z/worlds/plugins/translation_bridge/translation_worker.py"
SPEC = importlib.util.spec_from_file_location("translation_worker_api_usage_test", WORKER_PATH)
worker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(worker)


with tempfile.TemporaryDirectory() as directory:
    worker.API_USAGE_FILE = Path(directory) / "usage.json"
    worker.record_cloud_usage(1, ["abc", "de"])
    worker.record_cloud_usage(3, ["1234"])
    saved = json.loads(worker.API_USAGE_FILE.read_text(encoding="utf-8"))
    month = __import__("time").strftime("%Y-%m")
    assert saved["months"][month]["azure"] == 5
    assert saved["months"][month]["deepl"] == 4

    worker.cloud_translation_config = lambda: {
        "service": 1,
        "api_keys": {1: "azure-secret", 2: "", 3: "deepl-secret:fx"},
        "azure_region": "global",
        "timeout_seconds": 1.5,
        "allow_private_messages": False,
    }
    worker.cloud_translation_client.deepl_usage = lambda *_args, **_kwargs: {
        "character_count": 123,
        "character_limit": 500000,
    }
    report = worker.cloud_api_report()
    assert "Microsoft Azure：已設定。本機本月送出 5 字元" in report
    assert "Google Cloud：未設定" in report
    assert "DeepL：官方本期已使用 123／500000 字元，剩餘 499877" in report
    assert "azure-secret" not in report and "deepl-secret" not in report

print("API usage tests passed")
