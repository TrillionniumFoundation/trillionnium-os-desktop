## Primary trust boundary

Describe the single primary trust boundary changed by this PR. Explain why the change cannot be split further without losing independent buildability or rollback safety.

## Scope

### Included

- 

### Explicitly excluded

- 

## Exact subjects

```text
base SHA:
head SHA:
prospective merge SHA, when applicable:
external source/toolchain pins:
```

Prior-head workflows, artifacts, approvals, and evidence do not transfer after a push.

## Claims and non-claims

### Strongest claim supported by this PR

- 

### Explicit non-claims

- 

## Security invariants

- [ ] All untrusted inputs are bounded before allocation or authority changes.
- [ ] Missing or malformed configuration fails closed.
- [ ] No fixture, development binary, or qualification-only authority enters the production graph.
- [ ] Deadlines are absolute and do not extend through partial progress.
- [ ] Identity/capability/reference validity is rechecked at the effect boundary where external state can change.
- [ ] Potentially completed effects become indeterminate and are not automatically replayed.
- [ ] Logs and evidence contain no raw secrets or sensitive page content.

## Contract and compatibility impact

- [ ] No public contract change.
- [ ] Contract/schema, Rust model, golden vectors, errors, tests, migration, and documentation change atomically.
- [ ] Breaking behavior has an explicit version or migration policy.

## Verification

```text
commands executed:
workflow runs:
artifact IDs and SHA-256 digests:
fault-injection/property/fuzz coverage:
```

- [ ] Results belong to the exact final head.
- [ ] A failed, skipped, cancelled, empty, historical, or differently bound run is not counted.
- [ ] Evidence fields marked `*_tested` are false unless the corresponding test executed successfully.
- [ ] Source evidence is not represented as installed-image, hardware, signing, or release evidence.

## Rollback and recovery

Describe how this PR can be reverted independently and what happens to persisted state, protocol peers, active sessions, receipts, and partially completed effects.

## Documentation

- [ ] Module/component documentation is updated.
- [ ] Status and claim ceilings remain truthful.
- [ ] Operations and troubleshooting instructions preserve evidence and do not weaken controls.

## Review

- [ ] Final review is requested only after the last behavior-changing push.
- [ ] The author has not self-approved or used administrator bypass.
- [ ] Security-critical paths have independent owner review.
