# Native Objective interaction

Conversation keeps the existing per-workspace draft owner. The optional
original Hepta `ChatWorkspace`/Robrix presenter remains the sole shared draft
owner, and its chat `RequestSend` still returns `SendUnavailable`; the renderer
does not install a chat owner or fabricate a delivered message.

The first supported profile is Notes-only: the text is the configured Notes
document content, not a free-form AI execution instruction. A separate
**Write note via Hepta / 通过 Hepta 写入笔记** control snapshots that text into
the narrow Session Objective protocol. It is enabled only while the current
Session has a `Ready` observation no older than two seconds on both local
receipt and host observation clocks. Standalone Session has no configured
trusted host and therefore cannot enable submission. The UI cannot select a
host endpoint, agent, authority issuer, signature or permission.

The current protocol accepts text only and the trusted host binds the real
Notes target and original Notes operation. This does not save a document to
disk; Notes application memory and durable owner operation records are distinct. A draft with quoted context cannot be
sent: the UI explains that limitation and preserves every reference. Notes content is limited to 4096 UTF-8 bytes by the original Notes protocol.
Oversized text disables writing and is never silently truncated, and shared-presenter rejected edits or active IME
composition prevent submission. Sending retains the original draft.

Each explicit new objective gets one random `client_intent_id` before queue
admission. The same identifier is retained for all status and cancellation
requests, including uncertain submission. There is no automatic submission
retry and no new identifier minted to recover an ambiguous result. Further
new submissions in that workspace are gated until the current objective is
observed refused/not sent or terminal. At most 128 disposable intent views are
kept in this Shell process; these are not a recovery ledger.

The UI renders admission, request retention, publication retention, run
revision/phase, cancellation and issues separately. It rejects unrelated
intent/session responses, revision rollback, conflicting equal revisions and
terminal run regression. Old observations are labelled as last observed;
Session disconnection invalidates readiness. Neither admission nor terminal
run status establishes a device effect.

Availability and current-intent status use a separate coalesced passive queue
and cannot fill the user-action queue. Actual execution, authority binding,
durable request ownership, Agentd submission and cancellation remain in the
trusted host and original Hepta owners. See
[`ui/session/OBJECTIVE_BRIDGE.md`](../../ui/session/OBJECTIVE_BRIDGE.md).

Tests in `ui/shell/src/objective_panel.rs` cover fresh readiness, Session
changes, wall-clock rollback, conflicting run observations and stable intent
identity. These test the UI contract; an original host/Agentd end-to-end run
is a separate gate.
