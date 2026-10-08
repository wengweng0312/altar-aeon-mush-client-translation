"""Cloud-primary sessions must translate while LMT tunes in the background."""

from pathlib import Path
import runpy


ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "src/mush-z/worlds/plugins/translation_bridge/translation_worker.py"
module = runpy.run_path(str(WORKER), run_name="cloud_lazy_lmt_test")

source = WORKER.read_text(encoding="utf-8")
run_start = source.index("def run():")
run_body = source[run_start:]
assert "if cloud_translation_candidates():" in run_body
assert "LMT-60 tuning in background" in run_body
assert "threading.Thread(" in run_body
assert "SERVER_START_THREAD.start()" in run_body
assert "SERVER_START_THREAD.join(timeout=5)" in run_body
assert "stop_candidate(ACTIVE_CANDIDATE)" in run_body

server_start = source.index("def _start_server_impl():")
server_end = source.index("def start_server():", server_start)
server_body = source[server_start:server_end]
assert "force_benchmark = FORCE_BACKEND_BENCHMARK_FILE.is_file()" in server_body
assert "allow_autotune = SERVER_ALLOW_AUTOTUNE or force_benchmark" in server_body
assert "if selection is None and not allow_autotune:" in server_body
assert "safe_default_no_benchmark" in server_body

calls = []


def fake_start():
    calls.append("start")
    module["SERVER_READY"] = True


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return b'{"content":"ok"}'


worker_globals = module["http_post"].__globals__
worker_globals["start_server"] = fake_start
worker_globals["SERVER_READY"] = False
worker_globals["SERVER_STARTING"] = False
module["urllib"].request.urlopen = lambda *_args, **_kwargs: FakeResponse()
result = module["http_post"]("/completion", {"prompt": "x"}, 1)
assert calls == ["start"]
assert result["content"] == "ok"

print("cloud lazy LMT startup regression: PASS")
