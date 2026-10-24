# Same physical disk, two original-owner boots

`run_native_owner_prior_boot.py` is the separately enabled two-VM campaign for
`prior-boot-unknown-v1`. It consumes the original producer's frozen
`NATIVE_PRIOR_BOOT.md` contract and its getter-only `OperationIntentV1`
observation amendment. Source review and host tests do not establish native
qualification. The existing six scenarios remain a separate mandatory group;
this campaign does not replace or extend their public event schemas.

The acceptance plan has only `schema_version`, `scenario`, and `nonce`. Both
boots use the same plan bytes. The original Root determines Fresh or Retained
from the actual mounted state; neither the plan nor the runner supplies a
claimed phase, issuer, lease, Current, registration, or previous boot identity.

## Required physical execution

The compiled original owner, product kernel, original OSDK build, source pair,
toolchains, source-before/after inventories, BIOS and base initramfs pass the
existing input gates. Every owner ELF still satisfies the original 8 MiB file
and 16 MiB LOAD bounds, with the unchanged release profile and default
features. Both QEMU processes use the original machine, CPU, memory, device,
network, serial and boot flags.

The runner formats one 256 MiB raw ext2 disk exactly once. It holds that host
inode open read/write with an exclusive flock throughout the campaign. Path, host
device/inode, link count, size, filesystem UUID and complete stopped byte hash
are checked before each boot. Each actual QEMU process inherits the same held
descriptor through `pass_fds` and opens `/proc/self/fd/<descriptor>` as its one
original raw virtio drive. A pathname replacement-and-restoration race cannot
redirect that inherited descriptor. A byte
identical copy, replacement inode, hard link, snapshot overlay, recreated
filesystem or changed input hash is rejected.

Copies retained after a stopped VM are forensic artifacts only. No copy is a
boot input. The original raw disk remains the sole execution input. Read-only
filesystem extraction never invokes debugfs with `-w`, and the stopped-copy
hash is checked before and after every extraction stage. The actual execution
inode and stopped hash are rechecked before the second boot. SQLite receives
only another private extraction.

## First actual boot

The original four-role entry performs fresh installation and admits one real
old K/D/request through its original writer, FinalUse owner and FileTransport.
It incurs actual copyout EFAULT after the kernel effect. The existing bounded
callback still holds the original dispatch locks; it does not recursively
inspect the Host's locked writer or publish a made-up Indeterminate receipt.

Within the callback boundary Root observes its actual protected Current,
physical material, original two FinalUse frontiers, independent installation
pin and retained authority observations. It saves one bounded Root-owned
record using the original protected storage primitive and emits the exact
`prior_boot_cut` event. The record is observation, never a second ledger or
authority. A Current token must bind the full original head transcribed by
the actual event.

The host reads a complete matching event line and immediately sends SIGKILL
to that actual QEMU process group. It retains all raw serial bytes, including
bytes already buffered after the cut, the exact argv/input hashes, actual
`-SIGKILL` return status, cut offset/hash, and host monotonic observation and
signal-call times. Host time is not relabeled as guest BOOTTIME. The original
producer must expose its actual cut-emission BOOTTIME and callback deadline;
independent stored-state validation remains mandatory even when the host
reaction was fast. No normal completion or source-terminal event is accepted
after the cut.

There is no verified mapping between host monotonic time and guest BOOTTIME.
`kill_within_guest_callback_window_proven` therefore remains false even when
this campaign succeeds. The original guest callback budget is still at most
two seconds. Acceptance requires the observed durable stopped-state cut below;
it does not infer the exact guest time of host SIGKILL.

After QEMU has actually exited, the runner retains and reads the same disk.
It verifies the Root cut file's original bounded envelope, owner/mode/inode,
physical material hash, independent pin and consumer-local stores. It checks
the old K across the original operation ledger, immutable admission/outbox
pair and all matching source events. The original framed SHA-256 digests and
immutable binding must agree. A terminal anywhere in this K's event history
is a failure; querying only the latest row is insufficient.

Both the exact retained material and the active original SQLite database are
checked. Active database reads include the actual WAL rather than silently
opening the main database with `immutable=1` and discarding committed WAL
frames. Any scratch copy used by a read-only SQLite reader is explicitly
forensic; authoritative DB/WAL bytes and the raw disk must remain unchanged.
This rejects a late kill whose old archive is still Unknown while the live
database has already appended a terminal.

This fault is termination of a QEMU VM process. It does not qualify physical
host power loss, storage-controller cache loss or hardware durability.

## Second actual boot

The first post-kill disk hash is the exact preimage of the second boot. There
is no intervening mkfs, image replacement, logical database repair, authority
reset or substituted Current. The actual new proc boot UUID must match the
new kernel bootstrap/QueryAbi bytes and differ from the first boot.

