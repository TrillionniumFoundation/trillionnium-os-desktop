# Producer07 audit02: exact Rust type correction

The actual audit01 matching build failed with E0277 in audit.rs:207. The closure parameter `bytes` was inferred as i32 while String::len returns usize. This revision adds the explicit `bytes: usize` annotation. The other 31 candidate inputs are byte-for-byte unchanged; the public authority, lifecycle, cleanup, timeout, observation bounds and tests remain unchanged.

The original audit01 source and failed build are preserved. `prior-audit01-actual-failure-reference.json` binds the parent-observed original terminal and full-receipt hashes; it is not a substitute for those original bytes.

This freeze contains the complete 32 candidate inputs, exact 31-input deadline06 basis, full basis-to-candidate patch, narrow audit01-to02 patch, and actual local source/patch controls. No Rust compiler or new Rust test ran locally. Matching compile, ordinary tests, actual Rust Owner and Android constructor qualification remain pending.

`FIELD-SOURCES.md` and `PRIVATE-CELL-NEXT.md` are unchanged from audit01 and continue to define the data-only interface and later private NORMAL scope. No Main or host-network action is authorized by this source freeze.
