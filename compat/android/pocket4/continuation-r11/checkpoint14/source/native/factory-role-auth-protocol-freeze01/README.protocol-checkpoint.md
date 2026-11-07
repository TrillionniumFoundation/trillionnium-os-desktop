# Role factory authorization: separate source checkpoint

This is a new, unintegrated authorization component. It does not modify the
ordinary V2 factory, the NOFILE 26-case implementation, candidate07, Main, or
any installed application. It is not permission to enable the new role path.

## Actual local coverage

The current production source and its transport control were copied and pinned
before the local05 build. Strict GCC C++17 `-Wall -Wextra -Werror -O2 -pthread`
compilation completed. The actual executable passed 14 `SOCK_SEQPACKET`
receive cases and 471 assertions. `SO_PASSCRED` and `SO_PASSPIDFD` were real
kernel socket options; delivered `SCM_PIDFD` was not an injected descriptor.
Valid frames, exact ancillary counts, short/long/corrupt frames, 253 incoming
rights, missing identity options, EOF, and output/descriptor ownership were
checked. All owned descriptors were restored.

One additional owned-thread control held its proc task directory, observed live
status, joined the thread normally, and then obtained `ENOENT` resolving status
through that same held directory. The directory device/inode stayed unchanged.
Numeric TID reuse was not forced. This is a task-inode lifetime observation,
not full verification of the registry's caller authentication.

`local03` is retained as a real failure: the local executor's `/proc` mount
reported ancestor namespace IDs while `gettid` returned namespace-local IDs.
The fixture, not production `VerifyProc`, was changed so the owned thread opens
its kernel `thread-self` directory and transfers that descriptor in its shared
FD table. The exact read-only namespace diagnostic is preserved. `local04`
passed the revised fixture; `local05` reran it against the current source after
the two state/ownership source corrections below. Old `local02` is only its
older 12-case scope, not proof for later source. The initial syntax failure is
retained with the exact failing input files.

No registry authorization positive, parent-approval exchange, fork-child token
rejection, policy installation, factory service, platform integration, or
Android qualification was executed in these local controls.

## New source contract

The fixed 160-byte `DP4ROLE1` wire and registry are separate from V2. A trusted
initial-user-namespace root owner is initialized with an immutable paired-build
digest. A Begin claim does not supply authority. Per-message kernel PIDFD and
connection PIDFD must agree with actual current credentials and a verified proc
view. Caller-supplied SCM credentials are not UID/GID authority. Unsupported
kernel identity APIs fail; there is no numeric-PID or untrusted path fallback.

The root parent approves once for the exact live child PIDFD, actual parent,
fork-return PID, paired build, original UID/GID and immutable UID/GID ranges.
The role process has nonzero identities, exact SETUID/SETGID/SETPCAP E/P/I,
empty bounding/ambient sets, NNP, and seccomp mode 2. Those observations are
necessary checks; they do **not** attest which filter is installed. Approval
still depends on the future matched pre-guest platform entry described below.

Grant lifetime and connection lifetime are distinct. Revocation retains a
PIDFD tombstone until confirmed process death. A failed or interrupted poll is
not death and cannot delete the tombstone. Begin cannot reauthorize that same
live process. A suspended grant retains its generation, subject PIDFD, context,
token and held caller task-directory lease.

Suspend first enters `Suspending`. The owner must send its acknowledgement and
explicitly Detach while the original connection is still live. Only then does
the state become `Suspended`; the client waits for the owner's close. A HUP
before this point revokes. Attach needs the same live process, unchanged
context, exact generation/token and original live caller lease. A fork child
cannot use its parent's token as its own grant. Observed context mismatch
revokes permanently. An unknown token or a different process does not revoke
someone else's grant merely because the token was copied.

The source also checks current `thread-self` in the owner's held matching proc
view before mutating registry state. Numeric getpid/gettid alone would not
distinguish a shared-VM process with colliding namespace-local IDs. This source
correction is compiled; its positive/negative registry behavior is still a
separate pending mechanism control.

## Required integration before enablement

Unchanged snapshots before/after suspension do not prove that no transient
credential or namespace transition happened between them. A valid deployment
must establish the fixed base/range policy and NNP for all threads early,
before any guest/preload code, and retain those irreversible constraints.
The actual Java/JNI sequence requires the trusted parent/child approval inside
the native fork path, before Java postForkCommon restarts daemon threads.
Range values currently live in remaining Java arguments and need a typed,
version-gated native handoff. An AppZygote role label alone is insufficient.

The matched Bionic query-only policy, ART/engine lifecycle, root-parent grant
exchange, role client, response wire, factory event loop and authorized snapshot
production are not connected by this checkpoint. Root image/namespace and
last-host-thread exit constraints, app-zygote range semantics, UID/GID/capability
transitions, exec, fork, and repeated generations still need their complete
platform contracts. Ordinary zero-capability V2 admission stays unchanged.

The next control is a bounded owned root-parent/role-child socket/PIDFD mechanism
fixture with exact owned-child cleanup. Its policy is explicitly a fixture and
cannot qualify the production platform's early-filter chain. No service or
remote execution is authorized by this source checkpoint.
