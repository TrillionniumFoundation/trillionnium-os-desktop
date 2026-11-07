# Producer05 complete host-prefix control — source review, no runtime admission

This control tests the complete `ip netns exec` → native `unshare` startup prefix used by the explicit relay path. Its native executable is a declared stand-in. It does **not** execute the actual Rust `Owner::configure_command`, Android init, the init-barrier constructor, an app, a pressure workload, or any Main operation. Source flags and result fields retain these distinctions.

## Established evidence

The installed compatibility shim forks `subprocess.Popen` without `pass_fds`; its SHA-256 is `fe3a685034ed0dc948597436965dfd35ea183fc2b0519d9b0c5730c79d7c060b`. It cannot preserve the four capability descriptors or the exact direct-parent contract. Producer05 changes one Rust file to select `/usr/bin/ip` and `/usr/bin/unshare`, omitting the unsupported `--forward-signals` option only when relay is explicit. The legacy None path remains its original argv.

The actual producer05 matching host build succeeded with 122 supervisor tests, 23 relay tests, seven ordinary IPC controls, worker-origin controls, and the compiled entry ABI. Its 34,073-byte receipt SHA is `1623811c108a7cac8af3460d828c063ed9e7064519d2d4e41d70bce4ab25e64c`. That build did not start namespaces or Android. It retained a separate immutable actual producer04 snapshot before applying the one-file change.

The actual host tool readback binds ip, unshare, Python, systemctl, and systemd-run to root-owned, non-set-ID, no-file-capability binaries. The 3,548-byte receipt SHA is `bf316b27302e7fcf3c5be35d98e6f23aea5103733e3c91dc8681ef4063ddc8e0`. `/usr/bin/python3` is a packaging symlink; the executing interpreter is instead checked through its kernel `/proc/self/exe` descriptor. The proposed common owned attempt directory was absent at that readback.

The local controls cover actual owned socketpairs, SCM_RIGHTS/CLOEXEC ownership, credential rejection, truncation, unexpected SCM_PIDFD cleanup, root artifact metadata, and exact owned-child retirement. The coordinator controls cover pure receipt contradictions, real create-only atomic files, and regular-file fixtures for the hierarchical-retirement decision. Those fixtures do not qualify actual cgroupfs. The C probe has been compiled with C11, `-O2 -Wall -Wextra -Werror`; six ordinary exec controls check absence/detection of each fixed descriptor and early rejection outside private PID 1. No local control performs systemd or namespace effects.

One local test initially assumed that the executor's PID view and procfs view matched. They do not; the formal actor now refuses mismatched views. The first primary Python executable was also correctly rejected because it is owned by UID 65534. Subsequent ordinary controls use the root-owned system Python. A separate real socketpair negative found that unknown SCM_PIDFD was rejected without closing its delivered descriptor when SO_PASSPIDFD was explicitly enabled. That original source/receipt is retained, and the receiver now adopts and closes that descriptor before rejection. Formal channels never enable SO_PASSPIDFD.

## Matching preparation, then a separate execution decision

`prepare-template.py` is instantiated into a single stable-key, root-owned host preparation/build request. It creates only `/home/alex/work/pocket4-relay-prefix-r11-source-05-01` and, if absent, the root-private common directory `/home/alex/work/pocket4-relay-prefix-r11-owned`. It writes the five pinned source/test files, compiles the probe, runs 16 transport/owned-resource tests and 24 coordinator tests plus six native ordinary controls, and records exact source and binary hashes. It makes no systemd, namespace, network, Android, or Main calls. The request must be reviewed before dispatch; source preparation does not authorize a runtime attempt.

The example plan is deliberately non-executable: its nonce and compiled-probe digest are placeholders. After the matching host build, one separate immutable plan must contain its actual probe hash, the frozen actor/coordinator paths and hashes, the five observed tool hashes, a fresh nonce, and the complete read-only Main fence. The controller recomputes and checks every binding before any runtime effect. It refuses an old path, unit, netns, `/etc/netns` configuration, or persistent claim. The historical framework fence is only accepted if the original live processes, boot ID, daemon invocation, original cgroup, resources, installed binaries and cell configuration still match at execution time.

## One attempt, finite envelope, independent authority

