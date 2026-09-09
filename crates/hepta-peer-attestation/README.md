# hepta-peer-attestation

**Work package:** S04 / D0C-05 identity mechanism  
**Claim ceiling:** local Linux process/service and request-custody attestation;
no semantic principal, capability, browser authorization, production activation,
installed-image, hardware, signing, or release claim.

## Responsibilities

The crate binds `SO_PEERCRED` PID/UID/GID to bounded procfs facts, uniform
real/effective/saved/filesystem IDs, process start time, cgroup-v2 path, systemd
unit, executable bytes, and pidfd liveness. Namespace PID mapping is resolved
without guessing; ambiguous or malformed mappings fail closed.

Optional qualification/development static executable modes re-open a fixed,
root-owned, executable, non-writable, no-follow path on every refresh. Those modes
are not enabled by the product default graph.

## Request-scoped custody

`AttestedPeer::request_custody` duplicates the same pidfd with close-on-exec and
retains the original attestor and executable source. The sole custody owner is not
cloneable. Verifier clones can only recheck or observe revocation; they cannot
extend custody, substitute a PID, change the procfs root, or reset failure. Drop,
explicit revoke, process exit, identity drift, unreadable source, or digest change
latches permanent revocation.

Full refresh may perform bounded file I/O and hashing, so it is not a hard
real-time primitive. A cheap liveness check is available for wait loops. Later
BrowserActor boundaries must recheck at engine entry, engine return, and final
result publication.

## Failure handling

Mechanism identity is not authorization. Identity loss after a possibly executed
effect must become indeterminate and never automatic; it must not be reported as
confirmed success or replayed blindly.

## Verification

```bash
cargo test --locked -p hepta-peer-attestation --all-features
cargo clippy --locked -p hepta-peer-attestation --all-targets --all-features -- -D warnings
```

Tests cover PID/start-time/ID/cgroup/unit drift, executable replacement,
namespace ambiguity, no-follow static paths, caller exit, source substitution,
request-custody drop, cross-thread verification, and latched failure.
