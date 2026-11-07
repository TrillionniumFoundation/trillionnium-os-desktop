# Pending first IHG owned launch and read-only inspect

This template derives from the exact Ticket02 coordinator/task adapter. The
first IHG read-only metadata and current launcher reference are fully bound.
Before launch, the original worker revalidates the current installed target and
helper, resolves the launcher again inside the held Main context, takes the
same original global action lock, and only launches a new leaf task with its
original exact owned-scope cleanup. Inspect has its original before/after state.
No click, text, login, booking, package-wide stop or settings action is admitted.

Actual IHG helper build/install receipts, UID, signed installed APK identity and
state wire are intentionally absent. qualified() rejects before file/device
access while these bindings are pending. No source manifest or request exists.
No Ticket lock-failure run is replayed or reclassified by this template.
