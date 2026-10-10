"""Read-only prototype for automatic NPC identity discovery.

The prototype deliberately does not import the worker, open its SQLite cache,
or call a translation provider.  It asks a narrower question: can a name be
confirmed from a small set of reliable grammatical signals and then found in
previously unknown sentences without teaching the system every verb?
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path


STOP_NAMES = {
    "a", "an", "the", "you", "your", "he", "she", "it", "they", "we",
    "alter aeon", "dragon tooth", "iron bay", "mushclient", "nvda",
    "quest", "tip", "level", "english", "chinese", "traditional chinese",
    "enter selection", "direction",
    "someone", "rumor", "charactor",
}
TITLE_PREFIXES = {
    "captain", "elder", "lady", "lord", "mayor", "master", "mistress",
    "priest", "priestess", "doctor", "general", "king", "queen", "sir",
}
KNOWN_EVENT_WORDS = {
    "says", "tells", "asks", "whispers", "shouts", "yells", "exclaims",
    "gives", "leaves", "arrives", "assists", "follows", "joins",
}
PROPER_TOKEN = r"[A-Z][A-Za-z'’-]*"
PROPER_SEQUENCE = re.compile(r"(?<![A-Za-z])(?:%s)(?:\s+%s){0,3}(?![A-Za-z])" % (PROPER_TOKEN, PROPER_TOKEN))
TALK_TARGET = re.compile(r"\bYou try to talk to\s+(.+?)\.{3}", re.I)
COMBAT_POSSESSIVE = re.compile(
    r"\b(%s(?:\s+%s){0,2})(?:,?\s+the\s+[a-z][a-z -]{1,40})?'s\s+.{1,60}?\s+"
    r"(?:heals|annoys|scratches|hits|injures|wounds|mauls|decimates|devastates|"
    r"maims|mutilates|dismembers|disembowels|massacres|obliterates|demolishes|"
    r"destroys|annihilates)\b" % (PROPER_TOKEN, PROPER_TOKEN), re.I,
)
MAP_TARGET = re.compile(r"^\s*(%s(?:\s+%s){0,2})\s*->" % (PROPER_TOKEN, PROPER_TOKEN))
EVENT_SUBJECT = re.compile(
    r"^\s*(%s(?:\s+%s){0,3})(?:,?\s+the\s+[a-z][a-z -]{1,40})?\s+(%s)\b" %
    (PROPER_TOKEN, PROPER_TOKEN, "|".join(sorted(KNOWN_EVENT_WORDS))), re.I,
)


def clean_identity(value: str) -> str | None:
    value = re.sub(r"\s+", " ", str(value)).strip(" .,!?:;()[]{}'\"")
    value = re.sub(r"^(?:a|an|the)\s+", "", value, flags=re.I)
    value = re.sub(r",\s+the\s+.+$", "", value, flags=re.I)
    value = re.sub(r"\s+the\s+[a-z][a-z -]{1,40}$", "", value)
    parts = value.split()
    if parts and parts[0].lower() in TITLE_PREFIXES:
        parts = parts[1:]
    value = " ".join(parts).strip()
    if not value or value.lower() in STOP_NAMES:
        return None
    if not all(re.fullmatch(PROPER_TOKEN, part) for part in value.split()):
        return None
    return value


def evidence_from_line(line: str):
    """Yield (identity, variant, strong evidence) tuples."""
    seen = set()

    def emit(raw, reason):
        if reason == "map_target":
            raw = re.sub(r"^(?:N|S|E|W|NE|NW|SE|SW)\s+", "", str(raw), flags=re.I)
        identity = clean_identity(raw)
        item = (identity, str(raw).strip(), reason)
        if identity and item not in seen:
            seen.add(item)
            return item
        return None

    for pattern, reason in (
        (TALK_TARGET, "talk_target"),
        (COMBAT_POSSESSIVE, "combat_possessive"),
        (MAP_TARGET, "map_target"),
        (EVENT_SUBJECT, "event_subject"),
    ):
        for match in pattern.finditer(line):
            item = emit(match.group(1), reason)
            if item:
                yield item


def confirmed_name_mentions(line: str, confirmed: set[str]):
    """Find confirmed names in arbitrary new grammar; no verb knowledge used."""
    found = set()
    for match in PROPER_SEQUENCE.finditer(str(line)):
        identity = clean_identity(match.group(0))
        key = identity.lower() if identity else ""
        if key in confirmed:
            found.add(key)
    for identity in sorted(found, key=len, reverse=True):
        yield identity


def audit(trace: Path):
    records = []
    evidence = defaultdict(set)
    variants = defaultdict(set)
    strong_lines = defaultdict(set)
    all_source_lines = []
    with trace.open("r", encoding="utf-8-sig", errors="replace") as handle:
        for line_number, raw in enumerate(handle, 1):
            try:
                record = json.loads(raw)
            except (TypeError, ValueError):
                continue
            source = str(record.get("source", ""))
            records.append(record)
            for source_line in source.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
                if not source_line.strip():
                    continue
                all_source_lines.append((line_number, source_line))
                for identity, variant, reason in evidence_from_line(source_line):
                    key = identity.lower()
                    evidence[key].add(reason)
                    variants[key].add(variant)
                    strong_lines[key].add(line_number)

    # Candidate discovery stays broad, but automatic locking is deliberately
    # narrower.  Dialogue and map targets are direct identities; repeated
    # subjects are strong; combat possessives need a second kind of evidence.
    confirmed = {
        key for key, reasons in evidence.items()
        if ("talk_target" in reasons or "map_target" in reasons or
            ("event_subject" in reasons and len(strong_lines[key]) >= 2) or
            ("combat_possessive" in reasons and "event_subject" in reasons))
    }
    arbitrary_mentions = defaultdict(list)
    for line_number, line in all_source_lines:
        for identity in confirmed_name_mentions(line, confirmed):
            key = identity.lower()
            # Keep examples not already serving as a confirmation signal.
            if not any(found.lower() == key for found, _variant, _reason in evidence_from_line(line)):
                if len(arbitrary_mentions[key]) < 8:
                    arbitrary_mentions[key].append({"line": line_number, "source": line.strip()})

    identities = []
    for key in sorted(confirmed, key=lambda item: (-len(strong_lines[item]), item)):
        identities.append({
            "identity": key,
            "evidence": sorted(evidence[key]),
            "confirmation_lines": len(strong_lines[key]),
            "variants": sorted(variants[key]),
            "unknown_grammar_mentions": arbitrary_mentions.get(key, []),
        })
    return {
        "trace": str(trace),
        "records": len(records),
        "confirmed_identities": len(identities),
        "candidate_only_identities": len(evidence) - len(confirmed),
        "identities_with_unknown_grammar_mentions": sum(bool(item["unknown_grammar_mentions"]) for item in identities),
        "identities": identities,
    }


def render_markdown(report):
    lines = [
        "# Automatic NPC Identity Prototype Audit", "",
        "Read-only: no provider calls, cache writes, or worker changes.", "",
        "- Records: `%s`" % report["records"],
        "- Confirmed identities: `%s`" % report["confirmed_identities"],
        "- Candidate-only identities: `%s`" % report["candidate_only_identities"],
        "- Reused in grammar not needed for confirmation: `%s`" % report["identities_with_unknown_grammar_mentions"],
        "", "## Identities", "",
    ]
    for item in report["identities"]:
        lines.extend([
            "### `%s`" % item["identity"], "",
            "- Evidence: %s" % ", ".join(item["evidence"]),
            "- Confirmation lines: %s" % item["confirmation_lines"],
            "- Variants: %s" % ", ".join("`%s`" % value for value in item["variants"]),
        ])
        examples = item["unknown_grammar_mentions"]
        if examples:
            lines.append("- Unknown-grammar matches:")
            for example in examples[:4]:
                lines.append("  - trace %s: `%s`" % (example["line"], example["source"][:240]))
        lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("trace", type=Path)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--markdown", type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.trace)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.markdown.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.markdown.write_text(render_markdown(report), encoding="utf-8")
    print("NPC_IDENTITY_AUDIT_OK records=%d confirmed=%d reused_unknown_grammar=%d" % (
        report["records"], report["confirmed_identities"], report["identities_with_unknown_grammar_mentions"],
    ))


if __name__ == "__main__":
    main()
