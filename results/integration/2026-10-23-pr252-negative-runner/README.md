# PR #252: restore the strict old-root workload negative control

## Result

This candidate changes only the two Python files
`tests/kernel/control/run_g1d_workload_negative.py` and
`tests/kernel/control/test_g1d_guest.py`. It is based on exact Desktop head
`ea704ddca7753f1565144969ad3e1d91c4a317f6`, tree
`6e844ce1cab2231579139c2a1687a453bf1db11a`.

The original 24 host-oracle tests and two new real-source regressions now pass
in both normal and optimized Python: **26 passed in each run**. These are host
checks of mutation construction and the existing strict evidence oracle. No
Cargo, compiler, QEMU, native guest or GitHub operation ran for this repair.
The real negative kernel still needs the original CI build and boot after
publication; this candidate does not claim that guest qualification.

## Original failure and cause

The retained original artifact is 12,379,990 bytes with SHA-256
`5d170a414f3c9db586bcddf24077e1b198009afe3f63371e067f3664624f329f`.
Its exact-head positive `g1d-trusted-control/result.json` reports complete,
passed, source unchanged, and kernel SHA-256
`662cecceda1e34b77aedc0d259a83dd16275454cfb233d5394a34904c0eb2905`.
The subsequent negative runner reports:

```text
ValueError: credential selection is absent or ambiguous
```

That failure happens while selecting the source mutation, before a negative
worktree is created or a negative kernel is built. It is not evidence that the
old-root guest was rejected correctly.

The runner pinned a one-line `let credentials = if index == 1 ...` statement.
The actual reviewed Rust source at `trusted_roles.rs:123–127` is formatted as
five lines. The old host test synthesized a source fixture from the runner's
own `BEFORE` constant, so it stayed green without exercising the real Rust
input. All ten original files used locally, including the six original Python
import dependencies, match their full Git blob and SHA-256 identities in the
artifact's complete source manifest.

## Minimal correction and retained boundaries

`BEFORE` and `AFTER` now contain the exact reviewed five-line selection. Their
only semantic difference is the workload expression:

```diff
-            workload_credentials()?
+            Credentials::new_root()
```

The manager/recovery branch, role index and all surrounding bytes are identical.
The constructor still requires exactly one original block and no existing
postimage. It does not accept arbitrary whitespace, a regular-expression match,
a missing selection, duplicate selections, or an already mutated source.

Every original runner function has the same AST, including `mutation`,
`verify_delta`, `evidence`, `run` and error handling. The positive and negative
guest evaluators and the kernel source are unchanged. The unchanged source
delta check still rejects changes to any other tracked path, the source mode,
the source hash/size, or any extra edit. The unchanged evidence checks still
require the actual unsafe old-root observations, the unchanged probe and
dependencies, exact source/build identities, image rejection controls and a
real bounded guest exit. A timeout or arbitrary failure cannot pass.

The first added test reads the real tracked `trusted_roles.rs` from the checkout
and compares the entire mutated file against an independently specified single
workload-expression replacement. The second rejects a different role selector,
a changed credential helper and a duplicate reviewed selection. These checks
run through the existing workflow's normal and `-O` host-test steps before its
kernel build. The workflow itself does not need a change.

## Actual red/green evidence

Complete stdout, stderr and identity receipts are retained under `validation/`:

| Stage | Normal Python | Python `-O` | Meaning |
|---|---|---|---|
| New real-source tests, original runner | 26 run; 1 error and 1 failure; exit 1 | Same two failures; exit 1 | Reproduces the real selection error and rejects the self-fixture blind spot |
| New tests, corrected exact constants | 26 passed; exit 0 | 26 passed; exit 0 | Mutation construction and all original host rejection checks pass |

The red error is the exact original `credential selection is absent or
ambiguous` failure. The second red case shows that appending the old fixture
constant to the differently formatted real input could be accepted without
changing the live selection. The corrected exact block rejects this ambiguity.
All four runs record identical before/after source snapshots. Python optimized
mode does not disable the production `require` checks or unittest assertions.

`validation/base-manifest.json` binds the original input files and artifact.
`validation/source-manifest.json` binds the two final candidate files, preserved
runner/test ASTs and the exact one-expression planned mutant.
`validation/planned-kernel-mutation.patch` is an unbuilt test-control postimage,
not a production kernel patch or a guest result. `publication/` holds the
complete two-file source patch, full-content upload entries and hashes.

Publication must recheck both original file blobs at the current PR head before
applying this candidate. The original CI workflow must then execute its full
positive and old-root negative build/boot sequence on the new immutable head.

