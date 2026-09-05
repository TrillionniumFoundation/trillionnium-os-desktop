# Immutable receipt admission and failure-atomic fixture publication

**Plan:** `2026-08-29-d6`

**Status:** local source candidate; independent review and exact-image evidence pending

**Scope:** receipt consistency and the isolated D3 development fixture only

## Admission identity is not a completion result

The first Requested fact fixes the meaning of a receipt ID. Dispatched and
terminal facts describe that same admission, not a newer PageOwner or a new
request with a reused ID. The journal previously kept only lifecycle and effect
class in its progress map. A correctly hashed successor could therefore change
request, session, revision or privacy identity. Record hashes alone detect byte
changes relative to a supplied hash; they do not enforce semantic continuity.

The shared `ReceiptProgress::advance` helper now validates the event, the legal
state transition, and a commitment to all immutable admission fields. It is
used by append, disk recovery, complete-chain validation, public envelope
aggregation and forensic lifecycle export. No execution or policy callback is
introduced into the journal.

## Exact field contract

The following ordered fields form one internal commitment:

| Group | Fields | Encoding |
| --- | --- | --- |
| Identity | receipt_id, plan_revision, image_id, servo_commit, browserd_version, session_id, operation | Each is a u16 big-endian UTF-8 byte length followed by those bytes, using the existing checked required-string encoder |
| Admission revisions | session_generation, document_generation, semantic_snapshot_revision, mutation_epoch | Four u64 values, big-endian, in the listed order |
| Classification | source, effect_class, privacy_class | Existing v1 enum discriminants, one byte each, in the listed order |
| Request | request_sha256 | Exactly 32 bytes |

SHA-256 covers the byte prefix `hepta.receipt.admission-binding.v1` followed by
one NUL byte, followed by the groups above. The progress map stores the resulting
32 bytes; it does not duplicate identity strings or retain detail content. The
commitment is an internal equality key, not an authentication signature or a new
record field. The authoritative record format remains HPTJRNL1/HPTREC01 v1.

Lifecycle, outcome, response digest, error code, detail and time observations
are not in the identity key. They still pass the existing per-event validation
and state-transition rules. Optional detail remains bounded and SecretRedacted
always forbids it. Freezing privacy means that a later lifecycle event cannot
remove redaction by relabeling the same receipt as Public or Internal; changing
to a stricter class is also refused rather than silently changing the contract.

The four revisions are the admission coordinates, not the post-action state.
An operation may advance the actual PageOwner. Its receipt still binds the
coordinates at admission; post-action results belong in the bounded response or
subsequent observation, not in rewritten admission fields.

## Enforcement and failures

| Entry point | Required behavior on identity drift |
| --- | --- |
| `ReceiptJournal::append` | InvalidInput before any record write or progress publication; the original valid continuation can still be appended |
| `recover_bytes` / `inspect_path` | Complete-record drift is Corruption even if its payload/record hashes were recomputed |
| `inspect_chain` / `open_chain` | Validate every event across the full supplied chain; reject before repairing any torn active tail |
| `ReceiptEnvelope::from_records` | Reject inconsistent input instead of dropping journal-only identity fields from the public envelope |
| `export_journal_redacted_jsonl` | Validate per-receipt progress before creating output; valid unresolved facts remain exportable without invented terminal outcomes |

The public `RecoveryReport` type can be constructed by a caller. Well-typed
input is not proof that it came from the disk scanner. Both export paths must
therefore enforce semantic consistency themselves. Neither authenticates the
report against an external source or verifies hardware provenance.

Normal append still follows validate/prepare, encode, write_all, sync_data,
then in-memory publication. Storage/custody failures retain the existing poison
rules. Identity validation never repairs, deletes or reclassifies complete
records. On restart the binding is reconstructed from original records; no
sidecar or writable cache can replace it.

## Compatibility and clock semantics

Clean historical v1 records with stable admission identity remain readable.
A historical complete record with inconsistent identity is now rejected. The
operator must preserve it for investigation; no automatic migration rewrites
request hashes, privacy, origins or receipt identities. This is a stricter
reader/writer semantic rule, not a silent binary-format conversion. Independent
review is required before promoting the changed behavior.

The journal intentionally retains supplied observations from different clocks.
This change does not impose a new per-receipt monotonic timestamp restriction.
Its maximum logical timestamp remains available to a restarted observer. Public
envelopes still reject a terminal timestamp preceding admission; that preexisting
export rule is distinct from storing observations. D3 logical timestamps are
ordering coordinates, not physical elapsed-time measurements.

## BrowserActor duplicate admission

`ReceiptLifecycleObserver::requested` must not replace the existing in-flight
coordinates when a duplicate request ID is rejected. BTreeMap entry admission
checks Occupied without mutation and inserts only a Vacant entry. If the first
Requested append fails, its newly inserted entry is removed as before.

This matters when PageOwner changes between the original admission and a rejected
duplicate: the later Dispatched event must retain the first session/revision
binding. The journal's shared check is the second line of defense; it must not
be used to excuse corruption of the observer's own admission map.

## D3 atomic fixture response preparation

`AtomicFixtureRuntime` remains a deterministic, local-only development adapter.
It owns no Servo node, performs no network effect and does not qualify D3. Its
u64 internal counters are returned through an i64-bounded JSON integer type.
Checking only u64 overflow is insufficient: response conversion can still fail.

For PageAct, target/revision validation and all fallible result construction
now precede the last cancellation/deadline check. Only then are the action count
and consumed snapshot published. No fallible conversion, callback or yield
follows that commit. A representability failure leaves both unchanged; a
successful action consumes the exact observed snapshot once.

For Observe, the previous snapshot is deliberately invalidated at entry. The new
snapshot is published only after all target/result fields are representable and
the final control check succeeds. A failed observation must not leave an
unreturnable target available for a later action. Invalidation of an old
observation is intentional fail-closed behavior, not a promise to retain every
old state on every rejection. Allocation abort, malicious in-process mutation,
real Servo dispatch and durable external effects are outside this guarantee.

## Executable checks and evidence ceiling

The Rust journal binding tests mutate every identity group, reopen real files,
recompute hostile record hashes, append a torn tail, rotate a real chain and
verify refusal without repair. Export tests cover public and forensic paths,
including valid unresolved redaction. BrowserActor tests move PageOwner between
a first admission and a rejected duplicate. D3 tests call actual PageRuntime
entry points using a control token captured from a real local BrowserActor;
they exercise JSON limits, cancellation, deadline, target drift and exactly-once
fixture consumption. They do not attest a production semantic principal.

```bash
cargo test --locked --offline -p hepta-session-core lifecycle_binding
cargo test --locked --offline -p hepta-browser-actor duplicate_requested
cargo test --locked --offline -p hepta-d3-development --features development atomic_tests
python3 tools/verify_receipt_journal.py
python3 -m unittest tests.test_verify_receipt_journal -v
```

The Python source audit consumes both implementation helpers and the executable
test source. Mutation tests remove each field, parent/chain call site, comparison,
module wiring and regression declaration. This is a structural guard, not a
formal proof or a replacement for the Rust matrix. Full repository/Python tests,
default/all-feature Rust checks, independent review and exact-main regressions
remain necessary.

No historical PASS artifact is refreshed by editing its claimed source hash.
New source invalidates the applicable D0C/D3 evidence. This work does not select
the latest journal head, add archival checkpoints, authorize replay, implement a
Servo retained-node adapter, enable production AgentPort, prove an installed
image, qualify hardware, establish signing custody or make a release claim.
