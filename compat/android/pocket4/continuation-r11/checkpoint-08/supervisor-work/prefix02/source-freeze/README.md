# Prefix02: canonical Main command-line identity

This independent source revision fixes the measured Main preflight representation defect. The original source05-01 tree, failed plan and first failed preflight remain unchanged. The complete runtime prefix has not yet been executed.

## Actual diagnosis

The original preflight receipt SHA is `0b29fe07377483c57406145b838e38a3854a64276a09e16ac9aa4bd5fddb35ad`; it stopped at the original system_server identity comparison. The subsequent fixed-PID read-only diagnostic retained the original PID 3589120, birth 80797249, parent, UID, PID/mount namespaces and live pidfd. It read a stable 99-byte cmdline containing `system_server` and 86 trailing NUL bytes. The original prefix capture produced 85 extra empty arguments. The pinned framework epoch guard produced the original `['system_server']` value, with every other field equal to the unchanged original plan. The exact 3,419-byte diagnostic SHA is `04bd2b638f389e850eb8ab15fa5f3701de20cb0e013b472a8dca4470ccf34f0a`.

`MainFence.capture` now omits empty strings when presenting cmdline, matching the pinned `framework_epoch.py` SHA `f43f766f19a151d7d33ecd0c99c2e81f832fce7dcb1804e5c774e833066a6288`. It retains nonempty arguments verbatim. This is the only production-code change. The general actor identity parser, complete startup argv equality, FD transport, owner/child proof, native C probe, deadlines, budgets and retirement rules retain their prior bytes and behavior.

## Controls

The candidate coordinator passed 27 local controls: the previous 24 plus the actual 99-byte observation replay, a nonempty Main argument-change negative, and an empty-field startup argv negative. The new presentation controls explicitly use an identity/readlink seam and an owned temporary directory; they do not open a live Main PID or enter a namespace. The generic startup qualifier still rejects an inserted empty argument.

Running the two presentation controls against the original coordinator reproduces one expected failure for the retained actual padding and preserves the nonempty-change negative. The exact successful local receipt SHA is `f9dd553946633f9db52c398a09fa4acd27593c87c85bd013e3b5b7e7ce1608ac`.

An initial harness postcondition incorrectly expected one old-version failure while its negative test also required the new normalized presentation. The old version consequently failed both assertions. That original test source, output and harness failure are preserved under `evidence/local-controls-01/`. The final negative checks the relevant property directly: a nonempty argument survives presentation and leaves the original identity comparison unequal. The corrected suite and old-version negative then ran with the expected results.

Fresh device controls for this revision are pending: 16 unchanged actor controls and 27 coordinator controls. The prior native probe's six ordinary controls remain referenced as prior actual evidence; this revision claims no new native build or native-control execution.

## Exact native probe reuse

The new source directory is `/home/alex/work/pocket4-relay-prefix-r11-source-05-02`. The native probe remains the exact existing root-owned artifact `/home/alex/work/pocket4-relay-prefix-r11-source-05-01/bin/prefix-probe`, SHA `79b30f9fa4a1e7635ae4786a50372b3fcaa84ad619269476e40a1badd65c0e82`, size 21,752, device 66306, inode 34481448, mode 0700. Its matching receipt SHA is `1e70d9df93309ff5be991f0a20e4b5b4493e57a0b64fcc3881075e652a5ae712`; the unchanged C source SHA is `d088edf44d523a67e2881ce6c0715a4885664f11c5315938e04f52738c43a34a`.

`probe-reuse-binding.json` records the full original metadata and required stage checks. The stage must verify that receipt, both original and copied C bytes, the original probe's object identity, full hash, root ownership, mode and absence of file capabilities. No existing source or executable is overwritten. Runtime still opens and retains the exact pinned probe FD and compares the returned object identity.

## New plan and one-shot scope

`normal-plan.json` has SHA `cc003f5e6bbb54e1c8a8cd86a78a50b65ee7598ac37992f64b5f89a32923a41f`. It uses fresh nonce `d5ac0c8b6b3250e8ab02a33f1d04fe9ea64f3a32667325dff1827499ba77336a`, unit `p4-relay-prefix-d5ac0c8b6b3250e8ab02a33f-normal.service` and a distinct evidence/once-claim directory under the established root-private prefix base. Its actor/coordinator source paths point to the new root. Its complete historical Main identity, tool hashes, limits and probe artifact are identical to the original plan. This is a source-repair attempt with a new identity, not a replay of the failed source01 plan.

The new stage, preflight and normal runtime requests are not submitted. Their concrete source/pin/plan bindings must be reviewed before dispatch. Actual full-prefix execution, actual Rust Owner/Android init/barrier enrollment, abandoned-generation recovery, installed activation and commercial-app acceptance remain open. This source revision makes no production-ready claim.
