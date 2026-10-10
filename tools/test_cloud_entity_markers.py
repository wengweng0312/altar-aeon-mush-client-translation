"""Regression tests for provider-specific no-translate wrappers."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLIENT = ROOT / "src/mush-z/worlds/plugins/translation_bridge/cloud_translation_client.py"
MARKER = "ZXQNPC0000QXZ"


class Response:
    def __init__(self, value):
        self.value = value
    def __enter__(self):
        return self
    def __exit__(self, *_args):
        return False
    def read(self):
        return json.dumps(self.value).encode("utf-8")


def load_client():
    spec = importlib.util.spec_from_file_location("cloud_marker_client", CLIENT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def main():
    client = load_client()
    seen = []

    def opener(request, timeout=0):
        payload = json.loads(request.data.decode("utf-8"))
        seen.append((request.full_url, payload, timeout))
        if "microsofttranslator" in request.full_url:
            text = payload[0]["Text"]
            return Response([{"translations": [{"text": text}]}])
        if "googleapis" in request.full_url:
            return Response({"data": {"translations": [
                {"translatedText": payload["q"][0]}
            ]}})
        return Response({"translations": [{"text": payload["text"][0]}]})

    source = MARKER + " attacks you."
    for service in (1, 2, 3):
        result = client.translate_many(service, [source], "test-key:fx", opener=opener)[0]
        assert result == source, (service, result)
        url, payload, _timeout = seen[-1]
        encoded = json.dumps(payload)
        assert 'translate=\\"no\\"' in encoded and MARKER in encoded, (service, payload)
        if service == 1:
            assert "textType=html" in url
        elif service == 2:
            assert payload["format"] == "html"
        else:
            assert payload["tag_handling"] == "html"
            assert payload["tag_handling_version"] == "v2"

    print("CLOUD_ENTITY_MARKERS_OK azure=html google=html deepl=html")


if __name__ == "__main__":
    main()
