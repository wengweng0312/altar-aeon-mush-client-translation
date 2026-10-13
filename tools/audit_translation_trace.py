"""Offline newest-first audit for Alter Aeon translation trace JSONL logs.

This tool is intentionally read-only.  It never starts a model, calls a cloud
provider, edits SQLite, or changes a player log.  It produces a compact human
report plus a normalized newest-first JSONL file for deeper follow-up.
"""

from __future__ import annotations

import argparse
import atexit
import importlib.util
import json
import re
import shutil
import sys
from collections import Counter, OrderedDict
from datetime import datetime
from pathlib import Path
from urllib.request import urlopen


DEFAULT_BRIDGE = Path(r"D:\altar aeon\Mush-Z\worlds\plugins\translation_bridge")
HAN = re.compile(r"[\u3400-\u9fff]")
LATIN_WORD = re.compile(r"[A-Za-z]{2,}")
PROMPT_LEAKS = (
    "translate the following", "traditional chinese:", "english:",
    "do not add explanations", "preserve proper names",
    "將所有文字翻譯", "不要省略", "不要添加任何解釋", "保留適當的名字",
)
FUNCTIONAL_REASONS = {
    "translation_error_or_fallback", "unchanged_english", "empty_result",
    "no_chinese_result", "possible_line_collapse", "possible_under_translation",
    "possible_repetition_loop", "possible_prompt_leak",
}


def reverse_lines(path: Path, block_size: int = 128 * 1024):
    """Yield UTF-8 lines from the end of a potentially large file."""
    with path.open("rb") as stream:
        stream.seek(0, 2)
        position = stream.tell()
        remainder = b""
        while position:
            size = min(block_size, position)
            position -= size
            stream.seek(position)
            chunk = stream.read(size) + remainder
            parts = chunk.split(b"\n")
            remainder = parts[0]
            for raw in reversed(parts[1:]):
                if raw.strip():
                    yield raw.decode("utf-8", errors="replace").rstrip("\r")
        if remainder.strip():
            yield remainder.decode("utf-8", errors="replace").rstrip("\r")


def trace_files_newest_first(root: Path):
    active = root / "lmt_translation_trace.log"
    files = [active] if active.is_file() else []
    archive = root / "log_archive"
    if archive.is_dir():
        files.extend(sorted(
            archive.glob("lmt_translation_trace_*.log"),
            key=lambda item: (item.stat().st_mtime_ns, item.name),
            reverse=True,
        ))
    return files


def nonempty_lines(value: str):
    return [line.strip() for line in value.replace("\r\n", "\n").replace("\r", "\n").split("\n") if line.strip()]


def repetition_strength(value: str):
    lines = nonempty_lines(value)
    strongest = 1
    if len(lines) >= 4:
        counts = Counter(lines)
        repeated = max(counts.values(), default=1)
        if repeated >= 4 and repeated / len(lines) >= 0.45:
            strongest = max(strongest, repeated)
    sentences = [part.strip() for part in re.split(r"[.!?。！？]+", value) if len(part.strip()) >= 8]
    counts = Counter(sentences)
    return max(strongest, max(counts.values(), default=1))


def suspicious_reasons(record: dict):
    source = str(record.get("source") or "")
    result = str(record.get("result") or "")
    status = str(record.get("status") or "").upper()
    engine = str(record.get("engine") or "unknown").lower()
    error = str(record.get("error") or "")
    try:
        elapsed = float(record.get("elapsed_seconds") or 0.0)
    except (TypeError, ValueError):
        elapsed = 0.0
    reasons = []
    if status in {"ERROR", "ERR", "FALLBACK", "FAILED", "FAIL"} or error:
        reasons.append("translation_error_or_fallback")
    if source and result and source.strip() == result.strip() and LATIN_WORD.search(source):
        reasons.append("unchanged_english")
    if source and not result and status not in {"CONTROL"}:
        reasons.append("empty_result")
    if source and result and LATIN_WORD.search(source) and not HAN.search(result):
        reasons.append("no_chinese_result")
    source_lines = nonempty_lines(source)
    result_lines = nonempty_lines(result)
    if len(source_lines) >= 4 and len(result_lines) <= max(1, int(len(source_lines) * 0.34)):
        reasons.append("possible_line_collapse")
    source_compact = re.sub(r"\s+", "", source)
    result_compact = re.sub(r"\s+", "", result)
    if len(source_compact) >= 180 and len(result_compact) < max(24, int(len(source_compact) * 0.16)):
        reasons.append("possible_under_translation")
    # Repeated mobs/items are valid MUD output.  Flag only repetition that the
    # translator added or materially amplified beyond the English source.
    source_repetition = repetition_strength(source)
    result_repetition = repetition_strength(result)
    if result_repetition >= 4 and result_repetition >= source_repetition + 2:
        reasons.append("possible_repetition_loop")
    lowered = result.lower()
    if any(marker in lowered for marker in PROMPT_LEAKS):
        reasons.append("possible_prompt_leak")
    slow_limit = 5.0 if engine in {"lmt_q4", "local", "unknown"} else 3.0
    if elapsed >= slow_limit:
        reasons.append("slow_translation")
    return reasons


