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
    structured = dict(newest)
    structured["source"] = "Usage:\nscan - scan all\nscan <direction> - scan one\nscan help - this page"
    assert "structured_line_collapse" in audit.suspicious_reasons(structured)
    wrapped_help = dict(newest)
    wrapped_help["source"] = "Keywords are: 'example'\nThis is ordinary display-wrapped prose\nthat continues on another source line\nand should not be treated as a table."
    assert "structured_line_collapse" not in audit.suspicious_reasons(wrapped_help)
    numeric = {
        "status": "OK", "engine": "lmt_q4", "elapsed_seconds": 0.1,
        "source": "Mana: 25, Level: 31", "result": "法力：20，等級：31",
    }
    assert "numeric_value_mismatch" in audit.suspicious_reasons(numeric)
    formatted_numeric = dict(numeric)
    formatted_numeric.update({"source": "Cost: 9000000", "result": "費用：9,000,000"})
    assert "numeric_value_mismatch" not in audit.suspicious_reasons(formatted_numeric)
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
    advice = audit.repair_advice({"record": newest, "reasons": reasons})
    assert advice is None
    help_case = {
        "record": {
            "source": "Sorry, no help matches that.  Perhaps you meant:\n    races",
            "result": "", "engine": "lmt_q4", "ts": "2026-01-03T00:00:00",
        },
        "reasons": ["translation_error_or_fallback"],
    }
    advice = audit.repair_advice(help_case)
    assert advice["family"] == "help_no_match_suggestions"
    assert advice["confidence"] == "high"
    entity_pairs = audit.extract_entity_pairs(
        "Gimthen says, 'Hello.'", "金騰說：『你好。』",
    )
    assert entity_pairs[0][:3] == ("npc_name", "Gimthen", "金騰")
    arrived = audit.extract_entity_pairs("A guard has arrived.", "一名守衛已經來了。")
    assert arrived[0][:3] == ("npc_name", "A guard", "守衛")
    assert audit.extract_entity_pairs(
        "A guard has arrived.", "一名守衛從北方跑了過來。",
    ) == []
    source_variants = {
        "Gimthen says, 'Hello.'": {
            "occurrences": 2,
            "results": {
                "a": {"value": "金騰說：你好", "count": 1, "newest_ts": "2", "engines": ["lmt_q4"]},
                "b": {"value": "吉姆森說：你好", "count": 1, "newest_ts": "1", "engines": ["azure"]},
            },
        },
    }
    entity_variants = {
        ("npc_name", "gimthen"): {
            "occurrences": 2,
            "translations": {
                "a": {"value": "金騰", "count": 1, "newest_ts": "2", "engines": ["lmt_q4"]},
                "b": {"value": "吉姆森", "count": 1, "newest_ts": "1", "engines": ["azure"]},
            },
        },
    }
    consistency = audit.build_consistency_suspicions(source_variants, entity_variants)
    assert consistency[0]["kind"] == "npc_name_variation"
    assert consistency[0]["confidence"] == "high"
    assert consistency[0]["existing_guard_to_retest"] == "npc_names_or_mob_types_registry"

print("TRANSLATION_TRACE_AUDIT_OK newest_first=yes readonly=yes")
