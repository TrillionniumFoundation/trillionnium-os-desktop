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
| Frozen fd/a39 prepared UI and private window | Exact fd/a39, explicit prepared preedit SDK | All 16 UI build commands exited 0; private X11 AT-SPI 7/7, atomic EditableText 5/5 and real IBus 5/5; five owned long-lived children cleaned up | Physical/Wayland/Orca/visual checks, authenticated Send and installed original Root/Notes |
| Frozen fd/a39 Root dev-small package | Same original source pair | Both build stages and two strip stages completed; 341,288,592-byte Agentd was rejected by the original 128 MiB per-file bound | That execution produced no accepted package; its blocked result is unchanged |
| Frozen fd/a39 Root product-linux build/install | Same original source pair, Rust 1.96 | Eight build commands passed; Agentd 117,408,600 bytes; original host tests 53 passed plus two actually executed privileged cases; original pack, verify and installation all passed | Real authenticated submission, Notes effect/readback/terminal/restart and continuous authority renewal |
| Calculator Core | Desktop `5a8684cc4591a4163c162f198b4121ca4cfc6ebc`, tree `5bece45cf0c433194a2aeefdd924990844d3e398`, Rust 1.96 | 81 passed; zero failed, ignored or filtered | Original owner attachment, native windows, production tasks |
| Calculator App/Session | Same Desktop 5a, default features | 138 top-level passed, zero failed, 2 ignored; actual Session normal exit and SIGKILL both reached idle egui Close at frame 4 with zero input events/effects | Compositor-window and original Root/owner end-to-end qualification |
| Module documentation | Same clean complete Desktop 5a | 16 Cargo entries, 11 development domains, 57 kernel members, 91 documents, 1,504 local links; no errors | A documentation contract/link check is not runtime evidence or proof every module is finished; external URLs were not fetched |
| A10 host CI | Same Desktop 5a, run 41685844434 | Real headless Weston first-frame/lifecycle, AccessKit AT-SPI and original shared input checks passed; two Clippy errors then failed the whole run | Later skipped cleanup/capture/phase checks and qualification of the new fix commit |
| Hepta Memory | `0259fc82cc1b6ac9e245227dceffb767e306378f`, tree `4005ffe2bad095cf1d5e0d006393d08ced831cd8`, parent a39 | 394 executed: 393 passed, 1 failed; 13 skipped | A successful full Memory suite or Calculator production loop |
| Federation recheck | Same Hepta 0259; CPUQuota 400%, unchanged test limits | First attempt reached the original 60-second test timeout; second returned requested_peers=16 but completed_peers=0 and failed | Higher CPU quota did not resolve the failure; a specific I/O root cause is not established |
| Original owner candidate stage 2 | Hepta `580a07bfadad97d1dfc13ece112facc13dcc00bb`, tree `cd6004e85a5ae28513a0bcf32da5bf7b190103f5` | Objective 66 passed / 2 skipped; causal receipt selection 1 passed / 407 unselected; Agentd selection 6 passed / 587 unselected | Original Core execution, subsequent joint Root changes, real windows and production authority |
| Separate exact original-owner image profile | Pre-commit component identities retained below; same tree as published Desktop `fe55fe8e1764f4967bae295311d288d8049b6eae` | Fixed kernel toolchain admitted and installed; eight Rust components formatted; original host build.rs input checks passed; 47 normal and 14 optimized Python checks passed | Actual locked 204-package graph, full kernel, native original-owner effects and persistent G2 |
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
change. The exact c2 head subsequently completed all five PR workflows
successfully: G0 41691929848, Session 41691930336, ARM64 original Agentd
41691930194, Native UI 41691929883 and A10 41691929849.
The [final CI snapshot](calculator-ci-c2/calculator-c2-ci-status.json),
[Native UI steps](calculator-ci-c2/calculator-c2-native-ui-jobs.json) and
[A10 steps](calculator-ci-c2/calculator-c2-a10-jobs.json) retain the API results.
A10's formerly skipped cleanup, capture and phase/peer steps all actually ran
and passed on c2. These are source-bound CI results; the later joint Root/owner
candidate and installed two-application product remain unqualified.

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

