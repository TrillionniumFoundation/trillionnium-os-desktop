# Disabled role listener admission and snapshot dispatch candidate

This source adds a real bounded listener caller for the existing role Registry. It uses accept4, kernel-identified Receive, Begin/Approve/Attach and an exact fixed response. The previously frozen old V2 factory main is byte-identical and this candidate does not enable or bind an ambient service. The separate owner-lifetime revision is an explicit dependency: its repaired Registry is the preimage for the new local handle-returning approval wrapper, and its repaired OwnerLease is included byte for byte.

## Authorization and publication

Begin returns a pending challenge and a local handle; it is not snapshot authority. Root approval still runs the original held PIDFD, kernel sender, actual parent, same namespace, typed initial UID/GID, declared range, deadline and immutable context checks. ApproveAndIdentify returns only the handle from that successful transition; no peer supplies a slot/serial. The legacy Approve signature delegates to the same implementation. Its authority body is unchanged. A root caller still must attest the actual early pre-guest policy transition: this API does not construct or trust missing Android policy inputs.

One two-second deadline covers accept, receive and acknowledgement. The listener must already be held by its trusted owner, nonblocking/CLOEXEC and configured for credentials and PIDFD delivery before any connection. Existing owner control/PIDFD liveness checks continue through the reply. All failures after a successful transition close the identified grant, including approval acknowledgement failure; rejected arbitrary tokens do not close unrelated grants. Pending expiration, maximum sixteen grants, tombstones and unknown-operation rejection remain in the Registry.

The reply is 224 bytes: fixed magic/version/size, state, zero reserved words, a Begin-only generated challenge and visible PID, plus the complete 160-byte canonical request. The receiver requires exact request equality, changes no output on failure, and closes known received FD-bearing ancillary records before rejecting them. It does not authenticate the factory by itself: the real client must independently bind its trusted root factory connection.

After true approval, the existing DispatchOne path calls CreateAuthorizedSnapshotBefore and completes FinishCreate before any SCM_RIGHTS publication. Suspension, detach, reattach and release use the existing held grant and lifecycle checks. No root capabilities, ordinary zero-cap gate, native metadata owner, NNP/base/range gate or old V2 path is relaxed.

## Actual local controls

The complete current translation units build under the recorded strict compiler. Fourteen local codec/real socketpair cases passed, with 216 assertions: canonical replies, exact request binding, short/long records, unexpected rights, automatically delivered PIDFD closure, credentials rejection without accidental fd closes, and atomic invalid-input rejection. This is transport evidence only: no accept/listener authorization or root snapshot was executed.

The new actual listener control compiles and its default invocation only prints PLAN. Its nine root cases are NOT RUN: Begin is pending; a wrong typed parent PID cannot approve; duplicate root approval cannot grant again; ordinary sealed snapshot dispatch/release; maker failure and recovery under the same grant; wrong token and unsupported active operation revoke; peer HUP; separate service-owner HUP or unexpected data; request timeout; and explicit same-lease suspend/attach. Nine role children plus nine separate root-owner peers are planned. The fixture binds only a unique owned abstract address once and verifies the server's actual known root credentials. Its root/role policy is the existing explicit non-platform fixture.

## Remaining production interfaces

The source exports AdmitOne; no enabled service loop, Android engine connector, trusted root-parent approval producer, early typed fork JNI, or policy installation is supplied. The actual Android root parent still needs typed UID/GID/ranges available before guest code, all-thread NNP, immutable base policy, exact range policy and matching generation proof. The current ART/AOSP and old V2 factory call sites are not silently replaced. Default metadata generation remains disabled. These missing authority inputs are blockers, not values inferred from a peer label or sampled snapshots.
