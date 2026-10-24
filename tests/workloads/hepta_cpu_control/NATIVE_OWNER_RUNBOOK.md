# Original native owner execution

This module executes an actual tracked executable in the original
`codex-hepta-agentd` package, built from the explicitly reviewed source pair.
It generates no userspace owner. The original Supervisor, Registry, Root
authority, writer, checkpoint, FinalUse consumers and HOS2 adapter remain the
runtime implementations. The old small `ReadUsage` executable and the kernel
Process ktests are separate evidence and cannot pass this gate.

## Modules

| Module | Responsibility |
| --- | --- |
| `build_original_entry.py` | Build the original locked/default-feature release target, perform its original packaging and enforce the original static ELF bounds. |
| `native_owner_inputs.py` | Verify the frozen source review, complete source snapshots, actual original build records, embedded ELF, exact-source OSDK and retained product kernel. |
| `run_native_owner.py` | Freeze inputs, make fresh ext2 state, run two loader controls and the requested native owner scenarios, retain complete raw evidence. |
| `native_owner_evidence.py` | Check original K/D bytes, complete Root Current receipts, actual process boundaries, CPU accounting and the ordered source/recovery events. |
| `native_owner_copyout.py` | Check the two actual response-loss scenarios against complete original receipts, callback/exit timing, early Unknown recovery and unchanged descriptor Install counts. |
| `native_owner_fault_wire.py` | Independently compare the complete original Install frame hash without executing or generating a guest operation. |
| `test_native_owner_copyout.py` | Exercise inert adversarial DTOs for the two response-loss gates; these records never qualify execution. |
| `test_native_owner_evidence.py` | Reject altered, missing, reordered, relabelled and semantically contradictory inert records. These are parser tests, not native execution. |
| `test_native_owner_runner.py` | Exercise actual bounded subprocess output, timeout, input mutation, exact ext2 formatting/preimage retention and source-review parsing. |
| `NATIVE_OWNER_EVIDENCE.md` | Define the finite acceptance plan and original-entry evidence protocol. |

## Source and build admission

There is deliberately no automatically selected source pin. After the two
repositories' functional changes are committed and reviewed, supply a JSON
document with these exact fields:

```json
{
  "schema": "hepta.native-original-owner-source-review.v1",
  "desktop": {"head": "FULL_OS_COMMIT", "tree": "FULL_OS_TREE"},
  "hepta": {"head": "FULL_HEPTA_COMMIT", "tree": "FULL_HEPTA_TREE"},
  "entry": {
    "package": "codex-hepta-agentd",
    "name": "ACTUAL_TRACKED_TARGET",
    "kind": "bin",
    "path": "codex-rs/hepta-agentd/src/bin/ACTUAL_TRACKED_TARGET.rs",
    "sha256": "ACTUAL_ENTRY_SOURCE_SHA256"
  },
  "userspace_toolchain": {
    "channel": "ACTUAL_FIXED_VERSION",
    "manifest": "codex-rs/rust-toolchain.toml",
    "sha256": "ACTUAL_TOOLCHAIN_MANIFEST_SHA256"
  },
  "scope": "Describe the reviewed exact original owner and kernel changes. Review alone conveys no execution qualification."
}
```

The uppercase placeholders above intentionally fail admission. Every commit,
tree, source digest and fixed compiler version must come from the actual frozen
sources. The review hash is a separate mandatory command-line input. The
runner's own clean harness commit is recorded independently from the compiled
source pair, avoiding a self-referential review commit. Later source or review
changes require new builds and execution; they do not inherit an earlier pass.

`build_original_entry.py` must complete its four actual commands: Cargo
metadata, locked/offline original release build, original release packaging,
and ELF inspection. Its `result.json`, complete source-before/after snapshots,
packaged ELF and logs must remain available. No feature removal, fixture root
package, substituted dependency, profile override or bound increase is accepted.
The source-reviewed original release profile is read from the actual manifest.
The ELF remains at most 8 MiB with the original 16 MiB LOAD-map bound enforced
by `run_g1c_guest.inspect_probe_elf`.

## Product kernel pipeline

Build the product kernel only after the complete original owner passes its
static shape gate. The kernel must embed those exact packaged bytes. The build
wrapper records the same full source snapshots used by the original
`run_queryabi_candidate_guest.source_snapshot`. It executes these two actual
steps and retains their unedited commands, working directories, logs and exits:

1. `osdk-build`: `cargo +nightly-2026-07-21 install --locked` with the original
   `cargo-osdk --path <compiled-desktop>/kernel/asterinas/osdk`. An OSDK built in
   another worktree may embed a different OSTD/source path and is not accepted.
2. `g2-kernel`: the compiled source's `support/build/kernel.sh kernel`, with
   `HEPTA_G2_TRUSTED_DAEMON=1` and `HEPTA_TRUSTED_INITIAL_ELF` selecting the exact
   original owner. Original G1c/G1d selectors remain off.

The supplied `--kernel-pipeline` directory has this retained structure:

```text
pipeline.json
source-before.json
source-after.json
source-built-cargo-osdk
osdk-build.log
g2-kernel.log
product-kernel.elf
kernel-build/
  command.sh
  environment.log
  source-inputs.json
  make-exit-code.txt
  log-exit-code.txt
  run-exit-code.txt
  kernel.log
  generated.Cargo.lock
  trusted-initial.elf
  trusted-initial-manifest.json
  initramfs.cpio.gz
  initramfs-manifest.json
```

