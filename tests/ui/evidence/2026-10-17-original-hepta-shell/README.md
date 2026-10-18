# Original Hepta → persistent Session → native Rust Shell: R6 evidence

Two complete six-stage runs passed against the **unchanged original Hepta Agentd**. Each run used one continuously running native Rust Shell, a real Session worker for stages 1–4, and an explicitly replaced trusted Session for stages 5–6. Thirteen original framebuffer PNGs are retained: the first failed attempt's Starting image, six images from the existing R5 UI, and six from the newly compiled observation-freshness UI. A10, the root integrator, and the independent reviewer individually inspected the images. Raw machine receipts continue to say that a separate visual review is required; the additional review records supply that review without rewriting executed receipts.

Start with [report.json](report.json), [source-bindings.json](source-bindings.json), and the [independent review](reviews/independent-original-shell-review.json). [SHA256SUMS](SHA256SUMS) covers every archived file except itself. [copy-manifest.json](copy-manifest.json) identifies each copied original, byte count, SHA-256 and original file mode. There are no executables, Cargo targets, private display cookies, font bytes, or original Agentd state databases in this archive.

## Exact executed sources

| Attempt | Actual execution commit | Actual tree | Production UI build source | Result |
| --- | --- | --- | --- | --- |
| capture01 / runtime01 | `c50d7b9b688135a22ced2f7f3cbe21c3028d8e17` | `1b606b1922751fe938fa4bcca0a923516323f418` | R5 `35f379101c0863027e971ccb91faf8da71cf929c` | Failed initial capture oracle; one real PNG; no ACK |
| capture02 / runtime02 | `28843c6632fe63db6b3fecb4d05888e90976fd16` | `759c42b36d965174dc00a39b7f28e962ed667d85` | Same R5 build | Six stages passed |
| capture03 / runtime03 | `145e94c364243789b88c23b1292f9d4d9ca9a0e9` | `98dee80a7ec855a84c777b350fed8ef675e31fc1` | GREEN03 `84f0070b6e7e01238a8dac6044748b15101c9497` | Six stages passed |

The root integrator supplied these published objects with the same trees: old successful source [66dba7f4](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/commit/66dba7f40c2fa8fea2e7828ec2fd4db336bb681f), new successful source [299794f9](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/commit/299794f90d4557cec4ee9a7fc92c397031fced4f), and final oracle [cd92cf08](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/commit/cd92cf08c398bfbf8ea55381acc529d210a5bdc1). These are publishing mappings, not substitutions for the original execution IDs. A10 verified the local executed objects, full `ui` subtree, external Session dependency closure, and executed helper blobs; A10 did not fetch those new remote objects independently.

The original Hepta pin remains `f8c9419df6ddeb36ff8b522a50219981fb8d9345`. Both runs used the same actual original Agentd ELF SHA-256 `f476f9bb435c5127839c48ae7135d5a6fa7695ff5253460fdd8d19d7b084d4fa` and linked original probe SHA-256 `46c8f20bef00d5e4b76ae7fcba784937bc1c4d9a33d6b416cd4acc1b96d43365`. The original probe's owner receipts and complete build/runtime evidence are maintained by A07; the paired runtime receipts are included here to bind the UI results directly to those owners.

### UI executable identities

| Actual binary | Existing R5 build used by capture01/02 | GREEN03 build used by capture03 |
| --- | --- | --- |
| `trill-shell` | `81e9bcbf79c4060c3047ad0c80df711bfd855f2f47c3900522927d37404d776f` | `62d0f304d6a3a53db4bc605e374470a924a56bfeb63387b1c12f9f245f17536a` |
| `trill-session` | `5c29cfd7f11455000d7c3d9c0cc2c58fb7fe8761ab326da34c794d0f3481924f` | `f152e6413742baa3349aded2283f9aff41bfe1bc552586aa260ade6327d5d16d` |
| `trill-ctl` | `920093314640ad1dd721425ec78457f4ca74c83f9c1a0a878d4ddfee4924a882` | `ba85b891f91a88ac3ad5240535f5dd6261c47eadbcc1bb64593add0a0aa2b598` |

