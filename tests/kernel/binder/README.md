# Limited Binder guest qualification

`run.py` compiles `binder_probe.c` as a static program and runs it only inside an
ordinary Asterinas QEMU guest. The inherited safety runner retains source bytes,
compiler output, exact kernel/initramfs/firmware hashes, raw serial output and a
fresh run nonce. It neither executes the probe on the host nor attaches host
storage or networking to the guest.

The implemented profile is described in
[the development and technical document](../../../support/android/BINDER_BYTES.md).
The actual-thread D1 contract is in
[BINDER_THREADS.md](../../../support/android/BINDER_THREADS.md). It adds up to
eight real participating threads per original Process/image/open, with shared
sixteen-event and sixteen-buffer bounds. It uses manual workers; automatic
registration/spawn, nested/oneway calls and Android boot remain unimplemented.
This gate is independent of the historical A08 primitive ioctl/layout checks.
A byte-only pass does not qualify object IPC. `object_run.py` runs both the
original byte/budget probe and the three-process object/handle probe against the
same ordinary kernel. It now also runs `fd_probe.c` for actual open-file transfer
and failed receive cleanup. These gates still do not qualify Android boot,
FD arrays, thread pools, Android service registration, SELinux
policy, or a Hepta device effect.

Run from this checkout with its own source-built OSDK, pinned toolchain, external
private build cache, the fixed vDSO directory, and at most two compiler jobs:

```sh
python3 -I -B tests/kernel/binder/run.py --smp 2 --output /absolute/new/evidence
```

The driver uses actual process and thread allocation identities, so the probe
opens a fresh endpoint in each process. It intentionally tries an inherited
parent endpoint and expects rejection. The server response is checked by the
other process using bytes read from the real receive mapping.

## Page-budget integration regression

The full probe also includes a receive-mapping admission failure. Its separate
`--budget-only` runner option selects this same case without the transaction
suite. A child enters a real capped cgroup, reserves all 16 receive frames, and
maps across a PML4 boundary with budget for only the first three new table pages.
The mapping must return ENOMEM, increment the denial event, release every receive
data frame after actual reference destruction, and permit the same endpoint and
address range to be mapped successfully after the ceiling is lifted. Charged
empty table nodes may remain; the probe does not pretend those nodes were freed.

This case actually reproduced an integration bug: the Binder caller ignored
`MapHandle::map_frame`'s newly fallible return value and reported mmap success.
The driver now propagates the error before publishing its receive area. The
existing VMAR error path removes its mapped prefix. The before-fix failure and
after-fix passing guest evidence are separate. Two earlier fixture failures
(missing parent controller activation and cold stderr/TLS COW at the ceiling)
are retained and are not counted as reproductions of the product bug.

## Actual object/handle gate

```sh
python3 -I -B tests/kernel/binder/object_run.py --smp 4 --output /absolute/new/evidence
```

This gate validates strong/weak local objects, per-endpoint handle namespaces,
three-process forwarding and return to the original node, nonzero strong-target
calls, buffer ownership and explicit reference retention, precise owner reference
notifications, malformed input/underflow rejection, copyout retry and old-owner
death without identity reuse. Its helpers consume and acknowledge actual BR
reference work; they never inject a synthetic kernel result. Guest fixtures have
an alarm bound and are only compiled on the host.

The FD probe uses original open files and pipes, not a proxy. It verifies
acceptance rules, CLOEXEC, shared offsets after source FD reuse, two-FD EMFILE
rollback, repeated EFAULT with the same hidden reservations, installed descriptor
lifetime after FREE/endpoint close, prepared-close release and 128 concurrent
enqueue/request/reply cycles. An ordinary-byte-only invocation does not validate
these additional capabilities.

The same runner includes `cleanup_probe.c`: 256 real queued snapshots saturate
the global prebuilt-cleanup permit bound, a further snapshot is rejected before
publication, and later actual FD transfer recovers. A real TCP SO_LINGER baseline
must take at least 1.5 seconds; cleanup of an equivalent prepared socket must
leave independent descriptor refunds and pipe EPIPE below one second. No mocked
file destructor or host network is used; the sockets use guest loopback only.

## Death subscription gate

`object_run.py` also compiles `death_probe.c` for real owner/subscriber processes.
It verifies SIGKILL/exec identity, wrong-cookie and duplicate acknowledgement
rejection, 32-record saturation/refund, attached last-reference cancellation,
CLEAR-detached owed handshakes, small reads, EFAULT retry, poll and preserved
ordinary requests while their admission queue is full. Sixteen actual child
close/CLEAR races report which legal ordering occurred; deterministic death-first
cases still require Dead → Done → ClearDone. Unique cookie restrictions remain
deliberate. These older probes do not replace the separate actual-thread suite.

## Actual-thread ownership and lifecycle

```sh
python3 -I -B tests/kernel/binder/thread_run.py --smp 4 --output /absolute/new/thread-evidence
```

`thread_run.py` executes three probes: two actual callers/workers sharing opens;
explicit and actual thread exit with real objects, FD rollback and terminal
capacity; and prepared node/death work handoff after its reader exits. The
single prepared transaction slot still retains an EFAULT descriptor for its
original thread only, so siblings can receive EBUSY until retry or retirement.
Normal active copying uses bounded admission and signal-aware waits; consumed
commands are never replayed. See the D1 contract for the full lock/lifetime and
fallible pre-publication queue-storage rules.

Both thread and object runners accept `--product-evidence` for a successful
exact-source ordinary product receipt. Omit it to use their original self-build
path. The [documentation supplement](../../../docs/agents/MODULE_DOCUMENTATION_2026_10_26.md)
records the separate `d3ae4b9a` reception and the limits of those actual runs;
this runbook does not qualify an Android service manager or automatic pool.
