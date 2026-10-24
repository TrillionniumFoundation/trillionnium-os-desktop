# G2 native successor protocol

This separate, default-off `g2-trusted-daemon` path belongs only to the exact
frozen initial Root Process and its original image. It is not a public HOS2
operation, an ambient-root grant, or a way to load a caller-selected executable.
Initial HOS2BOOT v3 (200 bytes) and the G1-d three-role profile remain unchanged.
The complete original writer/FinalUse and actual guest qualification are still
required before persistent control or fault recovery is claimed.

## Root launcher transport

The experimental ioctl is `_IOWR('H', 3, 128)` (`0xC0804803`). Its argument is one
128-byte in/out buffer, copied in once before interpretation. Every integer is
unsigned little endian. Unsupported profiles return ENOTTY. A foreign Process,
an inherited/transferred descriptor, an ended image or a live non-Root role
cannot use this endpoint. Linux UID 0 alone has no authority.

| Request offset | Width | Meaning |
| --- | --- | --- |
| 0 | 8 | ASCII `HOS2LAUN` |
| 8 | 8 | Protocol version 1 |
| 16 | 8 | Command: 0 Query, 1 Advance, 2 ReadRetirement, 3 AckSaved |
| 24 | 8 | Expected launch generation; Query requires 0; ReadRetirement/AckSaved require the exact current nonzero generation |
| 32 | 96 | All zero |

| Reply offset | Width | Meaning |
| --- | --- | --- |
| 0 | 8 | ASCII `HOS2LRES` |
| 8 | 8 | Protocol version 1 |
| 16 | 8 | Mode: 1 Manager/Recovery pair, 2 history-only process |
| 24 | 8 | Current kernel launch generation; initial pair is 0 |
| 32 | 8 | Actual original Root PID |
| 40 | 8 | Actual original workload PID |
| 48 | 8 | Actual Manager PID, or 0 in history-only mode |
| 56 | 8 | Actual Recovery PID, or 0 in history-only mode |
| 64 | 8 | Actual history-only PID, or 0 in pair mode |
| 72 | 8 | Previous generation; 0 for initial Query and first Advance |
| 80 | 16 | Original Manager history CapSpace of this generation |
| 96 | 16 | Original Recovery history CapSpace of this generation |
| 112 | 16 | All zero |

Query reports the current immutable launch receipt without changing any owner.
Advance accepts the current generation, checks that all previous privileged
children have exited and been reaped, and prepares all new resources before
publication. A retry of the immediately preceding successful Advance returns
exactly the saved receipt even after copyout failed; it never starts a duplicate
child. Other stale generation values return ESTALE. Generation overflow is
rejected. The retained receipt describes actual published Process allocations,
not a promise that the children have completed their userspace startup.

When both retained original D namespaces have `retired_through + 1 ==
next_sequence` and their original views still report NotSeen for that next
sequence, Advance prepares a fresh Manager/Recovery pair. Each process has a new
VMAR, image key and CapSpace, and fresh finite delegations on the same original
CPU owner. The original quota, resource revision, consumed CPU, carry debt and
workload identity are preserved. Old grants remain closed and keep their old
expiry. The owner's existing permanent watchdog callback is reused.

Otherwise Advance prepares one history-only process, retaining the exact same
two original namespaces and acknowledgement authorities. No CPU delegation,
effect namespace, sequence allocator or budget reset is created. Replacing a
crashed history-only process again requires its actual exit and reap. No
unretired history can be discarded to make room for a new pair. Historical
retirement remains possible if the original workload has ended: role 5 carries
its original PID as metadata, never resolves that PID anew and has no CPU or
process-control authority. A new Manager/Recovery pair still requires the same
original workload allocation to be alive.

## Immutable policy retirement evidence and Root acknowledgement

ReadRetirement returns one 128-byte `HOS2LWDR` record for the current launch
generation. Before the first Advance it returns ENODATA. The record is captured
from the old `WatchdogState.terminal` moved out under the SAME original CpuMax
lock that publishes the new policy. A timer firing after preparation but before
that cut is therefore included. No receipt is recomputed; no old manager, grant
origin, D namespace or mutable owner reference is retained by this record.

| Offset | Width | Meaning |
| --- | --- | --- |
| 0 | 8 | ASCII `HOS2LWDR` |
| 8 | 8 | Version 1 |
| 16 | 8 | Launch generation that produced this evidence |
| 24 | 8 | Original watchdog status: 0 untriggered, 1 Restored, 2 Ineligible, 3 JobStopped, 4 Expired, 5 ClockUnavailable, 6 Closed, 7 AccountingFault |
| 32 | 8 | Original evaluated time, or 0 when unavailable; the presence flag is authoritative |
| 40 | 16 | Original NativeResourceReceipt stable object ID, if Restored |
| 56 | 8 | Original receipt previous revision, if Restored |
| 64 | 8 | Original receipt revision, if Restored |
| 72 | 8 | Original receipt effective boottime, if Restored |
| 80 | 8 | Original receipt consumed CPU, if Restored |
| 88 | 16 | Previous policy's original Manager history CapSpace |
| 104 | 16 | Previous policy's original Recovery history CapSpace |
| 120 | 8 | Flags: bit 0 = a CPU policy was actually retired; bit 1 = evaluated time was Some; all other bits zero |

