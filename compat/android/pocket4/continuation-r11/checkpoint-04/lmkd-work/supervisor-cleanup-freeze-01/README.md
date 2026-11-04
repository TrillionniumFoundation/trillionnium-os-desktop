# Bound supervisor cleanup retention — revision 01

This freezes a cleanup-state fix against the retained source that was bound to
the two binaries installed on Pocket4. The source binding is reproduced under
`reference/`; this is not a build from the older audio-supervisor reference.
No installed binary, Main cell, Android runtime, network object or app was
changed by this work.

## Behavior changed

`DevelopmentCell` marks itself cleaned only after network teardown and runtime
directory removal both succeed. A failed network teardown retains the network
owner and prevents deletion of its runtime recovery record. Setup/spawn rollback
also preserves that directory if network retirement fails.

`DevelopmentNetwork` removes a resource from its ownership stack only after the
actual delete succeeds. It stops at the first failure, retaining the failed
resource and lower dependencies. A failed forwarding restore retains both its
previous value and recovery file. If the restore succeeds but record deletion
fails, a same-owner retry deletes only the record and does not repeat the global
sysctl write. The deterministic object names and delete targets are unchanged.
Recovery stops before consuming the forwarding record when resource retirement
fails, and retains the record when the actual restore fails.

`Daemon` retains its `ActiveCell` on failed polling, stop or shutdown. The failure
latch blocks new start/restart and operations needing an active healthy cell.
Routine polling neither repeats cleanup effects nor clears the slot. The loop
continues servicing failure responses rather than exiting and dropping the
owner. An authorized explicit stop or final shutdown can retry remaining work;
only real cleanup success releases the cell. The wire response adds
`cleanup_failed`, with `ok: false` and the retained child PID. Older strict
protocol clients reject the new enum value; the three lifecycle binaries must
be handled together during any later integration.

## Actual validation

The original retained implementation, with only a test helper and one owned
regression test appended, reproduced the defect: deletion of an owned
`android-cmdline` directory failed, but its second poll returned success. The
child was an actual owned `/bin/true` process and was reaped; this was not a
modeled cleanup result. The exact append and original receipt are included.

The first validation job shared a Cargo target directory between original and
candidate copies. Its candidate invocation replayed the original 75-test
binary, including the expected red regression. The command failed and the
actual-test/count gate rejected it. That candidate stage is unqualified. Its
receipt is preserved as `evidence/build-01-result.json`; only its original-code
negative control is used.

The second job used a newly created candidate source and target directory. It
copied and verified all 561 retained source entries, applied four pinned files,
ran rustfmt on the three Rust files, and recorded the exact formatted input
inventory before compilation. All seven new test names were observed in the
candidate output. Results were:

- 81 library tests and 10 CLI integration tests passed; none failed or were
  ignored. This includes the existing 84 tests and seven cleanup controls.
- `droidloomd`, `droidloomctl` and `droidloom-supervisor` built successfully in
  the development profile. They are not installed release artifacts.
- New controls exercise an actual failed owned-directory cleanup repeatedly
  through cell wait/stop and daemon poll/stop/shutdown, reject reentry, verify
  exact owned child retention and normal explicit recovery, and keep the actual
  owned Unix listener alive across a polling failure.
- Network controls call the same production teardown algorithm through its
  narrow effect seam. Real owned-file failures replace only host network/sysctl
  effects; they verify retained resources, recovery data and no replay of a
  completed forwarding restore. No host `ip`, `nft`, `iptables` or sysctl effect
  is performed by these new controls.
- The actual job enforced one CPU, 512 MiB and nice 5. Its max/OOM counters
  remained zero, all candidate inputs were unchanged after build/tests, and the
  original 561 source entries still matched the bound inventory.

The successful job was `1a1a7479613-fc05-2ad2`, completed at
`2026-11-04T15:57:54.528787Z`. The exact receipt SHA-256 is
`43d6de97be053cc15790fd9db8316177639b7600dd659709d13b14f910fc3c56`.
The source inventory used by that job is
`35d414aea3cb2f60e9a9ba2e367060530f77fe5671ea00347856e0114ade4309`.
The existing `cpu-placement-probe` example emits two unused-function warnings
(`task_profiles` and `graphics_service`); neither function is changed here.
The candidate binary build itself produced no warning.

## Files and reproduction

`source/` contains the exact 25-file source/reference export with the four
matching changes applied. It is an excerpt of the full workspace, not a
standalone Cargo workspace. `preimage/` contains the four original changed
files. `changes.patch` applies those changes to the complete bound source;
`reference/source-inventory.json` specifies that full 561-entry baseline.
The matching-build scripts demonstrate the create-only source-copy, resource,
input and control gates. They contain fixed unique historical destinations and
must not be rerun against those existing destinations.

The successful remote build is retained under
`/home/alex/work/pocket4-supervisor-cleanup-r11-build-02`. The original source
remains at
`/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/production-media-term-candidate`.
Do not modify the original. A subsequent build needs a fresh destination and
idempotency key, exact preimage/source pins, its own Cargo target directory,
one build job, the same controlled offline dependencies and explicit bounded
resources. No daemon/lifecycle action is part of these build commands.

Rustfmt also normalized existing layout in the three changed Rust files. The
matching freeze keeps those exact compiled bytes; unrelated format changes do
not add runtime behavior.

## Qualification still open

Retention is guaranteed while this daemon owns its in-memory cell handle. Final
shutdown can still return an error and the process can be forcibly terminated;
cross-daemon recovery and proof that the old namespace has fully retired require
the separate installed lifecycle integration. Existing numeric-PID/PDEATHSIG
behavior, recovery existence probes and cross-generation forwarding-record
replay are not claimed fixed by this patch. Network creation failure can leave
deterministically named residue for explicit recovery; this is not a completed
rollback claim.

There is no installed LMKD lifecycle hook, real network failure canary, release
deployment, production Android recovery or app acceptance in this receipt.
The patch is not evidence that all Pocket4 apps are production ready.
