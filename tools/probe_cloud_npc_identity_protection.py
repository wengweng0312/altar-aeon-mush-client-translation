"""Live, isolated probe for protecting confirmed NPC identities in cloud MT.

This script never prints credentials and does not touch the production cache.
It uses synthetic Alter Aeon-like sentences and reports only provider results.
"""
from __future__ import annotations

import argparse
import importlib.util
import re
import time
from pathlib import Path


MARKERS = ("ZXQNPC0000QXZ", "ZXQNPC0001QXZ")
CASES = (
    ("single_dialogue", "Gimthen says, 'Welcome to my shop.'", (0,)),
    ("repeated_dialogue", "Gimthen nods. Gimthen says, 'Bring it to me.'", (0, 0)),
    ("combat", "Bellnor attacks Gimthen, but Gimthen dodges.", (1, 0, 0)),
    ("unknown_verb", "Gimthen florbles impatiently.", (0,)),
)


def load_client(path: Path):
    spec = importlib.util.spec_from_file_location("cloud_translation_client", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def read_config(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip().lower()] = value.strip()
    return values


def protect(text: str, indexes: tuple[int, ...]) -> str:
    names = ("Gimthen", "Bellnor")
    offsets = {0: 0, 1: 0}
    result = text
    # Replace in source order, one occurrence at a time.
    for index in indexes:
        name = names[index]
        start = result.find(name, offsets[index])
        if start < 0:
            raise AssertionError("fixture identity missing")
        wrapped = '<span translate="no">%s</span>' % MARKERS[index]
        result = result[:start] + wrapped + result[start + len(name):]
        offsets[index] = start + len(wrapped)
    return result


def validate_and_restore(text: str, indexes: tuple[int, ...]) -> str:
    expected = [MARKERS[index] for index in indexes]
    found = re.findall(r"ZXQNPC\d{4}QXZ", text)
    if sorted(found) != sorted(expected):
        raise ValueError("marker set/count changed: expected=%r found=%r" % (expected, found))
    # Accept harmless provider normalization of the span wrapper, but no other tags.
    cleaned = re.sub(r"</?span(?:\s+[^>]*)?>", "", text, flags=re.I)
    if "<" in cleaned or ">" in cleaned:
        raise ValueError("unexpected markup in response")
    for marker, chinese in zip(MARKERS, ("吉姆森", "貝爾納")):
        cleaned = cleaned.replace(marker, chinese)
    return cleaned.strip()


def azure_translate(client, texts, key, region, timeout):
    url = ("https://api.cognitive.microsofttranslator.com/translate"
           "?api-version=3.0&from=en&to=zh-Hant&textType=html")
    headers = {
        "Content-Type": "application/json; charset=UTF-8",
        "Ocp-Apim-Subscription-Key": key,
    }
    if region and region.lower() != "global":
        headers["Ocp-Apim-Subscription-Region"] = region
    data = client._post_json(url, headers, [{"Text": text} for text in texts], timeout,
                             client.urllib.request.urlopen)
    return [str(item["translations"][0]["text"]).strip() for item in data]


def deepl_translate(client, texts, key, timeout):
    host = "api-free.deepl.com" if key.endswith(":fx") else "api.deepl.com"
    headers = {
        "Authorization": "DeepL-Auth-Key " + key,
        "Content-Type": "application/json; charset=UTF-8",
    }
    payload = {
        "text": texts,
        "source_lang": "EN",
        "target_lang": "ZH-HANT",
        "tag_handling": "html",
        "tag_handling_version": "v2",
    }
    data = client._post_json("https://%s/v2/translate" % host, headers, payload, timeout,
                             client.urllib.request.urlopen)
    return [str(item["text"]).strip() for item in data["translations"]]


def run_provider(name, translate, client, key, region, timeout):
    protected = [protect(source, indexes) for _, source, indexes in CASES]
    started = time.perf_counter()
    if name == "azure":
        outputs = translate(client, protected, key, region, timeout)
    else:
        outputs = translate(client, protected, key, timeout)
    elapsed = time.perf_counter() - started
    if len(outputs) != len(CASES):
        raise ValueError("response count changed")
    restored = []
    for output, (case_name, _, indexes) in zip(outputs, CASES):
        restored.append((case_name, validate_and_restore(output, indexes)))
    return elapsed, restored


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--client", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()
    config = read_config(args.config)
    client = load_client(args.client)
    providers = (
        ("azure", azure_translate, config.get("azure_api_key", "")),
        ("deepl", deepl_translate, config.get("deepl_api_key", "")),
    )
    tested = 0
    for name, translator, key in providers:
        if not key:
            print("%s SKIP no key" % name.upper())
            continue
        tested += 1
        try:
            elapsed, restored = run_provider(
                name, translator, client, key,
                config.get("azure_region", "global"), args.timeout,
            )
            print("%s PASS cases=%d elapsed=%.3fs" % (name.upper(), len(restored), elapsed))
            for case_name, result in restored:
                print("  %s: %s" % (case_name, result))
        except Exception as error:
            # Provider client exceptions contain only sanitized error codes.
            print("%s FAIL %s" % (name.upper(), error))
    if not tested:
        raise SystemExit("No configured Azure or DeepL key was found.")


if __name__ == "__main__":
    main()
