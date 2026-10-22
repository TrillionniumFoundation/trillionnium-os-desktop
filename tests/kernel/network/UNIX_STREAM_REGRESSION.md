# AF_UNIX shutdown and auxiliary-data regression

## Defects and implementation

The stream fast path previously cached the readable byte count before reading
the peer's shutdown flag. A peer could publish bytes and then shut down between
these observations, allowing an empty cached count to become an incorrect EOF.
`EndpointReadSnapshot` captures shutdown before any buffer-length observation
used by that read. The consumable snapshot preserves the existing generic
`Endpoint::read_with` interface for pipes and makes the ordering explicit for
the stream path. The byte-count Acquire still precedes the auxiliary-data flag
load; ancillary data publication retains its original ordering.

The stream auxiliary-data loop also lacked an exit after a successful zero-byte
read when credentials were compatible with the default credentials and peer
shutdown was already visible. It now returns the accumulated bytes and control
messages when no progress remains. Sequence-packet handling still processes
zero-length packets, peek behavior remains non-consuming, and rights transfer
uses the existing original ownership path.

The first native syscall run also exposed a per-operation nonblocking bug:
`recvmsg` always used the socket's file-description blocking mode and ignored
`MSG_DONTWAIT`. An open, empty blocking socket therefore slept instead of
returning EAGAIN. The stream/sequence-packet receive entry point now attempts
that operation directly when the flag is present, preserving the shared
blocking mode, receive timeout and all control-message handling. The unchanged
`open_empty` regression observed this failure under the original 20-second
alarm before the fix. The runner pins this third production source file across
the positive and all three qualification variants.

The first stale-snapshot control then reached a real premature EOF after a
successful 96-byte peer write and shutdown, but its queued-data witness failed:
`FIONREAD` returned `ENOTTY`. That run remains an unqualified negative because
the original oracle requires the actual remaining byte count. The stream and
sequence-packet socket now implements the existing typed
`GetNumBytesToRead` ioctl. It reads the receive queue length while holding the
original reader lock, returns zero for an unconnected socket, and rejects a
listening socket with `EINVAL`. It releases the socket and reader guards before
copying the count to userspace. Sequence-packet counts include all queued data
bytes, including the packets after the first; empty packets add no bytes.

The eight positive cases additionally check this ioctl before and after real
reads, peeks, shutdown, empty packets, packet truncation, and invalid copyout.
These are extra syscall assertions inside the existing cases. The protocol,
original shutdown-race function, semantic-negative oracle, 64-iteration race
bound, and 20-second process alarm are unchanged. New source and probe pins bind
these assertions consistently across the positive and three control kernels.

These are socket correctness changes. They do not themselves qualify original
Agentd shutdown, production authority, native HOS2 effects, or persistent Hepta
recovery. Those gates retain their independent original-owner lifecycle tests.

### Source ownership and concurrency contract

| Owning source | Responsibility | Contract retained by this change |
| --- | --- | --- |
| [`fs/utils/endpoint.rs`](../../../kernel/asterinas/kernel/core/src/fs/utils/endpoint.rs) | Publish shutdown and create the consumed `EndpointReadSnapshot`. | A shutdown Release publishes writes completed before it. The peer takes its Acquire snapshot before observing the read data. The existing generic `read_with` interface used by pipes remains available. |
| [`unix/stream/connected.rs`](../../../kernel/asterinas/kernel/core/src/net/socket/unix/stream/connected.rs) | Observe the receive queue, preserve auxiliary-data boundaries, consume reads, and expose the queued byte count. | The reader owns the same receive lock; byte-count Acquire still precedes `has_aux`. Stream zero progress returns bytes/control already accumulated. Packet boundaries, peek non-consumption and original descriptor ownership remain in their existing paths. |
| [`unix/stream/socket.rs`](../../../kernel/asterinas/kernel/core/src/net/socket/unix/stream/socket.rs) | Select per-operation receive behavior and dispatch the typed queue-length ioctl. | `MSG_DONTWAIT` performs one original receive attempt without changing shared file-description flags. FIONREAD copies the observed count after socket/reader guards have been released. |

