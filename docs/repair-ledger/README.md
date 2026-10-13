# Translation Repair Ledger

This directory is the permanent rollback record for accepted automated or
semi-automated translation repairs.  Analysis output under `analysis/` is
temporary and ignored by Git; accepted repairs must also have a ledger entry
here.

Every entry records:

- the real trace case that reproduced the problem;
- the failure before the change and the result after isolated replay;
- every production file changed;
- the pre-deployment backup and SHA-256 hashes;
- regression tests and replay results;
- deployment state and the source commit;
- exact rollback scope.

The analyzer may propose candidates and fixtures, but it must never edit or
deploy production source on its own.  A reviewed change is deployed only after
its isolated regression passes.  Rollback restores only the files named in the
entry, never the entire Mush-Z installation.