The full production closure includes `services/hepta-os/src`, its `Cargo.toml` and its `Cargo.lock`, in addition to `ui`. That path dependency is outside the UI directory. Matching only `ui` would not bind a reused Session binary sufficiently. The new build produced four binaries; `trill-app-window` has SHA-256 `08c3bbe84b5d6e773f367f9751a1432eaee327bf45a5b172150f34f165342510` and was not launched by this read-only capture. All four build identities and actual RED/GREEN attempts are in the sibling [observation-freshness evidence](../2026-10-17-observation-freshness/README.md).

## Actual visible behavior

The visible Agent ID is `22222222-2222-4222-8222-222222222222` throughout. The table uses spawn/current generation pairs. Each image has its own raw phase record and actual Session IPC snapshots immediately before and after capture.

| Stage | Existing R5 PNG | New GREEN03 PNG | Visible outcome |
| --- | --- | --- | --- |
| 1 Starting | [R5 phase 1](capture02-r5-passed/phase-1-starting.png) | [new phase 1](capture03-freshness-passed/phase-1-starting.png) | OBSERVED, Starting, 1/1, ready false, promotion ready true |
| 2 Running | [R5 phase 2](capture02-r5-passed/phase-2-running.png) | [new phase 2](capture03-freshness-passed/phase-2-running.png) | OBSERVED, Running, 1/2, ready/promotion true |
| 3 Draining | [R5 phase 3](capture02-r5-passed/phase-3-draining.png) | [new phase 3](capture03-freshness-passed/phase-3-draining.png) | OBSERVED, Draining, 1/3, ready/promotion false |
| 4 Old spawn after restart | [R5 phase 4](capture02-r5-passed/phase-4-old_spawn_stale.png) | [new phase 4](capture03-freshness-passed/phase-4-old_spawn_stale.png) | STALE, `protocol_mismatch`; current state unknown; old Draining history retained |
| 5 Explicit trusted replacement Session | [R5 phase 5](capture02-r5-passed/phase-5-recovered_running.png) | [new phase 5](capture03-freshness-passed/phase-5-recovered_running.png) | OBSERVED, new original process, Running, 5/6 |
| 6 Original process stopped | [R5 phase 6](capture02-r5-passed/phase-6-stopped_stale.png) | [new phase 6](capture03-freshness-passed/phase-6-stopped_stale.png) | STALE, `unavailable`; R5 retains Running 5/6, new run retains Draining 5/7 |

The final stop observations differ because original termination can progress through Draining before the worker's last successful sample. Both runs retain their actual last observation unchanged across subsequent failed polls. These results do not establish that the UI fix caused the timing difference. Both main panel and Inspector clearly identify stale history and unknown current state. The UI continues to show objective submission unavailable.

| Run | One continuous Shell | Session stages 1–4 | Session stages 5–6 | Actual original process IDs |
| --- | --- | --- | --- | --- |
| R5 | PID 615673; XID 2097155 | PID 615562, worker 615564, instance `b4122eb42acae07a5d5b97c1c496e2fd` | PID 615926, worker 615929, instance `b4b8c3aa629eeac9d5968a060d2b0559` | 615532 → 615755 |
| GREEN03 | PID 616470; XID 2097155 | PID 616357, worker 616359, instance `1726d69f559ede7d224e8bc0f12c282b` | PID 616715, worker 616717, instance `7df3d71d043233ca8649ad3560f57432` | 616327 → 616535 |

Session PID/instance are established by the raw owner records and actual kernel IPC peer credentials; the screenshots display “SESSION ONLINE” rather than those Session identifiers. A single persistent Shell/window is established by the process and X window records, not by visual similarity.

### Sampling and image limits

The capture uses actual `XGetImage` bytes from a private authenticated Xvfb framebuffer, not generated images or an injected renderer projection. The original Session data reaches the real Rust Shell through its ordinary Session IPC polling. An actual before snapshot, 2.5-second paint/poll interval, raw PNG, and actual after snapshot bind each stage. Human reviewers then read the pixels and compare visible identity, phase, readiness, diagnostics and sample times.