The snapshot prevents a later shutdown observation from reinterpreting an earlier
empty queue length as EOF. A snapshot taken before shutdown can still return
EAGAIN for an empty observation, after which the existing retry/poll path applies.
The publication argument concerns writes completed before shutdown; it does not
turn the endpoint into a new serialization mechanism for a sender already racing
past its shutdown check. This regression also does not establish absence of
independent signal, poll wakeup, scheduler or runtime-shutdown defects.

FIONREAD is an instantaneous queue observation, not a reservation against another
reader. The race negative makes its queue witness after the real producer has
completed and been reaped. A missing ioctl, failed copyout or unrelated errno
cannot stand in for the required 96 queued bytes.

## Executable regression

`unix_stream_probe.c` makes actual Linux system calls. Its default eight cases
cover open-empty EAGAIN, queued bytes before shutdown, partial reads and peeks,
credential-only exhaustion, credentials, SCM_RIGHTS with the same underlying
object and close-on-exec, sequence-packet boundaries including an empty packet,
and sequence-packet truncation. The optional `shutdown_race` case uses a real
forked writer, a start barrier, a bounded producer delay, write/shutdown results,
waitpid status and FIONREAD. Every payload byte is checked in the C process.

The protocol has a per-boot random nonce, a consecutive sequence number,
bounded ASCII records, exact field sets, the actual process identity, and an
independent shell-recorded process exit. `unix_stream_oracle.py` requires the
complete selected case sequence, original boot markers in order, QEMU exit 33,
and no deadline, output-bound or fatal-kernel failure. Its synthetic test
fixtures are parser/rejection tests only; they never establish native execution.

`run_unix_stream_guest.py` requires a clean reviewed Git head and tree. It
checks the source bytes and file modes against every tracked Git blob, builds
through the original ordinary product wrapper, verifies the generated lock and
first boot, then injects only the static probe and a bounded shell invocation
into that boot's original initramfs. The second boot uses the exact same kernel,
QEMU and BIOS. It has one TCG CPU, 512 MiB RAM, and no attached host disks or
network. Serial capture is bounded while QEMU runs. Source and boot input bytes
are checked again after execution.

From the reviewed checkout, with the existing pinned kernel build environment:

```sh
python3 -B tests/kernel/network/test_unix_stream_guest.py
python3 -BO tests/kernel/network/test_unix_stream_guest.py
python3 -I tests/kernel/network/run_unix_stream_guest.py \
  --expected-source-head REVIEWED_COMMIT \
  --expected-source-tree REVIEWED_TREE \
  --target-dir /absolute/task-owned/target \
  --output /absolute/new/evidence
```

The target and evidence directories must be outside the source checkout.
The output retains the actual source snapshots, ordinary build and boot logs,
generated lock identity, static probe, injected initramfs, serial stream, tool
identities, and final structured result. A failing build or guest remains failed.

## Qualification-only controls

The patches in `controls/` are applied only to separate disposable worktrees.
They never belong in the positive production kernel. The runner separately
pins each source variant and requires the selected probe case to match it.

| Variant | Selected case | Required actual result |
| --- | --- | --- |
| `positive` | `all` | All eight complete syscall cases, actual process exit 0 |
| `race-fixed` | `shutdown_race` | All 64 iterations, at least one real peer write/shutdown scheduling window, process exit 0 |
| `race-stale` | `shutdown_race` | Same real scheduling window, successful reaped 96-byte writer, premature zero-byte read while FIONREAD still reports 96, process exit 1 |
| `aux-zero-progress` | `credential_only` | Three actual zero-progress loop iterations after the 13-byte payload, the specific bounded ELOOP result, process exit 1 |

The race control yields after an actual empty byte-count observation so the
original peer can write and shut down; it creates no substitute data or success
result. The stale variant moves only the snapshot back across that observation.
The auxiliary control restores the old missing exit and observes three real
unchanged iterations before a diagnostic ELOOP. Arbitrary timeout, panic,
producer failure, different errno, missing writer witness or absent scheduling
window does not pass either negative control.

