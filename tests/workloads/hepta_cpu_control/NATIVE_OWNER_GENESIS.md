# Original no-head interruption and same-disk recovery

`run_native_owner_genesis.py` executes one explicitly selected two-VM case.
It is independent of the six-case runner, the two partial-activation cases,
and the prior-boot Unknown campaign. Those nine cases remain mandatory. None
of their results, or the host tests for this reader, qualifies a new native
source pair.

| Explicit scenario | First stopped original authority | Second original first publisher |
| --- | --- | --- |
| `original-genesis-before-writer-v1` | Durable input, initial physical material and pin; no candidate, signature, local writer or checkpoint | Original signature sequence 1, owner epoch 1, Supervisor spawn 1 |
| `original-genesis-writer-reserved-v1` | Original reserve CAS at sequence 1; complete pending claims, no signature or checkpoint | Exact old claims completed at the same sequence as historical evidence; replacement signature sequence 2, owner epoch 2, Supervisor spawn 3 |
| `original-genesis-before-head-v1` | Complete durable original signature at sequence 1; no checkpoint or local writer | The same historical signature is retained; replacement sequence 2, owner epoch 2, Supervisor spawn 3 |

Every second boot first initializes the original checkpoint with publisher
epoch 1, counter 1 and local writer generation 1. An absent checkpoint is
never represented as head zero, a fabricated Current or a generation-zero
writer. The two replacement paths preserve the actual Starting record and
the original Supervisor's Failed-to-Starting transition.

The original entry and product kernel must pass the existing source/build
gates. This runner keeps the 8 MiB ELF and 16 MiB LOAD limits, original release
profile and default features, one reviewed immutable ELF, four original
initial Processes and native capability boundaries. Root sessions remain
120 seconds, writer leases 20 seconds, Manager grants 300 seconds, Recovery
grace 30 seconds and watchdog restoration 5 seconds. Each VM has the existing
outer limit of at most 120 seconds.

## Exact first-boot boundary

The first VM emits exactly one `genesis_cut`. Its phase and complete fields
must match the selected original producer. All four actual immutable-image
commit markers and the original v3 role activation must precede it. Any later
owner event fails the cut. Only the recorded host SIGKILL and actual raw exit
`-9` are accepted for this VM.

For the reserved case, `before_admission` is explicitly the original state
captured after candidate lease publication and before reserve CAS. The later
`reserved_issuer` is the original owner's full protected readback from the
actual reservation callback. These are distinct observations; the reader
does not label the earlier Registry snapshot as simultaneous with the later
callback. The pending record must have exactly the original eight fields,
the initial purpose, previous sequence zero, complete claims, original key,
original admission time, typed preimage SHA and domain-bound signing SHA.
The completed original issuer shape has exactly its original five fields.

The host retains the complete serial bytes, signal call entry/return times
and the exact cut line/offset/hash. It does not map a host elapsed duration
onto guest BOOTTIME. `kill_within_guest_wait_window_proven` remains false.
The semantic boundary is independently proved from the stopped disk: no
checkpoint, no local Host writer or effect, and the exact selected original
authority state. SIGKILL is not represented as hardware power loss.

## One actual physical disk and original material

The runner formats a single 256 MiB raw ext2 disk once, holds its unique
read/write descriptor with its inode lock, and passes that same descriptor
to both actual QEMU processes. The raw/virtio profile is unchanged. Path
replacement, even a path ABA, cannot redirect QEMU to a different inode.
The second boot uses neither a restored image nor an inspection copy.

After each VM has stopped, a separately retained forensic copy is inspected
through a read-only descriptor. Debugfs stdout/stderr and every command,
exit, tool identity, raw inode metadata and extracted-file hash are retained.
SQLite reads a private extraction containing the actual database and WAL.
`immutable=1` is not used. Actual SHM bytes are retained but are not reused as
SQLite input; scratch inspection files are identified separately. No repair,
checkpoint, schema migration or replay writes to the actual state disk.

