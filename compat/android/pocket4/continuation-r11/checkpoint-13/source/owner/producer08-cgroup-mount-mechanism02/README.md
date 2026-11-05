# Owned cgroup2 repeated mount mechanism 01

Status: source frozen; local strict C compilation only. Device execution NOT SUBMITTED by this agent. Root owns the exact request.

The controller retains the existing 1 CPU / 512 MiB / 120 second profile, held own-cgroup resource gate, pinned tools, create-only `/opt/p4-cgroup-mount-mechanism-20261105-01`, and exact Main before/after checks. No Android or network operation occurs. The child never writes a cgroup control or moves a process; its current finite job becomes the root of a new cgroup namespace. Its mount namespace is newly private before any mount. One tmpfs contains both fresh mount targets.

Three arms: A first mount with NULL options; A repeats with Android's `memory_recursiveprot` and then NULL fallback; B first mount with NULL options. Every successful view must match the held finite invocation domain device/inode. Qualification requires first A and fresh B success, both repeated calls EBUSY, shared user namespace, distinct child cgroup/mount namespaces, exact child wait without forced kill, and removal of all private mounts. Unexpected outcomes are retained as failure, not normalized to expectations.

The probe records child PID/start ticks, MONOTONIC/BOOTTIME/REALTIME intervals and the actual syscall return/errno. Parent cleanup retains an exact child pidfd (or an unreaped direct child PID if pidfd acquisition fails); forced cleanup is bounded and never qualifies. No process-name lookup or global signal is used. Private mount namespace teardown additionally contains the mounts if explicit cleanup fails; such a run still fails.

The controller passes only its already-held resource cgroup to the probe, and keeps its own membership unchanged. It reuses the original read-only resource gate byte for byte. Existing compat ELF dynsym observation remains in the four-command closure, but no compat ELF is loaded by this host C program.

Scope: actual kernel mechanism only. A pass does not identify the sender of Owner08's old private journal candidates, prove an Android CgroupSetup call, qualify a bootstrap leaf, or qualify complete Owner/LMKD/app production readiness. The leaf/controller issue remains independent.

Local validation: `cc -std=c17 -O2 -Wall -Wextra -Werror -c` exited 0 (tool chunks `911c90`, final `737bbb`); no local namespace/runtime operation ran. Exact request/packet/template AST bindings pass; only controller `main` changes from the previously executed socket mechanism controller.

## Revision 02: exact invocation owner binding

Revision 01 was not submitted. Its assumption that the user-manager job cgroup is root-owned was not supported by the original resource receipt. This revision derives device/inode/uid/gid/mode from the resource-gated, retained current-invocation FD and compares every projected view against all five values, then resamples that same held FD. It never opens an arbitrary candidate domain. Root credentials still gate namespace/mount execution and every newly created tmpfs/target remains root-owned. Original revision 01 stays frozen; its planned remote root/nonce have never run and this is their only intended actual attempt under the new fixed key.

New local strict C compilation exited 0 (`83f477`). The 01 historical compile records are not substituted for that compile. No local namespace/cgroup/Android runtime ran.