The displayed sample may be an intermediate legitimate sample. In old phase 3 it is `1792277800252`, between before `1792277799249` and after `1792277801255`. In new phase 5 it is `1792278000290`, between `1792277999287` and `1792278001295`. It would be incorrect to require every visible timestamp to equal the final after snapshot. Stale stages separately require the complete retained observation to remain identical. Full live-phase identity, lifecycle, capabilities and ordered event-prefix constraints remain enforced.

The layout probe emits one marker from the first actual Hepta-page update. It is not six phase-specific render receipts. Six raw PNGs plus the separate visual reviews qualify the six visible stages. The private ACK JSON files release lifecycle barriers; they are coordination records, not pixel proof.

## First failed attempt and oracle correction

[capture01](capture01-failed/capture-receipt.json) remains failed with `live runtime metadata changed: health`. Its [Starting PNG](capture01-failed/phase-1-starting.png) is real. Before capture, promotion readiness was false and the event cursor was 2; afterwards promotion readiness was true and cursor 3 contained `app_server_ready`. Agent, process, spawn/current generation, Starting lifecycle, ready=false, fenced=false and capabilities were unchanged. Original app-server readiness legitimately completes asynchronously during Starting. Comparing the complete live health object for equality rejected that progress.

The final oracle permits only Starting's false→true promotion transition. It requires Running promotion readiness true, Draining promotion readiness false, strict booleans, fenced=false, stable source identity, monotonic sample/cursors and an exact existing event prefix. The after snapshot is compared against both the owner-held phase and the actual before snapshot, so an intermediate true value cannot regress to false. Original observation uses separate Health → Capabilities → Events → Health RPCs; the final health may already be ready while the preceding event page still lacks the readiness event. Tests tolerate independent RPC combinations without claiming that both synthetic combinations were observed in the original run. Complete stale-observation equality remains strict.

The read-only [raw frame replay](oracle-fix/raw-frame-replay.json) shows the original oracle rejecting the preserved frames and candidate commit `68c9aa3df9a45906a44d20bd7f1a0bc684a19f02` accepting them. This was a replay, without a new runtime, PNG or ACK. The final `aa3fc6feac114ee78910be604fa2a190be080ab0` adds the explicit unfenced constraint and precise documentation. Its [actual eight contract tests](oracle-fix/final-tests-receipt.json) pass, and that final oracle produced both subsequent real successful captures. The candidate and final-source evidence are intentionally distinguished.

The initial attempt did not ACK phase 1. Shell/Xvfb cleanup ran, and the original owner hit its existing 120-second phase deadline and failed. That first runtime receipt remains failed; it is not relabeled as successful cleanup qualification. The two successful owners report all eight original-process checks, all eight persistent-Session checks, six exact ACKs, unchanged source/binary/helper identities, private-state cleanup and a disarmed child guard after completion.

## Production freshness fix and qualification

The separate production P2 fix addresses queued old Observed responses after a paused UI: receiving an old response must not refresh only the local arrival clock and make stale source data look current. It checks both monotonic receipt age and original sample time before every page is drawn, preserves historical data and existing stale diagnostics, and restores Observed only after a valid new sample. Six Rust regressions cover the real pre-draw receive/status path, boundary ages, future/missing samples, retained stale diagnostics and recovery. The build archive preserves RED, mistaken RED cache reuse in GREEN01, actual GREEN02 test success followed by a strict-Clippy helper-type failure, and complete GREEN03 success. These ordinary six-stage live captures qualify integration of the newly bound production ELF; they do not replace or pretend to reproduce the delayed-queue regression.

The display rejects access without its private cookie and listens on no TCP port. Original owner, Session, Shell and Xvfb are bounded task-owned processes. A fresh exec wrapper sets `PR_SET_PDEATHSIG(SIGKILL)` and immediately verifies the expected parent PID; the actual parent-death regression confirms the exec child leader dies and is reaped after its parent is killed. Normal cleanup handles the owned process groups. That regression does not qualify arbitrary descendant-tree termination.

This evidence establishes Linux x86_64 native Rust/egui **read-only** original-Hepta projection through a persistent real Session and private X11 rendering. It does not establish physical-display operation, a target Rust kernel, mobile-device support, desktop control effects, keyboard/IME input, objective ingress, model turns, or completed AI actions. The captured Hepta screen is a runtime inspection page; chat-centered redesign and control ingress are separate work.
