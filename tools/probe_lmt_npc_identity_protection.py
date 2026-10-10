"""Isolated live LMT probe for confirmed NPC identity markers."""
from __future__ import annotations

import argparse
import importlib.util
import json
import tempfile
import time
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_SOURCE = ROOT / "tools" / "npc_identity_registry_prototype.py"
CASES = (
    ("single_dialogue", "Gimthen says, 'Welcome to my shop.'"),
    ("repeated_dialogue", "Gimthen nods. Gimthen says, 'Bring it to me.'"),
    ("combat", "Bellnor attacks Gimthen, but Gimthen dodges."),
    ("unknown_verb", "Gimthen florbles impatiently."),
)


def load_registry_module():
    spec = importlib.util.spec_from_file_location("npc_identity_registry", REGISTRY_SOURCE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def completion(url: str, source: str, timeout: float) -> str:
    # Match the production worker exactly.  Extra placeholder instructions made
    # this compact translation model translate the instructions themselves when
    # several names occurred in one sentence.
    prompt = "Translate the following text from English into Chinese:\nEnglish: %s\nChinese:" % source
    payload = {
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 192,
        "temperature": 0.0,
        "repeat_penalty": 1.1,
        "stream": False,
    }
    request = urllib.request.Request(
        url.rstrip("/") + "/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = json.loads(response.read().decode("utf-8"))
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("LMT_CHAT_NO_CHOICES")
    return str((choices[0].get("message") or {}).get("content") or "").strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:18083")
    parser.add_argument("--timeout", type=float, default=25.0)
    args = parser.parse_args()
    module = load_registry_module()
    with tempfile.TemporaryDirectory(dir=ROOT / ".test-tmp") as folder:
        registry = module.IdentityRegistry(Path(folder) / "identities.sqlite3")
        try:
            registry.confirm("gimthen", "吉姆森", variants=("Gimthen",))
            registry.confirm("bellnor", "貝爾納", variants=("Bellnor",))
            started = time.perf_counter()
            results = []
            failures = []
            for name, source in CASES:
                protected, occurrences = registry.protect(source)
                translated = completion(args.url, protected, args.timeout)
                try:
                    restored = registry.restore(translated, occurrences)
                    results.append((name, restored))
                except RuntimeError as error:
                    failures.append((name, str(error), protected, translated))
            elapsed = time.perf_counter() - started
        finally:
            registry.close()
    print("LMT %s passed=%d failed=%d elapsed=%.3fs" %
          ("PASS" if not failures else "FAIL", len(results), len(failures), elapsed))
    # ASCII JSON keeps Windows terminals from disguising valid UTF-8 as mojibake.
    for name, result in results:
        print("  %s: %s" % (name, json.dumps(result, ensure_ascii=True)))
    for name, error, protected, translated in failures:
        print("  %s: %s" % (name, error))
        print("    source=%s" % json.dumps(protected, ensure_ascii=True))
        print("    result=%s" % json.dumps(translated, ensure_ascii=True))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
