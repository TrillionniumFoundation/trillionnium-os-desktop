# Canonical live CI source identity

`tools/verify_ci_source_identity.py --repository PATH` performs read-only Git
source binding before existing qualification code. The default repository is
the current directory. Its exact ten environment fields, role/event rules,
bounds and workflow/job catalog are in
[`ci-source-identity.v1.json`](../../contracts/ci-source-identity.v1.json).
All 44 repository-source jobs in 25 workflows invoke the guard immediately
after their original checkout. Three runner-availability jobs in two workflows
have no source checkout or source qualification and remain outside this scope.
The original checkout, run, env, profiles, thresholds and budgets remain intact.
The module-documentation integration gate admits this exact guard as its sole
preliminary command before the existing isolated validator. Its ten fields,
role, body, placement and failure propagation are closed; arbitrary prior runs,
skips and mutable environment additions remain refused.
The new helper/test/contract/doc inputs appear in each affected PR/push path list.

For a PR candidate-head role, the guard resolves only the official full
`refs/pull/N/head`, comparing it with the event head and checkout. A candidate
commit can have its ordinary number of parents; it is not a prospective merge.
Prospective roles require exactly two raw commit parents, ordered as current
official base then current pull head. The full base, pull-head and pull-merge
refs must match the event base, head and tested merge, and the tested merge must
be the checkout. A fork's same-named branch cannot replace a missing pull ref.
The canonical positive decimal PR number must also match the event full ref
and ref name. Abbreviated SHAs, signs, leading zeroes, unknown roles/events,
unknown/missing input fields and noncanonical branch fields are refused.

Push and manual source roles bind the official current full branch to the event
and checkout. Manual runs remain diagnostic and non-authoritative. No tag,
missing-ref, cached-head, caller-approved or alternate-remote fallback is
available in the CLI. The original qualification code still decides its existing
evidence role after this preliminary source check. Default action checkout on a
PR is treated as prospective even if a historical job label says “exact head”.

The production CLI fixes the official HTTPS repository URL. Live lookups run
outside the checkout with global/system Git configuration disabled, so a local
checkout URL rewrite cannot replace that URL. Each reply must be exactly one
UTF-8 line with two tab-separated fields: complete lowercase SHA and the exact
queried full ref. Git suffix-matching aliases and additional rows are refused.
The tool uses the same immutable raw commit/tree/parent snapshot before and
after lookups, hashes the raw Git commit object, disables replace objects and
requires a clean checkout and refuses assume-unchanged or skip-worktree index
flags that could hide modified tracked sources. It compares the current bytes,
file type and Git executable mode of every tracked blob with its immutable tree
object, including the Git blob object header. Parent directories are retained
without following symlinks; tracked symlink blobs bind their link text. This
also detects equal-length changes hidden by Git stat caches and restored
modification times. It never fetches, commits or changes Git refs.

The guard has one 20-second source-check budget and at most five seconds per
native Git command. Combined stdout/stderr is limited to 256 KiB per command;
selected input/ref strings are at most 1024 UTF-8 bytes. Native subprocess pipes
are drained under that budget. The tracked tree is limited to 4096 files,
16 MiB per file and 64 MiB in total, read in 64 KiB chunks under the same
20-second budget. Special files, parent symlinks, submodules and exceeded limits
are refused. These source bounds do not establish a build or installed image
limit. The child starts in its own process group; its
original leader is observed without reaping until group signals are finished,
then reaped with a bounded cleanup wait. No signal is sent after that wait.
These limits do not alter any existing 20-second product request, five-second
cleanup or qualification-operation budget. Errors print only a fixed refusal
category. Successful stdout is bounded source metadata and is not a receipt,
approval or promotion token.

[`test_ci_source_identity.py`](../../tests/test_ci_source_identity.py) executes
real private Git fixtures for fork-only refs, malformed/missing/ambiguous full
refs, three or reversed parents, live drift, candidate commits, push/manual
roles, source drift, modified sources hidden by index flags or stat caches,
executable modes, link text, FIFO and source size refusal. Native subprocess
tests exercise actual output and
timeout refusal. Local catalog mutations verify guard placement, closed fields,
trigger coverage and all original step-body hashes. Private fixture remotes
are injected through a private test interface, never through CLI configuration.
The preserved old g2-native source prefix accepted invalid source topology/live
refs in the author's private probe; no expensive qualification body was run
with those invalid inputs.

A successful result is only a bounded snapshot of sampled source facts. It
does not promise refs stay unchanged after return, cover every native/opcode or
repeated interruption window, certify the following tests, approve a release,
change product activation or establish installed/native/hardware qualification.
`promotion_authority` and `production_ready` remain false.

S07 prospective checkout now uses the exact immutable event `github.sha`, rather
than interpolating a pull-request number into a mutable checkout ref. Its
pull-request-only job condition, preliminary live merge/base/head binding and
original ordered-parent qualification body are unchanged. Manual runs cannot
select PR code through this checkout expression. The source catalog changes
only that one checkout-step hash; the original qualification run hashes remain
unchanged. `test_s07_event_checkout.py` checks this execution boundary. Hosted
CodeQL and qualification must still run on the new exact source object.

The additive authenticated-update readback workflow uses the same preliminary
closed identity guard in both exact-head and prospective-merge matrix lanes.
Its original six checkout/qualification step objects are recorded without
changing their bodies, budgets, actual OpenSSL corpus counts or claim ceiling.
The closed workflow catalog includes this source workflow explicitly.
