# Owned role registry mechanism fixture

This fixture is prepared for independent matching compilation and one bounded
root-owned runtime. It has **not** executed its positive branch locally.
Strict GCC compilation and its side-effect-free default PLAN passed. The first
GCC attempt's `std::min` type-deduction failure and its exact input are retained.

The four production files are byte-for-byte copies of
`factory-role-auth-protocol-freeze01/source`. No ordinary V2, NOFILE, engine,
Android application, stock seccomp entry, or installed platform file changes.

## Runtime shape

The initial-user-namespace root process initializes the actual Registry, then
forks only its own clients. Each client closes inherited factory descriptors in
its private FD table, uses UID/GID 61179, removes supplementary groups, sets
exact SETUID/SETGID/SETPCAP E/P/I with empty bounding/ambient sets, sets NNP and
installs an explicitly **fixture-only** filter while single-threaded. Its own
UID/GID setters, namespace/exec transitions, alternate architectures and x32
calls are rejected. This is not the Android base/range-policy implementation or
evidence of production early-filter attestation.

All IPC uses anonymous nonblocking CLOEXEC seqpacket socketpairs. No listener,
network endpoint, namespace mount, persistent service, application, or snapshot
is created. The role endpoint is created by the role child after specialization
so SO_PEERCRED/SO_PEERPIDFD identify that child. SCM_PIDFD is emitted by the
kernel. The actual root parent approves through a separate real kernel-identity
socketpair. Source/payload descriptors in Create are owned `/dev/null` objects;
only authorization is invoked, never a snapshot maker or provenance publisher.

The original production namespace/proc, credential, NNP, capability, PIDFD-info,
parent, context, caller, deadline and tombstone gates are unchanged. Missing
kernel support, an ancestor proc view, or insufficient root authority fails.
The fixture does not replace those gates with injected observations.

## Cases

| Case | Required behavior |
| --- | --- |
| one_grant_create_release_tombstone | Begin + actual root approval + caller authorization/commit pass; Release revokes; the same live PID cannot Begin again. |
| same_pidfd_caller_suspend_attach | Explicit Suspend/owner acknowledgement/Detach retains one grant; same PIDFD and caller attach and Create without second root approval. |
| fork_token_rejected_parent_reattaches | A real nested fork sends the copied token from its own socket and PIDFD; Attach is EPERM, output untouched; original parent still attaches. |
| unexpected_active_hup_tombstone | Active peer closure revokes; a new endpoint cannot renew the grant. |
| pending_hup_tombstone | Unapproved peer closure revokes; same live process cannot restart Begin. |
| pre_detach_hup_tombstone | A Suspend request without explicit Detach does not authorize HUP; peer close revokes. |
| suspended_capability_loss_revokes | An owned client's irreversible capability drop while detached is observed and permanently revokes. |
| wrong_fork_return_pid_then_exact_parent | Wrong fork-return PID approval is EPERM; the exact actual parent approval still succeeds. |
| duplicate_root_approval_rejected | An already active grant rejects another approval with EALREADY. |
| pending_deadline_tombstone | The 2-second pending lifetime expires, revokes, and cannot be renewed by the same live process. |

Each direct fork also checks that its COW copy cannot operate the parent's
registry. This does not cover a shared-VM clone with PID-namespace collision;
that is still a separate unexecuted scope. No numeric PID/TID reuse is forced.

## Ownership and qualification

The harness has a 30-second monotonic overall bound and 2-second IPC/reap bounds.
It uses child PIDFDs, exclusive SIGCHLD default disposition, parent-death signals
with parent PIDFD checks after identity changes, and exact waitpid children.
Normal success requires 10 direct and one nested child reaped, no forced cleanup,
no unobserved cleanup result, and restored descriptor count. A failure requiring
forced retirement remains a failure. An outer owned runtime must be a subreaper
and independently reject/retire any remaining owned descendants; it must not
claim cleanup success merely from this harness's summary.

Real root parent approval in this fixture attests only its controlled client.
It does not qualify trusted Java/JNI range handoff, pre-guest all-thread NNP and
Android policy installation, ART/Bionic/engine lifecycle, root-factory service,
role raw-worker capability drop, authorized snapshot construction, Android
runtime, or any whole application. Suspend before/after observations alone do
not prove absence of transient credential or namespace changes.
