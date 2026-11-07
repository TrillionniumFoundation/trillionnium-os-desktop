# CP24 fixed-root collector source

This package is SOURCE_ONLY and unbound. Root has not supplied a CP24 cut or seed to this collector. Preparing these files selected and processed no CP24 evidence root.

## Input authority

Root supplies complete original `seed_raw`, complete original CP23 `parent_cut_raw`, and the authority object described by `input-contract.json`. Null authority fails before any Git callback. Whole UTF-8 size, SHA256, Git SHA1, cut, parent commit/tree, parent pins and exact root counts must all match.

The inherited canonical table is independently reconstructed from the pinned CP23 cut scope: its inherited roots plus its CP23 packages. Every inherited SHA, canonical name and checkpoint must match. New roots are unique and disjoint from inherited roots. Aliases remain labels.

## Preservation

The CP23 functions `shallow`, `traverse`, `metadata`, `verifyBlob` and `normalizedTree` are retained byte for byte. Every original shallow directory's Merkle SHA is recomputed. A child equal to an authorized inherited or new canonical root is cut at its exact path, recording its original SHA and checkpoint/package.

Every retained unique original blob is read completely and verified for advertised UTF-8 size, Git SHA1 and SHA256. Original leaves are reused by exact blob SHA. No original evidence is parsed and reserialized for preservation. A large-report carrier requires separate Root authorization and must reconstruct the entire advertised original; JSON links cannot authorize one.

Each package adds exactly `_dependency-mounts.json` and `_original-tree.json` (schema 3). The original-tree map includes only traversed directories before a cut, preserving their complete original immediate entries. Derived metadata receives full body readback; every normalized package receives a recursive path/mode/size/blob/Merkle comparison.

## Flat archives

`archive-references.json` is retained as an opaque original leaf with a verified pin. Its JSON fields are never followed to obtain another root, blob or URL. Unknown links remain unexpanded. A known canonical link is still only original evidence; the seed and actual Git subtree edges determine mounts. If Root wants a linked root included, it must be explicitly authorized in the frozen seed.

## Execution after Root binding

Load `pure-git-verifier.js` and export only utf8, sha256, gitBlob, treeHash and verifyGitTree as H. Evaluate `assembly.js` and call it with H to obtain A. Evaluate `git-adapter.js` with the Git tools object, H, A, durable get/set callbacks and this independently verified collector-source tree SHA.

Call `collect-batch.js` with H, A, the adapter, Root's input and bounded limits. Root traversal is sequential. Independent original blob reads run in groups of at most four, and every result is inspected. Defaults are one root and eight blobs per invocation. The returned summary contains counts and pins; do not print nonce-pool or private body text.

Only after collection proves every authorized root and unique original blob may `normalize-batch.js` run, with an explicit package limit from one to four. Each batch saves and reads back immutable progress mounting the original seed and collector source. An unknown immutable write response leaves a pending SHA and prevents automatic replay. Unavailable readback or HTTP 404 does not prove an earlier request never executed.

The two original CP23 helper files lack a final newline. Their reference blobs retain those exact bytes. Full replacement diffs record the original missing-newline markers; new source files have a final newline.

## Remaining publication gates

These functions provide package/file/cut inventories. They do not select a cut, interpret admission as actual running, add later results, create operational status, rewrite the old master, or change a branch or PR. Parent master content is carried by pin only; Root independently verifies the full original and performs a lossless append.

Preparation checks were JavaScript function compilation, exact preservation of the five CP23 functions, and null-authority rejection. No synthetic CP24 seed was created. Collection and normalization callbacks have not been executed. Root remains the sole publisher and Hepta dispatcher.
