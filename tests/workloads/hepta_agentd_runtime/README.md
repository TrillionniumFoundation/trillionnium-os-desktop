# F1 original Agentd runtime lifecycle gate

This is an opt-in guest runner for the next F1 runtime slice. It stages the real
Agentd, the unchanged original-library lifecycle fixture, and the real read-only
observer into an ordinary Trillionnium OS guest. It never launches those three
programs on the host.

The implementation and its host tests are not an execution receipt. A successful
run can establish the original-owner no-turn lifecycle on the specified guest.
It does not complete F1, native production G2, durable crash recovery, aggregate
memory isolation, SMP qualification, or hardware acceptance. The report keeps
those fields false even when its lifecycle oracle passes.

## Executed fixed-source lifecycle (2026-10-23)

The original unchanged b3 library fixture executed eight checks in the actual
7d Asterinas-derived ordinary guest: Starting, Running, bounded capabilities
and events, missing-run read, same-process draining, restart, rejection of an
old spawn, and controlled stop. PID changed 26 to 206 and spawn 1 to 5; QEMU
returned 33 without timeout and all inputs remained unchanged. The exact
[result and raw serial](../../../results/integration/2026-10-23-audit-closure/native-runtime-7d-b3/publication.json)
bind the full source identities and actual binaries.

The earlier cold preparation deadline, final clean-status deadline and formal
60-second Running-readiness failure remain retained. A separate diagnostic run
is not qualification. This success covers the original read-only lifecycle
only: no model turn, objective submission, device effect, production grant,
writer lock, authenticated cut, durable CPU K↔D or complete F1/G2 was executed.
It does not qualify later integrated source trees.

## Current fresh-build profile

The current `source-review.json` selects Desktop
`7d8906ef9fbb5f3af4e6bb0843b79ac666394833` / tree
`ca4b875cdb553291a99f4a550eb0b2bd6649de8c` and Hepta
`b3d3f2d4b01f123d7ac17575c27fb54d00094f7f` / tree
`b035a577969cb503d7c09620694a6b6c54178c97`. It includes the UDP, exec
argument, family user-frame, initial-stack and readonly fixes and the Oct 23
original-owner recovery/issuer/composition stack. The 84 selected source
identities are a review input, not a runtime receipt.

Use `build_kernel.py --execute` to run the original ordinary kernel build,
boot and QueryAbi candidate gate, with an explicit SHA-256 of this source
review. It retains the original command, pinned toolchain gate, raw QEMU
record, serial bytes, all three boot binaries and complete tracked-source
snapshots. It creates `kernel-build.json` only after successful build, boot,
QueryAbi checks, live artifact verification and unchanged clean sources.
The builder first force-builds the original locked OSDK in the same reviewed
checkout and records its binary hash. Local-development OSDK embeds a source
directory; a binary built in another checkout is not reused by version alone.
The builder also freezes `source-built-cargo-osdk` read-only and retains its
exact `osdk-build.log` identity before kernel qualification. `osdk-freeze.json`
binds those bytes/log to the source and command; it explicitly grants no kernel
qualification. All three retained files are checked again after the build,
and their identities are embedded in the successful kernel receipt. A failure
can therefore retain the original tool without inventing a successful kernel.
No provider credentials or trusted-image flags are inherited. A failed build
retains a failure result and never produces a success receipt.

The `--execute` flag is required; without it the builder performs no build or
filesystem mutation. Pass canonical clean source checkouts, the pinned VDSO,
and a fresh output directory outside both checkouts. An optional `--target-dir`
passes a Cargo build cache to the unchanged original qualification runner;
it never skips source checks, build commands, live boot or QueryAbi. The resulting receipt
and kernel are inputs to the existing `prepare_inputs.py`, followed by the
existing explicit `run_agentd_runtime.py --execute` guest run.

The historical c5/6d archive is now bound independently to
`retained-source-review.json`. `import_kernel_artifact.py` always preserves
that original identity; its receipt is rejected by the current runtime
profile. Importing old bytes cannot qualify the UDP-fixed kernel or the new
Hepta combination. The historical archive procedure below is retained for
replay and provenance only. Current native CI builds the reviewed kernel
from source instead of importing that older artifact.

Current F1/G2 and hardware qualification remain open until their own real
execution receipts exist. Host tests validate the runner, not the daemon.

## Original owners and precise scope

