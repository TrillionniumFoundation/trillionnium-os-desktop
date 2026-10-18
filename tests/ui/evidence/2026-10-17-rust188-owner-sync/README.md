# Final owner integration: Rust 1.88 and Weston evidence

The complete Linux host gate, headless Weston gate, strict UI Clippy and final
lock/formatter checks all passed on the **same source commit**:
`9b13dfbcb006a7f8af7cccd338e03174df74bad5`, tree
`00923201e6550280e68a5ca662a8a3c3a165a29c`. A00's publication verification
maps this tree to remote commit
[`865ecf381dc8ddb70470ee173add9bd3b4a6a29a`](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/commit/865ecf381dc8ddb70470ee173add9bd3b4a6a29a).
The raw execution records retain their local producer SHA. This document
records local execution, not a completed GitHub Actions run.

The passing source merges the fixed A10 owner cut
`d4eeeb5e868724f9400b34e1f0c3960723ac94dd` and preserves Qian QI's concurrent
Unicode-filter commit `a7379fa9b04a4e82b6936a84170c18f418bf3525` through an
author-preserving cherry-pick. Earlier 136-test evidence remains unchanged in
[the previous evidence directory](../2026-10-17-rust188-weston/README.md),
with its original source qualification. This final run executes **137 Rust
tests** on the newer combined source.

## Executed results

| Attempt | Producer | Exit | Result |
| --- | --- | ---: | --- |
| `check-host-01` | `f62731f` | 101 | Rust build passed; two real Session spawn tests returned EACCES. The EXIT formatter hook also recorded a real formatting difference. |
| `check-host-02` | `9b13dfb` | 0 | Complete Rust host gate, 137 tests, actual socket/UID probes, packaging and ELF replay passed after preserving and rebuilding the affected cache artifact. |
| `weston-01` | `9b13dfb` | 0 | Shell and application layouts, fresh Hepta-page projection, owned compositor crash/restart and observed cancellation passed. |
| `clippy-01` | `9b13dfb` | 0 | UI workspace/all-targets Clippy passed with `--locked --offline -- -D warnings`. |
| `final-check-01` | `9b13dfb` | 0 | All four formatter checks, four committed unchanged locks, 332-package offline metadata, empty root README and clean source tree passed. |

The 137 tests comprise 73 in the UI workspace, 17 in the separate A07 observer
crate, 39 in the host boundary models and 8 in the UI contracts. None failed
or were ignored in the passing run. The compiler was **Rust 1.88.0**
(`6b00bc3880198600130e1cf62b8f8a93494488cc`) and the compositor was
**Weston 13.0.0** on Linux `x86_64-unknown-linux-gnu`.

The actual host probes additionally verified both directions of SO_PEERCRED
refusal, continued same-UID service and owned Session teardown. A forged
cross-UID server could neither deliver its fabricated Snapshot nor receive
even the first CLI request byte. Eight malformed IPC frames were refused
before the first legitimate task consumed ID 1; the test then observed the
real owned child's outcome. The full log retains the container's sudo audit
warnings together with the successful checked UID assertions.

## Integration decisions exercised by this run

The Shell offers an explicit fresh window only for a Running task with a
nonzero PID and an already observed first layout. Unknown, partial, cancelling
or otherwise uncertain processes cannot use that shortcut. The Hepta page,
its explicit navigation/layout marker, shared Session projection and immutable
spawn/PID source identity remain intact.

The author's metadata filter strips control characters, bidi overrides and
isolates, direction markers and Unicode line separators before the UTF-8 byte
limit. Its new test also retains ordinary Chinese, Arabic and Emoji text.
This is display-data handling; it does not create permissions or establish
actual font/IME acceptance.

The merged gate retains custom `CARGO_TARGET_DIR` handling and checks every
Bash script individually. The new forged-server readiness check uses the
already-required sudo only to inspect its own nobody-owned 0700 runtime path.
The cross-UID cleanup continues its failure path if a child disappears between
the `/proc` existence check and metadata read, so `set -e` cannot abandon
cleanup early. The strict Cancel probe combines both branches' safeguards:
matching Session/task/PID, a nonterminal acknowledgement, and independently
observed termination or the exact already-exited failure case.

## Preserved first failure and cache recovery

[check-host-01/stdout-stderr.log](check-host-01/stdout-stderr.log) records
the two real `PermissionDenied` spawn failures. Later
[binary metadata](check-host-01/binary-mode-diagnosis.json) found the cached
Session ELF at mode 0644. Its recorded ctime is later than the failed gate's
finish; that timestamp does **not** establish the initial permission-change
time or identify an actor. Source review did not find a path that changes the
real Session ELF's permissions. The permission-mutation cause remains
**unknown**.

