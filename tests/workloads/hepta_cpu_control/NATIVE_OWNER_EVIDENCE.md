# Original-owner evidence protocol v1

The reviewed Root entry is the single serializer. It emits a record only after
the named original API or actual process/CPU observation returns. Host writers,
the workload and Recovery must not independently print interleaved envelopes.
The code remains the authority for exact fields and numeric bounds; see
`native_owner_evidence.py`, `native_owner_copyout.py`, and the independent
continuity modules described below. Extra envelope or
payload fields fail admission.

## Plan and envelope

Root reads this finite acceptance plan from `/test/hepta-g2-run.json`:

```json
{"schema_version":1,"scenario":"steady-state-v1","nonce":"64-lowercase-hex-host-nonce"}
```

The file is root-owned mode 0400. Root installation configuration, signer keys,
leases, Current receipts, registered identities and FinalUse grants are never
accepted from this plan. The Host configuration comes through the actual
original Supervisor/Root activation transaction.

Every output line has exactly this envelope:

```text
HEPTA_G2_EVIDENCE_V1 {"schema_version":1,"scenario":"steady-state-v1","nonce":"...","event":"roles","sequence":1,"payload":{...}}
```

Sequence numbers start at one and increase by one. The nonce and scenario must
match the current host plan on every line. Duplicate JSON keys, non-finite
numbers, boolean substitutes for integers, unknown event names, duplicate
records, unexpected suffix records and old G1c/G1d output all fail.

Kernel output independently requires four exact G2 image commits for the actual
ELF byte length and entry point, followed by one four-role activation. All four
commits and activation must precede the first userspace envelope. The kernel
continues to report `hepta_durability=false`; only the actual original owner
events can establish their own finite durability scope.

## Common prefix

| Event | Actual observations |
| --- | --- |
| `roles` | Bootstrap version 3/200 bytes, native boot ID, distinct Manager/Recovery namespaces, Linux boot UUID and all four actual process identities. |
| `state` | `/dev/vda` mounted as ext2 at `/state`, actual mount/store/material device IDs and distinct original store/material inode IDs. |
| `boundary` | Workload `kill(pid, 0/9)` returns EPERM for Root, Manager and Recovery; Host-store and Root-material access returns EACCES; workload device open is EACCES; Root manage/history return native PermissionDenied. |
| `owner_ready` | Actual original Manager identity, Supervisor spawn generation, issuer-key/proof digests, complete original Current receipt, physical material digest, complete original Device/Notes frontier DTOs and writer-lock device/inode. |

`roles.processes` has the keys `root`, `manager`, `workload`, `recovery`. Each
contains `role`, `pid`, `ppid`, `start_ticks`, four `uids`, four `gids`, `groups`,
five `caps` (`inheritable`, `permitted`, `effective`, `bounding`, `ambient`),
`nnp` and `sid`. Root is PID 1 and the actual parent of all three children.
Manager/Recovery are UID/GID 60001, workload is 60002, and all non-Root roles
have empty groups, zero capability sets and NNP 1. Workload's actual SID equals
its PID. These values come from actual process state, not argv or role labels.

## Original values retained verbatim

`prepared.request_json` is the original canonical
`Hos2InstallBudgetV1::to_json()` string. Its unchanged bytes bind K to native D,
the actual namespace, process-image manage slot/generation, revision CAS,
period and cap. `payload_sha256` hashes those exact UTF-8 bytes. D's sequence
remains the original 16-digit lowercase hexadecimal u64 string.

`native_result.terminal_json`, `source_terminal.terminal_json` and the recovered
terminal are identical original canonical `Hos2TerminalReceipt` bytes. The
receipt contains the exact original request and its actual `Applied` or
`NotApplied` observation. `Reserved`, `NotSeen`, `Retired` or `HistoryLost` is
never converted into an invented terminal. A public apply/reject string cannot
substitute for that receipt.

