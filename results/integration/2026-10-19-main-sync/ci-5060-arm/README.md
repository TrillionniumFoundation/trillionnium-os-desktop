# R9 5060 ARM: read-only passed, overall workflow failed

Run 39182491155 / attempt 1, job 117838018950, exact commit
5060ac6976b56b32647c728991e489cdee1cce9d (tree ae588699126910065c16b77d83f3ef20b53509f2)
ran from 2026-10-19 00:49:24 to 01:14:44 UTC and concluded FAILURE.

## Qualified and failed scopes

The original Agentd read-only gate passed eight original checks plus eight
continuous Session checks across six phases. Its five actual ARM64 ELF bindings
and upload step passed. This qualification belongs only to 5060, not to a later
main-sync candidate. The new Runtime sample clock is present in all six actual
Session/ctl snapshots; its metadata is recorded separately.

The subsequent isolated ObjectiveStart/known-run runtime log contains ten
objective checks, seven explicit submissions, three Session phases, two explicit
Session SIGKILL/reap records, and a final acceptance_pass. However, its Python
outer gate failed with `[Errno 39] Directory not empty: 'plugins'` before final
runtime-record validation and post-runtime ELF hashing. Its failed report lacks
runtime_records. The six-ELF qualification and upload were skipped. Raw runtime
success records do not override this gate failure. The three raw Objective
snapshots also contain the new clock, without granting overall qualification.

The temporary-root cleanup location follows from the preserved source/control
flow and OSError. A source-level candidate cause is normal-exit group-leader
reaping before descendant cleanup. The exact writer PID is not captured. A
separate deterministic regression/fix is required; no rmtree retry, CI rerun,
pin change or gate relaxation was performed for this review.

## Evidence

Only small artifact 12157118836 was downloaded: 1,701,840 bytes, GitHub digest
sha256:d615f6123262c95cd932a36d95aefc6f7939b18fdad2ab858e4254678d0e59a9.
All 83 ZIP members passed CRC verification. The 87 MB ELF artifact was not
downloaded and CI ELF bytes were not independently rehashed by this reviewer.
Complete connector-decoded job log, original API text, original reports,
build/runtime logs, checkout identities, exact source comparisons and 23 selected
artifact members are retained. Two small journal byte streams are encoded
losslessly in objective-journal-bytes.json, and their actual SHA is checked
against the original journal-inspection record. No production issuer, model
turn, operations dispatch, device effect, canonical intelligence, historical-run
resume, Shell pixels or target-OS graphics is qualified by this record.

A10 and both CodeQL check statuses succeeded at this same head; the final
exact-head five-check snapshot retains ARM failure. The prior A10 archive keeps
its earlier in-progress ARM snapshots unchanged. No R8 qualification is inherited.
SHA256SUMS covers every retained payload except itself; MANIFEST.json is the
byte catalogue. Verification helpers only read preserved data and fixed Git
objects; they do not execute the project or repair the failed gate.
