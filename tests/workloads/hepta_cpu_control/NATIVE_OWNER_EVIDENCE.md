# Original-owner evidence protocol v1

The reviewed Root entry is the single serializer. It emits a record only after
the named original API or actual process/CPU observation returns. Host writers,
the workload and Recovery must not independently print interleaved envelopes.
The code remains the authority for exact fields and numeric bounds; see
`native_owner_evidence.py`. Extra envelope or payload fields fail admission.

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
`source_terminal` frontiers, before any new effect. Reconciliation cannot
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

## Remaining acceptance work

The two schemas above are finite, independently named subcases. A successful
record always leaves full G2, unbounded CPU control, grant renewal, repeated
recovery, after-effect/before-terminal crash, cross-boot recovery and power-loss
flags false. Implement those paths in the original owners, review the new
source pair and add actual cases; do not widen this schema to infer them.
