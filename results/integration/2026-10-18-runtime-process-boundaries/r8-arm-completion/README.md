# R8 ARM64 completion: exact commit 05a7cd23

GitHub Actions run [39106645234](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39106645234),
attempt 1, completed successfully on 2026-10-18. The actual `original-agentd` job
ran from **07:11:37 to 07:36:49 UTC** on `ubuntu-24.04-arm`. This read-only review
retrieved its API state at 15:06:13 UTC and then verified its original logs and
small evidence artifact. No gate, compiler, daemon or UI was started for this
review.

The executed desktop commit is
[`05a7cd23f0a4b90b154ef0c45be89093b129f767`](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/commit/05a7cd23f0a4b90b154ef0c45be89093b129f767),
tree `592e13cc526a247ec4246a4cfe8458e07392d0e1`. The fixed original Hepta commit
is `f8c9419df6ddeb36ff8b522a50219981fb8d9345`, tree
`15c9d6ea07bf3832de82825a6cc1e8c958dd3d45`. Both checkouts ended clean with the
same identities. The original Cargo lock remained
`8354b4cbdf14389db7aa5508e2ed5b524fc2d4c4ea0ecb475955c933f8bea389`.

## Actual completed scope

| Qualification | Observed result | Original evidence |
| --- | --- | --- |
| Original Agentd and read-only observer | 8 ordered checks passed. | [Report](artifact/report.json), [actual runtime log](artifact/work/original_agentd_process_probe.log). |
| Continuous read-only Session | 8 additional checks, across 6 phases; same Session/worker for the first 4, then explicit replacement for the final 2. | Same report and runtime log; full phase/identity mapping in [review](review.json). |
| Isolated original ObjectiveStart | 10 ordered core checks and 7 explicit submission attempts passed. | [Objective report](artifact/objective-work/report.json), [actual runtime log](artifact/objective-work/runtime.log). |
| Known-run Session projection | 3 phases: `compiled_run_projected`, `old_endpoint_run_stale`, `replacement_run_projection_missing`. | The objective report contains all three complete snapshots and explicit Session stop records. |
| Original gate Python prerequisites | 17 passed: 5 manifest, 6 process guard, 6 Session receipt tests. | [Raw prerequisite log](artifact/logs/gate-prerequisites.log). |
| Objective receipt Python contracts | 12 passed. | [Raw receipt-contract log](artifact/logs/objective-receipt-contracts.log). |

The seven ObjectiveStart values count explicit submission attempts; they are
not seven Session tests. The producer deliberately supplies the exact replay
attempt. That does not establish automatic retry behavior in the product CLI.
The observed CLI exit codes, in attempt order, are `0, 0, 0, 12, 10, 12, 12`.
The third admitted response is explicit abstention without a runtime run.

The objective Session retained its full nonterminal run observation as stale
history after the original owner restarted. A newly launched Session then
reported a missing current projection. The stopped-owner journal inspection
independently verified durable admission. Missing current projection does not
erase that history or establish a terminal result.

## Verification and source binding

The [full connector-decoded job log](job-117613820420.log) contains both complete
reports. Each report is byte-identical to the corresponding gate stdout in the
artifact, and its runtime records match the separate actual runtime log. The
original reports, selected logs and identity files were copied unchanged.
[Source verification](source-verification.json) compares every recorded service
and probe source hash, recorded desktop input hash, and consumer tree to the
fixed Git objects. [The executed workflow](hepta-original-agentd.yml) is also
preserved unchanged.

The downloaded **evidence** artifact is 1,710,211 bytes; its SHA-256
`af4017f029eedfafc5e40229ae3caf6bfce3003113f1299dadb9bf78f1595eac` matches the
GitHub API digest. All 83 ZIP entries passed CRC verification. The full ZIP is
not duplicated in this archive; its complete member manifest and checksum are
recorded in [download verification](download-verification.json), and 23 relevant
original members are retained under `artifact/`.

The fixed workflow successfully checked and packaged five native inputs for
the read-only run and six for the objective run. Four shared binary hashes
agree between the reports. This review **did not download either large ELF
archive or independently re-hash its binary contents**. The reports preserve
the executed binary identities, and the successful packaging steps check ELF64
AArch64 headers and exact execution hashes. Their API metadata remains in
[artifacts-connector.json](api/artifacts-connector.json).

## Qualification boundaries

The objective run uses a disposable, explicitly enrolled test issuer.
`production_issuer`, `model_turn`, `operations_dispatch`,
`canonical_intelligence`, `device_effect`, and `historical_run_resumed` all
remain false. No Shell was launched or captured by this ARM workflow, and phase
acknowledgments do not grant pixel qualification. The native desktop captures
already recorded for R8 are separate evidence.

This completion belongs to `05a7cd23` and its fixed workflow. It is not a new R9
CI result and does not qualify the later CLI SIGKILL tests, later UI changes or
later kernel history. Existing queued snapshots remain valid as historical
observations; this archive appends the now-completed R8 result.
