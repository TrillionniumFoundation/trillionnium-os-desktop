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


## Claim ceiling

This document proves source-level local mechanism constraints only. It does not prove a semantic principal, capability authorization, BrowserActor, Servo execution, an installed image, physical hardware, signing custody, publication, or release.
