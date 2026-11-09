# Production identity input validation and sealed development handoff

The current patch targets the actual identity source commit
`b4dc3b49ce29e706efca0ba5a7c775864d9b54b8`. It preserves that owner's 19 identity
tests and adds shared input admission and immutable development-entry transport.
These are source repairs. The executing production backend, production UID/GID
mapping, applied seccomp, Android runtime and application acceptance remain
unqualified.

## Changes and admission boundary

- Shared CellSpec validation rejects UID/GID intervals that include the reserved
  unmapped ID u32::MAX. The highest valid interval ends exclusively at that
  value. Invalid specifications fail before any backend operation.
- Identity authority opens retain their held-parent, ownership and O_NOFOLLOW
  checks and use O_NONBLOCK so FIFO substitution reaches the inode-type veto
  without waiting for a writer.
- CLI and daemon use one bounded reader. A single nonblocking open is followed
  by fstat of that held regular file and an actual limit of 1 MiB plus one
  rejection byte. Changed ownership, permissions, length or modification
  metadata fails closed. A stalled remote regular-file I/O operation has no
  newly claimed wall-clock deadline.
- Non-root daemon peers retain the existing root-owned, non-group/other-writable
  specification policy inside the configured directory. Canonical directory
  aliases remain compatible; the admitted directory walk refuses replacement
  symlink components and the final file may not be a symlink. The ownership
  check and read use the same descriptor. CellSpec and peer-UID authorization
  still precede activation.
- The development parent serializes the already authorized value into a memfd
  with F_SEAL_WRITE, F_SEAL_GROW, F_SEAL_SHRINK and F_SEAL_SEAL. It does this
  before host setup. The parent descriptor remains CLOEXEC throughout; an
  appended pre-exec hook changes only the spawned child's descriptor table.
  Existing affinity and parent-death hooks remain installed.
- The private --sealed-spec protocol binds version, descriptor number,
  device/inode, exact length and SHA-256. The receiver requires actual effective
  UID zero, root ownership, mode 0600 and all seals. It uses bounded pread,
  independent of the inherited offset, owns a CLOEXEC duplicate, and closes
  the original inherited slot before Android construction. The unsafe
  bootstrap API explicitly requires that raw slot to have no Rust owner and
  no concurrent closer/replacer. This contract concerns exclusive ownership of the descriptor. The fixture owns its raw slot
  exclusively even though the libtest harness also has a main thread.
- Explicit root use of the legacy private --spec entry remains available.
  Daemon and normal development-run always use the sealed protocol. Original
  pathname replacement after admission cannot change the transmitted value.

The same source contract is documented in docs/contracts/runtime-layout-v1.md.
No image, app, account, subordinate grant, live owner source or system service
was changed during this qualification.

## Actual source validation on Pocket4

The project pins Rust 1.93.0. This round used the explicit installed compiler
**rustc 1.93.0 (254b59607 2026-01-19)**, cargo 1.93.0, and rustfmt 1.8.0-stable.
Cargo ran with --locked --offline -j 1, a separate target, the existing owned
offline registry, one CPU, CPU quota 100%, nice 19, and a 3 GiB memory limit.

| Validation | Actual result |
| --- | --- |
| Complete ordinary supervisor library suite | 159 passed, 0 failed, 22 explicitly ignored |
| Supervisor CLI suite | 6 passed, 0 failed, 0 ignored |
| Supervisor library and binary build | Exit 0 |
| Standalone sealed-entry Rust probe compilation | Exit 0 |
| Exact root-only parent controls | 7 selected controls passed; real effective UID 0 |
| Rustfmt, edition 2024, all 7 touched Rust files | Exit 0 |

The 22 library ignores consist of 13 existing environment/private-fixture
entries, seven new root controls run separately, and two new private helper
entries exercised by those parent controls. Helper invocations are not extra
independent acceptance cases. Exact names, command results, source/binary pins,
stdout/stderr hashes, resource samples, and durable H job identities/nonces
are recorded in source-qualification.json.

Actual root controls cover held-file authorization after a parent path is
replaced, original-byte preservation, exact seal/identity/owner rejection,
child FD consumption, an abnormal child exit, and creator-thread death with
SIGKILL followed by positive reaping. The ordinary suite separately proves
that a real non-root receiver is denied.

A further control uses the actual development_namespace_command constructor:
ip netns exec, unshare, then the sealed-entry Rust probe. The current CPU
placement implementation supplies a sched_setaffinity pre-exec hook when
configured; it does not launch a taskset executable. The control creates only
its own private mount/network/PID namespaces and private named-netns registry.
The probe consumes the original configuration after pathname replacement,
checks the inherited FD is closed, and never calls Android entry. Both exact
outer owners are reaped, both init pidfds report exit, the temporary named
network namespace is removed, and parent namespace identities remain unchanged.
The probe source is included in the patch for reproduction.

Six bounded mutation controls remove individual protections and must each
produce exactly one failed assertion with exit 101: nonblocking FIFO open,
the actual read limit, same-descriptor daemon read, F_SEAL_WRITE, child-only
inheritance, and original-FD consumption. FIFO failure releases and joins its
reader; the unending reader has an independent byte-count guard. These controls
do not depend on an OOM or an indefinitely blocked child.

The earlier published 098a58c qualification used Rust 1.95.0 and is retained
as historical evidence in the receipt. It is not relabeled as 1.93 or combined
with the current test count. Its cache-preparation memory sample reached the
3 GiB ceiling (max events 26413, OOM 0); that fact remains recorded. Current
samples describe these source tests, not a full Android build resource gate.

## Offline source replay

From this repository root:

```sh
python3 compat/android/pocket4/production-identity-input-validation-r1/verify_source_chain.py --repo-root .
```

The verifier uses Python's standard library and Git, without network access.
It checks all seven patch lengths and SHA-256 values, runs git apply --index
--check before each apply, verifies six existing preimages plus two absent
preimages, and checks all eight final source files. The temporary reconstruction
is removed on exit. It does not compile Rust or claim that CI ran the Pocket4
privileged tests.

The chain is the common text snapshot, cumulative audio prerequisite, GSI
layout support, namespace ownership, guest directory/umask repair, the updated
identity19 prerequisite, and this cumulative review delta. The audio prerequisite
already includes older host status/readiness work; applying that older patch
again is incorrect. The result is an exact declared source subset, not a
reconstruction of a full local Git commit or a current Audio build candidate.

## Remaining production requirements

Dedicated account custody, effective non-overlapping grants, all active and
FD-retained user namespace mappings, the executing pidfd-bound map broker,
Android-compatible setgroups semantics, idmapped data, peer identity translation,
applied seccomp and complete lifecycle validation still need independent
implementation and qualification. This input/transport repair grants no
Android, app or deployment acceptance credit. production_ready and
runtime_qualified remain false.
