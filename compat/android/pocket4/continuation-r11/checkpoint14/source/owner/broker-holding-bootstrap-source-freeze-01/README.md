# Broker bootstrap holding layout, source revision 01

## Exact defect and evidence boundary

The real ABI3 producer places Android init in the host-created `init-bootstrap` leaf and keeps the finite Android cgroup view at `/dev/.droidloom-cgroups/relay-v2`. The native Android `/sys/fs/cgroup` target is still its original sys tmpfs before constructor release. Actual producer09's matching broker source instead requires init directly in the domain root and `/sys/fs/cgroup` already mounted as cgroup2. Those source contracts cannot both pass.

NORMAL09 really failed after InitHello, with `lifecycle packet framing/ancillary data`; its original Owner retirement also failed, and the outer exact unit cleanup subsequently completed. At this freeze the exact broker stderr has not been returned. The incompatible gate is a confirmed source defect, not a fabricated attribution of the first observed transport error. No original result is changed.

## Two explicit protocols

The fixed 128-byte frame and sixteen SCM_RIGHTS remain. P4BOOT1/version1/reserved20=0 is retained only for the legacy owned fixture with an already projected root and init directly in that root. Its public helpers keep their old wire bytes.

The real ABI3 producer calls `LifecycleBroker::spawn_holding_in_context` and sends P4BOOT2/version2/layout3. That choice is internal to the trusted parent API, not inferred from a client path. The original broker rejects the new header; the new broker rejects unknown header/version/layout combinations. There is no retry or fallback to P4BOOT1 after failure. The legacy owned-child receiver rejects a holding packet and drops all transferred descriptors.

## Bootstrap-only verification

The new holding path retains exact directory FDs, independently checks cgroup2 and root ownership, and compares the holding-view inode with the inherited finite Android root. It checks the real native mount target and sys directory are still root-owned directories on the same tmpfs. Fixed relative paths use the existing openat2 no-symlink/beneath policy; callers cannot supply alternative paths.

The host-derived init membership must equal the named host-created leaf. Both its actual membership and the opened leaf have held ancestry proofs on the root's cgroup mount; the leaf's direct parent must equal the root. The root's local cgroup.procs must be empty and the controller-free domain leaf must contain exactly the held init PID. Init pidfd/birth checks bracket each capture. Captured FD identities, namespace-root-relative named targets, membership and ancestry are checked again before and after the permanent claim is written.

This changes only bootstrap. The service library remains byte-identical: the init lifecycle snapshot still checks its whole membership and namespace identity; actual LMKD authentication still requires its eventual `/sys/fs/cgroup` projection to equal the finite root and verifies real descendant ancestry. The existing role UID/GID, held executable, parent lineage, ten namespace handles, budget, one-shot claim, two-second transport limit, error propagation, READY/ACTIVE semantics and retirement poison are retained.

## Validation and outstanding work

The two preimages match actual producer09 input hashes before and after its successful compile. The supervisor source changes only the one spawn call. Three new Rust tests cover explicit codec separation, exact membership negatives, and real socketpair SCM_RIGHTS rejection/closure through the legacy owned-child receiver. Existing tests remain.

No Rust compiler is available in this local environment; no Rust test or Android runtime is claimed. A fresh matching compile and actual ordinary controls must precede a fresh owned NORMAL attempt. Expected library counts are 26 relay and 122 supervisor, plus the existing targeted public retirement, IPC, host-context and entry-ABI checks. The Android ABI3 DSO is unchanged. No Main deployment, host network change, thresholds change, RC/reinit work, or production-ready qualification is part of this patch.
