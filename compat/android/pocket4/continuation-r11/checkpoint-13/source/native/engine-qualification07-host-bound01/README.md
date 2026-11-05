# Candidate07 actual build → unchanged full-host qualification

This freeze binds five complete actual build receipts to the already-frozen qualification template03. The original reader01 remains failed: the successful inner terminal was 332929 bytes, beyond its 131072-byte bound. Root retrieved that same file by fixed-version binary reads; its complete SHA256 matches the build stdout pin. The input/final receipts and eight artifacts are independently retained in the root evidence bundle. No original receipt or runner was changed.

## Reviewed execution sequence

1. Root may dispatch `stage-request.json` once. It creates only the new 32-hex-nonce input directory and its single 2670-byte frozen input, as operator UID/GID1000. Existing names are rejected; fixed parent, held/named identity, exact bytes, owner and mode are checked. Default PLAN writes nothing.
2. After the staged input succeeds, root may dispatch `generated/host-check-request.json`. This runs the unchanged wrapper's read-only binding checks.
3. Only if the check succeeds, root may dispatch `generated/host-run-request.json`. It retains the original complete3793 registrations, CPU6, one repetition, no sharding, and the same baseline/loader/corpora/skip contract. Its owned unit is limited to CPU100%, MemoryMax1GiB, swap0, TasksMax128, RuntimeMax900s, with whole-control-group cleanup and original Main/resource guards.

The process-start wrapper for the actual host run remains the original 20%CPU/256MiB/1000s shape. Each phase has one stable key. A transport timeout must be reconciled using that same exact request; this freeze contains no automatic retry or additional execution.

## Pending gates

The host suite has not run. The four Android signal cases remain behind the actual host PASS, fresh private preparation, and independent root runtime review in the unchanged template03. This engine still has metadata generation default flag0. Host/signal qualification cannot qualify enabled ART lifecycle, factory, metadata generation or all applications. Main is not deployed by these requests.

## Evidence authority

`binding.json` gives all five original local/remote paths and actual hashes; `BINDING_VALIDATION.json` records the actual local generator invocation. `generated/GENERATED_PINS.json` binds its outputs. `LOCAL_SOURCE_CHECK.json` confirms every template payload, exact staged bytes, and the actual default PLAN. Root owns the original collector/addendum and all raw build records in its separate evidence directory.