Use `--variant` and `--selection` to select the table's exact pair. Commit each
isolated variant before invoking the runner, and retain its source head/tree
alongside the positive source. Run full aster-core tests because the shared
Endpoint abstraction also serves pipes. Qualification is complete only after
the full core run, ordinary positive, scheduled positive and both distinct
semantic negatives have been inspected; host compilation and synthetic oracle
tests are not substitutes.

## Development and evidence maintenance

Keep the probe, protocol and oracle as independently identified inputs. When
adding syscall assertions inside an existing case, retain the original protocol
and negative predicate or document the exact separate change before execution.
The final FIONREAD probe adds assertions and therefore has different source and
ELF bytes from the earlier probe; its positive and control lanes must all use the
same final identities. Earlier runs keep their earlier identities.

An evidence record must include the full raw serial, nonce, independent process
exit, ordinary first-boot identities, source head/tree, production source pins,
probe/tool/kernel hashes and unchanged-input checks. Replaying the original
oracle must reproduce its complete structured result. Each control also needs
its actual narrow source diff and a verified return to the positive source.

Preserve unsuccessful attempts separately: a process alarm is a failed test,
ENOTTY from a required queue witness is an unqualified semantic negative, and a
rustfmt refusal is a pre-execution failure. Later success must not rewrite any
of those records. State explicitly whether source snapshots and executable bytes
were reopened during independent review or only identified by a retained archive
manifest. A docs-only follow-up commit does not change the tested source identity
or establish a new combined release qualification.


## Recorded native qualification — 2026-10-22

The [preserved experiment and independent replay](../../../results/integration/2026-10-22-unix-stream/README.md)
bind the uninstrumented positive to source
`b824d80d44456c131a6cb9d4fcc84be95c6af273`, tree
`506d583455fa5ea2cf0c18fe10ed42c3874f7556`. All current syscall lanes used
the final FIONREAD probe ELF `701821798ff6b052aa7e2b0dd0da238ef517adf0313ad9d50175f40ebecaa56e`,
the original protocol/oracle, one TCG CPU and 512 MiB RAM.

| Actual lane | Preserved result |
| --- | --- |
| Complete aster-core | 274/274; zero failed, filtered or soft-skipped; QEMU 33. Original core environment and launch records bind it to the same positive source. |
| Ordinary positive | Eight cases, 47 records, child exit 0, QEMU 33; syscall guest 1.443 s. |
| Scheduled `race-fixed` | All 64 iterations and 64 actual scheduling windows, 131 records, child exit 0, QEMU 33; 2.156 s. |
| `race-stale` negative | Iteration 0, actual 96-byte producer and successful reap, premature EOF with FIONREAD still 96; exact failure, child exit 1, QEMU 33; 1.385 s. |
| `aux-zero-progress` negative | Exactly three real zero-progress iterations after 13 bytes, exact ELOOP failure, child exit 1, QEMU 33; 1.318 s. |

All four current syscall lanes completed without a deadline or output-bound
failure. Each had its own successful ordinary first boot and complete unchanged
source snapshots. Reconstructing their Git trees shows that each qualification
control changes only `connected.rs` from the positive. Both the frozen source
patch and the actually executed Git diff reproduce the same archived postimage.
The original execution records retain restoration to the clean positive source.

The evidence also preserves the v2 alarm exit 124, the unqualified v3
`race_fionread`/ENOTTY failure and the v4 pre-execution rustfmt refusal. The
primary replay keeps its original bytes; the separately recovered v4 command,
exit and stderr have their own supplementary review. Earlier probe identities
are not transferred to the final FIONREAD probe. Host compatibility runs remain
host evidence.

This completes the directed AF_UNIX gate above for this source. It does not
complete original Agentd shutdown, HOS2/G2, full E, a combined cross-branch
release, full A06/OSTD/SMP, display/input or physical-device qualification.
Future implementation changes require a new same-source run of the relevant
original gates; this documentation commit is not another kernel execution.