A pair launch with an untriggered retired watchdog has status 0 and flags 1. A
history-only launch has status 0 and flags 0: it did NOT retire a CPU policy, and
the previous policy/watchdog remains live. These states must never be conflated.
Some(0) has the time-presence bit; it is distinct from unavailable time. All
resource receipt fields are zero for outcomes other than the original Restored
receipt. The immutable launch receipt returned by Query/Advance is unchanged.

Root must durably save the verified full boot identity, launch generation,
launch receipt and retirement bytes through its original protected storage
before issuing AckSaved for that exact generation. AckSaved returns the same
launch receipt and is idempotent for the current generation. A stale or future
acknowledgement returns ESTALE and changes nothing. Kernel transport success
alone does not prove userspace fsync; native acceptance must demonstrate the
original persistence sequence.

Every subsequent **new** Advance requires this acknowledgement; otherwise it
returns EBUSY before image allocation or owner mutation. A retry of the last
successful Advance still returns its saved launch receipt while unacknowledged.
ReadRetirement retries and copyout failures preserve the complete evidence;
acknowledgement changes only its admission flag. Preparation/commit failure
retains the previous record. Only a successfully published, explicitly admitted
next launch may replace the single saved record. This bounded lifecycle receipt
is not a new delivery or durable-operation ledger.

## Kernel-generated successor bootstrap page

Successor images use HOS2BOOT v4, 240 meaningful bytes in the existing sealed
4096-byte page. Offsets 0..191 preserve the v3 layout; root_pid remains at 192.
All unused bytes remain zero.

| Offset | Width | Field |
| --- | --- | --- |
| 8 | 8 | Version 4 |
| 16 | 8 | Role 1 Manager, 3 Recovery, or 5 history-only |
| 24 | 8 | Meaningful length 240 |
| 32, 40 | 8 each | Observe slot/generation: 1/1 for roles 1/3; 0/0 for role 5 |
| 48, 56 | 8 each | Manage slot/generation: 2/1 for roles 1/3; 0/0 for role 5 |
| 64, 72 | 8 each | Manager history slot/generation: 3/1 |
| 80, 88 | 8 each | Recovery history slot/generation: 4/1 for roles 3/5; 0/0 for role 1 |
| 96 | 16 | Original boot identity |
| 112 | 16 | Retained Manager history CapSpace |
| 128 | 16 | Retained Recovery history CapSpace |
| 144 | 8 | Current actual Manager PID; 0 for role 5 |
| 152 | 8 | Original actual workload PID |
| 160 | 8 | Current actual Recovery PID; 0 for role 5 |
| 168 | 8 | Max cap: 50,000,000 ns for roles 1/3; 0 for role 5 |
| 176 | 8 | Original period: 100,000,000 ns |
| 184 | 8 | Finite management lease: 300,000,000,000 ns for roles 1/3; 0 for role 5 |
| 192 | 8 | Original actual Root PID |
| 200 | 8 | This process's actual PID |
| 208 | 16 | This process image's own fresh CapSpace |
| 224 | 8 | Kernel launch generation, nonzero |
| 232 | 8 | Reserved, zero |

Role 5 deliberately has a fresh local CapSpace distinct from both retained
history CapSpaces. QueryAbi must match its local space; QueryDelivery and
RetireThrough must match the selected retained history. It cannot call
ReadUsage/InstallBudget even by guessing the usual handle values. Only the
original durable writer, with its original protected owner and retirement
permit, may acknowledge terminal history. The bootstrap page itself makes no
claim about SQLite durability.

## Validation boundaries

The CPU owner tests exercise prepare-without-publication, both exact old-origin
fences, failed/stale commit rollback, preserved accounting and immutable D, and
128 replacements with one callback registration. The G2-only owner regression
also forces an actual watchdog effect between preparation and commit and checks
that the original immutable receipt and exact time survive that cut. Process tests must separately
cover non-Root and ended-image refusal, real unreaped-child rejection, sealed
image allocation/claim rollback, both original history frontiers, and receipt
replay without duplicate publication. Native acceptance must use the complete
original Rust entry, actual pidfd exit events and the original Supervisor reaper.
No C qualification probe substitutes for that entry or its writer.
