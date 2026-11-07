# Candidate06 Go5 streaming profile templates

This template advances the independent Go5 streaming profile to the new candidate06 source manifest `3c780a398075f77d1f6b1c477c6ceaa35349de17b88e77896aa22820259c0376`. It cannot produce a preparation request until `bind_composition.py` consumes the exact completed candidate06 composition receipt. No receipt or artifact success is synthesized.

The candidate has 948 files and 925 engine files. Three engine files carry the exact NOFILE source that passed the owned host and Android comparisons; the other 922 engine files, including all six signal-mask fixes, remain unchanged. The parent candidate05 manifest and its original matched gates are retained as parent evidence. They are not relabeled as execution of the new candidate.

The new source contract requires the actual composition receipt, the exact composer source, and the original raw Android and host receipts. It reuses the frozen composer's pure source/ancestry derivation and its unchanged Android assessment functions. All 11 tested production inputs must match the full new source. This adds an evidence gate; it does not omit any original source, build, resource, artifact, or cleanup gate.

The resources remain exactly those of the separate Go5 proposal: MemoryMax 10 GiB, fresh MemAvailable at least 13 GiB, owned swap maximum 1 GiB, fresh SwapFree at least 2 GiB, CPU 200%, and one normal builder job. The admission difference is 3 GiB and is not a reservation. Actual full cold build memory sufficiency remains unproved. The original Go6 and other failed attempts are preserved; this template adds no automatic retry.

The compiled Rust builder remains the actual `ea80146d…` binary from source450 manifest `6834ea57…` and compile receipt `a1d8fe1e…`. The copied runtime450 manifest is independently derived as `776435c8…`, with only the one-byte Go6-to-Go5 patch-data change. The tested Blueprint streaming patch, normal source-projection journal recovery and builder locks remain unchanged. These source identities are recorded separately rather than attributing the Rust binary to the changed runtime data.

The read-only Main snapshot source remains `f909bdfc…`. The default metadata-generation flag stays disabled. This build targets the engine and its complete matching host-test binary/data/loader closure. It does not execute the 3793-registration host suite, four Android signal cases, ART lifecycle, factory Android positive path, or whole applications. It does not deploy Main. The fresh source and output root is `full-build-combined06-go5-streaming-01`.

## Binding order

1. Root reads the authoritative candidate06 composition terminal and raw `candidate-06-composition-report.json`.
2. `bind_composition.py` checks its explicit SHA and exact source/proof fields, then creates a new local bound profile. Its controller changes only the composition-SHA placeholder; dependent controller/fence hash literals are derived afterward.
3. The bound `make_requests.py prepare-request` generates the source-preparation request. Root reviews and submits it once.
4. Only the new actual preparation receipt and actual runtime450 manifest can produce the later fenced cold-build request. The previous candidate05 preparation is rejected.

Local verification has checked the four default PLAN entry points and AST preservation of 24 prior controller functions, including memory admission, source_contract, artifact_gate, builder compilation qualification, and cleanup. These checks did not execute source preparation or a build. `TEMPLATE_PINS.json` binds the input templates used by the binder; `SOURCE_PINS.json` includes the complete frozen handoff.