`current` is the complete actual `CognitiveCheckpointReceipt` DTO, with its
original `token` and `head`. The oracle requires `phase: "current"`, no pending
proposal, the same agent, exact actual publisher UID/PID/boot/start ticks and
original writer binding. `Sha256Digest` serializes as a transparent 64-character
lowercase hexadecimal string. The opaque head token is not reconstructed or
treated as a grant by the runner. Source/authority authentication remains the
original runtime's work.

`local_event_id` is the original terminal event ID represented as its canonical
string. The same ID and terminal survive successor recovery; the harness does
not append a replacement event. `material_sha256` is the actual independently
retained physical recovery image, corresponding to that original Current.

`owner_ready` and `source_terminal` both contain `device_frontier` and
`notes_frontier`, each copied from that actual original consumer's `frontier()`:

```json
{"authority_epoch":7,"revocation_revision":1,"state_sha256":[0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31]}
```

The array above illustrates the wire shape only; it is not evidence. The DTO
has no sequence field. A claim changes the actual Device state digest while
the authority epoch and revocation revision may stay fixed. In these finite
scenarios the original revocation heads do not change, the Notes frontier is
untouched, and each new Device dispatch must advance its claimed state. The
Recovery owner's first two frontiers must exactly equal the Manager's final
`source_terminal` frontiers in the after-terminal case, or the independently
captured `copyout_boundary` frontiers in the before-terminal case, before any
new effect. Reconciliation cannot
consume another nonce. Comparing only epochs/revisions would miss a rollback
of the claimed nonce set and is insufficient.

## Steady-state sequence

After the common prefix, repeat the following five events for `lower` (25 ms),
`pause` (0 ns) and `resume` (50 ms), always in the original 100 ms period:

1. `prepared`: actual K, original canonical request and its digest.
2. `native_result`: original terminal plus actual before/after CPU usage.
3. `source_terminal`: original durable event, committed state, identical
   terminal, newly acknowledged original Current/material and both actual
   consumer frontier DTOs.
4. `history_ack`: the result of original
   `ProductionDurableWriter::retire_hos2_through`, with exact original D,
   source owner/generation, retired frontier, next sequence and original Current
   token. No independent fixture constructs the borrowed retirement permit.
5. `usage_window`: two real CPU/heartbeat observations at least two periods
   apart. Zero cap must keep both CPU consumption and workload heartbeat fixed;
   nonzero cap must advance both. The same revision/cap holds throughout.

Finish with `complete`, containing actual Root/final-owner PIDs, operation count
and final original Current token. There is no producer-supplied `passed` field.

Usage copies all actual `AgentdHos2Usage` fields and adds the actual workload
`heartbeat`. The oracle independently checks original cumulative/window
accounting, monotonic sample/event sequences, no dropped events, correct boot
and observer namespace, revision CAS and the actual effect's effective time.

## Manager exit after durable terminal

This scenario does not claim a crash before the source terminal. It prepares
`pending-retirement` with a 25 ms cap, records its actual native result and
original durable terminal/Current, and deliberately has not retired D yet.
Then Root emits:

1. `manager_retired`: actual held-pidfd `POLLIN`, observed signal-9 exit status,
   exact old start ticks, surviving Root identity and retained old
   Current/material. Sending a signal is not evidence that it caused an exit.
2. `watchdog`: two actual unedited `cpu.stat` strings plus actual Recovery usage.
   The original watchdog waits five seconds, restores the same CPU to 50 ms,
   records its own immutable revision/effective-time/accounting receipt and
   consumes the same one-effect recovery allowance. Its receipt must stay
   unchanged across both reads. No grace or watchdog deadline is extended.
3. `local_lease_retired`: the original old lease identity/generation, actual
   expiry and observed time. This case uses actual expiry. Process death alone
   cannot retire the original local lease.
