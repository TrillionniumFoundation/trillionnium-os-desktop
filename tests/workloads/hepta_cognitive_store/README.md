# Original CognitiveStore process-crash compatibility

This isolated lane links the unchanged Hepta `codex-hepta-memory` public API.
It exercises the real original SQLx/SQLite WAL implementation, with the
original dependency package identities retained from Hepta's Cargo.lock. It
contains no raw SQL, substitute database, production authority verifier, lease,
or owner test hooks. `source-review.json` freezes clean Hepta b3d3f2d4 and its
full Git tree. The existing Agentd lifecycle lane's 2da/068 profile is unchanged.

The fixture performs ten checks in order:

1. Atomically append an inert source, verified memory revision and two entities
   plus one relation with `remember_with_kg`.
2. Observe a nonempty WAL while that original store and its pool remain open.
3. Terminate the actual seed child with SIGKILL and check its wait status.
4. Reopen with legacy `CognitiveStore::open`; compare the full original memory
   record and the complete logical recovery anchor captured before the kill.
5. Retry `append_source` with the identical source and verify unchanged source
   identity and logical cut.
6. Open two independent processes and original pools before releasing either
   compare-and-swap correction.
7. Require one `correct_with_kg` success at revision 2 and one actual original
   `CognitiveStoreError::Conflict` for the same expected revision 1.
8. Append different content with the losing source's event key: success proves
   that the failed CAS rolled back its preceding source insert too.
9. Reopen after both contenders exit; compare the complete winning memory and
   retain the nonempty original KG/projection receipt.
10. Await original `close()`, reopen again, and compare the exact final logical
    cut and winning memory. Every original open also runs its integrity checks.

The direct child handles have kill-on-drop cleanup, bounded output, a readiness
barrier, and 90-second operation deadlines. The outer host runner retains a
waitable process-group leader through cleanup and then reaps it. The native
runner instead bounds the whole QEMU process and uses a fresh, finite ext2
state image. A native failure retains launcher stdout/stderr when available.

## Run and interpret

Run from the Desktop repository root. Use an absolute, clean Hepta worktree
path and new output directories whose parents exist:

```sh
python3 tests/workloads/hepta_cognitive_store/prepare_inputs.py \
  --hepta-source "$HEPTA_SOURCE"
python3 tests/workloads/hepta_cognitive_store/prepare_inputs.py \
  --hepta-source "$HEPTA_SOURCE" --execute --output "$STORE_BUILD"
sha256sum "$STORE_BUILD/build.json"
python3 tests/workloads/hepta_cognitive_store/run_host.py --execute \
  --build-receipt "$STORE_BUILD/build.json" \
  --expected-build-receipt-sha256 "$STORE_BUILD_RECEIPT_SHA" \
  --output "$HOST_RESULT"
python3 -m unittest discover -s tests/workloads/hepta_cognitive_store -p 'test_*.py'
```

Preparation uses installed Rust 1.95.0, offline dependencies, the original
explicit resolver and dev-small profile. An optional `--target` is an exclusively
leased build cache, not a source checkout. The external root omits only the
same exact, inactive duplicate SSH tungstenite patch alias as the original
Agentd fixture; the fixed crates-io target remains unused and checked. It then
requires offline resolution, locked metadata, locked build and Clippy, with no
package version, source or checksum drift. Provider credentials and inherited
RUSTFLAGS never enter the build or runtime child environment. No network
fetching is performed by this lane.

The native runner requires an actual ordinary OS kernel, its successful clean
build receipt and the explicitly reviewed Desktop source tree. It does not
build a kernel and does not infer the latest tree from a running worktree:

```sh
python3 tests/workloads/hepta_cognitive_store/run_native.py --execute \
  --build-receipt "$STORE_BUILD/build.json" \
  --expected-build-receipt-sha256 "$STORE_BUILD_RECEIPT_SHA" \
  --kernel "$KERNEL" --kernel-receipt "$KERNEL_RECEIPT" \
  --expected-kernel-receipt-sha256 "$KERNEL_RECEIPT_SHA" \
  --expected-desktop-tree "$REVIEWED_DESKTOP_TREE" \
  --initramfs "$INITRAMFS" --expected-qemu-sha256 "$QEMU_SHA" \
  --output "$NATIVE_RESULT"
```

Kernel receipt schema is `hepta.native-original-runtime-build.v1`, with
`kernel_profile=ordinary-os`, one `build_sources.desktop` identity, and the
actual kernel digest and command evidence. These caller-retained local
receipts are not remote attestation. The source-tree argument is an explicit
review input; this runner does not independently decide that arbitrary kernel
source is approved. Initramfs and BIOS retain the existing ABI lane's reviewed
identities. The read-only payload contains the fixture and the recursively
resolved dynamic libraries, inspected with readelf without host execution.
The writable state is a fresh 256 MiB ext2 image. Boot uses one CPU, no network,
4 GiB memory by default and a 600-second whole-guest deadline. This store
lane selects `loglevel=warn`; WARN/ERROR diagnostics and all explicit receipt
markers remain enabled. Its launcher finishes bounded file reads and encoding
before emitting the serial record, avoiding file-read logs splitting a buffered
hex record. It handles legitimate short TTY writes with a bounded write loop;
an I/O error or an interleaved/damaged record still fails the strict oracle.

`run_host.py` and `run_native.py` are disabled unless explicitly executed.
Successful host receipts keep `native_guest_verified=false`. Only a successful
real ordinary guest can set the native store compatibility result true.
Synthetic Python oracle tests, source preflight and static launcher compilation
are not runtime evidence. A failed build/guest is never promoted to a pass.

## Qualification boundary

The original legacy open takes a shared store fence; SQLite serializes these
local test writers. This is not the production exclusive writer-lock.
`ProductionDurableWriter` and authenticated writable generation recovery need
a real external `ProductionAuthorityLease` and verifier. No synthetic grant is
created to make those APIs callable. Capturing `recovery_anchor()` compares
integrity only; it neither publishes a trusted current witness nor grants write
authority. Legacy `open()` can accept a valid older state and is not an
anti-rollback recovery boundary.

All results explicitly keep production authority, production writer-lock,
authenticated recovery, power-loss durability, model turns, device effects and
complete F1 qualification false. A SIGKILL/reopen pass covers process-crash
compatibility of this exact original store on the tested filesystem. It does
not cover reboot/power loss, storage faults, malicious rollback, production
writer fencing, CPU/device control, a full agent objective or hardware.
Production store closure remains blocked until the actual provider/host
supplies its authorized writer and independently authenticated current cut.

The [2026-10-23 validation record](VALIDATION.md) distinguishes the actual host
and guest passes, exact source/binary inputs, failed earlier attempts and the
remaining production authorization boundary.
