# A01 daemon descendant lifecycle: original failure and patched verification

The unmodified production supervisor was reproduced leaking a TERM-ignoring descendant in two distinct paths. The parent's fix passed the same three controlled cases plus Drop-only and startup-exit-1 cleanup: **5 passed, 0 failed**, with both owned process handles exited and no probe rescue signal in any patched case. No QEMU VM was started.

## Actual observations

| Scenario | Original implementation | Patched implementation |
| --- | --- | --- |
| Leader dies on group TERM; descendant ignores TERM | stop returned in 50 ms; descendant kept executing for 6.206 s after supervisor exit | stop returned in 53 ms; both pidfds exited; no later heartbeat |
| Leader exits successfully before startup poll | entry was removed; descendant kept executing for 6.256 s after supervisor exit | startup reap cleaned group; stop returned in 0 ms; both pidfds exited |
| Leader and descendant both ignore TERM | timeout escalation at 5013 ms killed both; valid control | timeout escalation at 5013 ms killed both |
| Only supervisor Drop performs cleanup | not run on original | Drop returned in 50 ms; both pidfds exited |
| Leader exits 1 during startup | not run on original | original start API returned ExecuteCommand (6); both pidfds exited before harness return |

The original observation driver completed with exit 0, while its independent lifecycle-invariant check failed with exit 1: **2 failures / 1 control pass**. The patched driver completed with exit 0 and its separate measurement checker passed **5/5**. Driver exit 0 alone is not a pass. Full logs, nonce events, process/group identities, pidfd snapshots, kill-zero errnos and cleanup outcomes are retained under `runs/` and `runs-patched/`.

For each old leak, the leader handle had exited, its namespace kill-zero returned ESRCH, and the descendant handle remained unready while namespace kill-zero succeeded. The descendant emitted new nonce heartbeats beyond the production five-second timeout, so this was actual continued execution rather than a zombie or an immediate-assertion race. Only the two leaked, privately tracked descendant pidfds received the probe's SIGKILL cleanup; both exit handles became ready within two seconds. The control and all five patched cases needed no rescue signal.

## Source provenance and boundary

The original production daemon modules and error module were frozen byte-for-byte from commit `76eff6ea87242fedad781899146f96e397427f4e`. The patched production modules were frozen from the parent's ready worktree, before publication as `fb81fec167913827bcddfda15676dc6b26f35965`. The measured source SHA256 values are in the two provenance JSON files. The actual fixed toolchain was `nightly-2026-07-21`; all 17 external package identities and checksums in the diagnostic locks match the original OSDK Cargo.lock. Logs retain the initial offline resolution and subsequent alignment to those original versions before compilation.

The final fb81 commit added only a SIGCHLD waitability/no-auto-reap documentation comment in daemon/mod.rs after the measured build. Its signal.rs, supervisor.rs and error.rs are byte-identical to the measured freeze; mod.rs is not byte-identical. `patched-to-committed.json` records both hashes and `patched-to-committed.diff` contains the precise comment-only difference. Measurements remain tied to their actual compiled source hashes; no freeze or result was relabelled.

Production source is not copied into this evidence directory. Only two scaffold main.rs files, Cargo manifests/locks, scripts, minimal comment delta, provenance and logs are retained. The actual implementation remains in kernel/asterinas. The assembler reconstructs each measured freeze from retained Git commits and reverses the comment delta to restore the exact tested hashes. Its reconstruction/hash check was executed successfully without rerunning process cases.

The harness supplies only DaemonScheme's data fields and info logging. It calls the unchanged copied production SignalGuard and DaemonSupervisor methods. Roles are real Python subprocesses in the original daemon process group. A private nonce pipe reports getpid/getppid/getpgrp and readiness; independent pidfd handles, current-process-namespace kill(pid, 0) and post-return heartbeats provide lifecycle observations. Numeric /proc/<namespace_pid> is never used as the verdict. Descendant readiness is acknowledged before the leader may intentionally exit. Cleanup signals only the handles obtained for this test's own known creation tree.

Binding pidfds from reported numeric PIDs is not an atomic nonce-to-handle authentication protocol; no such guarantee is claimed. The continuing same-process nonce heartbeats support the positive leak findings. This limited host reproducer does not establish coverage for descendants escaping the group, arbitrary external reapers/ECHILD, SIGCHLD auto-reap, all interruption/QEMU-wait paths, or the full OSDK test suite. Native unit results are tracked separately by the parent. It also does not identify the individual cause of the earlier proc-based unit failure; this confirms a separate production lifecycle flaw. No unshare attempt, permissions change, account change or unrelated process signal was used here.

## Reproduce in fresh scratch

With the fixed Rust toolchain and cached locked dependencies available:

```sh
bash reproduce.sh /path/to/trillionnium-os-desktop /path/to/new-empty-scratch
```

The destination must not already exist. The script obtains production files with git show from the retained commits, assembles both scaffolds, restores the measured comment bytes, verifies every production-file SHA256, and builds with --locked --offline. It then runs the original cases (expecting the recorded invariant failure) and the five patched cases. Original and patched targets and run directories are separate. `commands.json` retains the exact commands and paths of this session; individual case JSON records contain exact process argv.

Verify all retained evidence with `sha256sum --check evidence.sha256` from this directory. Compiled binaries are not archived; their actual SHA256 values remain in the case records.
