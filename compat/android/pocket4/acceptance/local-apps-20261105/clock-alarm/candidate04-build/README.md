# Clock alarm dispatch candidate 04

Actual build: 2026-11-05 19:47:37–19:47:52 UTC. Candidate `433ff501…` is signed but **not installed**.

Only newly scheduled alarm envelopes use the new routing: FIRED goes to the existing foreground alarm service; the other eight states use the existing asynchronous receiver. Cancellation covers the old service identity and both new types. Validation binds generation, source state, parent and occurrence. Valid FIRED recovery remains supported; duplicate, missing, stale and terminal-state starts cannot silently leave an idle foreground-service request waiting. Original unmarked recovery and notification/user commands remain on their existing path.

The actual build compared all 2,941 classes and 19,744 methods: five old methods changed, six were added, and all other original methods remain. Across the four changed classes, 43 original methods remain unchanged. The 1,281 non-signature ZIP payload members differ only in classes.dex. Signing certificate, v3 verification and 16 KiB alignment passed.

The 53 local checks execute smali control flow in a small offline interpreter. Android boundaries **and the named App delegates** are doubles; see HOST_TEST_SCOPE.json. This is not an ART, database, service, notification, sound or end-to-end alarm qualification. The previous failed alarm trial is not rewritten, and old timer credit cannot be transferred to this candidate.

No signing keys, password arguments, private notification dumps, audio or process maps are included.
