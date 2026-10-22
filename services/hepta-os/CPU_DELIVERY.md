# Retained CPU delivery observation

The default-off `cpu-history` feature connects the existing production HOS2
outbox payload to the original A02 codec. It issues one `QueryDelivery` for the
retained D. There is no effect, retry, ID allocation, acknowledgement, retirement
or renderer entry point in this adapter.

## Existing production owner

The source contract is pinned to Hepta PR #2966 at
`f27c14641753e0b03ceaa0e76031c6d19b1efbfb` in
`CPU_UPSTREAM_CONTRACT.json`. The original owner is
`ProductionDurableWriter` / `LocalLeaseOutbox` in the existing `CognitiveStore`.
Its logical operation K is `OperationIntentV1.operation_id`. The scope digest,
subject, policy generation and payload digest are semantic constraints. Writer
generation is a separate current-owner fence. No scope identifier is invented
from a digest, and this adapter does not use the separate DurableOperationStore
model's compound key.

The existing owner already persists the complete canonical
`Hos2InstallBudgetV1` JSON in its immutable outbox under the original operation,
admission and event transaction. That payload contains D `(boot_id, space_id,
sequence)`, management slot/generation, expected revision, period and cap.
The 16-digit lowercase hexadecimal sequence preserves the full unsigned u64
identity in SQLite. Its existing migration 0016 adds the unique D index over
that same outbox. Admission and dispatch enforce the previous D's original
terminal evidence before progressing within a namespace.

The original owner also produces the non-serializable retirement permit from
its complete contiguous terminal prefix. This OS adapter adds no table,
migration, cursor or substitute durable receipt. That owner branch's exact
schema recovery rules and required gates remain applicable; its existence does
not qualify a native guest or authorize its production rollout.

## Bounded codec mapping

`RecordedCpuDelivery::from_owner_record` receives the original operation
metadata and canonical payload JSON. Before snapshotting, it performs:

- A 1,024-byte input bound and the original bounded stable-ID grammar.
- Strict typed JSON parsing, duplicate/unknown-field refusal, and exact
  canonical reserialization, including the original sequence grammar.
- SHA-256 recomputation of the payload and exact native scope.
- Recalculation of the original OperationIntentV1 domain-separated semantic
  digest, including the subject and policy generation. The HOS2 destination's
  required absent expected-predecessor CAS field is preserved.
- Encoding through the actual A02 `Request::encode`, which checks the complete
  96-byte InstallBudget request, handle, revision, period, cap and sequence.

The encoded frame is retained only to make the mapping reviewable. This module
has no method that sends it. Later changes to the caller's strings or metadata
cannot alter the snapshot. The digest checks establish correlation; they do not
authenticate a caller, prove a durable commit, grant a native slot or create a
live production writer.

The embedding host must use the existing writer's dispatch/observer exclusion
gate and current-owner checks, and refuse operations disabled by a protocol
contradiction. It must also preserve that owner's exclusive native namespace,
immutable D-to-request binding, authenticated transport and original recovery
cut. QueryDelivery carries no cap or source payload digest; an old receipt from
a conflicting use of D cannot supply those missing prerequisites.

## Read-only observation

`query_once` encodes one 104-byte QueryDelivery and accepts at most 128 response
bytes. The read request ID and current history-view handle come from the trusted
host. That view may differ from the original management handle, including the
existing recovery image's retained manager-history capability. Invalid query
identity is rejected before transport entry.

The shared codec validates every response field, opcode, request ID and delivery
sequence. The adapter additionally checks the original boot and requested
previous revision. A successful history result returns the nonzero stable
object ID actually observed in that result; the source payload does not contain
such an ID, so this adapter does not pretend to recover it from the bootstrap
page. The original trusted native owner remains responsible for the resource
and namespace binding.

| Observation | Result |
| --- | --- |
| Correlated saved successful install | `Installed`, including the observed object, revisions and CPU accounting values |
| Saved semantic rejection | `TerminalRejection` with the original status |
| Reserved, retired, not seen or lost history | `Unknown`; none establishes zero effect |
| Outer refusal, including revoked history authority | `Unknown`; not an old delivery result |
| Saved busy or indeterminate | `Unknown` |
| Transport failure, malformed bytes, boot or revision mismatch | Error; the original operation remains unresolved |

An Installed observation describes the saved configuration. It is not CPU
execution, model output, durable source confirmation or device qualification.
Only the original owner may persist an authenticated terminal observation and
produce its independently authorized retirement permit. Transport errors are
returned after one call; there is no reconnect or resend.

## Validation

`tests/cpu_delivery.rs` runs the real codec and this adapter with explicit
transport fixtures. The identical `hos2_production_owner.json` vector is also
consumed by the existing Agentd adapter test on the Hepta owner child. That side
uses the actual `Hos2InstallBudgetV1`, `OperationIntentV1` and
`AgentdHos2Device` implementation to check canonical JSON, all three digests,
bootstrap/QueryAbi, InstallBudget and QueryDelivery bytes. The OS side checks
those same request and response bytes with A02. These are transport and source
contract tests, with no native syscall or physical device claim.

The original A10 host script now prefetches the complete service lock, runs the
feature's tests and strict all-target Clippy in addition to its existing suites.
Its Rust version remains 1.88. Run the service checks with:

```sh
cargo test --manifest-path services/hepta-os/Cargo.toml --locked --features cpu-history
cargo clippy --manifest-path services/hepta-os/Cargo.toml --all-targets --locked --offline --features cpu-history -- -D warnings
```

The existing production owner still needs the full source-bound native guest
qualification, including the real recovered writer, external grant provider,
kill/revoke/reboot and contiguous retirement observations. Current fixture
results do not establish those gates or physical desktop/Android/GPU support.
Session/Shell and broker effect submission remain disabled.
