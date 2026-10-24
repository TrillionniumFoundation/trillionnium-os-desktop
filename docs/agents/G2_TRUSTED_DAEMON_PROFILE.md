# G2 original-owner initial role profile

This separate, default-off profile supplies the kernel side of the original
Root/Supervisor integration. Its presence and successful compilation do not
qualify a native durable writer, a CPU effect or recovery. The final evidence
must come from the real original Hepta entry and store. The existing G1-d
three-process qualification and its read-only manager history remain separate.

## Actual processes and authority

Before reading the trusted image or allocating any role PID, CapSpace or grant,
G2 requires the original kernel RNG to have a complete hardware seed. The
generator and immutable provenance share the same `Once`; no second RNG,
identity owner or caller-supplied readiness flag is introduced. An uninitialized
RNG, the upstream timestamp fallback, or an unqualified device-tree seed returns
`EAGAIN` and records `entropy-not-ready`. Ordinary diagnostic boots retain the
upstream fallback and do not gain a trusted-session claim from a valid UUID.
The current x86 path uses OSTD's bounded RDRAND interface; it trusts the selected
CPU/hypervisor entropy provider and does not certify arbitrary hardware, VM
clones/resume, an unimplemented virtio-rng seed path or reseeding.

`HEPTA_G2_TRUSTED_DAEMON=1` selects Cargo feature `g2-trusted-daemon`. The final
`minimal.mk` override forwards this feature explicitly into the actual OSDK
build argv and retains that command in `kernel.log`; upstream `FEATURES`
alone is insufficient because the overlay replaces `CARGO_OSDK_BUILD_ARGS`.
The overlay independently rejects mixed G1-c/G1-d/G2 selections and invalid
flag values. The ordinary build still selects no trusted profile. The same
reviewed static ELF is read once, compared byte for byte with the kernel's
embedded input and loaded into four private, sealed VMARs. The original limits
remain 8 MiB of file bytes and 16 MiB of page-aligned LOAD mappings, with no
interpreter, PIE, writable executable segment or later executable mapping.

| Process | Bootstrap role | Kernel capabilities | Initial credentials |
| --- | --- | --- | --- |
| Root, PID 1 | 4 | No CPU or history slot; sealed image is protected from cross-process mutation | Root |
| Manager, actual child of Root | 1 | Observe, manage, original manager history observe/ack | Root for its own device open, then the original Host's UID/GID 60001 |
| Workload, actual child of Root | 2 | None | UID/GID 60002; empty groups and capability sets; NNP; independent session |
| Recovery, actual child of Root | 3 | Independent observe/manage and original manager/recovery history observe/ack | Root for its own device open, then the original Host's UID/GID 60001 |

The workload retains the existing 256 MiB address-space admission and 64 MiB
aggregate user-data frame limits. Its different UID is necessary: sharing the
Host's fixed UID 60001 would permit access to private Host files and signals.
The old G1-d workload's UID remains 60001 in that old profile.

All resource objects, CPU delegations, namespaces, verified image tokens and
first-run claims are prepared before any role runs. The kernel publishes the
real parent and process-group relationships through the original process code.
Root performs the normal first-process device/console initialization; only then
does its startup hook release the three prepared children. The workload receives
exactly the already-open standard handles, with its own file table.

The original Supervisor must perform its real Registry `Starting` transition
and construct its original `SpawnSpec`/process lease. A dedicated driver may
consume one of these actual precreated children and deliver that spec to the
same final process. It must not manufacture a registry generation, write a
fixture `Starting` record, exec the role image or treat an inherited device
descriptor as a grant. Ordinary fork and exec still create no native role.

`/dev/hepta-control` remains root-owned mode 0600. Manager and Recovery therefore
open it in their own final process before dropping privileges in that same
image. The original Root service then verifies the actual four UIDs/GIDs,
empty groups, all five capability sets, NNP, boot/start identity and held pidfd.
The same `AgentdHos2Device` must remain inside the original synchronous FinalUse
effect dispatch. Root cannot open the device and pass its authority to a child.

## Bootstrap v3

The sealed page is still discovered through `AT_HEPTA_BOOT=240`. Version 3
preserves the first 192 bytes' field layout, changes the version and declared
length, and adds the actual Root PID. Unused bytes of the 4096-byte page are
zero. The page discovers already installed slots; its values are not an
authorization API.

| Offset | Width | Version 3 value |
| --- | --- | --- |
| 0 | 8 | `HOS2BOOT` |
| 8 | 8 | Version 3 |
| 16 | 8 | Role 4/1/2/3 for Root/Manager/Workload/Recovery |
| 24 | 8 | Declared size 200 |
| 32–88 | Eight 8-byte words | Existing observe, manage, manager-history and recovery-history slot/generation pairs; zero for Root and Workload |
| 96 | 16 | Actual native boot ID |
| 112 | 16 | Actual Manager image namespace |
| 128 | 16 | Actual Recovery image namespace |
| 144, 152, 160 | 8 each | Actual Manager, Workload and Recovery PIDs |
| 168, 176, 184 | 8 each | Existing 50 ms cap, 100 ms period and 300 s manager lease, in nanoseconds |
| 192 | 8 | Actual Root PID, 1 |

