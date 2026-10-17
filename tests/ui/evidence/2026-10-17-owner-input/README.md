# Native host ownership and focused-input evidence — 2026-10-17

The integrated Rust UI workspace built successfully, the runtime-ownership
script completed under a real non-root caller, and **four focused Rust tests**
passed. The same committed source also passed workspace/all-targets Clippy
with `-D warnings` and the final formatter check. This archive preserves the
earlier compiler failure, formatter failure and non-root script failure as
separate results.

The qualification is Linux host build, Session UID checks and synthetic egui
focused-input behavior. These records do not execute a full `check-host.sh`
run, real IME input, new compositor screenshots, original Agentd, authenticated
Hepta objectives, Asterinas or physical-device acceptance. Historical 137-test
and CJK screenshot receipts retain their own original source identities.

## Exact source and artifact identity

| Record | Source binding |
| --- | --- |
| Compiler failure | Local `b04a9e5ca7acd78272ddea325e752a7d6b252c9b`, tree `2af369506b7862e852fa9dedbb6a804425c72ec3` |
| Successful build, Session used by both script cases, and four strict-check steps | Local `35f379101c0863027e971ccb91faf8da71cf929c`, tree `48433c4f1e55de53e8c298193765949996eb18a0` |
| Published equivalent of that successful source | [`1974d9a94037440da358253e1f449b395daa4b64`](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/commit/1974d9a94037440da358253e1f449b395daa4b64); the immutable GitHub Git commit API independently returned the exact same complete tree `48433c4f1e55de53e8c298193765949996eb18a0` |
| Old runtime-owner script | Owner `45552fbd8f79ea713509908ac4b08a3fd44a95bc`, Git blob `23ae461b09420c29df02ee7e3743682fa2f58259` |
| Fixed runtime-owner script | `35f3791`, Git blob `45c70ebf1fb26b03db6addf33ab1679b93530fc6` |
| Precommit formatting sequence | The receipt records HEAD `b04a9e5` before commit `35f3791`. It describes the development worktree; it does not attest that each intermediate formatter input was a clean committed tree. The later strict formatter check is bound to committed `35f3791`. |

The successful build used Rust 1.88.0, a separately seeded target, one Cargo
build job, `--locked --offline`, disabled incremental compilation and debug
information disabled for dev/test profiles. It reused dependency artifacts;
the 5.60-second result is a warm workspace build, not a cold dependency-build
measurement. The original helpers retain the exact environment settings.

| Production ELF recorded after the successful workspace build | Bytes | SHA256 |
| --- | ---: | --- |
| `trill-shell` | 24,153,992 | `81e9bcbf79c4060c3047ad0c80df711bfd855f2f47c3900522927d37404d776f` |
| `trill-session` | 3,527,808 | `5c29cfd7f11455000d7c3d9c0cc2c58fb7fe8761ab326da34c794d0f3481924f` |
| `trill-ctl` | 1,494,736 | `920093314640ad1dd721425ec78457f4ca74c83f9c1a0a878d4ddfee4924a882` |
| `trill-app-window` | 22,627,904 | `08c3bbe84b5d6e773f367f9751a1432eaee327bf45a5b172150f34f165342510` |

An independent read-only `sha256sum` of all four production ELFs in the original
elevated build namespace matched these recorded hashes. The ordinary sandbox
could not see that namespace's `/dev/shm` paths; that visibility difference is
not evidence of deletion. ELF files and dependency caches are not included in
this source-evidence archive.

## Preserved compiler and formatter failures

The [first build receipt](build-before/receipt.json) and
[complete compiler log](build-before/cargo-build.log) record exit **101** from
the real `b04a9e5` workspace build. The three E0433 errors occur at Session's
new runtime/subdirectory/lock UID fences: its Linux production scope lacked the
`trill_ui_core::host_peer` module import. A test-only import could not satisfy
those production references.

Commit `35f3791` restores the Linux production import and formats the new
owner keyboard regression. The [successful build receipt](build-after/receipt.json)
and [raw log](build-after/cargo-build.log) record exit **0**, with Cargo's
`Finished dev profile ... in 5.60s` line. The source fix preserves the actual
UID checks and their rejection semantics.

