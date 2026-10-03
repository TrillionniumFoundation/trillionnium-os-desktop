# Request-scoped peer custody

S04 introduces an in-process identity-continuity primitive, not a capability.
After initial peer attestation, one non-cloneable `PeerRequestCustody` owns a
close-on-exec duplicate of the same pidfd and the exact original procfs and
executable source. Cloneable verifiers can only recheck that identity.

Dropping or revoking custody invalidates every verifier. Any liveness, source,
process, ID, start-time, cgroup, unit, or executable failure latches revocation;
restoring old files cannot revive it. A new request requires new custody.

A cheap verifier checks revocation and pidfd liveness. Full refresh reopens and
rehashes bounded identity inputs, so it is not hard-real-time. Future queue and
engine boundaries must perform full refresh at admission, engine entry, engine
return, and actor return.

Identity loss before dispatch denies the request. Identity loss after an operation
may have executed is indeterminate and never automatic. This source does not
provide BrowserActor, semantic principal mapping, product activation, or Servo.

The source validator also refuses malformed units, unknown public API fields,
reference hash mismatches and unreadable inputs. Its CLI does not echo input
lines, unknown field names, reference hash values or
exception text, which can contain credentials or private paths. It retains the
fixed finding category and failing exit status. The local unit parser identifies
the repository-relative filename and line number; operators inspect the original
source locally. Unknown fields produce one fixed finding per checked object.
This diagnostic boundary neither accepts malformed input nor
changes peer custody or product error handling. Tests exercise actual malformed
unit bytes, a JSON reference hash and a missing-file exception with controlled,
nonsecret canaries.

Every CLI finding is selected from fixed labels: `S04 unexpected-field`,
`S04 contract_sha256 mismatch`, the existing fixed custody/decoding/parsing
diagnostic, or `S04 SOURCE_INVALID`. The first three labels require exact known
finding messages; other source findings use the last label. No original finding
text is formatted into CLI output. The detailed `validate_root()` findings remain
available to local callers, and the CLI preserves the actual error count, failure
status and success message. Real subprocess tests cover valid inputs and refused
JSON, unit and source inputs containing controlled nonsecret Unicode, path and
credential-shaped sentinels. This output boundary does not assert that the
literal peer field names in the current scanner finding contain numeric peer
credentials.


## Claim ceiling

This document proves source-level local mechanism constraints only. It does not prove a semantic principal, capability authorization, BrowserActor, Servo execution, an installed image, physical hardware, signing custody, publication, or release.
