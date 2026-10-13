# Repair: Help no-match suggestion fallback

## Identity

- Date: 2026-10-13, Asia/Taipei
- Repair family: `help_no_match_suggestions`
- Confidence: high
- Source commit: `d6e5702 Add repair advice and fix help suggestions`
- Deployment: deployed to the local Mush-Z translation bridge
- Release: not performed by this repair

## Reproduction

The newest-first trace auditor found this real block:

```text
Sorry, no help matches that.  Perhaps you meant:
    races
    group rank grouprank rankings ratings rate
    bane weapon quarry race
    object flag artifact rare unique epic remarkable antique relic exceptional
    cleric petition celestials audience angels glory repentance
    warrior skill bloodrage blood rage
    druid skill birdcalls call birds flock songbirds magpie raven bald eagle falcon
    druid skill call legendary raptor roc phoenix thunderbird
    druid call list animals porcupine coyote boar hyena winter wolf stag black brown polar bear baboon elk ape mountain lion panther moose swarm rats bats viper
    druid salve insect repellent
```

Before repair it produced English fallback with:

```text
RuntimeError('LMT_SANITY_multiline_payload_missing')
```

## Accepted change

- Recognize the fixed no-match Help header and strict keyword-only rows.
- Translate only the fixed header.
- Preserve every suggested Help keyword row, indentation and order verbatim.
- Bypass legacy whole-block cache entries for this recognized structure.
- Do not call LMT or a cloud provider for this block.
- Teach the trace auditor to classify this family and emit a non-executable,
  high-confidence repair candidate with required invariants.

Production files changed:

- `src/mush-z/worlds/plugins/translation_bridge/translation_worker.py`
- `src/mush-z/worlds/plugins/translation_bridge/translation_worker.pyw`

Analyzer and tests changed:

- `tools/audit_translation_trace.py`
- `tools/test_translation_trace_audit.py`
- `tools/test_help_search_suggestions.py`

## Backup and hashes

Pre-deployment backup:

```text
deployment_backups/2026-10-13-help-no-match-suggestions-before/
```

Both original worker files had SHA-256:

```text
8D0CF0B0742A7AA7571DED4990AC64322844FB78400D7DA15703B21E51AD6DE5
```

Both deployed worker files had SHA-256:

```text
54D19E38B924CB421934F586476F16B499A639617739508B533FAF6230B6F64E
```

## Verification

- Static Python compilation: passed.
- Dedicated Help suggestion regression: passed.
- Full repository regression: 43 tests passed.
- Isolated replay cache: used; production SQLite was not modified.
- Cloud providers: disabled during replay.
- Before replay: fallback reproduced.
- After deployment replay: `fixed=1`, `unresolved=0`, `errors=0`.
- Current deterministic processing time in replay: 0.011 seconds.
- Analyzer-started llama-server: confirmed closed after replay.

Expected output begins with:

```text
抱歉，找不到符合的說明。你可能是指：
```

All following English Help keyword rows remain unchanged.

## Rollback

Restore only these two files from the backup directory above:

```text
translation_worker.py
translation_worker.pyw
```

Copy them back to:

```text
D:\altar aeon\Mush-Z\worlds\plugins\translation_bridge
```

Then restart MUSHclient.  No SQLite rollback and no NVDA add-on rollback are
required for this repair.
