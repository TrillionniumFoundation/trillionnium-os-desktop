# Producer07: bounded observations of the existing relay owner

This source candidate closes an observability gap in the actual Rust owner. The producer can already authenticate a real init peer, receive broker READY and ACTIVE, and require joined broker retirement, exact process death, an empty domain and final claim release. Its previous public response exposed ordinary cell state without these individual facts. A Running response could not prove enrollment; cleanup success could not explain the original runtime failure.

The candidate adds a data-only snapshot at the existing successful validation points. It does not add a lifecycle state, execution command, worker thread, pressure threshold, effect permission, network action or automatic recovery path. A serialized observation is never accepted by any authority API.

## Exact basis and execution boundary

The basis is the published producer05 31-file input set plus the exact three-file deadline06 correction. `baseline-deadline06/manifest.json` identifies this local basis. The complete source candidate adds one module, for 32 pinned inputs. Only ten inputs differ from that basis; nine have preimages and the new `audit.rs` is an explicit new file.

Parent-owned actual evidence for the basis:

- recovery04 compile: job `1a1a91dc14b-fc05-3186`, exit 0, durable; build receipt SHA-256 `2eb658308593cf760b7f99bbc9e3d7762295ef18c4628b050221838ffa274d4f`. Four binaries and two library test artifacts were recorded, with identical source inventories before and after. Own peak was 707211264 bytes, swap peak zero, max/OOM counters zero.
- recovery04 ordinary controls: job `1a1a922466f-fc05-31bf`, exit 0, durable; run receipt SHA-256 `64e6f6edd25f90431c2129fe70e63c97aca8bd1269ef63f18815574df0c977f2`. Both real public retirement transport controls passed, as did 23 relay library tests, 112 supervisor library tests, seven owned IPC controls, worker-context and entry-ABI checks. Own peak was 54697984 bytes, swap peak zero, max/OOM counters zero.

Those are basis results, not results for this new audit source. This local environment has no Rust compiler. New Rust controls are source only until an exact matching build and ordinary run are observed. No producer07 Owner, Android, namespace, pressure or Main execution has occurred.

## What is added

`RelayLifecycleAudit` is a bounded, serializable read-only projection. It binds the random owner nonce, canonical CellSpec digest and host UID to an observation of the actual process leader, held pidfd/proc birth identity, namespaces and executable. Actual init and broker identities are captured from their existing authenticated held handles.

The journal contains at most sixteen distinct ordered milestones and bounded error text. Times use `CLOCK_MONOTONIC`. Failed identity observations, clock/order/capacity faults, oversized payloads, truncated errors and mutex poison permanently set `recording_incomplete`. Such failure never substitutes a successful record. Runtime, retirement and cleanup errors remain separately visible; successful later resource release does not clear the first failure.

The new `ControlResponse.relay_lifecycle` field is optional and omitted when absent. Existing None responses retain their serialized fields and order. A paired candidate daemon/client must be used when the new field is present: an older client with `deny_unknown_fields` may reject it. Only Status and Stop include the field, and only root or the exact cell host UID may read it. Errors use the same authorization check. A new active legacy cell never inherits an older relay's snapshot. The final snapshot is retained in memory only after the original cleanup succeeds; daemon loss still requires external evidence and persistent claim recovery.

`DevelopmentCell::relay_lifecycle_audit()` also exposes the same observation to an owned in-process caller. It neither advances the owner nor changes cleanup.

## What remains unchanged

`HostContext` still originates at the process leader and revalidates worker identity/namespaces. The new broker accessor reads the existing authenticated ProcessPin; it does not accept a PID or expose a reusable authority handle. Init message checks and the final broker gate immediately before `sendmsg` are unchanged. Observation code is placed after actual sends and completed validations.

READY still means host preparation. ACTIVE still requires actual grant delivery and proves no PSI event. Broker RETIRED still requires the real terminal pressure audit plus exact child reap. The owner still separately proves exact owner/init death, domain emptiness, resource removal and final claim release. Retirement timeouts, retained failures, persistent poison and the new shared two-second deadline remain unchanged.

The pressure receipt projection includes exact registration records and aggregate event counts. It deliberately does not include per-event correlation or assert native stale-drop/kill qualification. Existing actual pressure and relief-stale evidence retains its original scope.

## Meaningful controls

Seven new Rust library controls cover recording gaps/order/clock failures, preservation of first errors through later successful-looking records, oversized payloads and Unicode truncation, poisoned audit mutex handling, refusal of non-leader self capture, UID-scoped retained response data, and prevention of cross-generation/legacy data reuse. The existing actual-owned-child pidfd control additionally checks the new observation against its held descriptors and rejects observation after exact reap.

These controls are not an actual init or broker lifecycle substitute. See `FIELD-SOURCES.md` for the evidence path of every field and `PRIVATE-CELL-NEXT.md` for the next bounded build and real Owner plan.
