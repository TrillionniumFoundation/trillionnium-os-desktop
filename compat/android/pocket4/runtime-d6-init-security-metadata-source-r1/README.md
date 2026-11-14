# D6 original init security metadata component

This capsule preserves the complete 430-file D6 producer and its exact D5 parent.
It contains the two changed source files, their complete preimages, both original
Git commit bodies, complete source inventories, the full current producer, and
the original qualification evidence. It is a component source publication. The
current combined product producer can incorporate this component without
replacing newer Android, security, AAC or runtime changes.

| Boundary | Exact value |
|---|---|
| D5 parent commit | `b08cdd2c70c05463c3b4c892012f7426691c502b` |
| D5 complete root tree | `af27a280676bc39b5ce98168ebba3ae1891e4e56` |
| D6 component commit | `7d86a66b8d95477781519cec99e53fd0e76b6f36` |
| D6 complete root tree | `224fdc48b1083044cdce30a09ee4ec995a48c12d` |
| Complete source sets | 430 parent files and 430 current files |
| Delta | 2 changed files; 428 files unchanged; no added or removed files |
| Actual historical ordinary evidence | 9 tests, 2 freshly compiled release products, 26 retired commands |
| Independent historical retirement | 32 original PIDs, 6 cgroups, all 430 source files and 52 command logs |

## Source change

`runtime/droidloom-supervisor/src/production_runtime_assets.rs` reads the actual
held init descriptor's `security.selinux` and `security.capability` attributes.
The admitted label is the complete 24-byte original value
`u:object_r:init_exec:s0` followed by NUL. Capability absence requires `ENODATA`;
missing label, wrong or truncated bytes, a present capability value, and
unavailable or denied reads fail closed. The check runs when preparing inputs,
matching the held witness and verifying the init mount. Original descriptor
identity checks remain in place. The accompanying runtime layout contract
documents this boundary.

The source does not make `ExecutionAdmission` constructible. It does not grant
SELinux transition, combined host/Android policy, APEX, Android boot or app
runtime qualification. The original image metadata observations are included
as source evidence. Ordinary `user.*` xattr fixtures exercise the reader's
mechanics and error handling; they never stand in for real `security.*`
attributes. Runtime and production readiness remain false.

## Historical results remain distinct

All 109 original evidence files are byte-preserved under `evidence/`.
The original 9f7 preparation failure remains failed. The original a00 ordinary
report also remains `FAILED`: its nine tests and two fresh Cargo builds had
completed, but the initial release-copy check rejected Cargo's internal hard
links. Its `release_binaries` map remains empty.

The a0b completion independently enumerated both aliases of each original
Cargo product, proved they were confined to its private target, made new
single-link `0555` copies and executed the supervisor's ordinary help entry.
It did not repeat Cargo or tests. The separate a1d retirement verified the
combined 26 commands, all 52 raw command logs, all 430 source identities and
the original actor/cgroup retirement. `verify.py` checks these report links,
the exact Cargo artifact messages and the complete nine-test Rust terminal.
It preserves all failure states and assigns no historical evidence to a new
CI execution.

## Verify and replay

The containing workflow must pin the SHA256 of `FILES.sha256` outside this
capsule. Check that pin and the complete inventory before executing its scripts.
Do not trust a digest obtained solely from an unverified copy of the capsule.
The scripts are independent of the caller's working directory and support
`python3 -I -B`.

```sh
python3 -I -B "$capsule/verify.py" \
  --inventory-sha256 "$RUNTIME_D6_INVENTORY_SHA256" \
  --output "$fresh_producer" --report "$fresh_replay_report"
python3 -I -B "$capsule/test_verifier.py"
```

The replay verifies every source file's complete bytes, SHA256, Git blob and
mode, reconstructs both complete Git root trees from the inventories, and
authenticates those roots against the original commit bodies. It copies all
430 current files to a fresh independent directory, creates private Git
metadata, and performs reverse/check/apply/reverse/check/apply round trips.
Each resulting full source tree and actual `git write-tree` result is checked.
Only a source root's `.git` directory may be skipped; nested repositories,
aliases, extra directories and files are rejected. The original input files
and directory identities must remain unchanged throughout. Git children use
umask `0022` even when the calling publication process uses `0077`; the private
parent directory remains private.

`--producer` checks an already reconstructed complete D6 tree after compilation.
It cannot be combined with a fresh replay request. All outputs and reports must
be fresh, canonical and outside input trees. The eight verifier controls retain
the previous contradictory-log, alias, mode, whole-tree and fresh-target
counterexamples and add checks for contradictory or incomplete Cargo terminals.

## Fresh CI

`ci-job-snippet.yml` is intended for an independent Linux job with the normal
host build dependencies and the Rust toolchain already configured. It checks
the external inventory pin, reconstructs the full producer, runs the verifier
controls, and invokes:

```sh
python3 -I -B "$capsule/run_ci.py" \
  --inventory-sha256 "$RUNTIME_D6_INVENTORY_SHA256" \
  --producer "$fresh_producer" --target "$fresh_cargo_target" \
  --report "$fresh_ci_report" --jobs 2
```

The CI runner compiles a fresh `droidloom-supervisor` library harness from the
complete source, selects its executable from the actual Cargo JSON stream,
executes exactly the nine runtime input controls, compiles both release
executables, and runs each ordinary `--help` entry. It rejects incomplete,
duplicated, contradictory, failed or ignored Rust records and Cargo terminals.
The complete 430-file bytes, modes, Git identities, membership and F9 observations
must match before and after. Cargo targets, logs and reports remain separate
from the producer. Historical binaries and logs cannot satisfy this execution.

The source capsule and local replay do not prequalify this fresh CI. No Android
build, device operation, host policy change, daemon service or Android cell is
started by these commands.