The fixture is the existing
[`original_agentd_probe.rs`](../../integration/hepta/original_agentd_probe.rs),
linked to the unchanged original `FleetRegistry`, `Supervisor` and
`UnixProcessDriver`. It registers the agent, writes the original no-turn model
configuration to its registered home, starts Agentd through the original driver,
and invokes the existing `hepta-observe` executable. The driver supplies the
registered identity and generation. The native launcher does not write registry
JSON, construct a second supervisor, set fake `HEPTA_*` values, or create grants.

The companion original session source is compiled unchanged because the fixture
references it. This gate supplies no session flags and tests no Session UI.
It uses a zero-second hold and the original fixture's eight acceptance checks:

1. Original Starting state and matching supervisor PID.
2. Original Running promotion without replacing that PID.
3. Bounded capabilities and original lifecycle history.
4. A missing run remains absent.
5. Original Draining in the same process.
6. Original restart creates a newer spawn and a different PID.
7. The previous spawn is rejected by the replacement daemon.
8. Controlled stop leaves no successful daemon observation.

`validate_records` also checks the actual observations printed by the fixture:
the registered private endpoint, exact record order, lifecycle-specific generation
offsets, same-spawn PID continuity, replacement identity, readiness, fencing, and
original Starting history. An `acceptance_pass` label by itself cannot pass.
Objective submission, model turns, and device effects must all remain false;
production authority capabilities fail this no-authority profile.

The launcher reads and hex-encodes each bounded diagnostic completely before
starting its serial record. It retries EINTR and legitimate short TTY writes;
a read error produces no stream prefix, and any write error prevents the child
success marker. The original 512 KiB stdout / 64 KiB stderr limits, nonce,
record ordering and strict hex oracle remain unchanged. Guest boot selects
`loglevel=warn`, retaining warnings/errors while preventing INFO syscall logs
from splitting records or exhausting the serial budget. Host C regressions
exercise the actual launcher emitter, including forced 127-byte writes and
interrupted reads/writes; they are not daemon runtime evidence.

The earlier
[`hepta_agentd_abi`](../hepta_agentd_abi/README.md) gate remains independent and
unchanged. Its expected missing-`HEPTA_FLEET_ROOT` rejection is useful early ABI
evidence. It is never relabelled as successful daemon startup.

## Historical retained sources

| Component | Reviewed commit | Tree |
| --- | --- | --- |
| Desktop fixture, observer and ordinary kernel source | `c5c88794bf227b1d862b2f914b02809a0090e854` | `87bc4e4d72697a7583fb0afafe4db4b41582941c` |
| Original Hepta owner libraries and Agentd | `6d6097da843f5831dfaf9cee3530da512d072a15` | `f722fbe5f24275c324089be720559a40901105f3` |

[`retained-source-review.json`](retained-source-review.json) records 28 selected source files with
their exact Git blob and SHA-256 identities. Selection covers startup, original
registry/supervisor ownership, the fixture and observer, and the unchanged ABI
helpers; it is not a claim that every Hepta source file was reviewed here.
The builder additionally requires clean Git checkouts at the complete fixed
commits and trees, before and after compilation.

An ordinary kernel receipt retains its actual `build_sources.desktop.head`.
A different build commit is accepted only when its complete tree equals the
reviewed tree. PR #245's merge commit `39c1d84ebf854958f5829c0118b0c8b92a6b4926`
has this same tree, while the retained A06 build actually used `c5c88794`;
that actual build head remains in the receipt. All 28 selected blobs were
rechecked at the fixed c5/6d pair. An upstream Asterinas vendor manifest is not the Desktop
repository identity. A new source tree requires a new review; there is no
`--ignore-source` switch.

## Files and responsibilities