The original Root cold-open path must validate the existing installation pin,
clock highwater, lease registry, canonical issuer/writer state, complete
protected head and exact retained physical cut. It must preserve the issuer
key and the original consumer-local files and frontiers, use the original
prior-boot retirement API and canonical registry pair boundary, and admit the
new Host only through the strict original factory. The independently saved
token from the first boot must match the actual previous head. New writer
generation, publisher epoch and adoption counter follow the original factory;
the runner does not synthesize any of them.

The recovered writer's lease now also commits to its original checkpoint
activation witness: complete candidate, whole previous token, exact material
anchor digest, and the actual new Root and publisher lifetimes. The second
transcript reconstructs that exact commitment from the actual authority DTO;
it accepts no older payload form. The independent stopped-disk reader opens
the hash-derived original witness and its Root-private lock in
`protected-source/authority/checkpoint`, checks complete saved payload bytes,
and hashes the original predecessor material. A directory scan never chooses
the candidate. The fresh first boot has no recovered activation witness.
These checks supplement, and do not replace, the original key/highwater,
complete registry, full head and DB/WAL checks described below.

Before the normal monitor starts, the original writer captures the real old
retained operation. Its K, D and canonical request are unchanged and its state
is Indeterminate. A dedicated original command then invokes the real device
observer. The original adapter refuses the old boot before selecting a
history capability: it sends neither an old Install nor an old Query ioctl.
The complete before/after retained operation and actual FileTransport counts
must prove this. An arbitrary error, current CPU cap or fabricated kernel
Unknown receipt cannot substitute for this observation.

The original adapter's boot refusal maps to `Unavailable`; the original
reconciler appends no source event for that result. The complete old event and
dispatch-claim histories must therefore remain identical across both physical
inspections. Counts are 0 Install / 0 Query before the new effect and 1 / 1
afterwards. The one new successful Install performs its original Query; old
observations perform neither ioctl.

The new original Root policy authorizes an independent new boot/namespace.
One fresh K/D must yield the actual original Applied receipt, durable source
terminal, independently observed Current/material, original history ACK and
a progressing CPU/heartbeat window spanning at least two original periods.
This effect cannot be an old K/D re-dispatch and cannot settle the previous
boot's outcome.

The old operation is checked again afterwards, with exactly the original
drain blocker still present. Completion uses a separate `prior_boot_complete`
event followed by the original sync/reboot path and actual QEMU success exit.
It never claims a successful normal drain, writer release or owner exit-zero.
Final read-only disk inspection must again find the old immutable admission
and no old terminal across the complete event history, while retaining the
new effect's actual terminal and Current lineage.

## Acceptance boundaries

Transport tests, parser tests, source review, host Root tests, ABI probes,
kernel tests and successful builds cannot set native qualification flags.
The eventual acceptance requires both actual QEMU records, both real boot
transcripts and both independent stopped-disk examinations under the exact
compiled source pair. A transcript-only result remains unaccepted.

This campaign can establish preservation of an unresolved old effect plus
new-boot original-owner control on the same retained disk. It does not settle
the old effect, prove unbounded control, qualify physical power loss, or
implicitly qualify the other six native scenarios. Full G2 and production
status remain separate until their own complete real-test gates close.

## Actual execution command

Run from a clean integrated OS checkout containing these modules. All seven
path arguments below must be absolute. The output directory must not exist,
must not overlap a source/build input, and must have space for the original
256 MiB image and independent stopped copies. Select the exact compiled source
pair and actual reviewed original build receipts; the running harness is
recorded separately and may be a later clean commit.

```sh
python3 -B tests/workloads/hepta_cpu_control/run_native_owner_prior_boot.py \
  --execute \
  --desktop-source "$G2_FROZEN_OS" \
  --hepta-source "$G2_FROZEN_HEPTA" \
  --source-review "$G2_SOURCE_REVIEW" \
  --expected-source-review-sha256 "$G2_SOURCE_REVIEW_SHA256" \
  --owner-elf "$G2_ORIGINAL_OWNER_ELF" \
  --owner-build-receipt "$G2_ORIGINAL_OWNER_BUILD_RESULT" \
  --expected-owner-build-receipt-sha256 "$G2_ORIGINAL_OWNER_BUILD_SHA256" \
  --kernel-pipeline "$G2_PRODUCT_KERNEL_DIRECTORY" \
  --expected-kernel-pipeline-sha256 "$G2_PRODUCT_PIPELINE_SHA256" \
  --qemu "$G2_QEMU_BINARY" \
  --expected-qemu-sha256 "$G2_QEMU_SHA256" \
  --mkfs /usr/sbin/mkfs.ext2 \
  --debugfs /usr/sbin/debugfs \
  --bios /usr/share/seabios/bios-256k.bin \
  --timeout 120 \
  --output "$G2_NEW_PRIOR_BOOT_OUTPUT"
```

`--kernel-pipeline` names the complete retained product-build directory;
its expected digest is that directory's actual `pipeline.json` SHA-256.
`--owner-build-receipt` names the actual original builder's result JSON.
Omitting `--execute` only reports that execution is disabled and cannot pass.
There is no CLI to inject prior transcripts, a stopped-state result, an old
identity or a prebuilt passing result.

