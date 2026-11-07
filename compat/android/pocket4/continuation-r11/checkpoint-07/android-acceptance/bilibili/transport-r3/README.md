# Bilibili existing-helper transport r3

Status: local transport controls only; no Main action or recorder admission.

This revision retains the root review's concrete r2 failure: a command timeout
followed by an exception from the held entry context's `__exit__` erased the
timeout, skipped command-result recording and skipped the post-command epoch
guard. The exact r2 source is included as an immutable negative control.

The r3 entry lifetime is explicit. It observes and attempts to record the
command result before releasing the entry lease. It collects entry acquisition,
release, evidence and post-guard failures separately. Once a command has been
attempted, the post-command guard is executed from its own finally path. A
secondary failure does not replace the original timeout or nonzero status.
After any failure the transport remains closed and cannot replay a command.

The 25 actual local controls include the r2 negative, timeout plus release
failure, successful command plus release failure, failed entry acquisition,
timeout plus evidence/release/guard failures, and release after an invalid
entry tuple. The original 19 controls remain. The command runner and namespace
target are explicit seams; no Android command, setns, actual helper execution,
Main UI, sound capture or service mutation occurs in these controls.

`reference/android-app` and `reference/framework_epoch.py` are the exact
previously read source bytes. Loading the private helper copy does not invoke
its CLI. The candidate has no action CLI. The caller must still actually bind
the shared helper's bytes, unchanged Main epoch, held namespace/root authority,
paired-root classpaths, Bilibili package/UID and the real recorder's intent,
global action lock and new-owned-task cleanup. The exact r10 recorder has not
yet been located, and its direct task-list/remove namespace calls are known to
need the same held-entry treatment. No whole-flow or application qualification
is claimed.