The material reader takes the exact required schema inventory from the
reviewed, source-bound original `cognitive_store.rs`. It reproduces the
original framed schema and all typed logical table rows, including actual
SQLite schema/migration rows. It checks both the independent Root material
and the original writable initial database against the complete retained
initial cut. An unexpected table, malformed type, omitted WAL, changed
schema/state digest or rollback journal fails.

At the first cut all five original local-writer/operation tables must be
empty: leases, events, outbox, operation ledger and dispatch claims. This is
checked from actual SQLite rows, not a producer boolean. Initial FinalUse
protected frontiers have no claims, and Host-local consumer files do not yet
exist. The original Fleet manifest and each exact lifecycle generation are
checked under their actual Root/group ownership and modes.

The second boot must retain the same original pin, immutable input records,
initial material, source database identity and key inode. Its clock must
cover the last actual retained highwater. No private signing-key bytes are
read or exported. A signed predecessor's complete unretired Agent selection
must be retired by the original revision-checked receipts, with the full
reason commitments and exact protected frontier. Expired rows remain
historical rows; the verifier does not invent a revocation for them.

After successful recovery, the actual new original writer executes one
25 ms CPU-budget operation in the new boot and actual new native namespace.
The gate requires the original Applied receipt, matching K/D, complete
durable terminal, Current/material, history ACK, and real CPU/heartbeat
progress over at least two original periods. It then requires the original
writer's released lease receipt, independently acknowledged released
Current/material, and original Supervisor exit-zero/reap transaction.

The final working SQLite/WAL and retained released material must contain
exactly that original operation, immutable admission, pre-effect
Indeterminate, matching committed terminal and released lease chain. An
optional secondary settled claim is checked when present; the original
writer's best-effort settlement is not used to replace its durable terminal.
The final physical head names the released Current. The producer's existing
`complete` token continues to name its last operation Current.

## Original first signature and exact checkpoint inventory

Current source uses the complete original Genesis activation commitment for
every first writer, including the earlier nine cases. The old initial-cut
digest is not an accepted fallback.

The checkpoint directory is the original protected bind at
`/state/hepta-native/protected/authority/checkpoint`, stored physically under
`protected-source/authority/checkpoint`. Only the exact expected original
frontier, publication locks and observations are allowed. Each observation
is a Root-owned mode-0600 regular file with one link, and its complete original
encoded wrapper is at most 16 KiB. No `.next`, additional unsigned candidate
or arbitrary observation is admitted by an inventory prefix.

Three original immutable records identify first-generation custody:

1. `checkpoint-genesis-v1.<Agent>` retains the actual initial Root, complete
   physical cut, original issuer/key and two original finite policies.
2. `checkpoint-genesis-activation-v1.<candidate SHA>` retains the whole
   original candidate, preparing Root and peer, genesis SHA and optional
   complete predecessor proof. Its finite signed lease payload commits the
   exact original domain and typed tuple; only its own payload field is zeroed
   while checking that digest.
3. `checkpoint-genesis-first-writer-v1.<Agent>` is the fixed historical
   lookup. Its exact payload fields are `schema_version`, `genesis_sha256`,
   `activation_id`, `registration` and `proof`. It always retains the original
   sequence-one proof. It does not become a Current, counter or new authority.

The usual original filename is `observation-v1-<SHA256(logical ID)>.json`,
with its separate `.json.lock`. The fixed first-signature record selects the
first activation from complete signed data even if old Registry leases have
since been pruned. The actual initial owner's proof SHA and Current grant/
fence must match. No directory scan or later canonical writer selects the
first authority.

For first-cut before-writer and reserved cases, the fixed first-signature
file must be absent. It must already exist for before-head. It exists after
all three successful second boots, retaining sequence one even when the
replacement is sequence two. If it existed before the first stop, its full
bytes and inode must survive unchanged. All three second boots retain the
expected first/replacement Genesis activation files and no extra candidate.

