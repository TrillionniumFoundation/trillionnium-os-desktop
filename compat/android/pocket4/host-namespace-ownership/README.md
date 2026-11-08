# Owned namespace shutdown on the installed Linux host

The installed util-linux 2.41.3 rejects `unshare --forward-signals`. Its waiting
namespace owner also ignores normal TERM. The first actual QPR1 attempt therefore
failed before Android started. This change uses the supported namespace options,
adds the missing private cgroup namespace, and makes Rust own signal delivery.

After spawning, Rust binds the sole namespace init while its direct `Child`
remains unreaped. It verifies parent, start time, PID namespace and namespace PID
1 around opening a pidfd. Normal shutdown sends TERM through that held descriptor.
The existing ten-second deadline remains. A forced stop targets the owned outer
process; its parent-death KILL contract covers both sides of util-linux's fork.
The outer process is waited and reaped, and the bound init must exit before host
network and runtime cleanup. A readable pidfd is treated as exit evidence, not
as a claim that Rust reaped a grandchild. If init identity was never bound, the
start fails and deterministic residue remains for independently checked recovery.

Apply [the complete patch](host-namespace-ownership.patch) to host commit
`ce2150070260a660a4f634d5bb43085fd6df541b`. The resulting normal commit is
`ecf986b7afe7a2c24e537e765ee600c0256b2096`, tree
`e053f6eb09d4ce0edab1a54691f61a623c8352de`. The base checkout stayed unchanged.
The patch includes the actual process owner and its explicit Linux controls.

## What actually ran

Normal, offline, locked Cargo execution on Pocket4 passed 127 library tests.
Nine explicitly selected environment/control/fixture entries were ignored by
that ordinary invocation. The three new root controls then ran separately with
zero skips and failures. Actual TERM completed in 0.066 seconds; actual forced
retirement completed in 10.039 seconds. Separate owner-death controls covered
before exec/fork and after fork but before Android entry. Held init and descendant
pidfds observed exit, and each directly owned namespace process was reaped.
All four normal release executables were built successfully.

The next bounded QPR1 probe used those actual daemon, client and supervisor
binaries. It entered `/system/bin/init` second stage and returned official
CP3A.260905.010 / 16176746, SDK 37.1 properties. The mount, PID, network, cgroup,
IPC and UTS namespaces were all measured as distinct from the daemon. No outer
cgroup wrapper supplied the property being tested.

Android did not finish boot. The official GSI `init.vndk-nodef.rc` selected by
the absent legacy VNDK property requested `reboot,bootloader`; the subsequent
shutdown waited for service-manager readiness. Modern vendor metadata must be
validated against the GSI contract before repairing that selection. Normal cell
stop and daemon stop succeeded. The observed processes, cgroup, mounts, image
loops, network, runtime and sockets retired, and original user-data metadata
stayed unchanged. Only the disposable probe data changed.

The [source and actual boot proof](source-and-actual-boot-proof.json) binds the
three changed source files, release binaries, original control receipts and
actual failed boot by their byte counts and SHA-256 hashes. The earlier failed
fixture observation is retained without being relabeled as a pass.

## Remaining qualification

This closes the installed-host namespace option and owned shutdown defects.
The development runner still lacks production UID mapping and seccomp. The
coherent QPR1 vendor/Native/Audio payload, complete Android boot, Denial/Main,
actual application workflows and final deployment remain separate gates.
Neither source tests nor an init property read qualifies production readiness.
