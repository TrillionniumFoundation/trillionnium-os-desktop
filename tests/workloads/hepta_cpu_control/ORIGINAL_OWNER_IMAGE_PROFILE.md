# Exact original-owner image experiment

`g2-original-owner-a39-v1` is a separate, default-off image admission experiment
for one measured original Hepta owner. It is not a repair or passing result for
the existing `g2-trusted-daemon` 8 MiB file / 16 MiB LOAD profile. G1-c, G1-d,
ordinary boots, and the legacy G2 selector retain their previous behavior and
do not require a new build input.

The [retained actual size rejection](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/tree/8f2b81541042e330c3aac844b7e68152d4cf217c/results/g2-original-owner-size-20261103)
was executed from Desktop `4dcd02d8058005b92b75b4e997ec4de08833e01d` with Hepta
`a39a0871d9601ffccb5e0d95d8f39d54b3a63360`. Its compiled and stripped original
owner is the only image this new version can admit. The new profile has no
kernel/native/runtime passing receipt at introduction. A successful host check
is not a kernel execution result.

## Fixed inputs and invariants

| Item | Exact value |
| --- | --- |
| Packaged ELF SHA-256 | `6ce96a0785b2cbb51bb71fabb2973c1e04d93e213d56694b42b4d717ed55a454` |
| File bytes F | 20,138,584 |
| Page-rounded LOAD bytes per role L | 20,168,704 |
| Largest page-rounded LOAD range S | 15,323,136 |
| LOAD segments | 4 |
| Private role images | 4: Root, Manager, Workload, Recovery |
| Source-owned descriptor SHA-256 | `138043c29a3d3428fb8b494d6aa40d14b0010f6793a58d1f9ca46892bca5b758` |
| Original userland compiler | Rust 1.96.0 |
| Original kernel compiler | `nightly-2026-07-21` |
| Finite guest configuration | q35, TCG, CPU max, 1 CPU, 512 MiB |

The tracked `original-owner-image-profile.json` fixes the Hepta commit/tree,
original entry, Cargo lock, toolchain manifest, ELF digest, F/L/S and role list.
`support/build/original_owner_image.py` accepts no caller-supplied descriptor
path or numeric budget. It checks the descriptor's complete SHA and compares its
measurements with the kernel's fixed Rust constants. A source-review JSON cannot
enlarge this profile. A changed source, build artifact, or budget requires an
explicitly reviewed new profile/version.

The original Cargo release profile, default features, writer, outbox, SQLite,
target and panic behavior are preserved. A rebuild whose packaged SHA differs
must fail this version even if it is smaller. Do not substitute a fixture or
switch source revisions to obtain a passing image identity.

The kernel still embeds expected bytes, reads the opened executable once,
compares the complete snapshot including its length, drops the input file,
creates independent private RAM VMOs, checks ELF permissions/placement, reads
final mappings back after all initialization, and seals them before activation.
Its original role boot pages and capability/UID boundaries remain unchanged.
Only this feature selects the fixed F/L/S measurements; the old constants remain
8 MiB and 16 MiB for the other trusted profiles.

## Build-time freezing

The core crate's host `build.rs` is inactive for ordinary and legacy features.
For the new feature it requires a regular bounded absolute
`HEPTA_TRUSTED_INITIAL_ELF` input and `/usr/bin/sha256sum` on the Unix build host.
The experimental workflow uses the existing Linux host. No Cargo crypto package
is added by the helper.

The helper reads the source once into a bounded byte vector, feeds that vector
to `sha256sum` through stdin, and compares the complete digest with the compiled
constant. It writes that same vector to a new private temporary file in Cargo's
`OUT_DIR`, changes it to 0444, syncs it, and publishes the final input with a
create-only hard link. It never replaces an unknown existing final file. An
existing final is accepted only if it is regular, has the exact bytes and mode,
and matches this image version. The compiler's `include_bytes!` reads this frozen
copy rather than reopening the supplied source pathname.

An interrupted write can leave a private staging name, but that name is never an
include input. A later invocation uses another create-only staging name. If an
existing final is incomplete, writable, or different, the helper refuses it.
Recovery is to recreate only that invocation's confirmed task-private Cargo
`OUT_DIR`/target output and rerun the same fixed input; never remove a shared
target, overwrite a disputed final, change the digest, or edit original source
to make the check pass. Retain the failed receipt and exact input identity.

The preparation helper disables Python bytecode writes before importing its new
profile module, including when the original `kernel.sh` command invokes it
without `-B`. A clean source snapshot must remain clean after preparation.

## Distinct selectors and receipts

The new kernel selector is `HEPTA_G2_ORIGINAL_OWNER_A39_V1=1`; it forwards only
`--features=g2-original-owner-a39-v1`. Mixing it with any G1-c, G1-d or legacy G2
selector is rejected. The existing wrapper still requires the dedicated guest
runner rather than permitting `kernel.sh run_kernel` to bypass its ordinary
boot gate.

For the existing source-bound entry builder, select
`--image-profile g2-original-owner-a39-v1` in addition to all original explicit
source/toolchain/cache/output arguments. The default remains the legacy profile.
The original compiler and packaging commands remain unchanged. The image check
occurs on the actual stripped output, and before/after tracked-source snapshots
remain mandatory.

| Record | New exact-profile schema |
| --- | --- |
| Source review | `hepta.original-owner-image-source-review.v1` |
| Original entry build | `hepta.original-owner-image-entry-build.v1` |
| Trusted initial manifest | `hepta.g2-original-owner-initial.v1` |
| Actual kernel pipeline | `hepta.original-owner-image-kernel-pipeline.v1` |
| Runtime result | `hepta.original-owner-image-runtime.v1` |
| Per-scenario result | `hepta.original-owner-image-scenario.v1` |