def markdown_text(value: str):
    value = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    return value.replace("```", "` ` `")


def write_case(stream, number: int, case: dict):
    record = case["record"]
    stream.write("\n### %d. %s\n\n" % (number, record.get("ts") or "unknown time"))
    stream.write("- Reasons: `%s`\n" % "`, `".join(case["reasons"]))
    stream.write("- Status: `%s`\n" % (record.get("status") or "unknown"))
    stream.write("- Engine/model: `%s`\n" % (record.get("engine") or "unknown"))
    stream.write("- Elapsed: `%.3f seconds`\n" % case["elapsed"])
    stream.write("- Request: `%s`\n" % (record.get("request_id") or "unknown"))
    stream.write("- Repeated occurrences: `%d`\n" % case["count"])
    if record.get("error"):
        stream.write("- Error: `%s`\n" % markdown_text(record["error"]).replace("\n", " "))
    stream.write("\nEnglish source:\n\n```text\n%s\n```\n" % markdown_text(record.get("source")))
    stream.write("\nChinese/result:\n\n```text\n%s\n```\n" % markdown_text(record.get("result")))


def repair_advice(case: dict):
    """Return a conservative repair family; never generate executable code."""
    source = str(case["record"].get("source") or "")
    rows = nonempty_lines(source)
    if rows and rows[0] == "Sorry, no help matches that.  Perhaps you meant:":
        return {
            "family": "help_no_match_suggestions", "confidence": "high",
            "strategy": "Translate the fixed header and preserve every suggested help keyword row verbatim.",
            "invariants": ["same_nonempty_line_count", "keyword_rows_byte_preserved", "no_model_required"],
        }
    if rows and (rows[0] == "You are using:" or any(" is obviously carrying:" in row for row in rows)):
        return {
            "family": "equipment_or_character_inspection", "confidence": "high",
            "strategy": "Parse slot rows and carried items, translate only semantic item fields, then reconstruct.",
            "invariants": ["slot_order_preserved", "duplicate_slots_preserved", "empty_slots_preserved"],
        }
    if rows and re.match(r"^(?:Usage|Syntax|Keywords are):", rows[0], re.I):
        return {
            "family": "help_command_layout", "confidence": "medium",
            "strategy": "Protect commands, placeholders and labels; translate descriptions as independent fields.",
            "invariants": ["commands_preserved", "placeholders_preserved", "source_order_preserved"],
        }
    if "translation_error_or_fallback" in case["reasons"]:
        return {
            "family": "unclassified_fallback", "confidence": "low",
            "strategy": "Keep English fallback and request human classification before proposing a parser.",
            "invariants": ["english_never_lost"],
        }
    return None


def write_repair_candidates(cases, run_dir: Path):
    advised = []
    for case in cases.values():
        advice = repair_advice(case)
        if advice:
            advised.append((case, advice))
    report_path = run_dir / "REPAIR_CANDIDATES.md"
    fixture_path = run_dir / "AUTO_REPAIR_FIXTURES.json"
    fixtures = []
    with report_path.open("w", encoding="utf-8", newline="\n") as report:
        report.write("# Translation Repair Candidates\n\n")
        report.write("These are non-executable proposals. Production code is never changed automatically.\n\n")
        for number, (case, advice) in enumerate(advised, 1):
            record = case["record"]
            report.write("## %d. %s | %s confidence\n\n" % (
                number, advice["family"], advice["confidence"],
            ))
            report.write("- Original time: `%s`\n" % (record.get("ts") or "unknown"))
            report.write("- Engine/model: `%s`\n" % (record.get("engine") or "unknown"))
            report.write("- Strategy: %s\n" % advice["strategy"])
            report.write("- Required invariants: `%s`\n" % "`, `".join(advice["invariants"]))
            report.write("\n```text\n%s\n```\n" % markdown_text(record.get("source")))
            fixtures.append({
                "family": advice["family"], "confidence": advice["confidence"],
                "source": record.get("source") or "", "old_result": record.get("result") or "",
                "old_reasons": case["reasons"], "required_invariants": advice["invariants"],
            })
    fixture_path.write_text(json.dumps(fixtures, ensure_ascii=False, indent=2), encoding="utf-8")
    return report_path, fixture_path, len(advised)


