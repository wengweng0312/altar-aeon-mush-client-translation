"""Run a disposable LMT Chinese-to-English benchmark.

This never imports the live worker, reads its cache, or writes under Mush-Z.
It starts a separate llama-server port and always terminates that process.
"""

import argparse
import json
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.request


def request_json(url, payload=None, timeout=5):
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json; charset=UTF-8"},
        method="GET" if data is None else "POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def wait_ready(port, process, timeout=25):
    deadline = time.monotonic() + timeout
    last_error = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("llama-server exited during startup")
        try:
            # Current llama.cpp may return plain text rather than JSON here.
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1) as response:
                response.read()
            return
        except (OSError, urllib.error.URLError) as error:
            last_error = error
            time.sleep(0.2)
    raise TimeoutError("llama-server startup timeout; last health error: %r" % (last_error,))


def translation_prompt(source, style="official"):
    context = ""
    if style == "mud":
        context = (
            "The text is a player message in a fantasy MUD game. Use natural online-game English. "
            "In this context, 練功 means level up, 打 a creature means fight, 任務 means quest, "
            "and 復活 means resurrect.\n"
        )
    return context + (
        "Translate the following text from Chinese into English:\n"
        f"Chinese: {source}\n"
        "English:"
    )


def translate(port, source, protocol, timeout, prompt_style="official"):
    prompt = translation_prompt(source, prompt_style)
    common = {
        "temperature": 0.0,
        "repeat_penalty": 1.1,
        "stream": False,
    }
    if protocol == "chat":
        payload = dict(common, messages=[{"role": "user", "content": prompt}], max_tokens=96)
        result = request_json(f"http://127.0.0.1:{port}/v1/chat/completions", payload, timeout)
        output = result["choices"][0]["message"]["content"].strip()
        tokens = (result.get("usage") or {}).get("completion_tokens")
    else:
        payload = dict(common, prompt=prompt, n_predict=96, repeat_last_n=128)
        result = request_json(f"http://127.0.0.1:{port}/completion", payload, timeout)
        output = str(result.get("content") or "").strip()
        tokens = result.get("tokens_predicted")
    return output, tokens


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--backend", choices=("cpu", "vulkan"), default="cpu")
    parser.add_argument("--protocol", choices=("chat", "raw"), default="chat")
    parser.add_argument("--prompt-style", choices=("official", "mud"), default="official")
    parser.add_argument("--port", type=int, default=18083)
    parser.add_argument("--timeout", type=float, default=35)
    parser.add_argument("--startup-timeout", type=float, default=90)
    args = parser.parse_args()

    runtime = args.runtime.resolve()
    server = runtime / ("backends/vulkan" if args.backend == "vulkan" else "tools") / "llama-server.exe"
    model = runtime / "gguf/LMT-60-1.7B-Q4_K_M.gguf"
    if not server.is_file() or not model.is_file():
        raise SystemExit("runtime server or model not found")

    samples = (
        "我已經到了，你在哪呢？",
        "你現在有空嗎？",
        "我在 ZXQTERM0000QXZ 等你，快過來！",
        "有沒有人可以帶我去練功？",
        "可以幫我復活嗎？我的屍體在 ZXQTERM0000QXZ。",
        "請不要拿地上的裝備，那是我的。",
        "謝謝你，我是新玩家，還不太熟悉這個區域。",
        "你有空一起打 ZXQTERM0000QXZ 嗎？",
        "我需要 mana，等我恢復一下。",
        "抱歉，我看不懂英文，可以說簡單一點嗎？",
        "有人知道 ZXQTERM0000QXZ 怎麼走嗎？",
        "我正在做 ZXQTERM0000QXZ 的任務，需要把信交給 ZXQTERM0001QXZ。",
        "這把 sword 你要嗎？不需要的話我就 donate。",
    )
    gpu_layers = "99" if args.backend == "vulkan" else "0"
    log_path = Path.cwd() / f"mushz_lmt_zh_en_{args.backend}_{args.protocol}.log"
    command = [
        str(server), "-m", str(model), "--host", "127.0.0.1", "--port", str(args.port),
        "--ctx-size", "2048", "--parallel", "1", "--gpu-layers", gpu_layers,
        "--reasoning", "off", "--no-warmup", "--log-colors", "off",
    ]
    started = time.monotonic()
    with log_path.open("w", encoding="utf-8", errors="replace") as log:
        process = subprocess.Popen(
            command, cwd=server.parent, stdout=log, stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        try:
            wait_ready(args.port, process, args.startup_timeout)
            print(json.dumps({
                "event": "ready", "backend": args.backend, "protocol": args.protocol,
                "seconds": round(time.monotonic() - started, 3),
            }, ensure_ascii=False), flush=True)
            for source in samples:
                before = time.monotonic()
                try:
                    output, tokens = translate(args.port, source, args.protocol, args.timeout, args.prompt_style)
                    row = {
                        "source": source, "result": output, "seconds": round(time.monotonic() - before, 3),
                        "tokens": tokens,
                    }
                except Exception as error:
                    row = {
                        "source": source, "error": type(error).__name__ + ": " + str(error),
                        "seconds": round(time.monotonic() - before, 3),
                    }
                print(json.dumps(row, ensure_ascii=False), flush=True)
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


if __name__ == "__main__":
    main()
