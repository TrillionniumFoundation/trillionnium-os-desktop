# Supervisor producer 04 — source freeze, matching build pending

This is a new source revision derived from the actual producer03 host build. Producer03 passed 23 relay Rust tests, 118 supervisor Rust tests, seven ordinary IPC controls, the leader/worker/fork context control, and the compiled entry ABI query. Its original source and receipt remain unchanged. Neither revision has executed the Android constructor or installed supervisor hook.

## Changes

The generated LMKD service uses explicit literal lines so the ten service options retain their indentation. Its native defaults, socket, UID/GID contract, and relay-required setting are unchanged. This source fix is not evidence that an Android parser failure was observed.

A completely retired generation retains its original runtime failure separately from a cleanup error. `Owner` snapshots the cause only after a verified worker join and retirement proof; `DevelopmentCell` carries it through the existing cleanup chain. The foreground runner returns that cause even if the outer child exited zero. The daemon reports stopped with `ok=false` for a failed retired run. Successful Stop still reports the Stop action's success. Repeated stop/shutdown, a failed later start, a later normal child exit, or a successful retry of a subsequent cleanup error cannot erase the original cause. A newly authenticated relay generation's actual COMMIT/DONE plus native grant ACTIVE observation clears it; ACTIVE claims no pressure event. Merely creating a new owner, including opting back to legacy None, cannot clear the cause.

History remains in the existing daemon instance. This revision does not claim a durable post-retirement failure-history database. The separate persistent generation marker still blocks restart/recovery whenever retirement was incomplete or daemon ownership was lost; it is unlinked only after the exact resource chain proves retirement. Automatic recovery of abandoned claims remains closed.

The final constructor capability handoff now explicitly requires a direct `/init second_stage` Command, with no wrapper or extra argument. Its last pre-exec callback rechecks root UID/GID, re-arms SIGKILL parent-death, and polls the inherited exact owner pidfd before clearing CLOEXEC on the one constructor channel. Ordinary helper execs still receive none of the four inherited capabilities. The exact CPU-command helper implementation will be read before runtime qualification; an unexpected wrapper is rejected by this source gate.

Unused private helpers from producer03 warnings were removed; a test-only resource accessor is marked test-only and the public entry ABI has documentation. Existing CPU-placement example warnings are not suppressed.

## Validation boundary

The three added tests have not been executed in this local environment, which has no Rust compiler. Required matching-build counts are 23 relay and 121 supervisor tests, seven ordinary IPC controls, the real context-transfer control, and the compiled entry ABI query. The status test uses a real owned child and a real temporary-directory cleanup error; only its initial failure cause is injected as an explicit status-propagation seam. The RC and Command tests are pure contract controls, not Android execution.

No Android service, init constructor, mount, namespace, cgroup, network, pressure experiment, or installed file was changed by preparing this snapshot. Explicit cell budgets remain mandatory; no canary budget becomes a production default. The existing 70/700 ms pressure thresholds and one-second expiry remain unchanged.

## Reconstruction and review

`source/` contains the same twelve submission paths as producer03 for review context. Exactly seven listed `overlay_paths` in validation.json are to be uploaded. The five unchanged paths must not be rewritten. `submitted03-to04.diff` compares the unformatted immutable submitted snapshots; the prior actual build formatted its six new modules. `actual_remote_preimages` pins the corresponding actual producer03 bytes so a future stage rejects a mixed or modified remote tree before writing anything. The next build must preserve a create-only snapshot of all actual producer03 inputs and its receipt before applying these seven overlays, then record the post-format inputs and their unchanged build-after hashes.
