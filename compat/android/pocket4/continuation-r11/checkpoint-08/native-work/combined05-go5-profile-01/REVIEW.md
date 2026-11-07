# Independent candidate05 Go5 / 10 GiB build profile

## Decision and exact scope

This is a new, locally prepared build profile. It has not prepared remote source, submitted a remote job, compiled the engine, or changed Main. The original Go6 / 11 GiB / 15 GiB profile and its failed admission remain unchanged.

The normal builder mechanism can consume the proposed change without replacing the builder executable: it reads `android/apex-compat/0008-soong-leaf-go-memory-budget.patch` from the selected builder source directory, applies it through the existing source projection and recovery journal, and records the applied patch hash in `effective_projection.patches`. The candidate patch is 583 bytes and changes exactly one byte, `6` to `5`, in the inserted `GOMEMLIMIT` value. Its SHA-256 is `39211a784284ed319b6abbbe4b327a88896931d39c6bdb91fe727a9a7589325f`.

| Item | Preserved profile | New independent profile |
| --- | ---: | ---: |
| Go soft memory setting | 6 GiB | 5 GiB |
| Owned unit MemoryMax | 11 GiB / 11811160064 bytes | 10 GiB / 10737418240 bytes |
| Required current MemAvailable | 15 GiB / 16106127360 bytes | 14 GiB / 15032385536 bytes |
| Admission difference | 4 GiB | 4 GiB |
| Owned unit MemorySwapMax | 1 GiB | 1 GiB |
| CPU quota | 200% | 200% |
| CPU affinity | Last two of the allowed CPU set | Same |
| Normal builder jobs | 1 | 1 |
| Controller timeout | 6400 seconds | 6400 seconds |

The four-GiB difference is an admission calculation, not a physical reservation. Memory is read again in the new invocation; the old observation of 14.088741 GiB does not admit a future build. The previous successful Go6 run reached both its 11 GiB memory limit and 1 GiB swap limit and recorded 27 `memory.max` events, although its OOM counters were zero. That evidence makes a successful smaller build uncertain. More collection work, longer execution, or an owned-unit memory failure remain possible. There is no automatic retry or fallback to another resource profile.

## New source and attempt identities

The new remote root, if separately admitted, is:

`/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/full-build-combined05-go5-01`

It has independent `builder-source`, `engine-working`, `android-out`, `attempt-01` and `build-fences-01` paths. Existing paths are rejected. No old output or failed attempt is reused.

The stable preparation key is `pocket4-native-combined05-go5-full-source-preparation-01-20261104`.

The stable build key is `pocket4-native-combined05-go5-fenced-full-engine-flag0-build-01-20261104`.

`derive_profile.py` reproduces the new controller and fence template from pinned reviewed preimages. The complete changes are in `controller05-to-go5.patch`, `fence03-to-go5-template.patch` and `go6-to-go5.patch`. The source preparation request is already frozen locally under `prepare-request-01`; it has not been submitted.

## Complete 449-file builder manifest strategy

1. Read the original `builder-source-after.json` and require its exact SHA-256 `e7c225bd2842c260d9f4149aca3c4483ed31c569efb31068b6d787892bd17017`. Re-inventory the original 449 files, including modes and any explicit symlink records, and require full equality before copying.
2. Copy the complete original tree into the new private root. Require its complete inventory to equal the original manifest before any mutation.
3. Derive the expected new 449-entry inventory by replacing only the Go patch's SHA-256. Require the old patch to be an ordinary 583-byte file with SHA-256 `6aaaf5ec96a75bb6480c202d6483a5b22bdd4963d6d3b66bbfad4d80ee5ed20e`. Preserve its mode and byte count; every other entry remains equal.
4. Open the copied patch with `O_NOFOLLOW`. Before writing, require a regular inode with link count one, the exact old bytes, and precisely the one-byte transformation. Write and fsync only this copied inode. Re-inventory the entire new tree and require exact equality with the derived inventory.
5. Save the actual new inventory as `copied-builder-source-manifest.json`. Its final hash cannot be claimed before preparation. The new receipt stores this actual hash separately from the original manifest hash and records the exact one-file delta.
6. Repeat the original input verification before preparation succeeds. At build entry, re-read the actual preparation receipt, new manifest, all new files, old inputs and plan. After the normal builder returns, recheck both old and new inputs.

