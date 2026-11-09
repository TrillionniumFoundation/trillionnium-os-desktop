# Pocket4 application runtime entry closeout

This capsule contains a reviewable source implementation, verified host-process
controls, and an independently pinned Firefox business-contract successor.
It has not been deployed. No Android application has been qualified by this
work: **0/42 runtime accepted; production_ready=false; runtime_qualified=false**.

## Source and integration

The final private source commit is
`4e16058cc0f6de83fabae68736dad7eb91edbc47`, parent
`d88c3dc642b9484ddb7e84c812d6ed0dcfb5899d`, tree
`2b10cb8d4eb6fa1a25e8a0f4c4e0cbe30bfb3255`.
The complete narrow patch is relative to
`b4dc3b49ce29e706efca0ba5a7c775864d9b54b8`. Its SHA-256 is
`189ed298dd152ee93db66c2a655872cc863403c4d6309a5c04a61d40c51c24ad`.
The source worktree was clean after committing. `source-publication.json`
identifies all 11 changed source/document files and the two unchanged
CPU-placement dependency sources needed by the isolated CI harness.

The existing Rust applications binary now has real installed-package inspection
and a pinned per-app runtime-plan entry. The daemon reads dynamic PM UID,
version and the complete installed APK byte set, binds each observation to the
actual host/framework generation, and can invoke one reviewed public HTTPS
fixture through Firefox's actual implicit Android resolver. The dispatcher
retains every selected row and separates blocked, unsupported and partial
observations. All common and business acceptance gates remain pending.

The transport binds proc directories, PIDFDs, namespace FDs, root and cwd. It
does not enter by a reused numeric PID. Every command joins its own cgroup
before exec, uses bounded nonblocking output reads, and proves that its cgroup
is empty and its direct child reaped before accepting output. Deadline checks
cover the loop, final output and completed retirement. Unproven retirement
retains owned handles and blocks another invocation. No Android namespace
init or cell cgroup is killed by these controls.

The maintained usage and exact plan schema are in `source/tools/README.md`.
Main/source receipts are byte pinned; their semantic qualification and
signature review are independent prerequisites. No fabricated Main receipt,
fixed Firefox UID, account session, or runtime pass is supplied.

## Verification boundaries

`verification/normal-tests.json` records actual full-workspace source tests:
13 focused supervisor tests plus 25 applications-library tests and 3 CLI tests,
all passed. Two explicitly privileged host controls were ignored in that run.

`verification/host-controls.json` records their separate actual run on the
final r2 bytes: 2/2 passed. These controls create only owned host fixtures and
exercise FD namespace entry, dead-PIDFD pre-exec rejection, normal/nonzero
commands, output overflow, a setsid descendant holding output pipes after its
leader exits, timeout retirement, and rejection of late successful output.
They do not start or enter Android.

`verification/cli-missing-socket-control.json` uses the real integrated registry
and all 42 real package names with a deliberately absent private test socket.
Its Main input is explicitly synthetic and temporary. The real compiled CLI
exits 1, preserves all 42 rows as blocked with pending gates, and reports zero
accepted apps, zero Android queries and no production/runtime qualification.
This is a parser, coverage and precondition control only.

## CI entry

From a repository containing this capsule at
`compat/android/pocket4/continuation-20261109-2840/apps-runtime`:

```text
cargo test --locked --manifest-path compat/android/pocket4/continuation-20261109-2840/apps-runtime/harness/Cargo.toml --lib -- --test-threads=1
```

Expected ordinary module count: **22 passed, 2 ignored**. The 22 cover 7 probe,
5 transport and 10 evidence-completeness tests. The ignored tests require an
explicit isolated root host with writable cgroup v2; their actual Pocket4 run
is recorded separately. This harness does not replace the full-workspace
runtime-plan/CLI tests or establish Android acceptance.

The harness loads production files with `#[path]` and the actual CPU-placement
source with `[lib] path`. Two visibility adapters forward directly to the
same production PIDFD functions; no process or namespace behavior is stubbed.
All 33 external lock records and checksums are retained from the already
published application checker lock. See `harness/LOCK-PROVENANCE.json`.

The actual same-file remote harness stdout reports 22 passed and 2 ignored,
with both streams read to their observed EOF and a final script metadata
record confirming the unchanged lock. Its separate process-status query then
timed out with the H channel. That one job's terminal state, durable completion
and retirement remain **pending/unobserved**; it was not replayed or cancelled.
`verification/samefile-ci-harness.json` preserves this distinction. The new
GitHub CI invocation independently verifies these 22 module tests. All earlier
full-workspace, privileged host-control, build, CLI-negative and source-commit
receipts in this capsule already have authoritative successful terminal reads.

## Firefox schema successor

`firefox-schema-integration` contains the actual registry successor, narrow
matrix/registry patches, and read-back integration receipt. The source matrix
was 376214 bytes with SHA-256
`9b812661db9171bd3d12bd4068a5d3d54c52ea6a7557bc02798693657a61f21c`.
Only `/apps/41/business_contract` changes in the matrix. The registry only adds
the `browser` profile and `org.mozilla.firefox` package entry. All 42 selected
apps now resolve complete contract definitions; all execution states remain
pending. Historical APK delivery observations are not refreshed by this patch.

The independent protected successor is at
`/home/alex/work/pocket4-android-final/qualification/firefox-runtime-contract-20261109-2840-r2`.
No canonical CURRENT, active owner source, original matrix, shared registry,
Android data image, signer material or Razr state was modified. Existing leaf
preparations with old registry pins require coordinated adoption; do not
overwrite their shared input behind those pins.

## Remaining execution prerequisites

The foreground runtime owner must first produce a qualified current Main and
activate matching daemon/client source. Each selected app then needs its
current official complete APK delivery and independent signature review.
Authenticated distribution, account/business environments, authorized external
test recipients, and Meituan's supported data-preserving signer migration
remain separate blockers. Other profiles are explicitly unsupported by this
new dispatcher and retain their existing qualified leaf entrypoints. Firefox
document/input/image, media, navigation/reopen, recovery and all common gates
still require actual current-runtime execution and reviewed evidence.

The private source/build root can be retired only after durable publication
and a fresh no-live-reference check. This capsule is source and verification
evidence, not permission to stop another owner or remove current data.