The earlier six-case, partial-activation and prior-boot runners now all
perform this first-signature file check, including steady-state and live
lost-copyout runs with no later writer. Their operation, failure, watchdog,
lifecycle and boot rules remain unchanged. The prior-boot campaign also
requires the same genesis/first-signature/first-activation bytes and inodes
across its two actual VMs.

## Actual command and retained results

Freeze a clean harness and both actually compiled source trees first. Fill
all digest arguments with the hashes of the independently retained current
receipts. Use a new output directory for each of the three explicit names;
no failed evidence directory is reused. The command is the same for each
case except its scenario and output:

```sh
python3 tests/workloads/hepta_cpu_control/run_native_owner_genesis.py \
  --execute \
  --scenario original-genesis-before-writer-v1 \
  --desktop-source /frozen/os \
  --hepta-source /frozen/hepta \
  --source-review /evidence/source-review.json \
  --expected-source-review-sha256 ACTUAL_REVIEW_SHA256 \
  --owner-elf /evidence/original-owner.elf \
  --owner-build-receipt /evidence/original-entry/result.json \
  --expected-owner-build-receipt-sha256 ACTUAL_OWNER_RECEIPT_SHA256 \
  --kernel-pipeline /evidence/product-kernel \
  --expected-kernel-pipeline-sha256 ACTUAL_PIPELINE_SHA256 \
  --qemu /usr/bin/qemu-system-x86_64 \
  --expected-qemu-sha256 ACTUAL_QEMU_SHA256 \
  --mkfs /usr/sbin/mkfs.ext2 \
  --debugfs /usr/sbin/debugfs \
  --bios /usr/share/seabios/bios-256k.bin \
  --timeout 120 \
  --output /evidence/genesis-before-writer-01
```

The runner is disabled without `--execute`. Execution requires `--scenario`,
all seven source/artifact/output paths and all four explicit hashes. It
verifies and retains the original immutable-loader byte-change and
truncation negative controls before the campaign.

The output retains `source-review.json` as its original bytes, source and
harness before/after snapshots, original build evidence, actual ELF/kernel/
BIOS/initramfs/tool identities, and reviewed schema source/inventory. Each
`boot-1` and `boot-2` contains `qemu.json`, unmodified `serial.log`, its actual
initramfs, the stopped state copy, the transcript result and `physical/`
inspection records. `campaign/state.raw` is the original two-boot inode;
`campaign/state-before.raw` is only the retained pristine preimage. The top
`result.json` reaches `passed=true` only after both actual exits, both physical
gates and all final source/artifact/tool identity checks succeed.

The named reservation or before-head flag is true only for that separately
executed scenario. `g2_complete`, `production_ready`, hardware qualification,
power-loss qualification and unbounded persistent-control qualification
remain false. The prior-boot Unknown/no-redispatch obligation is a separate
campaign; these no-head cases do not replace it.

## Host acceptance scope

Run the repository modules directly, from this directory:

```sh
python3 -B -m unittest -v \
  test_native_owner_evidence test_native_owner_copyout \
  test_native_owner_continuity test_native_owner_runner \
  test_native_owner_state_observations \
  test_native_owner_prior_boot_evidence test_native_owner_prior_boot_io \
  test_native_owner_prior_boot_store test_native_owner_prior_boot_disk \
  test_native_owner_activation test_native_owner_activation_witness \
  test_native_owner_genesis_record test_native_owner_genesis_store \
  test_native_owner_genesis_evidence test_native_owner_genesis_sql
```

The existing 88 tests remain, with 28 additional checks for exact genesis
records, three transcript branches, original material/journal reads and
first-signature physical inventory. Inert records only exercise rejection
and parser shape. Actual private SQLite/WAL, ext2 and owned host-child tests
exercise the inspection/transport implementation. They do not execute the
original daemon or qualify a native source pair. Actual native runs must
still pass the source-bound static build and each independent QEMU campaign.