## Later original private-window execution

[The complete fd/a39 window and Root records](owner-p0-fd-v4/README.md)
retain both the later original-window success and the separate Root package
refusal. The private prepared-preedit window now has actual 7/5/5 AT-SPI,
atomic-edit and IBus results under the original deadlines. This does not replace
the earlier Xvfb failure, establish a unique I/O cause, or qualify installed
Agentd/Notes effects. The raw UI build receipt's prior `window_qualified: false`
continues to describe its build stage; the later window execution has its own
receipt. The failed Root builder also retains its unchanged false fields.

All five original IBus screenshots now have [separate AI visual observations](owner-p0-fd-v4/window/visual/README.md)
and independent original-receipt SHA/dimension checks. The complete display
resolves the window-only black region as an overlapping visible candidate panel;
its `ni hao` and highlighted `你好` are legible. The original human/physical/Wayland/
Orca and authenticated-Send flags remain false. These are the same execution's
original images, not a new runtime test or an installed-product result.

## Later optimized original Root installation

The [fd/a39 product-linux record](owner-p0-fd-v5/README.md) retains its own
successful build and installation. The original size limits, features and
locks remain unchanged. All-targets and the separately executed privileged
tests total 55 distinct passed cases. The two complete small archives contain
31 original files, all independently checked by size and SHA-256. The actual
installed release is `/opt/trill-organ-20261103/releases/fd8d56c52b97-053cc1957b40`;
the installer explicitly did not start services or grant production readiness.
The prior dev-small failure is not overwritten or reclassified.

The implemented authority composition is limited to at most 300 seconds and
one same-boot recovery inside the original issuer window. [D14](../../../docs/DECISIONS.md)
records the missing continuous original-owner reauthorization transaction.
Passing an installed finite run cannot qualify continuous production use.

## Separate exact original-owner image profile

[PR #284](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/284)
publishes the default-off `g2-original-owner-a39-v1` source at
`fe55fe8e1764f4967bae295311d288d8049b6eae`, tree
`07cbb5e0187b4355200c2f5e0166228cecf1ecc1`. It fixes the original a39 ELF,
digest, LOAD layout and four-role composition while retaining the loader's
private snapshot, readback and sealing rules. The legacy 8/16 MiB profile and
ordinary exec limits are unchanged.

The [host-only evidence](g2-exact-owner-host/README.md) retains 32 original
files, 57,728 bytes, including complete command outputs. An
[independent review](g2-exact-owner-host/independent-review.json) rehashed every
original file and matched 22 component hashes to the published tree. The
original format/build/test receipts describe their actual pre-commit state;
their identities were not rewritten to claim a later canonical execution.
The fixed nightly compiler was actually installed, all eight Rust components
passed its formatter, and the source-owned build script compiled and checked
the exact original ELF without executing it. The Python checks passed 47
normal cases and 14 optimized cases on the same Python bytes.

The new source also adds bounded lifecycle memory observations. The seven
initial samples and optional successor samples are implementation points,
not observed guest results. They cannot establish a continuous peak, complete
process-tree accounting, successor overlap or global recovery reserve.
The real locked graph, source-built OSDK, full kernel and positive original
owner guest scenarios still need their own execution records. All native G2
and production flags in this archive remain false.

## Open product work

Linux Notes still needs installed original Root submission, the original writer
effect, independent App readback, durable terminal and disconnect/restart
reconciliation. Calculator needs a coherent newly pinned owner/Root pair and
the same actual task protocol across two real destinations. Component tests,
headless Weston checks and the full source graph are separate acceptance parts.

The [original G2 owner records and resource review](../../g2-original-owner-size-20261103/README.md)
show that its build/package succeeded but the old 8 MiB file / 16 MiB
LOAD profile rejected its actual 20,138,584-byte ELF and 20,168,704-byte aligned
LOAD total. This remains a failed static profile, not guest execution. The
separately published profile above has its own source and host checks; its
actual kernel and guest qualification remain open. Whole-system recovery
memory and trusted user-pause ingress remain open.

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