4. `material_adopted`: the complete unchanged old Current, actual canonical
   successor Current and exact retained material digest. The immediate
   successor head increments publisher epoch/counter and retains the old
   `last_current`; it is a real original Root adoption, not a local SQLite hash.
5. `owner_ready`: the actual Recovery process after original Supervisor,
   RootSession, independent material installation/ready confirmation and
   original writer open. Its real spawn generation is greater than the prior
   one; no fixed `1 -> 3` assumption is made. Local lease generation is exactly
   next, original issuer key/agent/writer-lock identity are retained, and the
   original consumer frontiers exactly retain the last Manager observation.
   Opening the new lease may produce
   a later Current than the immediate material-adoption receipt.
6. `reconciled`: query the original Manager D through Recovery's retained
   original history. K, request bytes and saved terminal stay identical even
   though the current CPU cap/revision now reflect the later watchdog effect.
   Query must not redispatch the old effect.
7. `source_terminal` and `history_ack` for the recovered original K/D.

Finally `used-recovery-allowance` is a newly authorized original Recovery
operation, with its own D, requesting 50 ms at the current revision. It must
produce actual native `NotApplied { status: 2 }`, remain a durable rejected
original terminal and retire normally without an additional CPU effect.
Record its `prepared`, `native_result`, `source_terminal`, `history_ack` and
`usage_window`, then `complete`.

## Lost copyout with the original writer still live

`lost-copyout-live-v1` prepares exactly one original operation named
`lost-copyout-live`, requesting 25 ms in the unchanged 100 ms period. After the
common prefix its sequence is:

1. `prepared` with the exact original first K/D and canonical payload.
2. `copyout_indeterminate` with `operation`, `pid`, `occurrence_key`, the full
   original `ProductionDispatchReceipt` as `receipt`, actual `before` and
   `after` usage, and `copyout` descriptor observation.
3. `copyout_reconciled` with `operation`, `pid`, `occurrence_key`,
   `request_json`, the original `ProductionOutcomeReceipt` as `receipt`,
   `terminal_json`, actual `usage`, original `before_state`,
   `before_payload_json`, `reconciled_count` and `copyout`.
4. Original `source_terminal`, `history_ack`, `usage_window`, then `complete`
   with operation count one.

The dispatch receipt must preserve state and target disposition Indeterminate,
no target receipt, the original nonempty error reason and event ID, and
`external_effect: false`. Its complete original dispatch request retains the
original namespace, lease, topic, K/idempotency key, payload bytes and digest,
subject, destination, policy generation, exact native slot scope digest,
semantic and operation digests and the original absent predecessor. The
provider error string is a diagnostic. Actual ioctl return/errno and complete
frame identity establish the selected response loss.

Every `copyout` observation has exactly `install_ioctl_count`,
`selected_ioctl_count`, `efault_count`, `armed`, and `last`. A non-null `last`
has exactly `install_ioctl_count`, `selected_ioctl_count`, `efault_count`,
`request_sha256` as the original 32-byte array, `request_bytes`,
`response_capacity`, `syscall_return` and `errno`. The Manager must retain
counts 1/1/1, unarmed, and the same exact diagnostic: full 96-byte Install frame,
original response capacity 128, actual return -1 and EFAULT 14. The independent
wire checker hashes comparison bytes only; it never submits them. Boot and
CapSpace identity are separately tied to the actual Manager process and the
immutable original request, because the Install frame itself omits those IDs.

The original observer must recover the one earlier Applied revision. Before
and after usage bracket its effective time and retain the accounting window.
Reconciliation cannot increment Install count or change the saved diagnostic.
Its complete original outcome and terminal event ID must match
`source_terminal`, and its original Current must precede history retirement.

## Manager exit after effect and before source terminal

`manager-exit-before-terminal-v1` prepares exactly one operation named
`lost-before-terminal`, also requesting 25 ms. Its ordered suffix is:

