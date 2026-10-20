# A01 → A04/A05 real Linux ELF guest handoff

The fixed Asterinas kernel actually executed the current A04 C ELF workload.
The unmodified A04 sequential suite failed: it timed out at 180 seconds after
8 exact matches, 1 completed failure and 19 unobserved packaged cases.
An independent fresh-guest diagnostic completed all 28 case attempts:
**24 exact matches, 2 completed failures, 2 timeouts**. This is not a full pass.

## Fixed inputs and real environment

| Input | Identity |
|---|---|
| Full Asterinas v0.19.0 upstream | `c4b7ed575b7b32773475b194d2ad41fb6d03765b` |
| A04 PR #8 source used | `16d672881909a5a9197d82126032b7d962db7d76` |
| Executed accepted A01 kernel, uncompressed | `e884f5e50cf296833276016894a39337cd9ac13bc51f6b1f2dea3cc3a6904b63` |
| Original accepted A01 initramfs | `86be65ab9234cd20ea6ec8d44a12b8765fd7a3e241fde920c71b3621ca0047f3` |
| Current A04 rootfs USTAR, 8,837,120 bytes | `df8df2e3cdcd308ef62a59268a4519e2923c9ff78145e46f26a4092725e80797` |
| SeaBIOS | `1a9ea4f17bcfb27bda5728e2c21d9fa074cf7947b9b4910bb28213a735c96735` |
| QEMU executable | `8a35ccba41582fc6c38b9df85fc9e35fa1d42f414d2d7d8090ee9b2f5e7c0854` |

Actual host: Ubuntu 24.04 userspace, Linux 6.18.44 x86_64; QEMU 8.2.2,
q35/TCG, CPU `max`, 1 vCPU, 512 MiB, fixed SeaBIOS, serial stdio,
ISA debug exit. No network, host data disks, KVM or ISO installer was used.
The guest kernel was built earlier with the pinned nightly-2026-07-21 and is
the already retained, accepted A01 Rust kernel artifact; this replay did not
rebuild or substitute a Linux kernel.

All 11 retrieved A04 source files were verified against their exact Git blob
identities. The current rootfs passed the original A04 strict tar verifier:
17/17 regular-file bytes, sizes and modes, with exact directory closure.
The old `8c7522ac…` tar was correctly rejected against the current manifest;
its 15 matching files do not make its two older probe ELF current.

## Results and evidence boundaries

`original-suite-status.json` and the raw-log archive preserve the unmodified
`replay_qemu.py` invocation: wrapper exit 2, raw QEMU status `null` because of
the real 180-second timeout, original 28-case initramfs SHA `f92af9aedb59ac3a829f7c3cf90797b71356d1a77a08b9729a2de0cb778d3075`.
The parser's `not_run=23` consists of 19 packaged C cases plus four unported
Python/Tokio workloads; they are not 23 additional C failures.

The authoritative `isolated-cases-03` run uses
`a01-a04-isolated-case-v1`: each case has the same pinned ELF bytes and
independent Linux reference facts in a fresh guest, maximum two concurrent
guests, 30-second timeout each. It calls A04's unchanged pack, parser and QEMU
command APIs. Its 24 matches each have raw QEMU exit 33, completed case
markers, ELF exit 0 and full JSON facts equal to the Linux reference.
Both `fd_limit` variants exit 20 while QEMU still exits 33. Both `scm_rights`
variants time out and have raw QEMU status `null`. No timeout is relabeled as
successful execution.

Both static and dynamic SQLite WAL/concurrent commits/crash/reopen workloads
matched. The 24 passing cases also include robust mutex owner death and
recovery, thread/futex joins, pathname AF_UNIX credentials, process
fork/exec/wait, epoll/eventfd/timerfd, file locks, mmap COW and CLOEXEC.
Three Python workloads and Rust/Tokio remain outside the 28 C denominator.
The guest filesystem is volatile RAMfs: SQLite process-crash recovery does
not establish S1 block-media persistence. Hepta W1 was not executed.