Before the two actual boots, both original immutable-image negative controls
must reject a one-byte mismatch and truncated owner. Both real boots then
require all four original image admissions, the exact role/isolation checks,
their own complete event sequence, actual exit result, and physical inspection.
Every original build/source/tool/input hash is checked again at the end. Only
that complete campaign may set its scoped `passed` flag.

Run the existing `run_native_owner.py` separately with the same exact original
inputs, a different new output directory, and no `--scenario` restriction so
that all six existing cases execute. Its renewal case retains its own 600-second
outer bound; this campaign retains 120 seconds per boot.

## Retained evidence and interpretation

| Path under the new output directory | Actual evidence and boundary |
| --- | --- |
| `source-review.json`, `source-before.json`, `source-after.json`, `harness-source-*.json` | Original review bytes, complete compiled source identities, separately recorded unchanged harness |
| `owner-build/`, `kernel-build-evidence/`, original owner/kernel/BIOS/initramfs artifacts | Original static build and same product kernel; no ktest ELF substitution or inherited qualification |
| `manifest-byte-mismatch/`, `truncated-snapshot/` | Original loader negative-control argv, raw serial, actual return and retained input hashes |
| `campaign/state.raw`, `state-before.raw`, `format-state.*` | One actual execution inode, one real format, retained pristine preimage; never restored between boots |
| `boot-1/qemu.json`, `serial.log` | Actual inherited FD identity, SIGKILL and raw -9, full serial bytes, exact cut line offset/hash and separate host timing |
| `boot-2/qemu.json`, `serial.log` | The same inherited raw inode, a genuinely new native boot, full original observation/effect transcript and raw 33 |
| `boot-{1,2}/stopped-state.raw` | Hashed copies made only after real QEMU exit; `execution_input=false` |
| `boot-{1,2}/physical/` | Actual read-only debugfs commands, complete stdout/stderr hashes, Root pin/Current/clock/registry/issuer/consumer identities and original observation bytes |
| `physical/result.json` activation witness section | Exact recovered candidate, whole previous token and actual Root/peer commitment, original saved witness/lock and retained predecessor material bytes |
| `physical/retained-sqlite/`, `physical/active-sqlite/` under each boot | Private actual DB/WAL extractions, complete source hash-chain and operation/claim observations; a late terminal in WAL is rejected |
| `result.json` and each boot's result | Scoped campaign result; per-transcript and per-disk readers alone keep `passed=false` and native qualification false |

Physical checks bind the original public installation pin, unchanged private-key
inode (key bytes are never read/exported separately), signed writer registration,
canonical issuer highwater, lease frontier, full checkpoint hash, retained
material path/hash, original FinalUse key-ring and consumed nonce journal.
Both actual consumer directories and their private files remain on the original
state volume. Only the original source-bound cold factory grants authority.

Successful output keeps `graceful_owner_release_verified`,
`unresolved_pending_handoff_verified`, `unbounded_persistent_cpu_verified`,
`original_native_owner_cycle_verified`, `g2_complete`, and `production_ready`
false. The old operation remains an explicit drain blocker. This result proves
neither later graceful handoff with that unresolved work nor complete G2.

## Host regressions

Run the old group and new group separately from the repository root:

```sh
python3 -B -m unittest discover -s tests/workloads/hepta_cpu_control \
  -p 'test_native_owner_prior_boot_*.py' -v

cd tests/workloads/hepta_cpu_control
python3 -B -m unittest -v test_native_owner_evidence test_native_owner_copyout \
  test_native_owner_runner test_native_owner_continuity test_native_owner_state_observations
```

The new group contains actual temporary ext2/debugfs and SQLite/WAL I/O, actual
host child SIGKILL, inherited-descriptor/ABA checks, and inert parser adversaries.
The inert records never enter the campaign's source/build/disk inputs. Actual
host test logs, exit codes, elapsed time and SHA-256 identities accompany the
integration delivery manifest; they are not guest execution receipts.

## Current-source first writer custody

Every current-source native case also verifies the fixed original
`checkpoint-genesis-first-writer-v1.<Agent>` observation, its complete
sequence-one proof, original Genesis record and exact GenesisActivation
commitment. The original initial owner proof SHA and Current select those
files. Later canonical writers and pruned Registry rows cannot replace this
historical lookup. Steady-state and live lost-copyout cases require these
physical files even when they have no later activation witness. The prior-boot
runner preserves all three records and locks across the same disk reboot.

See `NATIVE_OWNER_GENESIS.md` for the exact inventory, current first-payload
contract and independent three-cut runner. The former first-writer cut-only
payload is rejected for this source; earlier case semantics are preserved.
The three additional no-head cases, original component tests and host parser
checks do not qualify any other native scenario or a different source pair.
