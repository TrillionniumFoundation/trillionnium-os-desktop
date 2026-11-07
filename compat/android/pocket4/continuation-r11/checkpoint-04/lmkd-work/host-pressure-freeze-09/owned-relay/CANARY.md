# First real lifecycle bootstrap canary

Status: this is the unchanged bootstrap/protocol procedure carried forward into revision06, with terminal audit added. Parent freeze04 later passed actual owned bootstrap and Android r6 protocol/HUP trials; those receipts apply to the parent bytes. No revision06 broker/namespace/Android canary has run during source preparation. Only the device coordinator executes these commands after checking its current Main fence and workload admission. New pressure/stale modes are specified separately in `PRESSURE.md`.

## Scope

Run `bootstrap` first, once, under a fresh `p4-lmkd-relay-*` system service. It exercises the actual `droidloom-psi-owner` executable through the production `LifecycleBroker` adapter. The root driver stays in initial host namespaces and pins its exact actor Child. Only the actor enters six fresh private namespaces. It forks and retains private PID 1, binds the exact fresh `domain` cgroup at the private `/sys/fs/cgroup`, and exports 16 held descriptors through its inherited private channel. The driver's preexisting image/hash/nonce policy must match that packet.

The real broker validates the parent, pidfds, lineage, namespaces, executable files, accounting root and fixed budget. The actor receives an inode-bound READY permit, bind-projects only the socket, and holds private init until the driver's real RETIRED receipt and exact broker reap. Before releasing init for shutdown, the driver calls the production spawn adapter again and requires rejection while old owner/init are still alive. It then verifies both exact pidfds exited, actor exit status 0, the domain unpopulated, and unchanged memory limits.

`bootstrap` does **not** start LMKD, register a PSI trigger, allocate workload memory, change a budget after creation, select a victim, or modify Main. It proves real bootstrap/FD ownership/retirement only. `protocol` starts the real matching Android r6 LMKD, uses its real framework control protocol, and verifies native lease-HUP handling after broker retirement. Neither of these two modes induces pressure; the separate explicit pressure/stale modes never reuse their retired trees.

## Build only

Use a fresh source/build directory, for example `/home/alex/work/pocket4-lmkd-host-bootstrap-r12-source-04`. This is the proposed new directory, not a claim that it already exists. Pin the received source manifest and hash all inputs before and after the build. Keep the job at one CPU, 512 MiB and nice 5 or greater.

```sh
cargo build --locked --offline -j 1
cargo test --locked --offline -j 1
./target/debug/owned-ipc-controls
g++ -std=c++20 -O1 -Wall -Wextra -Werror -pthread owned-relay/fixture_init.cpp -o owned-relay/fixture-init
sha256sum target/debug/droidloom-psi-owner target/debug/owned-relay-canary owned-relay/fixture-init
```

Expected Rust tests for revision06: 20 total. Expected ordinary IPC controls: 7. These commands do not invoke any canary mode. Record the actual broker, driver and actor binary hashes in the build receipt; use those actual values below. Use a fresh revision06 build directory when compiling this revision; the revision04 paths below are retained as the parent command template, not matching revision06 binary pins.

## Prepare only

Preparation is its own reversible, root-owned file operation. It creates fresh exact `/opt/p4-lmkd-relay-bootstrap-r12-01/root` and `/run/p4-lmkd-relay-bootstrap-r12-01` trees, never reuses or overwrites an existing tree. The library table embeds 15 exact input paths, modes and SHA-256 pins recovered from the prior minimal-root manifest (`ae6524a94a5caae0ee1c95dab99a8dcc04e98c125f32777ea993ba837d42c83d`). It excludes that manifest's old LMKD and actor. Each held regular input and copied file is hashed; source identity/timestamps are rechecked. The runtime state stays noexec. Only a private `dev/null` device is created.

The prepare command takes the actual matching actor hash as `ACTOR_SHA`:

```sh
/home/alex/work/pocket4-lmkd-host-bootstrap-r12-source-04/target/debug/owned-relay-canary prepare \
  /opt/p4-lmkd-relay-bootstrap-r12-01/root \
  /run/p4-lmkd-relay-bootstrap-r12-01 \
  p4-lmkd-relay-bootstrap-r12-01.service \
  /home/alex/work/pocket4-lmkd-host-bootstrap-r12-source-04/owned-relay/fixture-init ACTOR_SHA \
  /home/alex/work/pocket4-lmkd-enrollment-r6-android-build-01/link/lmkd-cgroup \
  bd794b7b59d1047523cea6174bcd230c75aa2eececd1900b23f3f33a86061dde
```

Require `evidence/staging-result.json` with all hashes matched and `processes_started:false`. A failed prepare leaves the fresh incomplete tree for inspection; there is no recursive or global cleanup in this program.

## One actual bootstrap invocation

