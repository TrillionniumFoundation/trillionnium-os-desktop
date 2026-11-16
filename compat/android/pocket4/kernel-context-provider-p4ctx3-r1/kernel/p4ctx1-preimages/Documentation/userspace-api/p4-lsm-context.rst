Pocket4 explicit LSM context providers
=====================================

Scope
-----

CONFIG_P4_LSM_CONTEXT adds an opt-in representation selector for generic
proc attributes, SO_PEERSEC, and Binder transaction security contexts.
It does not namespace SELinux policy, relabel credentials, change enforcing
state, or remove any existing AppArmor, SELinux, capability, VFS, Binder or
socket access check. SELinux must actually be registered. There is no
fallback to a different provider when a selected hook returns an error.

An instance with no selection preserves the existing first-provider
behavior, including its errors. Explicit proc attributes such as
attr/apparmor/current retain their explicit provider.

Procfs and binderfs
-------------------

A new procfs or binderfs instance accepts lsm_context=default or
lsm_context=selinux. Selecting SELinux requires CAP_SYS_ADMIN in the
initial user namespace and a caller still in that namespace. All normal
mount and fsconfig authorization remains in force.

The choice belongs to the superblock. Binding or cloning its mount does
not change it. A remount may omit the option or repeat the same value;
changing it returns EBUSY. No already-open proc attribute changes provider.

For Binder, each device captures the choice from its binderfs instance
before publication. Transaction security contexts use the target device's
choice and the sender's saved Binder-open credential. They do not use the
current caller's namespace or a caller-supplied label. Legacy misc Binder
devices preserve the default. A selected successful context must carry the
requested provider ID and nonempty context bytes.

Network namespaces and sockets
------------------------------

The root-owned 0600 /dev/p4_lsm_context control device accepts the two
fixed-size ioctls in linux/p4_lsm_context.h. Both require an initial-user-
namespace CAP_SYS_ADMIN caller, an actual network-namespace FD, and its
exact nsfs inode number. The FD is converted to a held namespace reference
for the complete operation.

P4_LSM_NETNS_SET selects LSM_ID_SELINUX once, before the namespace has been
used for a userspace socket or derived network namespace. The initial
network namespace and namespaces owned by the initial user namespace
cannot be selected. Repeating SET, selecting after use, or attempting a
reset returns an error. SET performs no copy to userspace after mutation.
P4_LSM_NETNS_GET is read-only and reports the provider and fixed/used bits;
its input lsm_id, flags and reserved fields must be zero.

Socket creation and network-namespace derivation use atomic operations to
capture the choice and make subsequent SET fail. A protocol-creation
failure may therefore leave a namespace used. There is no socket-count
heuristic and closing the last socket does not reopen configuration.
Derived namespaces inherit a parent's fixed selection before per-net
initialization; an already-derived default child cannot be retroactively
changed by selecting its parent.

Each socket wrapper captures the provider before publication. Accepted
sockets inherit the listener wrapper, including pathname AF_UNIX
connections across namespaces. KCM clones and SCTP peeled associations
inherit their source wrapper. Kernel-internal creation keeps the default;
kernel accept paths inherit their listener. dup, fork, SCM_RIGHTS, and
setns cannot reinterpret an existing socket wrapper.

SCM_SECURITY and IP_PASSSEC remain outside this selector's ABI. Their
existing untyped secid paths require a separate consumer and provenance
audit; a successful SO_PEERSEC check is not evidence for them.

Required qualification
----------------------

Source preparation or compilation does not qualify the runtime. Before
production admission, test both AppArmor-first plus active enforcing
SELinux and the inactive-SELinux rejection arm in an isolated VM. Observe
real generic proc reads/writes, explicit AppArmor attributes, immutable
remount behavior, Binder saved-credential contexts, socket sizing/error
semantics, socketpair, both directions of pathname cross-netns accept,
inherited and transferred FDs, provider configuration races, stale/wrong
namespace FDs, post-use SET rejection, and child-netns inheritance.

Independent MAC denials must still hold. Production requires its actual
strict Android and host policy, stock binary consumers and application
acceptance in addition to these mechanism tests.
