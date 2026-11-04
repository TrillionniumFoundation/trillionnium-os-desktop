# Scoped PSI registration and worker candidate

This crate extends the independently reviewed authentication owner with a real PSI registrar and a single worker. The exact source and binary in `registration-controls-public.json` passed owned host registration/revocation controls on Pocket4. **Actual pressure events, Android enrollment, LMKD decisions and Main deployment remain unqualified.**

`LeaseOwner::register` accepts an already authenticated peer and trusted `CellAuthority`. A request can echo scope and exact medium/some or critical/full parameters; it cannot select a path, parent cgroup, sibling or new generation. Scope mismatch is rejected before a pressure file is opened. The only filename opened for registration is `memory.pressure`, relative to the held authority directory with CLOEXEC, NONBLOCK and NOFOLLOW. The kernel filesystem and file identity, cell generation and unchanged budget are checked around registration. Every partial resource has an owning RAII value before another fallible operation.

One worker owns process/control/cancellation and at most two PSI descriptors. It forwards only a real `POLLPRI` result; error/HUP wins and there is no second poll that could consume a shared PSI event bit. It does not choose thresholds, read process scores, select victims or reap applications. Observation timestamps, sequence numbers and the original scope/budget are encoded in the existing fixed 128-byte protocol.

Poll cadence is at most one quarter of the smallest existing window and at most 100 ms. Progress, observation age and clock order are checked after metadata reads, poll and send. A delay at least one existing window, a malformed live identity, a queue error or a changed budget revokes. Nonblocking calls are not claimed to be immune to kernel allocation stalls.

A local revocation guard invalidates and shuts down notification senders before the monitor vector is released, including early returns/unwinding. The real PSI descriptions close before thread completion becomes observable. The lifecycle must still require successful `finish_retirement` before replacing its cell; `Drop` alone is not a cleanup receipt.

## Real control result

The fresh job retained `cpu.max=100000 100000` and `memory.max=536870912`, including during its temporary hierarchy setup. Only the frozen members of that job moved into the control leaf. The root, control, target and sibling had finite source-configured budgets under that unchanged parent. No Main process moved and no existing cell was modified.

The test proved namespace-root direct registration `EPERM` before read-only projection, host registration against the exact target, rejection of real parent/sibling and stale scope requests, quiet polling, automatic peer-death revocation, explicit/generation/sealed-slot revocation, real PSI descriptor release, worker completion, alias HUP, and complete hierarchy restoration. All memory-event counters remained zero.

The Python fixture records created directory identities, pins job process generations/UIDs/namespaces, preserves timeout partial output, and performs dependency-aware cleanup steps with aggregated failures. Unknown members or changed generations are not moved or killed to manufacture successful cleanup. The fixture is not a general privileged helper.

## Remaining boundaries

The current supervisor executable has not been matched to the reference source. No code here is attached to that supervisor. The Android request/grant and SCM_RIGHTS client path is absent, and the C++ receiver has not been integrated with real LMKD event-loop/watchdog lease gates. Quiet registration success does not prove event delivery under pressure or foreground protection. The original r7/r8 failures remain independent blockers.
