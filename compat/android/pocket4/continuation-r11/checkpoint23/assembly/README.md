# Checkpoint 23 assembly candidate

This candidate contains exactly the 239 new original roots from the immutable Root seed at 2026-11-06 21:56:09 UTC, with 695 inherited canonical roots retained as reconstruction targets. It preserves every retained original leaf body. Original Git blobs are reused directly.

The packages tree is 5d0cb56fc67967b79307e68f671d08f0ff5b930a. Each normalized package adds exactly _dependency-mounts.json and _original-tree.json (schema 3). The latter contains only directories actually traversed before a canonical-root cut; entries for cut directories retain their exact original SHA. Restore omitted directories through the named checkpoint/package and recursively apply that package's metadata.

Verification covered all 459 distinct original shallow directories, 1,367 distinct original leaf bodies, 478 generated metadata bodies, and the entire normalized recursive tree. One 9,811,685-byte original report was recovered through the fixed two-part zlib carrier because direct blob retrieval did not provide text; the complete original SHA256 and Git SHA1 matched. The original report was not parsed and reserialized.

## Reproduction

Load pure-git-verifier.js and export utf8, sha256, gitBlob, treeHash and verifyGitTree. Evaluate assembly.js with that helper object. canonical(seed) builds the exact 934-root cut table; shallow validates each immediate tree and Merkle hash; traverse walks each of the 239 seed roots and stops at inherited or new canonical child roots. metadata reproduces both metadata bodies. verifyBlob checks a complete UTF-8 body against its advertised size and Git SHA1; normalizedTree recomputes package hashes. normalize-batch.js is the actual serialized immutable-object writer used for this assembly; its caller supplies Git create-blob/create-tree adapters and durable get/set state. No branch/ref operation is implemented.

The fixed seed, original blob verification ledger, large-report reconstruction code and proof, parent reference, exact cut scope, and complete new-file index are included. The index excludes itself, matching the prior checkpoint convention. Root may append its separately reviewed status/acceptance documentation and then rebuild the final index/master append; this assembly does not invent those state documents or publish a ref.

## Cut status interpretation

The unchanged seed field read_only_diagnostic_running_at_cut means ADMITTED_RESULT_UNCOLLECTED_BY_ROOT_AT_CUT. It does not establish an observed running state. No later Hyatt result is added to this cut. Historical FAIL, UNKNOWN and unrun evidence remains unchanged. Whole-app readiness is 0/45; Main deployment is false.

Authorized public immutable source packages retain their original nonce-pool leaves. No nonce-pool body is printed in chat. Private B02 baseline bodies and other private runtime material remain outside the fixed public scope.