The independent [precommit formatter receipt](format/receipt.json) retains
three operations: check-before **1**, formatter apply **0**, check-after **0**.
[check_before.log](format/check_before.log) contains the exact Shell formatting
diff. The zero-byte [apply.log](format/apply.log) and
[check_after.log](format/check_after.log) are preserved. These development
operations are not relabelled as a clean-commit acceptance run. The subsequent
committed-source formatter success appears in the strict-check receipt below.

## Actual non-root caller, with the same new Session ELF in both cases

The [runtime receipt](runtime-owner/receipt.json) records an existing `vscode`
caller with UID **1000**. Both raw console logs contain the actual `id -u`
output `1000`. The harness uses the existing noninteractive sudo capability;
it does not change sudo policy, create an account or configure another
authorization route.

Both script attempts execute the **same `35f3791` Session ELF**, copied with its
hash checked before launch. The Session intentionally runs with effective UID
0 inside disposable private fixtures, allowing the test to detect when mode
bits alone would let root enter another UID's directory. This comparison
isolates the old and fixed test scripts. It is not a comparison between an old
owner Session binary and a new Session binary.

| Attempt | Raw evidence | Actual result |
| --- | --- | --- |
| Old owner script `45552fbd` | [script](runtime-owner/before/executed-script.sh), [receipt](runtime-owner/before/receipt.json), [console](runtime-owner/before/console.log) | **RED, exit 1.** The first foreign-runtime rejection succeeds, then the non-root script cannot create `foreign_subdir/trillionnium-ui` after changing its parent to root-owned `0700`; the original console says `Permission denied`. |
| Fixed script `35f3791` | [script](runtime-owner/after/executed-script.sh), [receipt](runtime-owner/after/receipt.json), [console](runtime-owner/after/console.log) | **GREEN, exit 0.** The script creates children before restricting their parents and uses the existing sudo route to inspect protected paths. All three UID refusals and the positive bind complete. |

The fixed script's original fixture logs provide separate evidence for each
boundary:

- [Foreign runtime](runtime-owner/after/foreign_runtime.log):
  `XDG_RUNTIME_DIR owner UID differs from Session effective UID`.
- [Foreign child directory](runtime-owner/after/foreign_subdir.log):
  `UI socket directory owner UID differs from Session effective UID`.
- [Foreign lock](runtime-owner/after/foreign_lock.log):
  `session.lock owner UID differs from Session effective UID`.
- [Same-UID positive](runtime-owner/after/owned.log): the actual Rust Session
  reports PID 561858 and its disposable private Unix socket. Script success
  additionally requires timeout status 124, an actual socket and mode `0600`.

The old script's [first fixture log](runtime-owner/before/foreign_runtime.log)
is retained too. The collector copies fixture log bytes while the original
script runs; it does not rewrite that script or remove its cleanup trap. Both
archived scripts are byte-identical to their recorded Git blobs. The complete
raw [collector helper](helpers/test-runtime-owner-r5.py) shows this behavior.
The final runtime receipt records `fixture_directories_remaining: []`.

The repeated `sudo: unable to send audit message: Operation not permitted`
warnings remain in the original logs. The command outcomes, actual UID line
and Session diagnostics establish that the requested sudo operations executed;
the audit-message warning is not relabelled as a command failure or removed
from the record.

The reviewed [host aggregator at the published source](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/1974d9a94037440da358253e1f449b395daa4b64/tests/ui/check-host.sh)
passes the resolved `$ui_binaries` to this script and includes it in the
per-file `bash -n` loop. Those integration lines were reviewed; the entire
aggregator was not rerun by this evidence slice.

## Strict checks: four actual focused tests

All four steps in [strict-checks/receipt.json](strict-checks/receipt.json)
completed on `35f3791` with exit **0** between 13:37:30 and 13:37:38 UTC.

