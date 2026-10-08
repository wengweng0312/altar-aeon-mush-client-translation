"""Classify mined candidates by existing deterministic/template coverage."""

from __future__ import annotations

import argparse
import json
import re
import runpy
import sys
from pathlib import Path


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--worker", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    module = runpy.run_path(str(args.worker), run_name="translation_worker_audit")
    # runpy returns a namespace snapshot on this portable runtime.  Prime the
    # optional SQLite catalog explicitly before evaluating individual lines.
    module["load_deterministic_templates"]()
    source_report = json.loads(args.report.read_text(encoding="utf-8-sig"))
    deterministic = module["deterministic_translate"]
    semantic_match = module["semantic_event_match"]
    action_match = module["action_template_match"]
    combat_match = module["combat_template_match"]
    exact_headers = module["STRUCTURED_EXACT_HEADERS"]
    reviewed_phrase = module["reviewed_phrase_translation"]
    covered, uncovered = [], []
    for row in source_report["recurring_line_candidates"]:
        source = row["source"]
        reason = None
        if deterministic(source) is not None:
            reason = "deterministic"
        elif reviewed_phrase(source):
            reason = "phrase_glossary"
        elif semantic_match(source):
            reason = "semantic_event"
        elif action_match(source):
            reason = "action_template"
        elif combat_match(source):
            reason = "combat_template"
        elif source.strip() in exact_headers:
            reason = "structured_header"
        target = dict(row)
        if reason:
            target["coverage"] = reason
            covered.append(target)
        else:
            uncovered.append(target)
    uncovered.sort(key=lambda row: (-row["occurrences"], -row["translation_variant_count"], row["source"].lower()))
    result = {
        "covered_count": len(covered), "uncovered_count": len(uncovered),
        "covered_occurrences": sum(row["occurrences"] for row in covered),
        "uncovered_occurrences": sum(row["occurrences"] for row in uncovered),
        "covered": covered, "uncovered": uncovered,
    }
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    total_occurrences = result["covered_occurrences"] + result["uncovered_occurrences"]
    percent = (100.0 * result["covered_occurrences"] / total_occurrences) if total_occurrences else 100.0
    print("CANDIDATE_COVERAGE_OK covered=%d uncovered=%d occurrence_coverage=%.1f%%" % (
        len(covered), len(uncovered), percent,
    ))
    for row in uncovered[:100]:
        print("%5d %2d | %s" % (row["occurrences"], row["translation_variant_count"], row["source"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