def lmt_server_ready(port=18082):
    try:
        with urlopen("http://127.0.0.1:%d/health" % port, timeout=2.0) as response:
            return 200 <= int(response.status) < 500
    except Exception:
        return False


def load_isolated_worker(worker_path: Path, run_dir: Path, server_already_running: bool):
    """Load production translation logic while isolating every writable file."""
    spec = importlib.util.spec_from_file_location("trace_replay_worker", worker_path)
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)
    worker.CACHE_DB = run_dir / "replay_cache.sqlite3"
    worker.CACHE_CONNECTION = None
    worker.CACHE_DISABLED = False
    worker.TRACE_LOG = run_dir / "replay_worker_trace.log"
    worker.LOG = run_dir / "replay_worker.log"
    worker.API_USAGE_FILE = run_dir / "replay_api_usage.json"
    worker.CLOUD_CONFIG = run_dir / "cloud_disabled.txt"
    worker.CLOUD_CONFIG.write_text("service=0\n", encoding="utf-8")
    worker.cloud_translation_candidates = lambda _text="": []
    worker.BACKEND_CHOICE_FILE = run_dir / "backend_choice.json"
    live_choice = worker_path.parent / "backend_choice.json"
    if live_choice.is_file():
        shutil.copyfile(live_choice, worker.BACKEND_CHOICE_FILE)
    worker.FORCE_BACKEND_BENCHMARK_FILE = run_dir / "benchmark_lmt_next_start.flag"
    worker.SERVER_ALLOW_AUTOTUNE = False
    worker.SERVER_READY = bool(server_already_running)
    return worker


def stop_replay_server(worker):
    """Stop only the llama-server process launched by this replay worker."""
    process = getattr(worker, "SERVER_PROCESS", None)
    if process is None:
        return
    try:
        process.terminate()
        process.wait(timeout=8)
    except Exception:
        try:
            process.kill()
        except Exception:
            pass


def replay_cases(cases, args, run_dir: Path):
    """Replay recent functional failures through current code and live local LMT."""
    candidates = [
        case for case in cases.values()
        if FUNCTIONAL_REASONS.intersection(case["reasons"])
    ][:args.replay_limit]
    report_path = run_dir / "LMT_REPLAY_REPORT.md"
    if not candidates:
        report_path.write_text("# LMT Replay Report\n\nNo functional candidates.\n", encoding="utf-8")
        return {"fixed": 0, "unresolved": 0, "errors": 0, "report": report_path}
    worker_path = args.worker.resolve()
    if not worker_path.is_file():
        raise RuntimeError("Replay worker not found: %s" % worker_path)
    server_was_running = lmt_server_ready()
    worker = load_isolated_worker(worker_path, run_dir, server_was_running)
    started_server = False
    if not server_was_running:
        print("Local LMT server is not running; starting an isolated replay server...")
        try:
            worker.start_server()
            started_server = True
            atexit.register(stop_replay_server, worker)
        except Exception as start_error:
            report_path.write_text(
                "# LMT Replay Report\n\nThe isolated LMT replay server could not start.\n\n"
                "```text\n%s\n```\n" % repr(start_error), encoding="utf-8",
            )
            return {"fixed": 0, "unresolved": 0, "errors": len(candidates), "report": report_path}
    config = worker.DEFAULT.copy()
    try:
        config.update(json.loads((worker_path.parent / "translation_config.json").read_text(encoding="utf-8")))
    except Exception:
        pass
    config.update({"provider": "lmt_q4", "translation_cache_enabled": True})
    results = []
    print("LMT replay: %d recent functional candidates" % len(candidates))
    for index, case in enumerate(candidates, 1):
        source = str(case["record"].get("source") or "")
        started = datetime.now()
        try:
            translated = worker.to_traditional_characters(worker.translate(source, config))
            translated = worker.normalize_npc_names(source, translated)
            current_reasons = [
                reason for reason in suspicious_reasons({
                    "status": "OK", "engine": "lmt_q4",
                    "elapsed_seconds": 0, "source": source, "result": translated,
                }) if reason in FUNCTIONAL_REASONS
            ]
            state = "unresolved" if current_reasons else "fixed"
            error = ""
        except Exception as replay_error:
            translated = ""
            current_reasons = ["translation_error_or_fallback"]
            state = "error"
            error = repr(replay_error)
        elapsed = (datetime.now() - started).total_seconds()
        results.append({
            "state": state, "source": source, "old_result": case["record"].get("result") or "",
            "new_result": translated, "old_reasons": case["reasons"],
            "new_reasons": current_reasons, "error": error, "elapsed": elapsed,
            "original_ts": case["record"].get("ts") or "unknown",
        })
        print("  [%d/%d] %s %.3fs" % (index, len(candidates), state, elapsed))
    with report_path.open("w", encoding="utf-8", newline="\n") as report:
        report.write("# LMT Replay Report\n\n")
        report.write("Current worker logic was replayed against an isolated SQLite cache. ")
        report.write("Cloud providers were disabled and the production cache/trace were not modified.\n\n")
        counts = Counter(item["state"] for item in results)
        report.write("- Fixed now: `%d`\n" % counts["fixed"])
        report.write("- Still suspicious: `%d`\n" % counts["unresolved"])
        report.write("- Replay errors: `%d`\n" % counts["error"])
        for number, item in enumerate(results, 1):
            report.write("\n## %d. %s | original %s\n\n" % (
                number, item["state"].upper(), item["original_ts"],
            ))
            report.write("- Old reasons: `%s`\n" % "`, `".join(item["old_reasons"]))
            report.write("- New reasons: `%s`\n" % "`, `".join(item["new_reasons"]))
            report.write("- Replay time: `%.3f seconds`\n" % item["elapsed"])
            if item["error"]:
                report.write("- Error: `%s`\n" % item["error"].replace("`", "'"))
            report.write("\nEnglish source:\n\n```text\n%s\n```\n" % markdown_text(item["source"]))
            report.write("\nOld result:\n\n```text\n%s\n```\n" % markdown_text(item["old_result"]))
            report.write("\nCurrent replay result:\n\n```text\n%s\n```\n" % markdown_text(item["new_result"]))
    if worker.CACHE_CONNECTION is not None:
        worker.CACHE_CONNECTION.close()
        worker.CACHE_CONNECTION = None
    if started_server:
        stop_replay_server(worker)
    return {
        "fixed": sum(item["state"] == "fixed" for item in results),
        "unresolved": sum(item["state"] == "unresolved" for item in results),
        "errors": sum(item["state"] == "error" for item in results),
        "report": report_path,
    }


