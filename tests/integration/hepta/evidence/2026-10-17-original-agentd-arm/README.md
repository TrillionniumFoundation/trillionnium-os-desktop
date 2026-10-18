# Original Hepta Agentd: executed ARM64 read-only gate

**PASS, 2026-10-17.** The unchanged original Agentd was built, linked and run by
the original owner libraries on a native GitHub-hosted ARM64 Linux runner.
[Run 39037037916](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39037037916)
completed successfully; [job 117408854785](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39037037916/job/117408854785)
ran from **14:04:19 to 14:28:30 UTC**. This is an executed original-process
acceptance result. The earlier local compiler-check receipts remain historical
prerequisite results with their original narrower qualification.

## Exact source, environment and commands

| Input | Immutable identity |
| --- | --- |
| Desktop checkout | [`1974d9a94037440da358253e1f449b395daa4b64`](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/tree/1974d9a94037440da358253e1f449b395daa4b64) |
| Desktop full tree | `48433c4f1e55de53e8c298193765949996eb18a0`; local equivalent `35f379101c0863027e971ccb91faf8da71cf929c` has that exact full tree |
| Original Hepta | [`f8c9419df6ddeb36ff8b522a50219981fb8d9345`](https://github.com/TrillionniumFoundation/hepta-private-ci/tree/f8c9419df6ddeb36ff8b522a50219981fb8d9345), tree `15c9d6ea07bf3832de82825a6cc1e8c958dd3d45` |
| Original Cargo.lock | SHA256 `8354b4cbdf14389db7aa5508e2ed5b524fc2d4c4ea0ecb475955c933f8bea389` |
| Gate | `run_original_agentd.py`, SHA256 `fff0b1228d6f02da4f5a02c3a1af3eb1e5f9aa55f5b7021b8db997934d5e5ceb` |
| Original-library probe | `original_agentd_probe.rs`, SHA256 `6620f550cbfa4fa9561df375d8bf52208bd342c8530319818cd4b5cf351c2beb` |
| Runner | `ubuntu-24.04-arm`, native `aarch64-unknown-linux-gnu`, original Rust 1.95.0 and observer Rust 1.88.0 |
| Final source state | Both checkouts clean; [final identities](final-checkouts.json) match the initial commits, trees and locks |

The exact workflow and gate are part of the bound desktop tree. The native
prerequisites were installed in the disposable Actions runner, with fresh build,
Cargo and Rustup homes. This did not install packages or change services on the
local audit host. The original library probe retained the original workspace's
resolver and patch identities; its actually resolved external lock is retained
in the raw ZIP. Its SHA256 is
`a69c778be383103bf49dac0148964ca871e78527abb6cff5eeff7ea2549c7dc1`.
This run resolved a new external root and does not reuse the earlier local
probe-lock hash as evidence.

The gate executed `--execute`, built the observer with Rust 1.88 and its locked
manifest, and built the unchanged original binary with Rust 1.95:

```sh
rustup run 1.95.0 cargo build --locked --profile dev-small \
  --no-default-features -p codex-hepta-agentd --bin codex-hepta-agentd -j1
```

Cargo reports 17.28 seconds for the observer, 18 minutes 27 seconds for the
original Agentd build and 4 minutes 24 seconds for the original-library probe
build. These are the actual stage log durations in this runner, not minimum
hardware requirements. The combined build/run step ran from 14:04:52 to
14:28:05 UTC. The report's `recorded_at_utc` is its initial allocation time;
it is not the completion time. Stage timestamps are preserved in
[github-jobs.json](github-jobs.json) and the losslessly compressed
[decoded job log](job-117408854785.log.gz).

## Actual acceptance result

[report.json](report.json) records `status: passed`,
`large_build_attempted: true`, `runtime_probe_attempted: true` and
`live_agentd_acceptance: passed`. All five build/resolution/probe steps passed,
the exit-code file is `0`, and there are no blockers. The raw process output is
[original_agentd_process_probe.log](original_agentd_process_probe.log).

| Check recorded by the original-library probe | Actual result |
| --- | --- |
| `original_starting` | Original Agentd observed at Starting, spawn/current 1/1 |
| `original_running` | Same PID 23763 observed Running, spawn/current 1/2, ready and promotion-ready |
| `bounded_capabilities_events` | Original capabilities and bounded lifecycle events read through the desktop observer |
| `missing_run_read` | Deliberately absent run in this fresh owner read as `null` |
| `same_process_draining` | Same PID observed Draining, spawn/current 1/3, no longer ready |
| `original_restart` | Original Supervisor restarted the process; PID 23856, spawn/current 5/6 |
| `old_spawn_rejected` | Old spawn rejected, followed by successful new-spawn observation |
| `controlled_stop` | Original Supervisor stopped its process; a post-stop read could not succeed |

The runtime records in the report are byte-for-byte equivalent JSON values to
the original process log. The original Supervisor/FleetRegistry/UnixProcessDriver
own registration, lifecycle and cleanup. No owner implementation, original
source module or runtime store was substituted.

## Verified executable bytes

Both GitHub artifact ZIPs were downloaded after the run. The ELF ZIP was read
as a stream through its nested tar archive without executing any ARM program
on the local x86 host. All three regular executable members have mode `0755`,
ELF64 little-endian headers and `e_machine = 183` (AArch64). Their actual sizes
and SHA256 values match both the executed report and the original
[binary manifest](binary-manifest.json).

| Executable | Bytes | SHA256 |
| --- | ---: | --- |
| `codex-hepta-agentd` | 268,391,592 | `3e0753ab7b544ae4a76dee7df4d5c918eb7c766fc271ac9f7111bdb1979ebd6f` |
| `hepta-original-observer-probe` | 22,375,664 | `60a950fe8eb7d85a65ffb16917c2a9088e89b9b13c0cd2c62e94e1a83f08c7ee` |
| `hepta-observe` | 13,681,224 | `3acf4a86268480ca481cf17a5e85205968bf8cd0e9fe2affdc37b9db8eddb48f` |

The manifest binds the actual report SHA256
`243c06209026b1d79e299fe2f40beddae27ab020cb9e3c0eff538ce40e60279d`.
The nested tar's report, manifest and sums match the separately supplied files.
The independent local byte verification is recorded in
[artifact-verification.json](artifact-verification.json); its exact executed
audit script is preserved as [artifact-verifier-executed.py](artifact-verifier-executed.py).
That snapshot includes the audit's absolute paths and local equivalent commit;
it documents the verification actually run, not a new portable runtime gate.

| Download | Bytes | SHA256 |
| --- | ---: | --- |
| [Raw evidence ZIP](hepta-original-agentd-evidence-39037037916-1.zip), artifact 12103957363 | 456,519 | `7608b75c69fed1ff020fa3dff06f27650c316a9cd492779fb7da592991187a03` |
| [ELF ZIP, artifact 12103529332](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39037037916/artifacts/12103529332) | 80,692,154 | `85214ef3134e50967d9737f67c2f1bfc9d1f44feee9942b836be01356989b8df` |
| Nested `hepta-original-agentd-aarch64-linux.tar.gz` | 81,462,734 | `75019319213050f1490213fcb78992680b4ab4d904b757a706a1501c4230ce9c` |

The small evidence ZIP is preserved in Git with all 25 original members. Its
logs, locks, generated probe source/manifest and large raw metadata have not
been rewritten or truncated. [RAW_MEMBERS.json](RAW_MEMBERS.json) records every
member's size, SHA256 and ZIP CRC, plus the decoded job log's original and gzip
hashes. Compiler and patch warnings remain in the original logs. The large ELF
bundle remains a workflow artifact under the workflow's **14-day retention**;
[github-artifacts.json](github-artifacts.json) records its expiry on
2026-10-31. The evidence in Git remains available after artifact expiry; it
does not make the expiring ELF download permanent.

## Qualification boundary and next acceptance

This passes the original Agentd read-only process gate on native ARM64 Linux.
Each read launches a fresh `hepta-observe` CLI. The gate has no persistent
`trill-session` worker, Shell window or UI event path, and its ready hold was
zero seconds. The separate x86 X11 IME evidence must not be represented as a
single end-to-end ARM Agentd-to-Shell run.

The next integration acceptance must bind a built Session to this same
original-owner launch through the trusted endpoint, retain a continuous worker,
observe Starting/Running/Draining and stale state, reject a restarted owner's
old spawn, and explicitly receive a trusted new configuration for a new
Session. It must verify the Shell projection independently. The existing
`--hold-seconds 30` option enables a bounded first-Running test window; it was
not exercised by this run.

`objective_submission`, `model_turn` and `device_effect` are all **false**.
No issuer, production authority or effect provider was installed. An original
capability name in an observation is not an executed provider or device effect.
An absent run here does not prove non-publication after a future ambiguous
submission. Asterinas guests, Android/iOS, hardware input and physical device
control remain outside this receipt.
