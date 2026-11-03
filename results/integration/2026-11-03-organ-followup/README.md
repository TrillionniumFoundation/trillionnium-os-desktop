# 2026-11-03 follow-up execution evidence

This directory retains source-bound executions after the
[initial convergence checkpoint](../2026-11-03-organ-convergence/README.md).
It does not replace the frozen Desktop `fd8d56c52b971c2d5d0e6430f296803b43ef60a3`
and Hepta `a39a0871d9601ffccb5e0d95d8f39d54b3a63360` product pair, or turn a
component test into installed-product qualification.

## Results and exact scope

| Scope | Actual source | Actual result | Still unqualified |
| --- | --- | --- | --- |
| Notes/build successor CI | Desktop `bf15a519e9192b063071e8b9b61ef3319bed416e` | All 9 PR workflows successful, including the complete original Native UI, Root and prepared SDK gate | Installed Root, real Notes effect and restart reconciliation |
| Calculator Core | Desktop `5a8684cc4591a4163c162f198b4121ca4cfc6ebc`, tree `5bece45cf0c433194a2aeefdd924990844d3e398`, Rust 1.96 | 81 passed; zero failed, ignored or filtered | Original owner attachment, native windows, production tasks |
| Calculator App/Session | Same Desktop 5a, default features | 138 top-level passed, zero failed, 2 ignored; actual Session normal exit and SIGKILL both reached idle egui Close at frame 4 with zero input events/effects | Compositor-window and original Root/owner end-to-end qualification |
| Module documentation | Same clean complete Desktop 5a | 16 Cargo entries, 11 development domains, 57 kernel members, 91 documents, 1,504 local links; no errors | A documentation contract/link check is not runtime evidence or proof every module is finished; external URLs were not fetched |
| A10 host CI | Same Desktop 5a, run 41685844434 | Real headless Weston first-frame/lifecycle, AccessKit AT-SPI and original shared input checks passed; two Clippy errors then failed the whole run | Later skipped cleanup/capture/phase checks and qualification of the new fix commit |
| Hepta Memory | `0259fc82cc1b6ac9e245227dceffb767e306378f`, tree `4005ffe2bad095cf1d5e0d006393d08ced831cd8`, parent a39 | 394 executed: 393 passed, 1 failed; 13 skipped | A successful full Memory suite or Calculator production loop |
| Federation recheck | Same Hepta 0259; CPUQuota 400%, unchanged test limits | First attempt reached the original 60-second test timeout; second returned requested_peers=16 but completed_peers=0 and failed | Higher CPU quota did not resolve the failure; a specific I/O root cause is not established |
| Original owner candidate stage 2 | Hepta `580a07bfadad97d1dfc13ece112facc13dcc00bb`, tree `cd6004e85a5ae28513a0bcf32da5bf7b190103f5` | Objective 66 passed / 2 skipped; causal receipt selection 1 passed / 407 unselected; Agentd selection 6 passed / 587 unselected | Original Core execution, subsequent joint Root changes, real windows and production authority |
| Private Xvfb diagnosis | Frozen fd startup configuration | Own socket/lock existed by 0.4 seconds; actual child was in D state with page/buffer waits; original 15-second readiness failed, owned child reaped | Notes window, IME, model/owner effects, product qualification |

The complete host result files record commands, compiler identities and source
manifests. Desktop Core and App/Session used 11,562 tracked files totaling
396,685,570 bytes, with identical clean before/after manifests and no Git
alternates. Their manifest SHA-256 is
`ecd1df685d19a515aebe78e568d26db5b14eab1400c6d6513c8f96ce6c59d4cf`.

The two App/Session top-level ignored tests are the real-font test requiring
`TRILL_UI_TEST_CJK_FONT` and a parent-selected child fixture. The latter really
ran and passed in its child. Nested child summaries and their filtered counts
are not added again as distinct top-level passes. The lifetime test records an
83,333-microsecond repaint output and four frames; it is a host egui component
test, not an installed compositor-window claim.

## Observed Clippy failure and exact repair

[A10 run 41685844434](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/41685844434)
remains failed. Its continuous error-log excerpt is retained at
[a10-clippy-excerpt.log](calculator-ci-5a8684/a10-clippy-excerpt.log).
The errors were `work.join().ok().expect(...)` and the complex five-field
argument tuple.

[Commit c2c3698](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/commit/c2c369836e87e9cf27b4dc9aa8b7446e85efdf90)
uses direct Result handling and a named `AppArguments` structure with the same
values. Its tree is `56f2672a7eeca971870e616762b0a730bec2d32b` and parent is 5a.
It introduces no lint suppression, dependency, identity or acceptance-bound
change. This directory records the repair without claiming c2 CI has passed.

The published A10 artifact is 1,972,532,001 bytes because its artifact directory
also contains the Cargo target. This checkpoint did not download the full ZIP.
Published ZIP metadata is distinct from independently checked full-file host
receipts and from a selected decoded job-log excerpt.

## Original owner and retained Memory failure

The actual stage-2 commands use the original Hepta `just` test entry. The six
Agentd selections cover losing the effect reply while retaining independent
readback, refusing effects on the readback path, total-deadline enforcement,
the six-tool catalogue and old catalogue boundary, and the new seed/profile
and Session metadata contracts. A separate causal-receipt regression preserves
an earlier applied fact after later manual edits. Subsequent joint Root changes
are not included in these execution results. Nextest also calls filtered-out
selections "skipped"; 407 and 587 here are unselected cases, not full-suite passes.

The complete Memory build/test stage took 1,894.886 seconds; the Nextest test
summary itself took 991.442 seconds. Its sole failing test is the original
`cognitive_runtime_tests::product_v2_reports_peer_truncation_before_aggregation`.
Both full-suite attempts returned `memory federation discovery timed out`.
The later targeted attempt has a different failure observation: 16 requested
peers and zero completed peers. The raw full and targeted logs are retained.

This federation implementation reads local SQLite stores and revalidates
current authority around reads within a shared two-second budget. Neither that
budget nor the 16-completed-peer assertion was relaxed; no mock store replaced
the actual stores. Stage timing and failure coverage still need examination
after competing large-build I/O subsides. The Xvfb page/buffer wait observation
does not identify a particular file or establish a unique federation cause.

## Open product work

Linux Notes still needs installed original Root submission, the original writer
effect, independent App readback, durable terminal and disconnect/restart
reconciliation. Calculator needs a coherent newly pinned owner/Root pair and
the same actual task protocol across two real destinations. Component tests,
headless Weston checks and the full source graph are separate acceptance parts.

The [original G2 owner records and resource review](../../g2-original-owner-size-20261103/README.md)
show that its build/package succeeded but the old 8 MiB file / 16 MiB
LOAD profile rejected its actual 20,138,584-byte ELF and 20,168,704-byte aligned
LOAD total. This remains a failed static profile, not guest execution. A future
independently versioned owner resource profile needs its own source, budget,
unchanged image-identity/sealing rules and execution evidence. Whole-system
recovery memory and trusted user-pause ingress remain open.

Original Android signing/installed-peer qualification and fixed X230 native
drivers/recovery remain separate open conditions. This checkpoint claims no
phone effect, bare-metal boot or production qualification.

## Preservation

The complete host files were read with immutable version bindings and verified
against independent SHA-256 calculations and the original result receipts.
`index.json` records exact file sizes and digests. GitHub CI snapshots are API
state observations, and the A10 excerpt is an explicitly selected contiguous
portion of the decoded job log. They do not claim a full artifact ZIP digest.
Failed, ignored, filtered and unexecuted conditions retain their original scope.
