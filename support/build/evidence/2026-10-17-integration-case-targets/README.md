# Per-case OSDK workspace isolation — 2026-10-17

This A01 support-only change gives every integration case a new exclusive
`case-NN/target` as `CARGO_TARGET_DIR`. Its generated `osdk/` base crates and
bundles stay private. Only the explicit `debug`, `release` and
`x86_64-unknown-none` compilation artifact directories are shared by verified
symlinks into the already isolated cache. No old generated workspace is linked,
copied or deleted.

The root/cache profiles are checked with NOFOLLOW and directory identities
**before** harness normalization or any Cargo action. New cache/target/profile
creation is exclusive. Existing unexpected paths, cache links/files or changed
identities fail without replacement; partial owned outputs remain available.
The existing integration lock covers preflight, linking and all sequential
cases. Each case and `target-profile.json` bind the target/cache identities.

Only these three owned source files changed:

- `support/build/osdk-integration/run.py` — SHA256 `6d1ade703a944aa4773033f86edeed3c82d0e5f274253e9327458efcd92451cc`
- `support/build/osdk-integration/test_case_targets.py` — `eab6279e3a1d478a07593c48e2d25e9a751dff5fa0e1201e4daa1d68bb193392`
- `support/build/osdk-integration/README.md` — `e8d8f3431278aceebcad5443bec2c68a93aba624fe7d6ac36028639d3da89213`

`sources/fixed/`, `sources/baseline/`, `case-targets.patch` and
`source-validation-ready.json` retain the exact reviewable source. Baseline
`run.py` was byte-compared to commit
`7997651e257e32d3161e1bb572d0130772009410`; this is a single-file baseline
binding, not a claim that the entire red fixture was a clean source checkout.

## Observed failure and bounded diagnosis

The earlier real native matrix at `d895dd73...` failed case20
`work_in_workspace` before any guest: OSDK exit6, generated dependency path
`.../myos` from an earlier example rather than current
`.../myworkspace/myos`. Selected original logs/record and a stable read of the
old shared manifest/stat are in `native-diagnostic/`; ABI's independent old
artifact postcheck is retained if available. That postcheck also found one
cross-case same-name boot ELF path had been replaced. Missing historical full
bytes are not reconstructed or declared validated here.

Pinned SDK `base_crate/mod.rs` at `d895dd73...` already compares
Cargo.toml, main and linker scripts. Its SHA256 is
`490aa4fc7a57362e1816c3778690de6d4d1af9508c2d4aec2e2c9524b4a74676`.
The native environment recorded that source, and the fixed source-built SDK
binary still matches SHA256
`9338c5166093eb8133a0f6999e82ba70fe31f71ed26d3902b46887d194e122d9`.

A real small probe using that exact SDK and pinned Cargo demonstrates that the
SDK **normally regenerates** a changed dependency path between two same-name
projects. The failure is therefore not attributed to a missing manifest
comparison. Historical writer identity/cause remains unknown.

The fault probe deliberately restores an earlier manifest only into its
fixture-owned shared output immediately before real Cargo metadata:

- With the old source removed, shared-path metadata exits101.
- With the production per-case target helper, the same stale restoration still
  occurs at the old shared location, while current private manifest points to
  the correct second project and metadata exits0.

All five valid SDK invocations in each completed probe deliberately encounter
fake Cargo build exit42 **after real metadata**, so their outer SDK exit6 is
expected. No rustc/kernel build or QEMU is performed by this probe. It is a
source-built SDK/actual metadata test, not kernel or native-matrix acceptance.

## Actual validation

| Evidence | Exact result and scope |
| --- | --- |
| Baseline public runner red | One assertion failure under each of `-I` and `-I -O`; subprocess fixture intentionally retains a stale same-name generated manifest. It is not an upstream SDK behavior model or VM. |
| Intermediate targeted | 8/8 in each mode, 16 executions; before preflight and final two tests. |
| Final full host suite | **141/141 ordinary + 141/141 optimized = 282 executions**, both exit0, all captured source input hashes stable. Includes all ten new methods and existing host/GDB fixtures; zero VM/kernel runs. |
| Independent ordering/custody review | Same fixture: prior candidate reached prepare/production collaborators before rejecting foreign cache link; final source rejects with calls=[] and preserves foreign contents. Reviewer separately ran the nine tests that existed at that time; the tenth is covered in final full suite. |
| Production helper + actual SDK/Cargo metadata | Final source-bound probe: normal regeneration confirmed, fault red101 → private-target green0. Build deliberately stops42. |
| Tiny actual host Cargo | Two offline locked build invocations exit0; metadata reports distinct per-case target roots and the second compiler artifact is `fresh=true`, confirming compilation cache reuse. This is a tiny no_std host library, not the OS kernel. |

