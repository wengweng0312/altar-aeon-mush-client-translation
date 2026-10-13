"""Isolation regression for the newest-first read-only trace auditor."""

from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUBJECT = ROOT / "tools/audit_translation_trace.py"
SPEC = importlib.util.spec_from_file_location("translation_trace_audit", SUBJECT)
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


with tempfile.TemporaryDirectory(dir=ROOT / ".test-temp") as temporary:
    bridge = Path(temporary) / "bridge"
    archive = bridge / "log_archive"
    archive.mkdir(parents=True)
    old = {
        "ts": "2026-01-01T00:00:00", "status": "OK", "engine": "lmt_q4",
        "elapsed_seconds": 0.5, "source": "Old sentence.", "result": "舊句子。",
    }
    newest = {
        "ts": "2026-01-02T00:00:00", "status": "OK", "engine": "lmt_q4",
        "elapsed_seconds": 6.5,
        "source": "Title\nFirst long source line without punctuation\nSecond long source line without punctuation\nThird long source line.",
        "result": "只剩一行。",
    }
    (archive / "lmt_translation_trace_20260101.log").write_text(
        json.dumps(old, ensure_ascii=False) + "\n", encoding="utf-8",
    )
    (bridge / "lmt_translation_trace.log").write_text(
        json.dumps(newest, ensure_ascii=False) + "\n", encoding="utf-8",
    )
    files = audit.trace_files_newest_first(bridge)
    assert files[0].name == "lmt_translation_trace.log"
    assert json.loads(next(audit.reverse_lines(files[0])))["ts"] == newest["ts"]
    reasons = audit.suspicious_reasons(newest)
    assert "possible_line_collapse" in reasons
    assert "slow_translation" in reasons
    assert audit.suspicious_reasons(old) == []
    legitimate_repeats = {
        "status": "OK", "engine": "lmt_q4", "elapsed_seconds": 0.5,
        "source": "\n".join(["A chair is here."] * 5),
        "result": "\n".join(["一把椅子在這裡。"] * 5),
    }
    assert "possible_repetition_loop" not in audit.suspicious_reasons(legitimate_repeats)
    generated_loop = dict(legitimate_repeats)
    generated_loop["source"] = "A chair is here."
    assert "possible_repetition_loop" in audit.suspicious_reasons(generated_loop)
    assert audit.FUNCTIONAL_REASONS.intersection(reasons)

print("TRANSLATION_TRACE_AUDIT_OK newest_first=yes readonly=yes")
