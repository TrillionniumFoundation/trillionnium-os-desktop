# A01 fresh owner and CI evidence, 2026-10-17

This archive freezes the **existing remote observations from this task**. It runs no compiler, Cargo, QEMU, kernel, owner test or installation. [Report](report.json), [tool requests](commands.json), [retrieval provenance](retrieval.json) and [source bindings](source-bindings.json) preserve what was read and the exact scope. GitHub event timestamps are retained; per-request client timestamps were not captured and are not reconstructed. Packaging time is separate. JSON payload fields are retained with serialized whitespace; log/source files preserve the decoded connector text, not HTTP transport/ZIP bytes.

| Owner/ref | Fresh remote observation | What it establishes |
| --- | --- | --- |
| A01 PR22 /01a344c6 |Three check-runs completed success. Real host-evidence run38934897399/job117087809403 passed boot23x2, runner30x2, archive20x2: **146 executions** |Scoped host CI dispatch/completion closed for this published source, not kernel execution or future heads |
| A02 PR76 /606244b6 |Real G0 host-contracts run38932550749/job117079887722 success with stable Rust1.99.0 |Owner branch CI green; not kernel-pinned nightly acceptance |
| A00 workflow PR83 /f0a5e45b |Pinned-host-codec run38933667337/job117083661444 success, but actual stdout says bootstrap only and no fixed-nightly tests executed |Workflow bootstrap only, not13-step acceptance |
| A06 PR18 /57b23ede |Still Draft; issue63 open; cpu source45d93fe1 still returns on dead Weak Process |Potential uncharged final interval remains; no new QEMU exploit is claimed |
| A06 retained kernel evidence |OSTD221/core153 reported374,3VMX/EPT soft skips, exercised lower bound371 |Owner historical source-bound regression only, not A01's earlier359 denominator or final-debit proof |
| A06 real G0 job |Run38932286139/job117079015930 failure from three ABI test-helper Clippy diagnostics; later control stages skipped |Actual host failure, distinct from kernel compilation |
| A05 visible branch0013f91b |Latest change is Linux QueryAbi/ENOTTY probe; inspected ioctl remains generic |No new native five-operation implementation/acceptance evidence |
| A04 PR8 /77edc6bf |Latest commit restores executable mode. Its retained cloud preflight exits2: QEMU unavailable, raw guest exitnull |Owner still has no guest result there; no new fd-limit/SCM_RIGHTS fix or guest pass |

## Exact A01 CI source and denominator

The real job checked out synthetic merge e4677fe48628763831531cac5bbef8d358ce2f7c, with parents mainbc294f75 and A01 head01a344c6. Both full commit objects identify **the same complete tree351a2dc689ce515cf9a3a521cad192813cc15745**. Therefore the146 actual host executions bind to that A01 tree despite the workflow's synthetic checkout. The complete [job log](logs/pr22-host-evidence.log), [job steps](api/pr22-job-steps.json), [checks](api/pr22-check-runs.json), [head commit](api/pr22-head-commit.json) and [synthetic commit](api/pr22-synthetic-commit.json) are retained. Archive sources existed and20 real tests ran in each mode; this was not the source-absent bootstrap.

## Distinguish the A02 results

The [A02 stable G0 log](logs/pr76-stable-g0.log) actually identifies rustc1.99.0 b940084d7 and the stable toolchain path. The [workflow83 log](logs/pr83-pinned-bootstrap.log) actually prints: BOOTSTRAP ONLY: A02 runner not yet present; no fixed-nightly tests executed. Neither can be relabeled a new kernel-nightly13-step run.

A02 also committed its own [configured-cloud pinned acceptance record](api/pr76-owner-pinned-acceptance.json), reporting13 successful checks and no unexecuted checks. It is included as **owner evidence**, not a newly executed independent result. Its execution provenance names pre-merge working HEAD00061b6 and exact input hashes; the final merge606 is not presumed byte-identical merely from that HEAD. The root task is separately responsible for independent exact606 validation and adoption coordination. Current main remainsbc294f75.

## Remaining runtime ownership

A06 [source](source/a06-cpu.rs), blob45d93fe11506e6f6813142de1012352b958a5897, still returns when weak_process().upgrade() fails in charge_task_cpu. [Issue63](api/issue63.json) remains open. Its concern is lost pending final runtime under original cgroup ownership; existing percentage/kernel-test results do not specifically prove that debit. The separate [failed stable G0 log](logs/pr18-stable-g0-failure.log) reports chunks_exact_to_as_chunks in transport_preflight, mutation_kill and transport_vectors and exit101, with control checks skipped. This is not an A06 kernel compilation failure.

A05 owns the actual process/CapSpace/ioctl implementation. A04 owns workload/reference/packaging while kernel ABI corrections require their kernel owners. A07 owns the existing durable Hepta composition and effects. A01's separate historical24/28 same-ELF guest diagnostic must not be attributed as A04's new execution, and A06's371 lower bound must not overwrite A01's historical359. Full G1/G2, VMX/default-UNIX, cross-host reproduction and immutable environment acceptance remain open. The separate A01 archive-repair task addresses two current output-custody flaws; no correction is claimed by this read-only archive.

## Integrity and limits

The current PLAN, STATUS and fixed source locks are retained; source bindings distinguish exact source text from JSON semantic equivalence. The global Asterinas pin remains c4b7ed575b7b32773475b194d2ad41fb6d03765b and nightly-2026-07-21. Large unrelated directory-tree/search inventories are omitted; selected tree entries are explicitly derived from the earlier complete responses. No credentials or private machine configuration were read.

Only this new evidence directory was written. No root README, upstream lock, old evidence, owner source, branch or remote state was modified. SHA256SUMS covers every other file. Verification parses every JSON, checks source Git blobs and available fixed local Git objects, validates reported CI/log scopes and six A01 test summaries, then verifies all saved file checksums.