| File | Responsibility |
| --- | --- |
| `build_kernel.py` | Execute the reviewed ordinary build, boot and QueryAbi gate and retain current-source kernel inputs. |
| `prepare_inputs.py` | Verify clean source identities, build unchanged userspace offline, preserve original dependency identities, and freeze inputs and build receipts. |
| `import_kernel_artifact.py` | Verify the fixed successful A06 archive, replay its unchanged original boot and QueryAbi checks, and transcribe the real ordinary kernel build receipt. |
| `run_agentd_runtime.py` | Verify frozen inputs, inspect ELF dependencies without execution, construct fresh guest images, launch QEMU explicitly, and evaluate the strict lifecycle result. |
| `agentd_runtime_probe.c` | Create the private empty guest work directory, launch the original fixture, retain its true wait status, and emit nonce-bound bounded diagnostics. |
| `test_agentd_runtime.py` | Host regressions for evidence rejection, source/file binding, staging, disabled mode, and terminal failure reports. Synthetic records remain test data. |
| `test_runtime_emitter.py` | Compile and execute the actual bounded C emitter with interrupted/short I/O, capacity limits, and fail-closed errors. |
| `test_target_cache.py` | Check explicit cache selection, real process lease exclusion/release, retained failure evidence and unchanged original build commands/deadlines. |
| `test_kernel_import.py` | Reject wrong or incomplete CI metadata, untrusted archives, changed source snapshots, ktest images, and failed original builds. |
| `test_kernel_build.py` | Check disabled mode, pre-build source rejection, failed-build receipts and retained/current profile separation. |
| `source-review.json` | Fixed reviewed source identities and scope. |
| `retained-source-review.json` | Independent historical archive identities; never updated to relabel old binaries. |
| `.github/workflows/f1-original-runtime-host.yml` | Run host tests and compile the guest launcher. This workflow never qualifies native runtime. |
| `.github/workflows/f1-original-runtime-native.yml` | Build and qualify the current ordinary kernel and three original x86_64 executables, then evaluate the real no-turn lifecycle. |

## Historical retained native CI path

The native workflow runs on `ubuntu-24.04` x86_64. The workflow and launcher come
from the pull request's exact head; compiled Desktop/Hepta source checkouts are
separate clean directories at the reviewed pair above. It uses Rust 1.95.0 for
userspace and a genuine kernel built with the original pinned kernel toolchain.
The earlier ARM64/f8c9419 workflow's ELF files are not inputs to this x86_64 gate.

The retained kernel comes from the successful
[A06 run 39898657974](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39898657974),
artifact `12480223660`, named `a06-exact-kernel-ktest-39898657974`:

| Input | SHA-256 |
| --- | --- |
| Exact 222,254,688-byte artifact ZIP | `12f6e6ccd459358e5cc254c7aa60d1f0ca16d9930e66c0f58906c18ab9b5784e` |
| Ordinary `a06-queryabi-candidate/product-kernel.elf` | `5a4f528b344c2d0bdb40c41c446e141d206aafb84d4cb6a6895dcf5c962f1450` |
| Original initramfs | `86be65ab9234cd20ea6ec8d44a12b8765fd7a3e241fde920c71b3621ca0047f3` |
| Original SeaBIOS | `1a9ea4f17bcfb27bda5728e2c21d9fa074cf7947b9b4910bb28213a735c96735` |

Despite the archive's `ktest` name, this importer selects its separately built
**ordinary product image**. It verifies `ActionChoice::Run; no --cfg ktest`, the
original `make ... run_kernel` arguments, all three zero build/wrapper exit
records, the actual source head in the build environment, and the original
nightly source gate. The boot record binds the exact kernel/initramfs/BIOS bytes.
All 7,821 tracked source identities must be identical before build, after boot
and after the original QueryAbi guest. The selected 28-file review is checked
against that complete kernel snapshot where it concerns Desktop files.

The importer verifies the four original checker source files against that
snapshot, then calls the unchanged `check_boot` and `evaluate_guest` on retained
raw serial bytes. Every evaluated QueryAbi field must equal the original receipt.
It preserves the original command, raw logs, metadata, full source snapshots and
their hashes. It writes `built: true` only after these original build/execution
records pass; `kernel_built_in_this_import` and `guest_executed_in_this_import`
remain false. Importing this kernel does not provide Hepta runtime evidence.

The CI job fetches only the original locked dependency graphs into a fresh Cargo
home, then builds Agentd, the unchanged fixture and observer offline. It never
executes those ELF files on the host. Its final step explicitly invokes the
native runner with `--execute`, a 900-second bounded deadline and 4 GiB guest
memory. Success requires the original eight lifecycle checks from the real
fixture. Logs, build receipts, the three actual ELF files, raw guest serial and
fresh guest state disk are uploaded on failure as well as success. Each pass is
still only a no-turn lifecycle qualification; the runner keeps full F1/G2 and
hardware completion false.

The pinned archive must remain available. An expired or deleted artifact fails
the download/import step. Updating it requires reviewing a new actual build,
its source tree and raw records, then changing the explicit pins; there is no
fallback to the latest artifact, a ktest image or a fabricated receipt.

## Prepare actual build inputs