| Step | Actual command scope | Result |
| --- | --- | --- |
| [Clippy](strict-checks/clippy.log) | `cargo clippy --manifest-path ui/Cargo.toml --workspace --all-targets --locked --offline -- -D warnings` | Passed; Cargo records 3.28s. |
| [Shell focused tests](strict-checks/shell_focused.log) | `cargo test --manifest-path ui/Cargo.toml -p trill-shell --bin trill-shell --locked --offline focused_ -- --nocapture` | **3 passed, 0 failed, 0 ignored, 25 filtered out.** |
| [AppWindow focused test](strict-checks/app_focused.log) | `cargo test --manifest-path ui/Cargo.toml -p trill-app-window --bin trill-app-window --locked --offline focused_run_button -- --nocapture` | **1 passed, 0 failed, 0 ignored, 11 filtered out.** |
| [Formatter](strict-checks/fmt.log) | `cargo fmt --manifest-path ui/Cargo.toml --all --check` | Passed; original output is zero bytes. |

The three Shell tests are
`keyboard_focused_host_action_cannot_fake_a_primary_pointer_click`,
`synthetic_chinese_ime_commit_uses_focused_text_edit` and
`focused_draft_file_buttons_ignore_keyboard_candidate_confirmation`.
AppWindow runs `focused_run_button_enter_cannot_invent_a_pointer_click`.
These exercise synthetic egui focus/commit and primary-pointer rules. They
do not exercise a real XIM, IBus, Wayland text-input service or physical seat.
Filtered-out tests are not counted as passed, and this total is not a rerun of
the historical 137-test suite.

## Resources and explicit cleanup

[ui-r5-target.json](environment/ui-r5-target.json) records copying 2,679
dependency-cache files, totalling 798,898,890 bytes, into a newly allocated
private target. The [preparation helper](helpers/prepare-ui-r5.py) uses ordinary
copies and refuses unexpected symlinks. It does not hard-link or mutate the
earlier target. The build helpers retain their one-job, deadline and resource
stop settings. Their shared-cgroup memory samples are not per-process peaks;
the 7 GiB field is a configured stop threshold. The `minimum_free_bytes`
fields are configured reserves, separate from the actual recorded free-space
samples.

After the four strict steps ended, the separate
[cleanup receipt](environment/ui-r5-cleanup.json) records removal of exactly
two completed test executables: the Shell test binary (8,134,024 bytes) and
AppWindow test binary (7,332,072 bytes), with their SHA256 values preserved.
Recorded free space increased from 93,728,768 to 109,199,360 bytes. The four
production ELFs and older caches remained intact. This later receipt leaves
the original strict-check receipt unchanged and explains the later absence
of those two test executables.

## Archive integrity and replay information

[raw-artifacts.json](raw-artifacts.json) lists **33 original files, 60,612
bytes**, with each archive path, original path, byte length and SHA256.
[RAW_SHA256SUMS](RAW_SHA256SUMS) can be checked from this directory using
`sha256sum -c RAW_SHA256SUMS`. All raw files were copied byte for byte,
including empty logs and trailing blank lines. [summary.json](summary.json)
records the source mapping, test denominators, source-blob identities and
qualification boundaries. No build or test was rerun to create this archive.

The full staged `git diff --check` reports exit 2 only for the original blank
lines at EOF in `strict-checks/app_focused.log` and
`strict-checks/shell_focused.log`. Those original bytes are retained for
integrity. The separately checked authored README, summary and integrity
indexes have no whitespace diagnostics.

The six original files under `helpers/` retain the exact execution logic for
target preparation, failed/successful builds, non-root collection, strict
checks and the formatter toolchain wrapper. They contain task-specific paths
and UID assumptions. A replay requires deliberately prepared fresh paths,
the recorded toolchain and the corresponding immutable source; the helpers
are preserved execution records, not portable installers. Their shared
`ChildGroup` dependency is the versioned
[`tests/integration/hepta/run_original_agentd.py` at the tested source](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/1974d9a94037440da358253e1f449b395daa4b64/tests/integration/hepta/run_original_agentd.py).
Its blob/hash is recorded in `summary.json`. Using that process-cleanup helper
does not run or qualify original Agentd.

The evidence commit follows the tested code. It adds only this archive and
does not change the source identities, results or timestamps inside the
original receipts.
