# Durable receipt journal

**Work package:** `TOS-D0C-06`
**Owner:** `hepta-session-core::receipt_journal`
**Claim class:** local lifecycle durability only

## Boundary

The journal records facts supplied by the session/BrowserActor layer. It does
not admit a request, drive Servo, authorize a capability, execute an operation,
or replay anything. The product may bind it to BrowserActor only after this
standalone durability gate passes.

In the current D3 development profile, the observer persists a logical
monotonic sequence in the `*_monotonic_ms` fields. The sequence is strictly
ordered across reopen and rotation and is suitable for lifecycle ordering; it
is not a claim about wall-clock elapsed duration. A runtime integration that
needs physical elapsed timing must bind and attest its monotonic clock before
raising the claim ceiling.

Every segment is a private `0600` regular file. A sidecar writer lease is
created atomically, held with an advisory descriptor lock, and binds the
current Linux boot ID, PID, and `/proc` start time. A clean teardown keeps the
sidecar inode and writes a `released=1` marker while holding the lock; this
avoids a check-then-unlink rename race and lets the next opener safely reuse
the same inode. A crash leaves the identity payload stale; reopening requires
the explicit crash-recovery policy and verifies that the recorded process
identity is no longer live before replacing the payload in place. Malformed or
unreadable lease state is never treated as stale, and a replacement lock inode
is never removed by an old writer.

## Format and chain

A segment begins with a fixed 148-byte header. Each record has a fixed
208-byte prefix, a bounded canonical binary payload, and a 32-byte SHA-256.
The prefix binds:

- format version, lifecycle, source, effect and privacy classes;
- strict global sequence;
- monotonic and wall-clock observations;
- session/document/snapshot/mutation identity;
- request and optional response digests;
- the previous record digest;
- payload length and payload digest.

Rotated segments bind the previous complete segment digest and last record
digest. Rotation is refused while any receipt is unresolved. The in-memory
successor carries terminal receipt progress, and `inspect_chain` replays
lifecycle/effect-class validation across every supplied segment, so a receipt
identifier cannot be admitted again after rotation. Callers reopening a later
segment must inspect the complete ordered chain before treating it as
appendable.

## Commit and recovery

Append order is:

```text
validate event and lifecycle transition
  -> encode complete record
  -> write_all at the known complete offset
  -> sync_data
  -> update in-memory sequence and chain state
```

A write or sync failure poisons that writer. It cannot append again until the
file is reopened and scanned. A trailing partial record is reported as a typed
torn tail with the exact last complete offset. Explicit crash recovery may
truncate only that tail and sync the truncation. A digest, sequence, transition,
length, or chain error inside a complete record is hard corruption and is never
auto-repaired.

Recovery exposes unresolved `requested` and `dispatched` receipts. A dispatched
potential external effect always returns `never_automatic`; the journal has no
API that executes or reissues it. Observation recovery can tell the caller that
a fresh observation may be made, but the caller must create a new admission and
receipt lifecycle.

## Privacy, export, rotation, and retention

`secret_redacted` records cannot persist a detail field. The public
`export_redacted_jsonl` entry point now emits one canonical
`trillionnium.desktop.receipt.v1` envelope per receipt ID: requested and
dispatched records are aggregated with their terminal completed,
interrupted, or indeterminate fact. It validates the envelope field set and
status/error-code rule before atomically committing the JSONL. An unresolved
receipt is rejected rather than exported with an invented status. The
journal-level fields (sequence, record digest, lifecycle, effect/privacy
class, and request/response digests) remain available through
`export_journal_redacted_jsonl` for forensic consumers; that format is not a
receipt.v1 envelope. Retention planning returns only old, inactive segments
whose sealed digest exactly matches the source digest recorded by a completed
export; it never deletes files itself.

The observer emits only fields it owns at this lifecycle boundary. Optional
producer-owned fields in the receipt.v1 schema—such as package-lock and
normalized-target digests, final URL/redirect evidence, challenge and
snapshot evidence, receipt-chain digests, and signing-key identity—are
intentionally omitted until their owning producer supplies them. Omission is
not a negative assertion: consumers must treat an absent optional field as
“not supplied by this observer,” never as proof that the fact is empty, false,
or unavailable.

## Promotion evidence

D0C-06 requires Rust 1.93 formatting, Clippy with warnings denied, the complete
workspace test suite, repository validation, the contract/source audit, and the
journal fault corpus covering:

- complete append/restart/chain recovery;
- illegal lifecycle transitions;
- torn-tail detection and explicit repair;
- complete-record tampering;
- disk-full partial writes;
- unresolved external-effect replay refusal;
- redacted export;
- rotation and cross-segment chaining;
- retention safety;
- concurrent-reader partial-tail behavior.

Passing this gate does not claim BrowserActor, Servo, an enabled AgentPort, or
an authorized external effect.
