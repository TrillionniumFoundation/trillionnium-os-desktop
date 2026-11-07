# Owned PSI pressure and stale-queue continuation, revision06

This is an uninstalled host/actor candidate. It does not change the Android r6 binary or its default 70/700/1000 ms PSI settings. Preparation and local controls have not executed either pressure phase. Parent freeze04's actual bootstrap and Android protocol/HUP passes remain valid for those parent bytes; they are not revision06 matching-build or pressure results.

## Fixed admission and scope

Use a new build directory, for example `/home/alex/work/pocket4-lmkd-host-pressure-r11-source-06`, and a new root/state/unit/invocation for each phase. The names below are proposed fresh names, not a statement that they exist. Never reuse a retired or failed cell. The coordinator owns all device actions and retains its existing Main epoch, health, resource-admission and other-session fence.

| Boundary | Fixed value |
|---|---|
| Outer owned systemd unit | 512 MiB max, unlimited high, swap 0, one CPU, 64 tasks, nice at least 5 |
| Measured child `domain` | Initial max 512 MiB, high 384 MiB, swap 0; never changed after authority creation |
| Native registered PSI | Actual write must equal `some 70000 1000000` and `full 700000 1000000` |
| Registered owned cached target | 64 MiB, UID 10001, oom_score_adj 900 |
| Registered owned foreground | 128 MiB, UID 10002, oom_score_adj 0 |
| Registered protected target | 16 MiB, UID 10003, oom_score_adj -1000 |
| Additional owned processes | 4 MiB sentinel and an unregistered allocator capped at 216 MiB |
| Allocation progression | 4 MiB requests; 16 MiB extra per-step reserve; observed current cap 432 MiB; intended plateau about 412–416 MiB |
| Abort | Any changed bound, max/OOM counter, wrong victim, second kill, lost identity, new/still-fresh stale event, incomplete audit, or deadline |
| Outer wall-clock bound | Exact owned unit `RuntimeMaxSec=60`, `TimeoutStopSec=3`, `KillMode=control-group` |

The initial below-high plateau must remain quiet for more than two original windows, with all targets alive and zero actual kill count. The larger foreground target makes the cached-first priority choice observable. Pressure is requested only through allocations by the owned child; no forged PSI frames, lowered thresholds, production test server, or direct pressure-file injection is used.

The positive phase stops requesting allocations at the first observed cached pidfd exit. One already requested chunk may finish its bounded allocation/acknowledgement. The final reserve and cached size must return current below high after that single victim; otherwise the trial fails rather than allocating against the remaining foreground target. A medium-only event followed by a legitimate cached kill produces `partial_medium_only`, not a critical pass. The actor never continues pressure to force a critical event after a victim.

The separate `stale` phase stops only the exact owned LMKD through its pidfd after real enrollment. It queues real kernel pressure observations, stops allocating, waits 2200 ms with stationary scoped PSI totals, then resumes that exact LMKD. Every actual queued event must already be older than its unchanged window; all targets stay alive and actual kill count remains zero during the next 1200 ms above-high observation. After this observation is complete, the allocator releases only its own pages while all processes stay alive. This creates cleanup headroom without changing memory budgets or erasing any queued event. Any later event in the terminal audit still makes stale qualification inconclusive.

## Matching build and ordinary controls

Hash all input files against the new source manifest before and after this single bounded build. The parent Android r6 binary is unchanged:

`/home/alex/work/pocket4-lmkd-enrollment-r6-android-build-01/link/lmkd-cgroup`

SHA-256: `bd794b7b59d1047523cea6174bcd230c75aa2eececd1900b23f3f33a86061dde`.

```sh
cargo build --locked --offline -j 1
cargo test --locked --offline -j 1
./target/debug/owned-ipc-controls
g++ -std=c++20 -O1 -Wall -Wextra -Werror -pthread owned-relay/fixture_init.cpp -o owned-relay/fixture-init
python3 -B -m unittest discover -s owned-relay -p test_qualify_pressure.py -v
sha256sum target/debug/droidloom-psi-owner target/debug/owned-relay-canary owned-relay/fixture-init
```

Expected controls are 20 Rust tests, seven ordinary IPC controls, strict actor compilation, and 16 Python tests. The Python tests use explicitly synthetic evidence and temporary ordinary files; they do not prove kernel PSI, Android, or a native kill. The socketpair tests prove terminal packet framing/FD cleanup; they do not substitute for namespace admission.