The first full **139-test intermediate** ordinary attempt had one failure:
the pre-existing 0.5-second descendant fixture had no readiness file when its
timeout expired (138 other tests passed). It remains in
`raw/green-full/I/`. An isolated same-source check and then both 139-test
modes passed. No production change or test relaxation was used for that retry.
The later preflight change and two new tests justify the final 141-test suite.
These runs are recorded separately, not combined into an invented matrix.

The first actual SDK probe setup attempts also failed honestly: attempt01 used
invalid fixture boot method `direct` (SDK5/controller1); attempt02 omitted
fixed rustc from fixture PATH (SDK12/controller1). Original stderr, command
receipts and controller versions remain. Later attempts use new directories.

Final raw receipts:

- `green-full-final/{I,IO}/{invocation.json,console.log}`: complete commands,
  selected environment, exact input SHA256 before/after and real exits.
- `actual-sdk-probe-05-final/`: fixed SDK path/hash, actual Cargo metadata,
  generated manifests, explicit fault controls, command start/end times.
- `tiny-host-cargo-final/`: actual fixed Cargo/Rustc hashes, environment,
  metadata and JSON compiler artifacts showing freshness.
- `independent-review/`: frozen review, original red/green order fixture,
  nine-test receipt and actual flock check.

## Limits and storage

This packet adds **zero actual upstream22 matrix reruns, zero kernel builds and
zero QEMU guests**. Root owns the later exact-published-source native rerun.
UNIX/TCP/capture acceptance and original upstream assertions are not relaxed.

Per-case generated outputs prevent cross-case base/bundle collisions. Within a
single case, run/test of the same crate can still replace its same-name bundle.
Persistent per-guest input snapshots are a separate recorder task. Shared
compiled ELF/symbol artifacts can change during serial compilation; existence
of an old artifact is not a freshness or retention proof. This is not a
privileged-writer security boundary and does not attribute the old writer.

No upstream/core source, normal recorder, fixed kernel/toolchain, other owner
branch, production disk/service/BIOS or root empty README was changed by this
task. This agent made no commit or push.

`raw.tar.gz` contains **1381 logical payload entries** represented by
**1377 regular-file members and 4 internal hardlink members**. Logical payload
bytes total 4,565,559 (including the four linked payloads), while ordinary
member data bytes total 4,551,399.
The archive remains 999,293 compressed bytes; SHA256
`4711dcca8593133057df96fbd4c3330a90f0f3f2985120447ae41eb75b26b548`.
All 1381 logical payloads were size/SHA256 verified in memory. Each hardlink
header names a legal same-archive **regular** member; its logical payload is
verified directly from that target's bytes, without extraction or link-chain
resolution. `raw-members.json` indexes all four hardlink paths, targets,
zero-based header/target positions, payload sizes and SHA256. Its separate 61
source symlinks remain metadata-only: the archive contains no symlink members.
Bytecode caches are excluded. The raw archive preserves existing files without
rewriting their logs.

The original `freeze-evidence.py` is retained unchanged as the actual historical
freezer; it mislabeled the logical source-file list as regular archive members.
Publisher review caught that metadata error before publication. The corrected
member-type accounting and full hardlink index are in `raw-members.json` and
`report.json`; `packaging-correction.json` records the before/after metadata,
unchanged archive/source/test hashes and the strict in-memory verification.
Pre-correction README/report/checksum/index/freezer and the original freeze
receipt are preserved in the explicitly labeled scratch snapshot referenced
there. No Cargo, VM or tests were rerun for this packaging correction.
The outer
`SHA256SUMS` covers all frozen ordinary files except itself, including the
independent review's own checksum file.