def audit(args):
    root = args.trace_root.resolve()
    files = trace_files_newest_first(root)
    if not files:
        raise SystemExit("No translation trace files found under: %s" % root)
    stamp = datetime.now().strftime("run-%Y%m%d-%H%M%S")
    run_dir = args.output_root.resolve() / stamp
    run_dir.mkdir(parents=True, exist_ok=False)
    normalized_path = run_dir / "TRACE_NEWEST_FIRST.jsonl"
    report_path = run_dir / "TRANSLATION_TRACE_AUDIT_REPORT.md"
    malformed_path = run_dir / "MALFORMED_TRACE_LINES.txt"
    cases = OrderedDict()
    slowest = []
    engines = Counter()
    statuses = Counter()
    malformed = []
    scanned = 0

    print("Translation trace audit")
    print("Source: %s" % root)
    print("Files: %d" % len(files))
    print("Output: %s" % run_dir)
    with normalized_path.open("w", encoding="utf-8", newline="\n") as normalized:
        stop = False
        for file_number, path in enumerate(files, 1):
            print("[%d/%d] %s" % (file_number, len(files), path.name))
            for line in reverse_lines(path):
                try:
                    record = json.loads(line)
                except Exception as error:
                    if len(malformed) < 100:
                        malformed.append("%s: %r\n%s" % (path, error, line[:2000]))
                    continue
                scanned += 1
                record["_trace_file"] = str(path)
                normalized.write(json.dumps(record, ensure_ascii=False) + "\n")
                engine = str(record.get("engine") or "unknown")
                status = str(record.get("status") or "unknown")
                engines[engine] += 1
                statuses[status] += 1
                try:
                    elapsed = float(record.get("elapsed_seconds") or 0.0)
                except (TypeError, ValueError):
                    elapsed = 0.0
                if elapsed > 0:
                    slowest.append((elapsed, record))
                    if len(slowest) > args.slowest * 4:
                        slowest = sorted(slowest, key=lambda item: item[0], reverse=True)[:args.slowest]
                reasons = suspicious_reasons(record)
                if reasons:
                    signature = (
                        str(record.get("source") or ""), str(record.get("result") or ""),
                        tuple(reasons), engine, status,
                    )
                    if signature in cases:
                        cases[signature]["count"] += 1
                    elif len(cases) < args.max_cases:
                        cases[signature] = {
                            "record": record, "reasons": reasons,
                            "elapsed": elapsed, "count": 1,
                        }
                if scanned % 5000 == 0:
                    print("  scanned %d records; suspicious %d" % (scanned, len(cases)))
                if args.max_records and scanned >= args.max_records:
                    stop = True
                    break
            if stop:
                break

    slowest = sorted(slowest, key=lambda item: item[0], reverse=True)[:args.slowest]
    reason_counts = Counter(reason for case in cases.values() for reason in case["reasons"])
    with report_path.open("w", encoding="utf-8", newline="\n") as report:
        report.write("# Alter Aeon Translation Trace Audit\n\n")
        report.write("Generated: %s\n\n" % datetime.now().isoformat(timespec="seconds"))
        report.write("Newest records were scanned first. This was a read-only audit; no model, API, cache, or game files were changed.\n\n")
        report.write("## Summary\n\n")
        report.write("- Trace root: `%s`\n" % root)
        report.write("- Files visited: `%d`\n" % len(files))
        report.write("- Records scanned: `%d`\n" % scanned)
        report.write("- Unique suspicious cases retained: `%d`\n" % len(cases))
        report.write("- Malformed JSON lines retained: `%d`\n" % len(malformed))
        report.write("- Engine/model counts: `%s`\n" % dict(engines))
        report.write("- Status counts: `%s`\n" % dict(statuses))
        report.write("- Suspicion counts: `%s`\n" % dict(reason_counts))
        report.write("\n## Interpretation\n\n")
        report.write("Flags are candidates for human review, not automatic proof of a bug. Line collapse and repetition can be legitimate for some MUD structures.\n")
        report.write("\n## Suspicious cases, newest first\n")
        for number, case in enumerate(cases.values(), 1):
            write_case(report, number, case)
        report.write("\n## Slowest translations\n\n")
        for number, (elapsed, record) in enumerate(slowest, 1):
            report.write("%d. `%7.3f s` | `%s` | `%s` | %s\n" % (
                number, elapsed, record.get("engine") or "unknown",
                record.get("status") or "unknown",
                str(record.get("source") or "").splitlines()[0][:140],
            ))
        report.write("\n## Output files\n\n")
        report.write("- Complete normalized trace, newest first: `TRACE_NEWEST_FIRST.jsonl`\n")
        report.write("- Malformed input samples: `MALFORMED_TRACE_LINES.txt`\n")
    malformed_path.write_text("\n\n".join(malformed), encoding="utf-8")
    repair_report, repair_fixtures, repair_count = write_repair_candidates(cases, run_dir)
    latest = args.output_root.resolve() / "TRANSLATION_TRACE_AUDIT_REPORT.md"
    shutil.copyfile(report_path, latest)
    shutil.copyfile(repair_report, args.output_root.resolve() / "REPAIR_CANDIDATES.md")
    shutil.copyfile(repair_fixtures, args.output_root.resolve() / "AUTO_REPAIR_FIXTURES.json")
    replay = None
    if args.replay_lmt:
        replay = replay_cases(cases, args, run_dir)
        shutil.copyfile(replay["report"], args.output_root.resolve() / "LMT_REPLAY_REPORT.md")
    print("Completed: %d records, %d suspicious cases" % (scanned, len(cases)))
    print("Report: %s" % report_path)
    print("Latest: %s" % latest)
    print("Repair candidates: %d (%s)" % (repair_count, repair_report))
    if replay is not None:
        print("Replay: fixed=%d unresolved=%d errors=%d" % (
            replay["fixed"], replay["unresolved"], replay["errors"],
        ))
        print("Replay report: %s" % replay["report"])
    return 0


def main():
    parser = argparse.ArgumentParser(description="Audit Alter Aeon translation traces newest-first")
    parser.add_argument("--trace-root", type=Path, default=DEFAULT_BRIDGE)
    parser.add_argument(
        "--output-root", type=Path,
        default=Path(__file__).resolve().parents[1] / "analysis" / "translation-trace-audit",
    )
    parser.add_argument("--max-records", type=int, default=0, help="0 scans every record")
    parser.add_argument("--max-cases", type=int, default=1000)
    parser.add_argument("--slowest", type=int, default=100)
    parser.add_argument("--replay-lmt", action="store_true", help="replay recent functional candidates using the already-running local LMT server")
    parser.add_argument("--replay-limit", type=int, default=100)
    parser.add_argument("--worker", type=Path, default=DEFAULT_BRIDGE / "translation_worker.py")
    return audit(parser.parse_args())


if __name__ == "__main__":
    sys.exit(main())