Use the actual build receipt's broker/driver/actor hashes. A nonmatching source, warning requiring correction, failed test, or missing terminal build result blocks a device trial. Parent freeze04 binaries cannot be relabelled revision06.

## Prepare one fresh positive cell

Only after the matching build and current device admission, the coordinator may prepare the fixed paths. Substitute `ACTOR_SHA` with the actual new matching actor hash.

```sh
/home/alex/work/pocket4-lmkd-host-pressure-r11-source-06/target/debug/owned-relay-canary prepare \
  /opt/p4-lmkd-relay-pressure-r11-01/root \
  /run/p4-lmkd-relay-pressure-r11-01 \
  p4-lmkd-relay-pressure-r11-01.service \
  /home/alex/work/pocket4-lmkd-host-pressure-r11-source-06/owned-relay/fixture-init ACTOR_SHA \
  /home/alex/work/pocket4-lmkd-enrollment-r6-android-build-01/link/lmkd-cgroup \
  bd794b7b59d1047523cea6174bcd230c75aa2eececd1900b23f3f33a86061dde
```

Preparation validates all 15 frozen library files and both new/copied executables. It creates no process or namespace, does not touch Main, and uses O_EXCL/fresh directories. Failure leaves only this owned incomplete tree for inspection.

## One positive invocation

The coordinator obtains the six current Main namespace inodes in order `pid mnt cgroup ipc uts net`, and uses only that captured fence. Substitute those decimal values and the exact new broker/actor hashes. Preserve one returned systemd InvocationID for this single dispatch; a timeout reading the result is reconciled against the same invocation, never dispatched again.

```sh
/usr/bin/systemd-run --unit=p4-lmkd-relay-pressure-r11-01.service --no-block --quiet \
  --property=Type=exec --property=RemainAfterExit=yes \
  '--property=Delegate=memory pids cpu' \
  --property=MemoryMax=512M --property=MemoryHigh=infinity --property=MemorySwapMax=0 \
  --property=CPUQuota=100% --property=CPUQuotaPeriodSec=100ms --property=TasksMax=64 \
  --property=Nice=10 --property=RuntimeMaxSec=60 --property=TimeoutStopSec=3 \
  --property=KillMode=control-group --property=LimitCORE=0 --property=LimitNOFILE=4096 \
  --property=LimitFSIZE=1048576 --property=RestrictRealtime=yes --property=UMask=0022 \
  --property=StandardInput=null \
  --property=StandardOutput=append:/run/p4-lmkd-relay-pressure-r11-01/unit.stdout \
  --property=StandardError=append:/run/p4-lmkd-relay-pressure-r11-01/unit.stderr \
  /home/alex/work/pocket4-lmkd-host-pressure-r11-source-06/target/debug/owned-relay-canary pressure \
  /opt/p4-lmkd-relay-pressure-r11-01/root /run/p4-lmkd-relay-pressure-r11-01 \
  p4-lmkd-relay-pressure-r11-01.service ACTOR_SHA \
  bd794b7b59d1047523cea6174bcd230c75aa2eececd1900b23f3f33a86061dde \
  /home/alex/work/pocket4-lmkd-host-pressure-r11-source-06/target/debug/droidloom-psi-owner BROKER_SHA \
  MAIN_PID_NS MAIN_MNT_NS MAIN_CGROUP_NS MAIN_IPC_NS MAIN_UTS_NS MAIN_NET_NS
```

The actor/driver enforce their own 35-second workload wait and shorter setup/retirement waits. The outer 60-second unit limit is the absolute device bound. A timeout is an incomplete trial, and forced teardown is not a successful retirement receipt. After exact LMKD exit, every nonvictim is checked again and reaped normally after its owned Q command; a dead target cannot be silently skipped during cleanup.

## Separate stale phase

After the positive invocation's receipts and exact teardown are reconciled, a stale trial needs its own admission and fresh root/state/unit, such as `p4-lmkd-relay-stale-r11-01.service`, `/opt/p4-lmkd-relay-stale-r11-01/root`, and `/run/p4-lmkd-relay-stale-r11-01`. Use the same new matched binaries, prepare those new paths, and change the invocation mode from `pressure` to `stale`. The limits and six freshly checked Main namespace values remain required. Do not automate a retry or reuse the positive tree.