`pipeline.json` records `passed: true`, `source_inputs_unchanged: true`,
`kernel_profile: "g2-trusted-daemon"`, `source_root`, `source_head`, `source_tree`,
`owner_sha256`, `osdk_source_root`, `osdk_sha256`, `kernel_sha256`, `kernel_bytes`
and exactly the two `steps` above. Each step has its actual `label`, `argv`,
`cwd` and integer `exit_code: 0`; a timeout is a failure. These are execution
records, not values to infer from an artifact's existence. `generated.Cargo.lock`
is copied from the actual OSDK target before another build can replace it, and
must equal the original fixed 204-package product lock.

Copy `product-kernel.elf` and `source-built-cargo-osdk` from the actual successful
build while their identities are still verified. Preserve the original build
manifest's paths and contents. Subsequent validation uses the retained files
and their actual recorded hashes, not a mutable Cargo target or a rewritten
record. A failed attempt keeps its own directory and cannot be relabelled.

## Execute

Use a new output directory outside the harness, compiled source trees and
frozen build-input directories. All paths and SHA-256 values are explicit:

```sh
python3 -I -B tests/workloads/hepta_cpu_control/run_native_owner.py \
  --execute \
  --desktop-source "$G2_OS_SOURCE" \
  --hepta-source "$G2_HEPTA_SOURCE" \
  --source-review "$G2_SOURCE_REVIEW" \
  --expected-source-review-sha256 "$G2_REVIEW_SHA256" \
  --owner-elf "$G2_ORIGINAL_OWNER_ELF" \
  --owner-build-receipt "$G2_OWNER_BUILD/result.json" \
  --expected-owner-build-receipt-sha256 "$G2_OWNER_RECEIPT_SHA256" \
  --kernel-pipeline "$G2_PRODUCT_KERNEL" \
  --expected-kernel-pipeline-sha256 "$G2_KERNEL_PIPELINE_SHA256" \
  --qemu /usr/bin/qemu-system-x86_64 \
  --expected-qemu-sha256 "$G2_QEMU_SHA256" \
  --output "$G2_NEW_NATIVE_EVIDENCE"
```

Without `--execute`, the command performs no input inspection or execution and
returns an explicit disabled record. The default run includes all four scenarios:
`steady-state-v1`, `manager-exit-after-terminal-v1`, `lost-copyout-live-v1`, and
`manager-exit-before-terminal-v1`. Repeat `--scenario` to select particular
named finite scopes; a partial selection cannot establish an unselected scope.
Both altered ELF loader controls always run against the same product kernel. The byte-change
and truncation must be rejected before any of the four images or roles resume.

The guest uses the original N0 TCG/q35/max profile, one CPU, 512 MiB, no network,
the pinned original SeaBIOS, and a deadline of at most 120 seconds per boot.
The runner freezes the original static entry at `/test/hepta-g2-owner`. Root
alone can read the mode-0400 `/test/hepta-g2-run.json`; that file contains only
`schema_version`, `scenario` and a fresh host nonce. It grants no authority.

Each positive scenario gets a new 256 MiB raw ext2 disk as `/dev/vda`. The
original Root mounts it at `/state`, installs its real independent authority
material and original Host paths there, and uses the original private ownership
boundaries. The runner retains the exact formatted preimage, actual post-run
state, formatter command/log, disk UUID, sizes and before/after hashes. This
demonstrates guest process lifecycle on retained virtual storage. It does not
claim host-power-loss, media or hardware qualification.

The actual Root entry must perform the original debug-exit completion after
all evidence is emitted; the accepted QEMU success is raw exit 33. A normal
PID-1 death, timeout, panic, serial truncation or exit 0 cannot stand in for it.

## Scope that remains separate

A pass in `steady-state-v1` proves the finite original writer/CPU path, pause
and resume, physical original source state and terminal-before-retirement
ordering. `manager-exit-after-terminal-v1` additionally proves an actual
Manager exit and independently authenticated successor in the same boot. It
keeps the original 5-second watchdog, its immutable receipt, the original
30-second recovery grace and the original single restoration allowance.

`lost-copyout-live-v1` additionally requires a real original FileTransport
EFAULT with one Install, an original returned Indeterminate receipt, and
observer-only source-terminal/Current/prefix recovery. The separate
`manager-exit-before-terminal-v1` gate requires actual SIGKILL within the held
callback's two-second window, original Supervisor/material recovery, an early
factory-before-monitor Indeterminate row and zero Recovery Installs. Its old D
result remains distinct from the independent watchdog receipt. Both have
exactly one original prepared operation; the monitor remains enabled.

These gates are acceptance code, not evidence that either original guest case
has run. Adding them does not transfer a host, kernel or previous-source pass
to the current original Rust entry. Every execution still requires the complete
reviewed source pair, successful original build and static bounds, fresh
retained guest evidence and the exact finite scope's own result.

None of the four finite results completes all G2 work. Flags remain false for:

- Reboot with the same original store, old-boot D refusal and Unknown preservation
  without redispatch. The original Root adoption and publisher-retirement APIs
  currently require the same boot; this must be addressed in those owners.
- Native grant renewal beyond the original finite 300-second grant, authenticated
  RootSession lifetime renewal and repeated native role replacement after the
  one Manager/Recovery pair is consumed. The current per-boot deadline remains
  at most 120 seconds; adding four boots' wall times cannot prove this scope.
- Host power loss, hardware behavior and production readiness.

Complete these through the original owners and add actual source-bound cases.
Changing flags, extending the test deadline, replaying an old receipt, resetting
a nonce ledger or loading another qualification executable cannot close them.

## Local verification

```sh
python3 -B -m unittest discover \
  -s tests/workloads/hepta_cpu_control -p 'test_native_owner*.py' -v
```

Parser fixtures explicitly remain inert. Bounded-I/O tests execute harmless
local subprocesses and the real ext2 formatter on new temporary files. A green
host suite is not a substitute for the source-bound QEMU executions above.
