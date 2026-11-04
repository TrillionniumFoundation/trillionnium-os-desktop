# Fixed R5 owned systemd retirement fixture — NOT EXECUTED

## Identity and admission

Name: p4-signal-r5-unit-control-20261104-01
Nonce: 969694d682504cb2ae81bf178474c96e8
Only unit: p4-signal-r5-unit-control-20261104-01-bus.service
Only unit cgroup: /system.slice/p4-signal-r5-unit-control-20261104-01-bus.service

Default command prints the plan only:
python3 -I owned_cleanup_fixture.py

The eventual admitted command is explicit and once-only:
sudo -n /usr/bin/python3 -I <frozen-source>/owned_cleanup_fixture.py --execute-once --source-manifest-sha256 <exact-final-manifest-sha256>

The program accepts no caller-selected unit, nonce, child executable or target.
The fixed claim is created with O_EXCL before any start. Unknown outcomes are
not replayed. The exact source manifest, four host tool hashes, original Main
activation and framework helper are checked. Main must remain at epoch
48cb65c93ff81edbf160455af6506f5c703f0958363f15de4a80ece57c37e93f.

## Small, bounded fixture

The single system unit uses Type=oneshot, RemainAfterExit=yes,
KillMode=control-group, Restart=no, CPUQuota=5%, MemoryMax=64M,
MemorySwapMax=0, TasksMax=16, TimeoutStartSec=15, TimeoutStopSec=5,
OOMPolicy=stop, NoNewPrivileges=yes, Nice=10 and UMask=0077.

Its fixed Python worker forks exactly one child. That child creates one
owned-sleeper subgroup under its own unit and moves only itself there. It writes
its exact birth/UID/cgroup record and acknowledges setup, then sleeps at most
45 seconds. No controller is enabled, no resource limit is changed, no memory
pressure is generated, and no namespace or Android command is entered.
The parent exits so systemd MainPID becomes zero while the one child remains.
RuntimeMaxSec is not used as an assumed oneshot lifetime guarantee.

Before testing cleanup, the driver requires all of these actual observations:

- Exact unit identity/properties and active state with MainPID=0.
- Root cgroup.procs empty, hierarchical populated=1 and pids.current=1.
- The known child is alive through an acquired pidfd and matching birth/UID/group.

## Recovery under the two injected faults

The initial post-start generation observation is deliberately withheld from the
cleanup row; the actual start acknowledgement is retained. Actual R5 reconcile
must obtain InvocationID/Description/ControlGroup from the real manager.

The save callback throws ENOSPC once at resources-before-cleanup.json. Actual R5
cleanup must retain that first error, reach the release phase, issue exactly one
stop for the verified unit and prove its hierarchical domain empty. A separate
original cgroup FD must then observe deactivation. The original child pidfd must
signal exit and the original process must be observed reaped.

The intentional error must keep would_qualify_full_canary=false. A passing
fixture means the bounded recovery behaved as required; it is not a passing
Android runtime or a production claim.

## Finally and scope

If any precondition fails after start, the driver still invokes actual cleanup
once. Unknown manager identity forbids blind stop. A previous attempted stop is
not retried. Child and held-cgroup FDs are closed; final unit/cgroup/Main
observations and every permitted transport are retained. The bounded worker has
its own 45-second lifetime if the controller fails.

There is no UI, audio, APK install, data clear, permission change, engine deploy,
Main unit stop or pressure operation. Evidence and failed state are retained;
the program does not reset-failed. Its proof concerns this one unit subtree and
one original child, not arbitrary escaped processes.

