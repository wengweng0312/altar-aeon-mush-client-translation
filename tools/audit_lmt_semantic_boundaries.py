"""Offline audit of semantic-boundary preservation in LMT trace records.

This tool never calls a translation provider and never writes the player cache.
It reuses the production recognizers only to distinguish existing structured
coverage from conservative candidates that deserve fixture review.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "src/mush-z/worlds/plugins/translation_bridge/translation_worker.py"


def load_worker():
    spec = importlib.util.spec_from_file_location("semantic_boundary_audit_worker", WORKER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def rows(value: str) -> list[str]:
    return [line.strip() for line in str(value).replace("\r\n", "\n").replace("\r", "\n").split("\n") if line.strip()]


def existing_route(worker, source: str) -> str:
    """Return the first important production route that already owns source."""
    checks = (
        ("quest_list", worker.is_quest_list_block),
        ("quest_structured", worker.is_quest_structured_block),
        ("wrapped_dialogue", worker.is_wrapped_dialogue_block),
        ("semantic_events", worker.is_semantic_event_block),
        ("action_templates", worker.is_action_template_block),
        ("combat_templates", worker.is_combat_template_block),
        ("room_preview", worker.is_room_preview_block),
        ("quest_information", worker.is_quest_information_block),
        ("character_status", worker.is_character_status_block),
        ("skill_help", worker.is_skill_help_detail),
        ("room_with_doors", worker.is_room_with_doors),
        ("tip", worker.is_tip_block),
        ("syntax_help", worker.is_syntax_help_block),
        ("book", worker.is_book_text_block),
        ("mobs", worker.is_mobs_in_room_listing),
        ("scan", worker.is_scan_listing),
        ("nearby_map", worker.is_nearby_map_listing),
        ("nearby_directions", worker.is_nearby_direction_listing),
        ("job_list", worker.is_job_list_block),
        ("class_skills", worker.is_class_skill_table),
        ("practice", worker.is_practice_table),
        ("library", worker.is_library_catalog),
        ("directions", worker.is_direction_listing),
        ("numeric_report", worker.is_numeric_report_block),
        ("repeated_rows", worker.has_repeated_source_lines),
        ("mixed_deterministic", worker.has_deterministic_lines),
        ("trailing_rows", worker.has_trailing_independent_rows),
        ("room_prose", worker.is_room_prose_candidate),
    )
    for name, check in checks:
        try:
            if check(source):
                return name
        except Exception:
            continue
    return "generic"


def looks_contextual(worker, source: str) -> tuple[bool, str]:
    source_rows = rows(source)
    if worker.room_title_index(source_rows) >= 0:
        return True, "room_title_or_wrapped_room"
    if re.search(r"\b(?:says|asks|tells|exclaims|shouts|whispers),?\s*['\"]", source, re.I):
        return True, "dialogue"
    if re.search(r"^(?:Quest Name:|Current goal|Previous goal|General Quest Info:|Keywords are:|Usage:)", source, re.I | re.M):
        return True, "quest_or_help"
    if any(line and not re.search(r"[.!?]['\")\]]*$", line) for line in source_rows[:-1]):
        return True, "terminal_wrapping_or_incomplete_row"
    return False, ""


def conservative_event_candidate(worker, source: str) -> tuple[bool, str]:
    """Identify review candidates, never production-safe rules."""
    source_rows = rows(source)
    if not 2 <= len(source_rows) <= 25:
        return False, "row_count"
    contextual, reason = looks_contextual(worker, source)
    if contextual:
        return False, reason
    eventish = re.compile(
        r"^(?:You\b|Your\b|\+\d|\-\d|\(notify\)|[^.]{1,100}\s+(?:is DEAD|has arrived|leaves|flies|walks|runs|departs)\b)",
        re.I,
    )
    if not all(eventish.search(line) for line in source_rows):
        return False, "not_all_event_shaped"
    return True, "complete_event_shaped_rows"


def clipped(value: str, limit: int = 1200) -> str:
    value = str(value)
    return value if len(value) <= limit else value[:limit] + "\n...[truncated]"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("trace", type=Path)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--markdown", type=Path, required=True)
    parser.add_argument("--examples", type=int, default=8)
    args = parser.parse_args()

    worker = load_worker()
    totals = Counter()
    routes = Counter()
    candidate_reasons = Counter()
    examples = defaultdict(list)

    with args.trace.open("r", encoding="utf-8-sig", errors="replace") as handle:
        for line_number, raw in enumerate(handle, 1):
            try:
                record = json.loads(raw)
            except (TypeError, ValueError):
                totals["invalid_json"] += 1
                continue
            totals["records"] += 1
            if record.get("status") != "OK" or "lmt_q4" not in str(record.get("engine", "")):
                continue
            totals["lmt_ok"] += 1
            source = str(record.get("source", ""))
            result = str(record.get("result", ""))
            source_rows, result_rows = rows(source), rows(result)
            if len(source_rows) < 2:
                continue
            totals["lmt_multiline"] += 1
            route = existing_route(worker, source)
            routes[route] += 1
            if len(source_rows) != len(result_rows):
                totals["physical_line_mismatch"] += 1
            source_units = worker.semantic_display_chunks(source)
            result_units = worker.semantic_sentence_chunks(result)
            # A translated row may legitimately end in a Chinese ellipsis or
            # another non-sentence terminator.  Physical rows still preserve
            # its boundary, so use the stronger of physical and sentence
            # evidence instead of reporting a false collapse.
            preserved_result_units = max(len(result_rows), len(result_units))
            if len(source_units) >= 2 and preserved_result_units < len(source_units):
                totals["possible_semantic_collapse"] += 1
                if len(examples["possible_semantic_collapse"]) < args.examples:
                    examples["possible_semantic_collapse"].append({
                        "line": line_number, "timestamp": record.get("ts", ""), "route": route,
                        "source_units": len(source_units),
                        "result_units": preserved_result_units,
                        "source": clipped(source), "result": clipped(result),
                    })
            if route != "generic":
                totals["already_owned_by_existing_route"] += 1
                continue
            contextual, contextual_reason = looks_contextual(worker, source)
            if contextual:
                totals["generic_contextual"] += 1
                candidate_reasons[contextual_reason] += 1
                continue
            candidate, reason = conservative_event_candidate(worker, source)
            candidate_reasons[reason] += 1
            if candidate:
                totals["new_safe_split_candidates"] += 1
                if len(examples["new_safe_split_candidates"]) < args.examples:
                    examples["new_safe_split_candidates"].append({
                        "line": line_number, "timestamp": record.get("ts", ""), "route": route,
                        "source_rows": len(source_rows), "result_rows": len(result_rows),
                        "source": clipped(source), "result": clipped(result),
                    })
            else:
                totals["generic_opaque"] += 1

    report = {
        "schema_version": 1,
        "trace": str(args.trace),
        "filter": "status=OK and engine contains lmt_q4",
        "totals": dict(totals),
        "existing_routes": dict(routes.most_common()),
        "candidate_reasons": dict(candidate_reasons.most_common()),
        "examples": dict(examples),
        "warning": "Candidates require human review and fixtures; this audit makes no production decisions.",
    }
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.markdown.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    markdown = [
        "# LMT Semantic Boundary Offline Audit",
        "",
        "This report is observation-only. It made no provider calls and changed no cache.",
        "",
        "## Totals",
        "",
    ]
    markdown.extend("- `%s`: %s" % item for item in totals.most_common())
    markdown.extend(["", "## Existing production routes", ""])
    markdown.extend("- `%s`: %s" % item for item in routes.most_common())
    markdown.extend(["", "## Candidate reasons", ""])
    markdown.extend("- `%s`: %s" % item for item in candidate_reasons.most_common())
    for category, values in examples.items():
        markdown.extend(["", "## Examples: %s" % category, ""])
        for index, example in enumerate(values, 1):
            markdown.extend([
                "### %d. %s; trace line %s; route `%s`" % (
                    index, example.get("timestamp") or "unknown time", example["line"], example["route"]
                ),
                "", "Source:", "", "```text", example["source"], "```",
                "", "Result:", "", "```text", example["result"], "```", "",
            ])
    args.markdown.write_text("\n".join(markdown), encoding="utf-8")
    print("LMT_SEMANTIC_AUDIT_OK " + json.dumps(dict(totals), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
