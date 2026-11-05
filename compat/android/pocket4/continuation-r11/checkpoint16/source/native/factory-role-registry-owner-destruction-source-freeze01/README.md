# Registry owner-only destruction — source freeze 01

The preimage rejects foreign processes/threads in its ordinary methods, but its destructor directly deletes the shared Impl. A foreign CLONE_VM process reaching inherited RAII destruction can therefore release the parent's Impl and mutate its allocator/descriptor fields. CLONE_FILES also makes the descriptor closes affect the parent's actual table. This is a deterministic source defect; the proposed actual control has not yet run.

## Narrow repair

The destructor now uses the existing OwnThread check, preserves errno, and does not clear impl_ on a rejected path. OwnThread includes the original current PID/TID check and the current thread observation through the owner's held proc view; it is not merely a cached owner-PIDFD observation. All authorization, listener/frame, parent/PIDFD, caller lease, phase, capacity, timeout, tombstone and cleanup algorithms are byte-identical. The ordinary V2 and snapshot source are unchanged.

Initialize previously used a temporary Registry as construction cleanup. Its proc proof is intentionally incomplete at several early failure points. Reusing the newly guarded public destructor there would leak partial resources. This revision therefore owns that unexposed Impl with local std::unique_ptr until successful initialization releases it into the public Registry. No new authority is inferred for a published object.

Close, Release and invalidation only revoke/reset a Slot; the owner's separate Impl.proc, self_pidfd, self and owner fields remain. A normal owner destructor after Close therefore retains the held-proc proof. Destruction uses OwnThread, not the stricter poisoned/credential-sensitive Owner check. If the held-proc proof itself is unavailable, it fails closed and the enclosing owner process lifetime must reclaim the resources. This destructor does not authorize a foreign caller to free/overwrite the Registry object's external storage or its containing object.

The header also corrects the FinishCreate description: a failed owner check can precede slot cleanup. The existing snapshot wrapper's same-owner Close and first-error preservation already handle that case; its source was not changed here.

## Meaningful proposed controls

The same control source is compiled against the exact preimage and candidate. The preimage arm performs real clone(CLONE_VM|CLONE_VFORK|CLONE_PIDFD|CLONE_FILES) with a separate stack and no concurrent parent allocator activity. The callback invokes the actual destructor. Before any new FD could reuse a number, the parent records whether every descriptor opened by Registry initialization was closed. It never reads or calls the freed preimage Impl and never destroys it a second time. There is no allocator hook, fake object state or simulated close. An observation of the defect is labelled OBSERVED_PREIMAGE_DESTRUCTION_BUG, not production PASS.

The candidate additionally uses a private fdtable with shared VM and an ordinary COW fork. Each child is bound to an actual PIDFD, executes the destructor, exits normally and is reaped. The original owner must retain exact descriptor objects, successfully Sweep, and later destroy its own Impl without leaks or errno change. A final real single-free-slot RLIMIT_NOFILE control verifies EMFILE cleanup between self-PIDFD creation and proc proof initialization; it restores the original limit and filler descriptors. No limit is raised.

Only local strict g++ compilation and both default PLAN entries were executed. local/result.json preserves those command outputs; source pins are post-compile observations, not a substitute for the matching target build's full before/after closure. Neither actual control arm, platform role/ART, new snapshot dispatch nor Main was executed. PID-namespace numeric alias and same-TGID foreign thread cases are not separately exercised by this fixture; the unchanged held-proc/TID gate remains the code boundary.

This is separate from the already frozen dispatch source; it has not silently replaced that source identity. Integrating the two requires a new explicit candidate after review. All preimage source, old PASS scopes and new pending controls remain distinct.
