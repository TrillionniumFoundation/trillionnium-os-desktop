# Bounded partition-table discovery

This change fixes the malformed GPT and EBR paths identified in the
2026-10-27 audit, including the divide-by-zero class reported upstream in
[Asterinas issue #4021](https://github.com/asterinas/asterinas/issues/4021).
It changes the original block-device partition scanner. It does not add a
parallel storage stack or perform any on-disk repairs.

## Implementation and publication

[`partition.rs`](../../kernel/asterinas/kernel/core/comps/block/src/partition.rs)
uses the original `BlockDevice::read_bytes` path and checks that the device's
sector count and every byte offset fit `usize` before entering it. I/O errors
are reported through the parser instead of being unwrapped.

[`partition/table.rs`](../../kernel/asterinas/kernel/core/comps/block/src/partition/table.rs)
contains the production decoder, using only `core`, `alloc` and a sector-reader
callback. It decodes little-endian fields from fixed byte buffers. It publishes
only normalized start/length pairs after validating the complete selected
table. Partial results from a malformed chain or failed array read cannot
reach `PartitionManager::update`. The existing scanner's behavior on a failed
scan is retained: it does not replace an existing partition list with partial
new state.

The block API currently defines 512-byte logical sectors; this patch does not
introduce a variable logical-sector-size contract. Buffer allocation in the
underlying BIO path and partition-node registration retain their existing
resource owners. Fallible parser-vector reservation does not qualify the
entire block I/O path under kernel heap exhaustion.

## Supported layouts and limits

| Layout | Validation and behavior |
| --- | --- |
| Legacy MBR | Require the signature, use the LBA fields, ignore unused entries, validate device bounds and reject overlapping primary ranges. CHS is not used to reject valid LBA partitions. Four primary slot numbers are preserved. |
| Extended MBR | Recognize types `0x05`, `0x0f`, and Linux `0x85`. Keep the extended container's primary slot, and append logical partitions from slot 5. EBR data is relative to its own sector; next links are relative to the extended container. |
| EBR chain | Iterative traversal with a shared visited list, at most 256 EBR sectors per disk. Validate each signature, link extent, container bound, and logical range. Reject cycles, EBR sectors inside published data, overlapping logical ranges, and extra active records beyond the canonical data/link pair. |
| GPT header | Require version 1.0, header size 92–512, reserved header word zero, correct header CRC, actual `MyLBA`, and the fixed alternate location. Bound usable LBAs, both table areas, and every entry-array arithmetic operation before reading entries. |
| GPT entries | Support current `128 × 2^n` sizes and legacy sizes that are multiples of eight and at least 128 bytes. Stream across sectors, including entries larger than a sector, and preserve unused slots. Validate each used range and reject overlaps. |
| GPT CRC | IEEE CRC-32 covers exactly the declared header and entry-array bytes. The header CRC word is zeroed for calculation. Partial final-sector padding is excluded from the array CRC; unused entries and extended entry bytes remain included. |

The local discovery limits are **4,096 GPT slots**, **4 MiB of entry-array
bytes per copy**, and **256 EBR sectors per disk**. Exceeding a limit produces
a diagnostic error before unbounded reads or allocation. These are explicit
resource limits, not a claim to accept every theoretically representable
partition table. Normal 128-slot GPT tables and ordinary MBR/EBR chains stay
within them. The result vectors use fallible reservation.

The format reference is
[UEFI 2.11, chapter 5](https://uefi.org/specs/UEFI/2.11/05_GUID_Partition_Table_Format.html).
The minimum GPT-array reserved area is retained even when fewer entry bytes
are used. Decoding larger entries does not allocate an entry-sized buffer.

## Primary and backup policy

Discovery checks the primary header at LBA 1 and the backup at the last
device LBA, never an unvalidated alternate pointer.

- If both copies validate, their disk GUID, usable bounds, entry dimensions,
  array CRC, and decoded partition geometry must agree. A conflict rejects
  the table; the scanner does not guess which valid map is newer.
- If exactly one copy validates, use that copy and emit a degraded-table
  warning. This includes recovery from a primary header or array I/O failure.
- If neither validates, publish no partial map and report the error. A disk
  with neither GPT signature is treated as having no recognized GPT.
- A valid nonprotective legacy MBR takes precedence. This prevents a stale
  GPT backup from being revived after legacy reformatting. A protective MBR
  is recognized in any of the four slots; its other records are not separately
  published alongside GPT partitions.

This is read-only discovery. It never rewrites a primary or backup table.
CRC checks detect corruption; they do not authenticate hostile media. The
agreement check concerns the interpreted map and declared CRC identity, not
a cryptographic proof that all reserved/name bytes of the copies are equal.

## Regression coverage

The production decoder's
[24 named regressions](../../kernel/asterinas/kernel/core/comps/block/src/partition/table/tests.rs)
have both host-test and `ktest` attributes. The fixtures encode their own disk
bytes and CRCs, and a reader can inject real `Result::Err` outcomes. Cases
cover valid GPT/MBR/EBR controls, unused slots, partial sectors, 136/256/512/1024
byte entries, known CRC vectors, malformed dimensions, extreme LBAs, header
and array corruption, valid-copy conflict, read-only fallback, I/O failure,
EBR self/multi-sector cycles, the EBR discovery bound, and data/metadata
overlap. Header mutations additionally assert that no out-of-device read is
requested.

Host execution compiles this exact production decoder through
[`support/build/partition-host.rs`](../../support/build/partition-host.rs):

```sh
rustc --edition=2024 --test support/build/partition-host.rs -o /tmp/partition-host-debug
/tmp/partition-host-debug --test-threads=1
rustc --edition=2024 --test -O -C overflow-checks=no support/build/partition-host.rs -o /tmp/partition-host-release
/tmp/partition-host-release --test-threads=1
python3 -I -B -m unittest discover -s support/build/ktest -p test_partition_gate.py -v
```

The host harness does not replace `BlockDevice`/OSTD with a simulated kernel;
it runs the pure decoder with an explicit input reader. It cannot qualify
the kernel I/O adapter, physical DMA, actual disk reattachment, scheduler,
or a booted kernel. Debug and optimized host runs must be reported separately
from kernel compilation and guest execution.

## Explicit native gate

The optional `aster-block` gate does **not** change the original four-crate
default suite or its denominators. It must be selected explicitly, with no
filter. It uses the same source-built OSDK, fixed N0 q35/TCG, one vCPU, 512 MiB,
SeaBIOS, raw QEMU exit 33, 300-second default timeout, serial hashing and
artifact recording as the original gate. The checker requires all 24 names,
each exactly once with its own terminal `ok`, no soft skips, no substituted
tests, and the complete runner terminator. Seven host oracle tests exercise
the rejection rules and preserve the four-crate default inventory.

On the actual pinned `nightly-2026-07-21` build host, generate the new test-base
lock once from the immutable upstream seed:

```sh
python3 -I -B support/build/ktest/prepare-locks.py --crate aster-block --bootstrap-optional
```

This initial optional bootstrap is explicitly **offline**. It starts from
the same original tree/blob/lock SHA as the existing preparer, runs Cargo
metadata, repeats it with `--offline --locked`, and audits every resolved
package. Only `aster-block-osdk-bin 0.1.0` may be added to the original seed
package set. No external version, source, checksum, `os-control`, or another
crate's test-base may be substituted. An absent cache entry fails; prepare
the original audited dependencies on the build host before retrying. This
option cannot be used for any of the original four suites.

Review and retain the actually generated
`support/build/ktest/locks/aster-block.Cargo.lock` and `aster-block.json`.
After that first generation, the normal explicit preparer uses the new
audited lock for its locked prefetch:

```sh
python3 -I -B support/build/ktest/prepare-locks.py --crate aster-block
python3 -I -B support/build/ktest/run.py --crate aster-block --output /absolute/new/partition-ktest-evidence
```

Use an isolated source checkout/target and build OSDK from that same source
path. The runner refuses an existing output directory and keeps its normal
source-verification and workspace lock. It verifies the OSDK-generated lock
against the selected block test-base lock after the run. The optional result
qualifies only the stated decoder suite; `check-report.py` continues to
require the original four crates for a complete default report.

The first local implementation check used Rust 1.99.1: all 24 decoder cases
passed in debug and optimized builds (with overflow checks disabled in the
latter), and all seven gate-oracle cases passed. Three unrelated stale
CPU/G2 fixtures failed on both that worktree and the untouched `94234e6a`
baseline. A separate fixture correction preserved the production 377-test
gate and original inventories; the integrated host directory then passed
all 41 cases.

The subsequent [2026-10-27 pinned execution](../../results/integration/2026-10-27-partition-validation/README.md)
used Desktop `d343c35da641f86a3fa0ff6c4293d4948bbe0b2e`, with only the two
newly generated block test-base files untracked. Original nightly Cargo
generated the 118-package lock from the immutable seed with no external
drift. The same pinned nightly passed the 24 host cases, built the original
OSDK from that checkout, compiled `aster-block`, and ran all 24 required
cases in the real q35/TCG/one-vCPU guest: zero failures, filtered cases or
soft skips, raw QEMU exit 33. The recorded raw serial and QEMU evidence
revalidate with the original checker. Original kernel and OSDK locks remained
unchanged. These are kernel-mode parser tests using controlled readers;
physical-media, virtio I/O, DMA, power-loss, SMP and whole-product acceptance
remain separate. A06 CI now selects this optional suite explicitly in
addition to its unchanged four-crate default gate.