The original G1-d profile continues to emit version 2, size 192, and three
roles. The production device adapter must explicitly validate v3 and its actual
process binding. A copied page, changed role/PID field, stale descriptor,
different Process or later exec must not activate a role.

## Original history acknowledgement

G1-d gives its manager an observer-only history view and gives its qualification
recovery image the acknowledgement authority. That behavior is unchanged.
G2 additionally gives the frozen original Manager owner an acknowledgement
view of its own namespace. Normal CPU delivery can therefore retire a durable
prefix without first killing the writer or exhausting the 1024-entry window.
The Manager and Recovery retain the same original `HistorySlot` and private
`OriginalOwnerAuthority`; no delivery table, frontier or ledger is duplicated.

Every production retirement must originate in the original
`ProductionDurableWriter::retire_hos2_through`. That function rebuilds the exact
immutable terminal prefix, acknowledges the protected whole-owner transaction,
rechecks live original authority and creates its non-serializable
`Hos2RetirementPermit` before the synchronous device call. The unchanged kernel
core still refuses holes, nonterminal entries, foreign namespaces and invalid
frontiers. Root and Workload have no history-ack slot.

The kernel's `HOS2OWN1` claim domain distinguishes this explicitly selected
frozen-owner profile from `G1DQUAL1`. It records a namespace/frontier claim; it
is not a SQLite digest, signature, fsync receipt or proof of a committed Hepta
terminal. The bootstrap log therefore still says `hepta_durability=false`.
Only the original runtime and retained store observations can establish the
durable-prefix property. Tests must demonstrate a real terminal then retire,
and refusal to retire a Pending/Unknown or interrupted prefix.

## Failure and recovery boundaries

Manager now has a separate Process from Root, so its actual exit/kill can fence
its canonical CPU grant while Root and Recovery survive. Recovery retains the
original Manager history. Its new source-writer generation must be assigned by
the original Supervisor and independently authenticated Root Current/material
handoff; the bootstrap does not authorize opening a second writer.

The existing finite lease, 30 s recovery grace and independent 5 s kernel
watchdog are unchanged. A slow original-writer handoff can legitimately occur
after the watchdog restores the conservative cap. Its effect has its own
immutable CPU-owner receipt and consumes the same one-effect restoration
allowance. A later recovery install can then be refused. The new writer must
still query the old Manager D and persist its saved terminal; the current cap
or revision is never a substitute for that historical result.

The old zero-cap and job-stop rules remain: an unclassified zero cap is not
automatically resumed, and the watchdog sends no `SIGCONT`. This is not a new
general-purpose trusted user-pause or `RevokeGrant` API. The profile prepares
one Manager and one Recovery role; it does not silently grant subsequent
ordinary replacement processes. Arbitrary role renewal, repeated recovery
replacement and availability beyond the finite grant remain separate work
until implemented and actually tested.

A reboot invalidates both native namespaces. The original persisted K/D and
payload must survive in the original store, but an old-boot query cannot be
invented from the new boot's cap. Unresolved effects remain unknown and are not
resent. Native persistence tests must identify their actual storage and failure
layer; a clean shutdown or host cache surviving QEMU exit is not power-loss
evidence.

## Build and acceptance

First use `tests/workloads/hepta_cpu_control/build_original_entry.py` to build
and measure the complete tracked original Hepta entry with its original lock,
default features, release profile and symbol packaging. The old 7.26 MiB
`ReadUsage` fixture did not contain the writer or FinalUse and cannot qualify
this image. Only then build the kernel with the exact frozen ELF:

```sh
HEPTA_G2_TRUSTED_DAEMON=1 \
HEPTA_TRUSTED_INITIAL_ELF=/absolute/path/to/frozen-original-entry \
support/build/kernel.sh kernel
```

Use the dedicated source-bound guest runner for execution. At minimum, retain
the following independent observations from the real original entry:

- Four actual processes, parentage and sealed bootstrap; all actual Host and
  workload credentials; workload denial of Host files, signals and HOS2 slots.
- The original Registry/Supervisor generation, protected authority/current cut,
  single original writer, original FinalUse and immutable K-to-D payload.
- Actual CPU application and original saved history; same-D replay and a
  changed-payload refusal without an extra effect.
- Lost response followed by query, a durable original terminal before retire,
  and an unresolved prefix that is neither retired nor resent.
- Actual Manager kill with Root alive, watchdog outcome and independently
  authorized successor writer reconciliation through Recovery's original view.
- Reboot with the real retained original store, old-boot refusal and unknown
  preservation; further recovery/replacement limits recorded explicitly.

The new process-state ktests validate one-time Root preparation, foreign-image
refusal, absence of a Root control slot, and closing/exec cancellation. They do
not replace the loaded-image, original-entry, persistence or recovery boots.
