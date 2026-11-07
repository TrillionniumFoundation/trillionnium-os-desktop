# Four-binary Status / Readiness rollout — source-only work02

The release build has passed actual qualification. No binary has been deployed and no service or Main identity has been changed.

## Actual release bundle

Source: actual report `459b355cfc7a4cadf4ed63706f9f6882f86084f4`, 146722 bytes, SHA-256 `cb0628aac421253277aad72b616d290503d62ca48bf8bcfd05bf97cf37640ea2`, tree `87ccdef7ae4687cfc48ab4efdb07bfb0dde6b527`. The report contains 38 completed commands, 15 independently run Rust/CLI tests and three owned-child lifecycle controls. All six executable profiles are release (`opt_level=3`, no debug assertions, overflow checks or debuginfo). Only the four normal executables below are candidates for installation.

| Executable | Bytes | SHA-256 |
|---|---:|---|
| droidloom-supervisor | 1997840 | `c94ccb72f1a78494b65ee76e0dcaaa207d7d427bc4ef765e32b2d9c194678409` |
| droidloomd | 1981536 | `8f43a4873d57cda4bfb9cafc0debbedda88626f60a825171a1296ea42e567a7e` |
| droidloomctl | 1744472 | `c9f9a36647dc18801f911117413f34e5240684076250e20414ac29e71f2e973a` |
| droidloom-applications | 1576016 | `71f51160685485fba0ef54727c66351a83b0e2dc236fd22f8c91471aac049534` |

Each candidate is at `/home/alex/work/p4-sr01-20261106/attempt01/cargo-target/release/<name>`. The original raw report remains the authority for file identity and nanosecond integers. The small release binding deliberately copies only lossless path/size/hash/profile fields.

## Installation source decision

The four packaging files were actually read with complete byte/hash checks in tree `3058983a8d7367d7eea93a2ab4b99fde5fa15e6a`. The lightweight `install-supervisor` explicitly targets a named ARM64 device and UID and replaces only three binaries. The broad `install-runtime` also changes images, data, runtime activation, Wayland, units and policy. Neither script will be executed as this four-binary update.

The source names `/usr/bin` candidates, three system/user unit paths and `/etc/droidloom/cell.json`. Those names are reference paths, not a finding that the current host uses them. The fixed read-only request in tree `ab9136b456ecd200b8ac322f60d49da453282a12` observes those nine known paths plus the already authenticated running daemon image, under the original complete Main guards. It has no child, Status RPC, action-lock, namespace, write or service operation.

That reader can establish file existence, exact content/metadata, held/named equality and whether the fixed named daemon equals the running image. It cannot establish effective systemd drop-ins or package ownership. Unknown ancestor/leaf symlinks are not followed, and unknown executable paths or private configuration bodies are not exported.

## Concrete transaction preparation

The next immutable mutation manifest must bind all four destinations to actual evidence, the old full hashes and metadata to actual installed files, and the new hashes to the release result above. If package ownership is established, package archive/database rollback must be qualified before selecting a transaction; a marker file alone is insufficient. If the direct-file branch is qualified, the candidate and rollback copies must be fully staged, verified and durably recorded before service shutdown or replacement.

The manifest must preserve per-file progress. Four separate renames are not one atomic transaction. A failure after any replacement retains the original first cause and the exact completed set; rollback is qualified only after all old bytes and metadata have been restored and independently checked.

Actual service-manager configuration must determine the stop/start sequence and all relevant user instances. The packaging source's user-session-before-daemon ordering is only a reference. No old task ID, package force-stop or unknown process kill is part of the operation.

## New generation and consumer binding

The old B02/R6/current-eight identities remain immutable historical evidence. Any approved restart creates a new generation. A new, explicitly deployment-aware baseline producer must bind the approved transaction receipt, installed/running executable hashes, unchanged image and service configuration, authenticated daemon/owner/init lineage, resources and stable eight-role observations.

The tested `current_discovery.py` candidate changes only the explicit RPC from lifecycle Status to fresh Readiness and preserves its eight-second gate and the original owner/InputBridge/namespace/environment/classpath checks. Its current B02 literals are static test inputs, not future runtime authority. New baseline/host/custom-context/helper generations must be bound from actual post-deployment evidence. No in-place R6 edits or old nonce/task/UID reauthorization is allowed.

## Rollback

Final deployment approval must cover the precise restore/restart path. On failure, close admissions, preserve the failed new result, stop only through the qualified service path, restore the complete reviewed old bundle or package transaction, and verify every restored byte. Cleanup and restart errors remain separate. A restarted rollback also creates a new generation requiring fresh baseline qualification; it never reactivates old B02 or historical task authority.

The installed inventory, effective service/package evidence, verified rollback material and deployment-aware baseline code remain open gates. This work02 has no executable mutation request and grants no deployment permission.