Immediately before dispatch, the coordinator must verify the current Main activation/process-generation fence and capture its six current namespace inodes in exactly this order: `pid mnt cgroup ipc uts net`. The actor verifies that each of its new namespaces differs from both the original host and these Main values. Main may legitimately share a namespace with the host; that does not authorize reusing it for the actor. Keep normal device health/admission checks outside this owned unit and stop if they no longer hold.

Substitute those six recorded decimal values for `MAIN_PID_NS ... MAIN_NET_NS`, and the actual matching binary hashes for `ACTOR_SHA` and `BROKER_SHA`. The binary deliberately accepts no process-name lookup, pressure flag, automatic retry, or implicit namespace discovery for Main.

```sh
/usr/bin/systemd-run --unit=p4-lmkd-relay-bootstrap-r12-01.service --no-block --quiet \
  --property=Type=exec --property=RemainAfterExit=yes \
  '--property=Delegate=memory pids cpu' \
  --property=MemoryMax=512M --property=MemoryHigh=infinity --property=MemorySwapMax=0 \
  --property=CPUQuota=100% --property=CPUQuotaPeriodSec=100ms --property=TasksMax=64 \
  --property=Nice=10 --property=RuntimeMaxSec=60 --property=TimeoutStopSec=3 \
  --property=KillMode=control-group --property=LimitCORE=0 --property=LimitNOFILE=4096 \
  --property=LimitFSIZE=1048576 --property=RestrictRealtime=yes --property=UMask=0022 \
  --property=StandardInput=null \
  --property=StandardOutput=append:/run/p4-lmkd-relay-bootstrap-r12-01/unit.stdout \
  --property=StandardError=append:/run/p4-lmkd-relay-bootstrap-r12-01/unit.stderr \
  /home/alex/work/pocket4-lmkd-host-bootstrap-r12-source-04/target/debug/owned-relay-canary bootstrap \
  /opt/p4-lmkd-relay-bootstrap-r12-01/root /run/p4-lmkd-relay-bootstrap-r12-01 \
  p4-lmkd-relay-bootstrap-r12-01.service ACTOR_SHA \
  bd794b7b59d1047523cea6174bcd230c75aa2eececd1900b23f3f33a86061dde \
  /home/alex/work/pocket4-lmkd-host-bootstrap-r12-source-04/target/debug/droidloom-psi-owner BROKER_SHA \
  MAIN_PID_NS MAIN_MNT_NS MAIN_CGROUP_NS MAIN_IPC_NS MAIN_UTS_NS MAIN_NET_NS
```

The coordinator records the returned service InvocationID and treats it as part of the owned run identity. Do not issue this command again against the same tree, even on failure. The persistent O_EXCL relay claim intentionally denies such reuse.

## Evidence required for this narrow pass

Require all of the following from the exact fresh run:

- The unchanged source/build hashes and successful `staging-result.json`.
- `inner-preflight.json` and `outer-preflight.json` identify the new private namespace/root/domain and exact owner/init generations; `root_pressure_test_performed:false` and `lmkd_started:false`.
- Actual `broker-ready.json` and `relay-projection.json` agree on socket inode, scope and fixed budget.
- `broker-retired.json` is Retired, `granted:false`, `faulted:false`, with the same generation/scope; the exact broker exited 0.
- Revision05 additionally requires `broker-pressure-audit.json` from the joined worker before RETIRED; bootstrap has zero registrations/events. This observation record supplies no pressure qualification.
- `phase-result.json` is bootstrap, `lmkd_started:false`, `psi_registered:false`.
- `driver-result.json` records real broker ownership, same-living-cell retry denied, joined and reaped broker, exact owner/init exit, domain empty, `android_enrollment:false`, `real_pressure_verified:false`.
- The exact owned systemd invocation exited successfully, and the Main activation/process-generation fence and health still match.

Failure to get these records is an incomplete or failed bootstrap trial, not a pass. A failure before or after READY keeps the result incomplete; no status codec test can replace these observations. Capture stderr and state rather than guessing the cause.

## Rollback

On success, preserve receipts first, verify the exact owned invocation is stopped and `cgroup.events` is unpopulated, then remove only its fresh owned staging directories if desired. Mounts live in the actor's private namespace and disappear with its exact owner/init exit. The broker source socket may be unlinked on retirement; the one-shot claim intentionally persists until that terminated fixture is removed.

On failure, the driver does not write a success record or reset its slot. Broker and actor have kernel parent-death links to the driver; actor similarly arms its exact private init. The coordinator may stop **only** the recorded owned systemd unit/InvocationID, verify all owned processes are dead and the cgroup empty, and retain the failed evidence. This is forced owned-fixture teardown and must not be labeled a successful joined-worker retirement. Do not touch Main's ACK LMKD, current Android cell, installed supervisor, presenter, or any unrelated unit.

The next actual Android protocol trial needs a new unit and new tree. A passing bootstrap trial alone does not qualify installed lifecycle recovery, Android enrollment/SCM_RIGHTS, actual PSI forwarding, group-kill scope, foreground preservation, or application readiness.
