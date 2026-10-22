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

These are socket correctness changes. They do not themselves qualify original
Agentd shutdown, production authority, native HOS2 effects, or persistent Hepta
recovery. Those gates retain their independent original-owner lifecycle tests.

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
the actual positive and both distinct semantic negatives have been inspected;
host compilation and synthetic oracle tests are not substitutes.