## Two concrete A05 reproduction targets

`static.fd_limit` and `dynamic.fd_limit`: `probe.c` lowers only its child's
soft `RLIMIT_NOFILE` to 32, opens files until `EMFILE`, closes held files and
waits for the child. The actual serial shows the child making 256 `openat`
calls and 256 `close` calls after two `prlimit64` calls; the outer probe then
reports the `probe.c:346` wait/status assertion and exits 20. This supports
an unenforced open-file limit. The serial does not directly decode the
child's exit status, so a child exit of 83 is an inference from the pinned C
control flow, not a separately measured value.

Read-only source locations are
`kernel/asterinas/kernel/core/src/syscall/open.rs`,
`fs/file/file_table.rs`, `syscall/prlimit64.rs` and `process/rlimit.rs`.
`sys_openat` inserts a descriptor into `FileTable`; the observed fixed
`FileTable::insert` does not check the process soft limit. Source hashes are
retained and all six inspected kernel files match the fixed upstream checkout.

`static.scm_rights` and `dynamic.scm_rights`: actual serial reports
`unsupported flags: MSG_CMSG_CLOEXEC`, then the receiver performs `fcntl` and
exits while the sender waits for a datagram acknowledgement. The pinned test
requires the received descriptor to have `FD_CLOEXEC`. Read-only inspection
of `net/socket/unix/ctrl_msg.rs`, `FileMessage::write_to`, finds the existing
TODO and insertion with `FdFlags::empty()`; the datagram receiver warns about
unsupported flags. This is a concrete owner-scoped reproduction target.

The same pinned static ELF actually passed both cases on the original Linux
host in this container: raw program exit 0 and all independent reference
facts matched. `linux-host-controls.json` preserves those controls and labels
them host execution. No A05/A06 core or OSTD file was changed. Robust mutex
and thread tests passed here; this evidence does not establish SMP or CPU-quota
behavior for A06.

## Preserved harness and evidence failures

The first independent 28-case attempt recorded 24 matches, but one
`static.ipc_epoll` serial pathname later contained only an earlier boot prefix
and no longer matched its recorded SHA. That run is explicitly **not fully
bound**; its original results and mismatching file are preserved, and the
writer/cause remains unknown.

An intermediate snapshot adapter retained raw CRLF when passing text to A04's
parser; the original `Path.read_text` performs universal-newline conversion.
This caused the exact runner-status regex to reject complete logs despite
passing case facts. The intermediate false results and source are preserved.
An explicitly offline reparse with the original newline semantics confirms
the adaptation error; it is not counted as a new guest run.

The final entry reads original serial bytes through the same open file
descriptor written by QEMU, stores a gzip snapshot immediately, preserves the
raw-byte hash, and normalizes newlines only for A04's unchanged parser. The
new complete `isolated-cases-03` run and final archive validate all 28 captured
serial snapshots and their hashes. The `sqlite_static.sqlite_wal_elf` raw serial
pathname later also differed from its captured bytes; its complete canonical
snapshot remains valid and the divergent raw file is separately preserved. Every snapshot includes its original bytes, including
the two timeout logs. The additional three-case portable-entry validation is
a repeated diagnostic, not three new workload types.

## Reproduction and retained files

Use `support/build/linux-guest/README.md` for fresh-directory extraction and
the original-suite and isolated-run commands. `a04-source.tar.gz` contains
the exact A04 source plus each actually executed adapter version; its member
index records every byte hash. `raw-logs.tar.gz` retains all original serial,
invocation, manifest, result and console records, including failed attempts.
Its member index is independently checked after archive creation.

`rootfs.tar.gz` retains the exact current tar. The already tracked A01 kernel
and original initramfs remain at
`support/build/evidence/2026-10-16/artifacts/`. Duplicate per-guest kernel and
derived initramfs copies are omitted from Git; every derived image's precise
hash and pack manifest are retained and are reproducible using the frozen
pack API and retained inputs. `report.json`, `isolated-summary.json` and the
master SHA manifest identify the final source and measured results.
