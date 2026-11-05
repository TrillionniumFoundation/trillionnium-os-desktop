# Independent Go5 streaming build profile

This is a new preparation and cold-output attempt. It leaves the original Go6 streaming attempt and all earlier resource, OOM, cancellation, source-copy, vet and fixture failures intact. It has not been prepared or built on Pocket4.

## Exact source relationship

The Rust executable remains the actually compiled 32,081,288-byte `droidloom-update` with SHA-256 `ea80146d5fc47f9927dd16a1ad91b6b48f0b30f0ce043d4eaef53f0e84f482b6`. Its actual compile receipt remains `a1d8fe1e891c876baeff555b18fce9bafe6a895d379d9e55261c6df1981785de`, and its original 450-file source manifest remains `6834ea57e4d0402bd5c6e6c405728a111af77fb54ea0e0bea407ba9647fa41b4`. The compilation and seven existing tests are not rerun or reattributed to another source manifest.

The new private runtime source copy changes exactly one byte in `android/apex-compat/0008-soong-leaf-go-memory-budget.patch`: the leaf Go soft heap value changes from `6GiB` to `5GiB`. The derived runtime 450-file manifest is `776435c88ca6ddb983456c639ca051e586731140394756f33abe53dc478357e3`. The other 449 files, including the Rust source and `0009-blueprint-stream-uncached-module-actions.patch`, remain byte-identical. Both manifest identities are recorded separately in the new preparation receipt and checked again before building.

The exact compiled `android.rs` passes the runtime `--source` repository's patch path to `Projection::patch`. That method invokes normal `git apply --check`, `--numstat` and `apply`, records original bytes in the projection journal, and hashes the patch file at runtime. This data is not substituted into the Rust source. The source excerpts and complete-file hash are recorded in `runtime-data-loading-evidence.json`. The new request uses this normal projection and lock/recovery path; it never edits shared AOSP directly or rewrites the old journal.

The previous actually observed Go6 Soong source is pinned as `ea5d759aa3d57c2bc9bce434746309ee988b3554923966a1fb78ec0ce3c18343`. The exact one-byte derived Go5 source must be `4e6fb778c1aee7bfc9b3206940364edbf3502912fe692fa91b612ab389ed07d9`. The final artifact gate checks that new hash and the unchanged tested Blueprint source hash; it does not compare the new Soong source to the old Go6 bytes or accept an unobserved projection.

## Resource change and evidence limits

| Setting | Preserved Go6 streaming profile | New Go5 streaming profile |
| --- | ---: | ---: |
| Go soft heap | 6 GiB | 5 GiB |
| Owned MemoryMax | 11 GiB | 10 GiB |
| Fresh MemAvailable minimum | 14 GiB | 13 GiB |
| Admission difference | 3 GiB | 3 GiB |
| Owned swap maximum | 1 GiB | 1 GiB |
| Fresh SwapFree minimum | 2 GiB | 2 GiB |
| CPU quota / normal builder jobs | 200% / 1 | 200% / 1 |

The admission difference is not reserved memory. The latest fixed read-only memory sample is historical evidence, never a substitute for the fresh kernel counters read by this new attempt. The new profile reduces the actual cgroup budget together with the admission threshold. Go's soft heap setting does not cap total process RSS, native allocations, or concurrent processes. The streaming comparison demonstrated output equivalence and reduced allocation in its fixture; it did not prove that a full cold AOSP build fits either budget. A build that reaches the owned OOM-kill gate remains failed even if it produces files.

The original Go6 streaming attempt failed before the inner builder due to its 14 GiB admission gate. Earlier nonstreaming Go4 and Go6 attempts had real owned OOM kills. Those failures remain evidence and are not reclassified by this proposal. No automatic budget retry is added.

## Preserved qualification

The candidate05 manifest remains `4e2f7f9ea09c6977afbe8d97c040fd2f1344772429f78fe0f16edc913dadc7ba`, with exactly 925 engine files and all six signal fixes. The new NOFILE production patch is not included in this engine source. The metadata-generation feature remains disabled. The build still targets `libberberis_arm64` and the complete matching host-test binary/data/loader closure. Building these artifacts does not execute the 3793-registration host suite or the four Android signal cases.

The read-only Main snapshot source remains exactly `f909bdfcaedfef29fcc1ba6a994c49bc21e99850204bac7e0565548bcd7139cb`. Epoch, activation, process identity, limits and Main OOM deltas are checked before and after; owned cleanup and artifact gates are unchanged. No Main deployment, ART build, factory service, app run or whole-app readiness is claimed.

`make_requests.py` produces only local request files. Its prepare request is for the new root `full-build-combined05-go5-streaming-01`. A build request cannot be generated until a new actual preparation receipt and the new actual runtime manifest both pass exact byte/SHA checks. The previous Go6 preparation receipt is rejected by the changed runtime-manifest and plan bindings.