The affected ELF's original bytes and mode were retained separately. The
[quarantine operation](check-host-01/quarantine-operation.json) then removed
only its two confirmed links from the disposable Cargo target cache. No
`chmod` was used to make the gate pass. Cargo genuinely rebuilt the artifact
before `check-host-02`; its
[independent mode trace](check-host-02/session-artifact-mode.jsonl) records
the absent path followed by a fresh inode at mode 0755. No later transition
was observed during the complete passing gate and its six-second follow-up.

The rebuilt Session bytes are identical to the preserved non-executable ELF:
SHA-256 `3d52f8c3d61c81975a13f518810d4170e84c2c28a070684e91014567764d39c5`.
All four binaries were still executable in the final check. These observations
support the successful rebuild/retest outcome; they do not invent a cause for
the earlier permission change.

The same first attempt also preserved
[Rustfmt's exact patch](check-host-01/a10/rustfmt.patch): a line wrap in the
author-added test string. That formatting-only change was committed in
`9b13dfb` before the final full gate was rerun.

## What the Weston and Hepta evidence establishes

[The Hepta page receipt](weston-01/logs/hepta-layout/evidence.json) binds the
actual Rust Session and Shell hashes to a completed, fresh Hepta page layout.
Session PID 528270 supplied Shell PID 528273 with an Observed projection of
the explicit scripted fixture PID 528269. It carried AgentId
`11111111-1111-4111-8111-111111111111`, spawn generation 7, running current
generation 8 and sample time `1792236957652` Unix milliseconds. A generic
Conversation first-frame marker cannot satisfy this probe.

The separate [Session disconnection probe](check-host-02/a10/session-observer-probe.json)
again observes the fixture, stops it, and requires a Stale projection retaining
the same last observation while the Session remains responsive to host actions.
The compositor test separately verifies the same Session across an owned
Weston restart and a newly launched client's actual layout. Its old client
failed; prior surface continuity is not claimed.

The scope is deliberately recorded in the raw evidence:

- The Hepta peer is a **scripted protocol fixture**. Original upstream Agentd,
  authenticated objective submission and device effects were not exercised.
- [Weston output](weston-01/logs/weston.log) explicitly uses a **no-op
  renderer**. Completed egui widget layout is not a screenshot, compositor
  pixel presentation, physical GPU result or monitor-mapping test.
- [Shell stderr](weston-01/logs/hepta-layout/shell.stderr.log) reports **no
  supported CJK font**. The Unicode test does not qualify visible glyphs or
  a live candidate/preedit input flow.
- The optional X11 stage reported **NOT VERIFIED** because its tools were
  unavailable. Inherited owner X11 evidence remains bound to that owner's
  earlier run, not this combined source.
- Target Rust-kernel UI, Android/mobile runtime and WASM were not run. Host
  models that describe Android buffers/input do not establish device execution.

## Reproduction and preservation

Use Rust 1.88.0 and the Linux dependencies in `.github/workflows/a10-host.yml`.
From the repository root, with an appropriate private artifact directory:

```sh
RUSTUP_TOOLCHAIN=1.88.0 bash tests/ui/check-host.sh
RUSTUP_TOOLCHAIN=1.88.0 bash tests/ui/headless-weston.sh
cargo +1.88.0 clippy --manifest-path ui/Cargo.toml --workspace --all-targets --locked --offline -- -D warnings
cargo +1.88.0 metadata --manifest-path ui/Cargo.toml --locked --offline --format-version 1
```

The complete commands, wrapper environment, producer trees, timestamps and
individual exit statuses are retained in each attempt's `execution.json` and
[runtime/run-host-rust.py.txt](runtime/run-host-rust.py.txt).
[summary.json](summary.json) gives the source/publication mapping, counts,
failure qualification, checksums and unverified capabilities.

[raw-artifacts.json](raw-artifacts.json) indexes **36 byte-identical raw
copies**, their original paths, lengths and SHA-256 values.
[RAW_SHA256SUMS](RAW_SHA256SUMS) verifies the committed copies. Original log
whitespace and EOF blank lines were retained, including the failed run and
its formatter patch. No previous evidence was rewritten.

The same index records the separately retained original failed ELF and the
new passing binary archive. The archive is 16,396,183 bytes, built and replayed
on `9b13dfb`, with SHA-256
`1d50c66dc4c8dbc5cee33e86762788afabe779b21ec8f2bf9be3f0c9231e7bb6`.
Its checksum and full replay output are committed here; the large archive
and failed ELF originals remain at the exact paths in the index.
