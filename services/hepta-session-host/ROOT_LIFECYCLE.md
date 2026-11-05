# Original Root joint lifecycle

This module composes the original Hepta owners and actual Linux Session processes. A Root stage file is an administrative observation. It is never a grant, Current, effect result, or a replacement operation ledger.

## Explicit entries and finite authority

`initialize-desktop --config <Root0600-input>` selects the existing `notes_calculator_v1` input schema, creates one original Core Desktop thread, and binds both actual application reservations to the same original writer. Notes and Calculator require separate durable state directories and separate typed targets.

`recover-desktop --config <same-input> --previous-generation <n> --latest-original-desktop` explicitly continues that same deployment after the original owner and Session have actually exited. Exact operation selection instead requires both `--notes-operation-id <id> --calculator-operation-id <id>`. The operation IDs are selectors for original retained signed records, not permissions or instructions to repeat effects.

The old Notes-only `recover` entry retains its existing finite issuer window. It cannot select a joint deployment or silently renew its issuer. Joint recovery has its own entry, matching seed type, sealed schema, and required Calculator persistence.

Neither entry lengthens the configured lifetime or a grant. Joint continuation uses the original Root clock and lease registry to prepare a finite same-ID issuer record at exactly revision + 1. The plan keeps the original epoch, binding, key and issuer directory. Root persists that exact plan before calling the original CAS. After success the successor config pins the new revision and the original factories reopen the same issuer. The old instance remains invalid at its old revision.

## One consumed spawn per generation

All recovery generations hold the same original `admin/recovery.lock`. Generation 1 reads the original files in `admin`. A successor writes only its own `admin/recovery-<generation>` directory. The supplied generation must match the original writer registration and actual Fleet spawn history; it is only a bounded numeric locator.

Before any child creation, preparation retains:

- `00-admitted.json`: exact predecessor registration, original thread and App targets, generation and selectors.
- `02-issuer-renewal-plan.json`: one immutable original issuer postimage, when explicit joint continuation is selected.
- `03-issuer-renewal-committed.json`: the exact canonical record returned by the original commit, matching that plan.
- `05-old-sockets-retired.json`: observations of only stale original sockets under protected Root parents.
- `06-spawn-consumed.json`: durable consumption of one child-creation attempt.

An interrupted pre-spawn attempt may reopen only with the same admission and same renewal postimage. It does not compute a later expiry on retry. An expired plan, a changed selector, a changed canonical record, a revoked issuer/writer, a changed epoch, or a consumed spawn refuses continuation. A previous fixed `admin/recovery` directory is preserved for original-owner reconciliation; it is not interpreted as a new generation.

The original Supervisor alone starts/stops/reaps its actual child. Serialized PIDs are compared with actual process birth metadata and independently observed retirement; they are never adopted or signalled.

## Joint startup and recovery

The successor first uses the original writer rotation and physical material recovery. The Root startup method observes original physical Current, then performs one CAS for the exact old Notes/Calculator policy pair to the actual new Reserved pair. Both admissions still use the same original retained issuer and writer. A partial pair is never installed as a successful transition.

Fresh sealed Desktop launch remains schema v1 with no previous recovery field. Joint recovery uses schema v2 with a strict previous pair. Each request retains an independently typed App target, exact helper SHA-256, private state directory and typed original-record selector.

The original Agentd resolves those selectors from its original protected signed-source cut and ledger. It installs only recovery factories for old targets. The old helpers admit observation and exact terminal-ACK metadata; they have no dispatch or FinalUse registration. New operations still require the new target's original admission and FinalUse checks.

Historical Committed state alone does not prove target retirement. Skipping older history requires an original owner durable record of the actual target ACK. Root's generation files do not provide that evidence and must never be used as a second retirement ledger.

## Durable product identity

New joint Root composition uses `trill.original-desktop-root.composition.v3`, with both typed targets and the exact `u/notes` and `u/calculator` state directories. Older v2 joint composition lacks required durable Calculator evidence and is refused. The original typed Desktop seed is read and verified as Desktop; it is not deserialized through an ambiguous untagged Notes/Desktop enum.

The joint artifact set includes both recovery helper ELF hashes. Recovery rehashes the original installed programs and source freeze and compares the original artifact set. Existing user state must have the original physical private-directory custody. Recovery does not create a new home, SQLite owner, authority epoch, signing key, or hidden writer.

## Validation and qualification

The durable Calculator checkpoint, single state worker and real recovery helper have separate host component/process tests. Those tests do not qualify this Root lifecycle composition.

This lifecycle source is integrated against the new Hepta successor, issuer renewal, original-record selector and retirement APIs. The Desktop Git dependency must be pinned to the final combined Hepta commit before compilation and packaging. Required acceptance is the original test suite plus an installed, same-source-pair Linux run through two actual successive owner/Session generations, followed by revoked-authority refusal. A source check, fixture, single recovery attempt, QEMU run, or an old source pair cannot substitute for that evidence.

Native Asterinas G2 and physical Android remain separate qualifications. This document describes the Linux original-host composition only.

## Per-target data and original issuer revocation

The shared u/notes and u/calculator paths are namespaces. The stores create
a distinct session_instance-task_id-incarnation directory for every new target;
an existing target is never reset as fresh. Old recovery helpers open only the
explicit previous target in RecoveryOnly mode and retain its exclusive lock.
A successor starts new documents. Notes offers an explicit saved-text copy
with revision/digest checks; Calculator does not automatically inherit values
or history. Neither path imports an old effect or retirement receipt.

The original local admin client can revoke only the currently configured issuer:

~~~text
admin --instance-file <generation admin/root-admin-instance.json>
  revoke-issuer --expected-lease-id <original issuer ID>
  --expected-revision <current configured revision>
  --reason-sha256 <nonzero lowercase 64-hex digest>
~~~

Generation 1 uses admin/root-admin-instance.json; later descriptors live in
admin/recovery-N/root-admin-instance.json. The existing private socket, actual
Root credentials, nonce, pinned peer and cumulative deadline remain mandatory.
The exact original lease, including epoch and binding, is compared inside the
same registry CAS lock. Only its committed self-revocation can use the private
terminal-confirmation path that no longer asks the revoked issuer to be live.

A successful issuer_revoked reply is a verified terminal fact, not a use token.
A lost or late reply remains unknown and must not trigger a mutation retry.
Record registry revocation and client confirmation separately. A real rejected
Gen4 recover-desktop attempt proves the recovery entry refused; if it fails
before renewal or writer rotation, it does not prove those later functions were
executed. Their detailed revoked-state cases require the original Rust tests.
Already-issued effects retain their own original finite FinalUse semantics.

For the two-successor scenario, use separate original Chat turns for Notes and
Calculator: the joint turn fence admits only one effect across both Apps per
turn. Retain the original request, target, operation, terminal, actual target
ACK and protected Current evidence for each generation. Preserve all per-call
timeouts and finite leases; an explicitly budgeted whole scenario does not
extend any individual deadline.