The preparation command needs canonical clean Git checkouts of both fixed source
commits, installed native Rust/Cargo 1.95.0, the original dependency cache, at least
8 GiB free, and a new output directory outside both checkouts and retained kernel
inputs. It invokes Cargo with `--offline`, locked application builds, original
`dev-small`, no default Agentd features, and no inherited provider environment.
It does not download a replacement toolchain. Rust 1.95.0 here is a userspace
compiler, not a substitute for the kernel's pinned nightly toolchain. The optional
`--fetch-dependencies` flag requires `--execute` and warms only the two original
locked x86_64 dependency graphs before offline compilation; no resolution drift
or application execution is permitted by that flag.

To resume a timed-out build, pass both `--original-target-cache` and
`--observer-target-cache` with the canonical existing target directories from
the previous attempt, and select a new output directory. Both caches must be
separate from each other, source checkouts, the new output and retained kernel
inputs. The builder acquires a nonblocking exclusive advisory lease on both
caches through final binary freezing; another preparation using a held cache
fails promptly. Other tools must respect these leases rather than run Cargo
directly against the same directories. No earlier failure log or result is
rewritten. The new report and userspace receipt retain the cache paths,
directory and lease identities, actual command working directories/target
paths, and unchanged 3600-second command deadline. This is cache reuse, not a
cold build or authentication of preexisting cache contents. The same source,
toolchain, original commands/features and dependency-lock checks still run.

The external fixture uses the original generic `prepare_runner` and
`verify_runner_lock` helpers. These preserve the original library path dependencies,
workspace resolver, profiles, shared package identities, and the existing narrow
omission of one verified unused duplicate tungstenite patch alias. The separate
older host gate's `f8c9419` source guard is unchanged; this builder performs its
own fixed `6d6097d` source verification before using the generic helpers.

The ordinary kernel must already have a retained build receipt. For the fixed
CI artifact, use the importer rather than authoring a success receipt manually:

```sh
python3 -I -B tests/workloads/hepta_agentd_runtime/import_kernel_artifact.py \
  --archive /absolute/a06-final.zip \
  --artifact-metadata /absolute/original-workflow-artifact-list.json \
  --run-metadata /absolute/original-workflow-run.json \
  --desktop-source /absolute/desktop-fixed-source \
  --output /absolute/new-retained-kernel
```

Keep this output's `original/` evidence directory with its `kernel-build.json`;
copies of the receipt in frozen/runtime bundles retain the same original hashes.
The general kernel receipt shape is:

```json
{
  "schema": "hepta.native-original-runtime-build.v1",
  "sources": {
    "desktop": {"head": "reviewed Desktop commit", "tree": "reviewed Desktop tree"},
    "hepta": {"head": "reviewed Hepta commit", "tree": "reviewed Hepta tree"}
  },
  "build_sources": {
    "desktop": {"head": "actual ordinary kernel build commit", "tree": "actual build tree"}
  },
  "kernel_profile": "ordinary-os",
  "built": true,
  "source_clean": true,
  "binary_sha256": {"kernel": "actual retained kernel ELF digest"},
  "commands": [["actual executable", "actual arguments"]]
}
```

This is a format illustration, not an execution receipt. Fill it only from
retained original build evidence and keep the originating logs and artifact
identities. The gate checks identities and file integrity; caller-retained
receipts are not cryptographic remote attestation. Kernel test images are rejected.

Run the same command without `--execute` first for read-only source/kernel input
validation. With actual paths and their independently retained digests:

```sh
python3 -I -B tests/workloads/hepta_agentd_runtime/prepare_inputs.py --execute \
  --desktop-source /absolute/clean/desktop-fixed-source \
  --hepta-source /absolute/clean/hepta-fixed-source \
  --kernel /absolute/retained-kernel/kernel.elf \
  --kernel-receipt /absolute/retained-kernel/build.json \
  --expected-kernel-receipt-sha256 <retained-receipt-sha256> \
  --cargo /absolute/rust-1.95.0/bin/cargo --expected-cargo-sha256 <cargo-sha256> \
  --rustc /absolute/rust-1.95.0/bin/rustc --expected-rustc-sha256 <rustc-sha256> \
  --cargo-home /absolute/original-dependency-cache \
  --output /absolute/new-frozen-inputs
```

On success, `input-manifest.json` binds the four distinct ELF files, both source
trees, all reviewed file identities, and the kernel/userspace build receipts.
The userspace receipt records actual commands, toolchain digests, the fixture
lock and patch omission, and all three resulting executable digests. A Cargo,
deadline, source, or dependency-lock failure retains `built: false` and a
structured preparation result when the new output directory was created.

