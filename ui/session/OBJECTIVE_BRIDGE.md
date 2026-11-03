# Objective bridge

The desktop sends only a typed user intention (`client_intent_id`, `text`). The
trusted deployment selects the Objective issuer, original writer, Agentd identity
and Unix peer. No renderer field can supply an envelope, signature, endpoint,
run ID, authority epoch or expected run revision.

The Session deployment may set `TRILL_OBJECTIVE_HOST_SOCKET` to an absolute,
private Unix socket and `TRILL_OBJECTIVE_HOST_PID` to its independently known
process ID. Session checks the socket owner/mode and kernel peer UID/PID. Missing
or invalid configuration remains unavailable. The Session generation is checked
before any command is forwarded. The standalone UI never creates this service.

The backend accepts one newline-terminated `ObjectiveCommand` and returns one
newline-terminated `ObjectiveObservation`, then closes its write half. Session
bounds the complete exchange to 150 ms. The backend must use the single bounded
`hepta_session_host::ObjectiveWorker`, which immediately returns a queued or
cached observation while the original owner does the work. Raw errors, source
content, signed envelopes and store paths are not returned to the renderer.

Availability requires the original Agentd to report `objective.start` major 1.
`observed_unix_ms` is a local presentation freshness marker, not a trusted clock;
clients must expire cached readiness and never treat it as effect permission.
A new intent ID is allocated once per user submission and reused for Status and
Cancel. A host restart recovers that ID through the original sender's retained
requests; it does not reissue or resend it. The host issuer must derive the same
run ID from its persistent trust namespace and the same client intent ID.

Admission, durable receipt retention, current run state, cancellation, and device
effect completion are different facts. The bridge reports the first four; it
never reports effect completion. A missing RunStatus does not disprove admission.
Cancel obtains its expected revision from a fresh original-owner RunStatus and
uses the original RunCancel protocol. A transport timeout remains unknown.

The initial text profile does not carry context references. UI must preserve the
local draft and refuse to silently discard its attached context when sending.
