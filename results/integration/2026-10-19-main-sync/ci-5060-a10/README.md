# R9 exact-head A10 completion

This archive independently reviews GitHub run 39182491046, attempt 1, at
5060ac6976b56b32647c728991e489cdee1cce9d (tree ae588699126910065c16b77d83f3ef20b53509f2).
Both A10 jobs completed successfully on 2026-10-19 UTC. Full connector-decoded
job logs and original API text are retained, including earlier incomplete snapshots.

## Executed scopes

UI workspace: 137 passed, 2 host-font tests ignored. Hepta default: 17 passed;
Hepta objective feature: 43 passed, including both real CLI SIGKILL boundaries.
The default baseline is repeated in the feature suite, so these are separate
command counts, not an aggregate of distinct tests. support/ui: 39; tests/ui
Rust contracts: 8. Python process guard, original Shell and original Objective
Shell contracts: 6, 8 and 10 respectively. Feature-off check, strict UI/A07
Clippy, four-manifest rustfmt, and committed UI lock enforcement succeeded.

Actual Weston first layouts, app layouts and cancellation passed. A subsequent
separate compositor test passed crash/restart with the same Session, a new socket
epoch and a new client first layout. It does not prove continuity of pre-crash
client windows. The Hepta page used a scripted UDS fixture. X11 mapping was
explicitly NOT VERIFIED because optional X11 tools were absent. No CJK IME,
physical GPU or Asterinas graphics qualification is claimed.

The fixed CI workflow built, packaged and replayed four native ELF files.
Artifact 12157021582 is recorded by metadata and upload digest only; its combined
binary-bearing ZIP was not downloaded, and this reviewer did not independently
rehash CI ELF bytes. See source-verification.json for this boundary.

The exact-head CodeQL and Analyze (python) checks also succeeded, in the separate
dynamic GitHub code-scanning run 39182489120. That run was outside the nine
repository workflow path predictions. Original ARM run 39182491155 remained in
progress at the retained poll02 snapshot; this archive grants it no qualification.
R8 results are not inherited. No project code or test was rerun by this reviewer.

review.json records exact groups and raw-log locations; SHA256SUMS covers every
payload except itself, and MANIFEST.json records the remaining file catalogue.