No binary in the frozen bundle is run by this preparation command. Do not
replace a missing original executable with a simulator or a host test binary.

## Run the guest explicitly

Without `--execute`, the runtime runner emits a disabled report and creates no
directories or processes. Native execution additionally needs an actual QEMU
executable and its retained digest, GCC, readelf, mkfs.ext2, the original
initramfs and BIOS, and a fresh evidence directory:

```sh
python3 -I -B tests/workloads/hepta_agentd_runtime/run_agentd_runtime.py --execute \
  --input-manifest /absolute/new-frozen-inputs/input-manifest.json \
  --expected-input-manifest-sha256 <frozen-manifest-sha256> \
  --initramfs support/build/evidence/2026-10-16/artifacts/initramfs.cpio.gz \
  --bios /absolute/retained-bios/bios.bin \
  --qemu /absolute/qemu-system-x86_64 --expected-qemu-sha256 <qemu-sha256> \
  --memory-mib 4096 --timeout 600 --output /absolute/new-runtime-evidence
```

The original initramfs must hash to
`86be65ab9234cd20ea6ec8d44a12b8765fd7a3e241fde920c71b3621ca0047f3`;
the BIOS must hash to
`1a9ea4f17bcfb27bda5728e2c21d9fa074cf7947b9b4910bb28213a735c96735`.
The runner preserves all original initramfs entries and inserts the launcher
before the existing ordinary boot success marker.

ELF metadata is inspected with `readelf`, never `ldd`. The three original
executables and their deduplicated x86-64 GNU loader/library closure go onto a
fresh ext2 payload image. The image is read-only both in QEMU and at the guest
mount. All original owner state goes onto a separate fresh 256 MiB writable ext2
disk. The launcher creates `/state/probe` with mode 0700 and requires that it did
not already exist. The actual original fixture requires an empty canonical
private directory before constructing the registry.

QEMU uses one vCPU, q35/TCG, no NIC, no monitor, no host directory share and no
inherited provider/authentication environment. It never mounts a filesystem on
the host. The fixture receives only a small explicit guest environment; the
original driver subsequently assigns registered child identities.

The host deadline is bounded to 120–900 seconds, serial capture to 8 MiB, emitted
fixture stdout to 512 KiB and stderr to 64 KiB. Guest diagnostic files share the
bounded state disk. The launcher preserves actual exit versus signal status;
the host requires ordinary QEMU exit 33, exactly one begin/boot sequence, the
current nonce, successful child and launcher status, the full original lifecycle
records, unchanged frozen inputs and unchanged read-only payload. Any timeout,
panic, repeated/stale marker, unexpected stderr, missing phase, changed PID,
invalid generation, or scope escalation fails.

Evidence includes `result.json`, raw `serial.log`, decoded fixture streams when
available (also on failed child exit), exact invocation/compiler/formatter
commands, both build receipts, runtime library identities and hashes, and the
fresh state image before/after hashes. A changed state image is not a power-loss
durability proof. Preserve the actual state image if diagnosing owner/store
failures; never promote a failed run by editing its report.

## Host validation and remaining native work

Run the host contract tests and compile the launcher without executing it:

```sh
python3 -I -B -m unittest discover -s tests/workloads/hepta_agentd_runtime -p 'test_*.py' -v
python3 -I -B -O -m unittest discover -s tests/workloads/hepta_agentd_runtime -p 'test_*.py' -v
python3 -I -B -m unittest discover -s tests/workloads/hepta_agentd_abi -p 'test_*.py' -v
gcc -O2 -std=c11 -Wall -Wextra -Werror -static \
  tests/workloads/hepta_agentd_runtime/agentd_runtime_probe.c -o /absolute/new-launcher.elf
readelf -lW /absolute/new-launcher.elf
```

These tests include the real retained initramfs transformation and dependency
inspection of real host ELF files as data. Their fixture observations are
explicit synthetic unit inputs. They do not run Agentd or substitute for a
guest execution. The host workflow retains this scope. The separate native
workflow must produce its own real build and guest receipts before native
lifecycle status can be advanced.

After this slice obtains its own real guest receipt, F1 still needs separate
original-store crash/restart and writer-lock evidence on the same source pair.
Production grants, final execution role admission, canonical K↔D replay and
retirement, aggregate memory accounting, autonomous recovery, real GPU/ARM/mobile
execution and hardware input each retain their own acceptance gates. This runner
does not add a second owner or fabricate those missing production inputs.