Each plan creates exactly one new nonce-bound network namespace, with no routes, addresses, veths or network configuration changes, and one new systemd unit. Each mode has a different nonce, network namespace, directory and unit. Every unit is fixed to CPUQuota 100%, memory.max 256 MiB, swap zero, TasksMax 32, RuntimeMaxSec 60, TimeoutStopSec 8, Restart no and KillMode control-group. These are small host-fixture limits, not proposed Android production budgets.

The unit first runs an internal waiting gate. The external coordinator captures the real InvocationID, original MainPID/pidfd, first cgroup descriptor/device/inode and the original netns descriptor. It persists those identities and publishes the actor input with create-only atomic rename. The waiting gate checks the externally pinned plan, actual unit/cgroup/netns and its own original PID before execing the actor in the same PID. No unobserved InvocationID is guessed.

The actor uses the full production argv prefix, including `ip netns exec`, native unshare's mount/PID/IPC/UTS flags, `--mount-proc`, `--fork`, `--kill-child=TERM`, and private mount propagation. It checks the actual unshare executable hash, exact retained Child → private PID 1 relationship, root credentials, transferred namespace descriptors, fixed FD object identities and the inherited owner pidfd returned from the target. The target seals capabilities CLOEXEC before a second ordinary exec checks that FDs 198–201 are absent.

The modes are separately admitted and never automatically looped:

1. **normal:** full prefix, genuine probe HELLO, subsequent exec without capability leakage, exact normal process exits.
2. **owner-kill:** a same-source externally pinned complete normal receipt is required. The actor signals only its original retained unshare pidfd and observes the original private PID 1 die.
3. **controller-loss:** a same-source externally pinned complete owner-kill receipt is required. The outer actor kills only its retained inner controller Child and observes the original unshare and private PID 1 pidfds become dead.

For both death modes the outer actor retains the probe's control-channel peer endpoint. The probe deliberately has no post-HELLO software owner-death poll. The result must observe death within ten seconds of the probe's monotonic start, while its independent native lifetime is fifteen seconds. A control HUP or native timeout cannot be counted as the parent-death contract. Time/user/cgroup namespace preservation and fresh mount/PID/IPC/UTS namespaces are independently checked through held namespace descriptors.

## Terminal and retirement rules

The actor samples its original cgroup before it exits. Its root cgroup.procs must contain only itself and hierarchical pids.current must be one; max/OOM counters and swap must remain zero. The external qualifier binds that audit to the first cgroup device/inode, exact unit InvocationID, terminal ExecMainPID and monotonic lifetime, successful actual exit, and systemd memory peaks. An empty root process list cannot hide an unknown descendant. A failed or incomplete actor report cannot be turned green by a later successful cleanup.

Cleanup runs before final receipt I/O and independently of evidence failures. The only stop target is the exact observed nonce-bound unit and invocation. The original actor pidfd must be dead, the original aggregate cgroup must be empty and removed, and the transient unit must unload. For a cgroup that disappears after exit, both always-present original cgroupfs counters must have deactivated through the held descriptor and the original path must be absent. A rename or replacement is rejected. If systemd clears its ControlGroup property, the independently held original retirement proof is still mandatory.

Only after unit retirement may the coordinator remove the same original netns mountpoint. It compares the held namespace identity, checks that the namespace has no live members and deletes only its exact fresh name. An ambiguous namespace creation with an unbound surviving path is retained as a cleanup failure. Unknown launch outcomes reconcile the same unit solely for retirement; they never authorize a second launch or turn the attempt green.

The permanent once claim is never removed. A lost external coordinator does not license automatic recovery or replay; retained namespace and first-unit records support subsequent read-only diagnosis. The bounded unit provides a final lifetime limit, but an unobserved cleanup remains incomplete. Main and all source/tool pins are checked again after retirement. `whole_attempt_qualified` requires the complete prefix proof, terminal binding, exact retirement and unchanged Main/source contract.

Even a complete host-prefix pass leaves actual Rust Owner/entry execution, real Android init constructor/receiver/enrollment, generation recovery, pressure qualification, activation and every commercial-app acceptance gate open. The broader fresh Android plan remains in `CANARY-PLAN.md` outside this frozen source; it requires a separate explicit finite CellSpec budget and distinct UID/subordinate-ID/path allocation.