The 925-file engine source and candidate05 manifest remain unchanged. The six signal-mask output pins, raw/effective source comparison, source genealogy, import policy, compiler, link references and feature-disabled requirement remain in force.

## Actual projection and artifact checks

The normal builder executable remains SHA-256 `16df26d88391c22c9f076917531f022907ec5608bd31e58e05c898605db9dcc4`. Its existing package and shared-AOSP source locks, recovery path and checked projection are retained. Its five-file `builder_files` receipt does not include the Go patch, so that receipt alone is insufficient to bind this change.

The new artifact gate therefore additionally requires the actual applied-patch map to match the previously successful map with only the Go patch hash replaced by the new hash. It captures the actual `build/soong/ui/build/soong.go` projection hash and requires it to differ from the old projection hash. It does **not** claim a precomputed expected hash for that entire Soong file. The causal binding relies on the pinned normal builder recording the patch after successful `git apply`, together with the exact source inventory, patch and all existing raw/effective engine checks.

The normal builder's initial and final receipts must still agree except for their declared status and artifact fields. All actual engine and host-test binaries, libraries and data are hashed. Build success would qualify only the selected engine and host-test artifacts. The complete host suite, binary review, owned signal controls, enabled metadata path, paired ART, factory runtime and Android adapter qualification remain separate gates.

## Main observations and final request

`main_snapshot.py` is byte-for-byte unchanged at SHA-256 `f909bdfcaedfef29fcc1ba6a994c49bc21e99850204bac7e0565548bcd7139cb`. The outer process remains UID 1000 and invokes only the existing pinned read-only helper with `sudo`. Main's framework epoch, activation, process identities, service-root cgroup identity and limits must remain equal across the build, and OOM-related deltas must be zero. Other resource deltas are recorded. Pre/post checks do not prove absence of every transient effect.

The fence template contains a deliberately invalid preparation placeholder and rejects execution before actions until a new actual preparation SHA is supplied. `make_requests.py build-request` requires the actual new preparation and 449-file manifest, each with an explicit SHA, and checks their profile and binding before producing a final immutable request. The final request sets the owned unit's MemoryMax to 10 GiB; the controller checks the observed owned cgroup limit before launching the builder. Main's resource limits are never changed.

Root has separately reported a current `system_server` identity admission failure. This profile does not adjust that identity contract or infer that Main remains eligible. Root must resolve that observation independently before any build can pass the unchanged Main fence.

## Local validation and its limits

`local-controls.json` records 22 passing controls against the actual new Python functions: exact one-byte source delta; expected manifest transformation; wrong hash, size, kind and file-count rejection; real private-copy mutation; real hardlink, symlink and bad-preimage refusal before writes; memory/swap boundary checks; projection-map drift refusal; exact preparation source packet; absent-preparation template refusal; and three actual default PLAN invocations.

The 449-row inventory, memory readings and projection receipts used in these controls are explicit fixtures. The controls have not read the remote 449-file tree, run the normal builder, reserved memory, started a service, entered namespaces or touched Android. The remote preparation and build remain unperformed.

## Source evidence

The exact source paths and hashes are recorded in `reference-pins.json`. The key reviewed locations are the `Projection::patch` / `effective_inventory` implementation and conditional Go patch invocation in the pinned `android.rs`, the actual input-receipt structure in `native_engine.rs`, the original candidate05 controller/fence, and the actual prior Go6 success/resource receipt. The first candidate05 full-build attempt `1a1a886d2c7-fc05-2ef4` remains an admission failure before compiler execution; its failure is not superseded by this proposal or by the local controls.