## Evidence correlation

Native `phase-result.json` and host `driver-result.json` intentionally retain `real_pressure_verified:false`. Each proves its own completion checks; the combined qualification additionally requires the joined host registration/event audit. The driver's `pressure_audit()` becomes readable only after exact broker reap.

The coordinator creates `qualification-inputs.json` only after collecting the complete actual evidence set. Its schema is:

```json
{
  "schema": 1,
  "phase": "pressure",
  "source_manifest_sha256": "ACTUAL_REVISION06_SOURCE_MANIFEST_SHA",
  "matching_build_receipt_sha256": "ACTUAL_MATCHING_BUILD_RECEIPT_SHA",
  "binaries_sha256": {
    "actor": "ACTUAL_ACTOR_SHA",
    "driver": "ACTUAL_DRIVER_SHA",
    "broker": "ACTUAL_BROKER_SHA",
    "android_lmkd": "bd794b7b59d1047523cea6174bcd230c75aa2eececd1900b23f3f33a86061dde"
  },
  "files": [
    {"name": "ACTUAL_REQUIRED_BASENAME", "sha256": "ACTUAL_FILE_SHA", "bytes": 123}
  ]
}
```

This is a shape illustration, not a valid run manifest. The actual list must exactly equal `qualify_pressure.required_names(phase)`, with no missing, extra, duplicate or path-traversing name. It contains staging and namespace/root receipts, READY/ACTIVE/RETIRED/projection, joined pressure audit, driver/native completion, owned identities, actual pressure-file identity, workload, before/after samples and the complete five-target final cleanup classifications. Positive additionally requires exact cached pidfd SIGKILL, LMK_PROCKILL identity/RSS and owned native kill diagnostic. Stale additionally requires the post-observation owned-page release receipt. No commercial logs, APKs or secrets are needed.

The caller supplies both manifest hashes from outside the artifact, so a self-reported empty or substituted evidence list cannot authorize itself. The verifier opens only fixed regular basenames through a held directory FD, rejects symlinks and duplicate JSON keys, checks lengths/hashes and full input sets, and performs no process or unit action.

```sh
python3 -B owned-relay/qualify_pressure.py \
  --evidence-dir /run/p4-lmkd-relay-pressure-r11-01/evidence \
  --manifest-sha256 ACTUAL_EXTERNAL_EVIDENCE_MANIFEST_SHA \
  --source-manifest-sha256 ACTUAL_REVISION06_SOURCE_MANIFEST_SHA \
  --phase pressure
```

Exit 0 is the narrowly described phase pass; exit 2 is valid medium-only partial pressure evidence; exit 1 is rejected/inconclusive. Real critical-event correlation requires a successfully queued original critical event before the observed cached exit and within the original window. The separate native diagnostic reports whether the actual kill decision was the critical `device is not responding` branch; correlation alone is not relabelled proof of that decision branch.

The qualifier does not itself prove the coordinator's source/build provenance, outer-unit OOM counters, exact systemd InvocationID, Main epoch or final unit cleanup. Those independent receipts must be checked before the coordinator marks a run accepted. Its output always leaves installed supervisor recovery, cgroup.kill, PID reuse and all-app production readiness unqualified.

## Failure and rollback

Stop issuing allocations on the first observed victim, reserve/deadline boundary or failed check. The source uses only retained exact child pidfds, private inherited channels, fresh owned roots and the fixed unit scope. It never kills a process by name or sweeps unrelated cgroups.

On normal completion, broker RETIRED plus exact reap precedes release of the private owner/init. Native HUP must disable pressure effects without an extra victim. The driver then verifies actor/init exit and an unpopulated domain. Preserve all receipts, stop only the exact owned InvocationID's unit, and verify the unit/cgroup are gone and Main's fence is unchanged.

On failure, preserve the failed evidence and exact invocation identity. The coordinator may stop only that recorded owned unit, whose control-group kill/PDEATHSIG relationships terminate its remaining private processes. Verify exact owned exits and empty/removed cgroup; label it forced teardown rather than joined-retirement success when the required receipt is absent. There is no installed binary change to roll back. Never alter Main's LMKD, presenter, installed supervisor or unrelated sessions.