1. `prepared`.
2. `copyout_boundary` containing `operation`, `pid`, `occurrence_key`,
   `request_json`, `payload_sha256`, actual `before` usage, the actual
   `diagnostic` above, `observed_boottime_ns`, `pending_until_boottime_ns`,
   complete independent `current`, physical `material_sha256`, and both full
   `device_frontier` and `notes_frontier` DTOs.
3. Original `manager_retired`, additionally containing actual
   `kill_boottime_ns` sampled after the successful held-pidfd SIGKILL syscall.
4. Original `watchdog`, `local_lease_retired`, `material_adopted`, and Recovery
   `owner_ready`.
5. `copyout_recovery_startup`: actual `pid`, `occurrence_key`, `capture_point`
   equal to `original_recovery_before_monitor`, `captured`, and `copyout`.
   `captured` is exactly one original row with `occurrence_key`, `topic`,
   canonical `payload_json` and `state: "indeterminate"`.
6. `copyout_reconciled` with the same fields as the live case.
7. Original `source_terminal`, `history_ack`, `usage_window`, and `complete`
   with operation count one.

The callback's positive BOOTTIME window is at most two seconds. The actual
kill completion must satisfy `observed <= kill < pending_until`; the original
pidfd readiness and signal-9 exit observation must name the same old lifetime.
Root retains the actual Current already containing the prepared Unknown, the
verified physical material, and the consumed Device/untouched Notes frontiers.
The original Supervisor and Root perform actual local-lease expiry, reaping,
canonical Current adoption and recovery. The early retained-row observation
comes from the protected original writer factory before target/monitor startup.
It cannot be replaced by a later live database query or a producer label.

The new Recovery descriptor must have counts 0/0/0, unarmed and null `last`
both before and after reconciliation. It observes old Manager D without an
Install. The recovered old Applied receipt retains the earlier revision,
stable CPU and effective time. The independent five-second watchdog has its
own later revision and immutable receipt; its restored current cap is never
used as old D's result. Both original consumer frontiers survive unchanged
through observer-only recovery.

The background monitor remains enabled in both cases. The serialized single-K
transition permits exactly `(before_state, reconciled_count)` of
`(indeterminate, 1)` or `(committed, 0)`. If it already retained the terminal
before Recovery `owner_ready`, `source_terminal` may name that same exact
Current and original event ID. The oracle does not demand another terminal
append or interpret a later Current as the earlier Unknown. A first-time
reconciliation must reach a later original Current; a changed or regressed
publisher, writer binding, event ID or retained frontier is rejected.

## Remaining acceptance work

These are four finite, independently named gates. Adding this schema or passing
its host parser tests conveys no native qualification. Only the reviewed
original Rust entry's actual source-bound guest transcript can set the named
lost-copyout or before-terminal-crash result flag. The two earlier scenarios
retain their original checks and do not inherit either new scope.

Each of these four results still leaves full G2, unbounded CPU control, grant renewal,
repeated recovery, cross-boot Unknown preservation, power loss and production
readiness false. Multiple fresh Process generations and an actual same-boot
control interval beyond the initial 300-second Manager grant require separate
original producer events and strict gates. The sum of multiple finite boots'
wall times is not that evidence. Cross-boot reuse must preserve the original
store and unknown outcomes without redispatch. No old receipt, reset store,
extended initial grant or substitute executable can close those paths.

## Original multi-generation continuity

The additional `successor-renewal-v1` and
`history-only-after-both-owner-exit-v1` gates are specified in
[NATIVE_OWNER_CONTINUITY.md](NATIVE_OWNER_CONTINUITY.md). They preserve these
earlier scenario checks and require independent read-only validation of the
actual retained Root launch files. Only the renewal campaign has a 600-second
outer execution deadline and 1024-event bound; individual authority lifetimes,
8-MiB/16-MiB ELF limits and earlier 128-event/120-second bounds stay unchanged.
Source reviews, real owner/kernel builds and actual guest execution remain
separate mandatory gates. Host tests do not qualify native continuity.