The source review retains the exact Desktop and Hepta identities, original
entry and toolchain fields, and adds the explicit `image_profile` and fixed
`image_profile_descriptor_sha256`. The existing runtime command requires the
same explicit `--image-profile` selection; it does not infer a larger allowance
from incoming JSON. Source review, actual entry build, actual kernel pipeline,
compiled profile, complete trusted manifest, and original ELF must all agree.

The new build result uses `image_profile_passed` and deliberately omits the old
`static_profile_passed` and ambiguous `limits_changed` fields. It records
`legacy_static_profile_passed=false`, `legacy_limits_unchanged=true`, and
`selected_image_limits_differ_from_legacy=true`. `profile_overridden=false` and
`release_profile_unchanged=true` describe only the unchanged original Cargo
release settings. They do not describe success under the old image budget.

An actual kernel-pipeline receipt must be generated by the reviewed source-bound
pipeline from its executed commands, source snapshots, OSDK identity, original
lock, frozen manifest and retained kernel. Naming a new schema in a hand-written
JSON file is not a substitute for that evidence. New runtime qualification must
use newly generated, matching receipts; it cannot relabel the retained legacy
failure or an ordinary F1/Store result. The legacy consumers reject new schemas,
the new profile name and its extra kernel selection marker.

## Memory accounting remains an experimental boundary

The initial image-related capacity calculation is:

`2F + 4L + 2S + 4 * 4096 + 4 * 8 MiB = 185,169,072 bytes (176.59 MiB)`.

It includes one embedded ELF, one shared snapshot retained by the launcher,
four private LOAD images, simultaneous expected/readback vectors for the largest
segment, four boot pages, and full touching of the four 8 MiB stack capacities.
Stack pages are populated on access; this is not an observation that all stack
capacity is initially resident. Role loading is sequential, so four simultaneous
pairs of verification vectors are not counted.

This subtotal excludes other kernel text/data, initramfs and executable/file
cache, VDSO, page tables, slabs, VMO metadata, allocation rounding/fragmentation,
kernel/task stacks, owner threads and heap, SQLite/WAL/cache, controller/history
buffers, and successor retirement overlap. It is not a complete 512 MiB peak or
a memory reservation. Only Workload currently has the fixed 64 MiB selected-user-
frame family account and 256 MiB address-space limit. Root, Manager and Recovery
do not have equivalent fixed accounts in this path; selected-frame accounting
also excludes several kernel allocation classes.

Keep `whole_guest_peak_verified=false`, `global_memory_reserve=false`,
`production_ready=false`, and `g2_complete=false`. Actual guest qualification
must separately measure role memory and allocator low-water/peak information
through initial loading, original writer/outbox initialization, both finite
scenarios and successor retirement. Merely booting with `-m 512M`, or subtracting
176.59 MiB from that number, proves no adequate runtime margin. In this kernel
`MemAvailable` is the same allocator-free figure as `MemFree`, not a reclaim
estimate. Sampled process RSS alone cannot account for all excluded allocations.

### Finite kernel lifecycle observations

This profile now emits at most 64 `[hepta-g2-memory]` records. Initial samples
bracket snapshot retention, each of the four prepared role images, and the
activation before first userspace execution. The original launcher's successor
and history-only preparation paths also sample their own finite lifecycle.
The original allocator and slab counters are read without changing their hot
paths, adding a resource reservation, or granting any authority. Ordinary and
legacy profiles compile without this observation module.

Each record includes its sequence, phase, generation, role/PID, approximate
ordinary allocator free bytes, slab backing bytes, and the minimum free bytes
among those retained samples. A role observation also reads its original
selected-user-frame account. Root, Manager and Recovery currently report
`account_present=false`; their zero account fields must not be read as zero
memory usage. Workload retains its original 16,384-page selected-frame limit.

`native_owner_memory.py` checks the exact record schema, bounded consecutive
sequence, initial role PIDs, causal placement relative to original image and
activation records, the computed sampled minimum and complete successor groups.
The old evidence consumer rejects these new records. The new scenario output
retains all samples under `lifecycle_memory`; it continues to report
`continuous_peak_verified=false`, `whole_process_tree_memory_verified=false`
and `global_memory_reserve=false`. These finite samples can miss transient
allocation peaks, especially while userspace and SQLite run between phases.
They are observations for subsequent sizing, never allocation admission.

Run its inert parser checks with:

```sh
python3 -B -m unittest discover -s tests/workloads/hepta_cpu_control -p test_native_owner_memory.py
```

Actual kernel
compilation and original-owner guest logs are still required to establish that
the sampler executed; the parser test does not provide guest measurements.

## Required validation and present limits

The source/schema regression suite exercises explicit profile selection,
original source binding, wrong-digest refusal at the exact file length, refusal
of an unrelated normal ELF, new/old receipt isolation, legacy parser rejection,
and preparation without new bytecode files. Its inert parser records and normal
host ELF are tests only; neither is original-owner runtime evidence.

Before any guest claim, run the actual pinned nightly host build script against
the real SHA-bound owner and verify the frozen include copy, then resolve the
actual generated product workspace with `--locked` and its selected feature.
The ordinary upstream lock has 235 package records and the generated product
lock has 204; counting records or leaving lock files unedited does not establish
that the new build script resolves successfully. Preserve the original 204-
package product lock and retain the actual metadata/lock result. At introduction
that Rust/locked-graph validation and all kernel/native execution remain pending.

After those prerequisites pass, build the new kernel in a separate private
source/target/output scope and run the original finite owner scenarios with the
matching source pair. Retain failures and source/profile identities separately.
Do not expand the original limits, remove default owner capabilities, or
substitute earlier F1/ordinary-Store receipts if this experiment fails.
