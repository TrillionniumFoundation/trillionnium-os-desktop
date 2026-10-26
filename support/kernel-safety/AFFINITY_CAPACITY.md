# Cold transfer capacity prerequisite (W3B1)

This internal prerequisite prepares the existing scheduler containers for a
single future affinity transfer. It does not enable forced migration or public
`cpu.weight`. W3A's blocked-wake route remains the production behavior until the
request/ownership transaction is connected and tested in an ordinary SMP guest.

Every physical destination container records reserved incoming slots. Ordinary
spawn/wake, current requeue and throttle parking preserve
`len + reserved <= capacity`; ordinary legacy growth still exists and accounts
for reservations. A transfer consumes its reservation immediately before its
actual insertion. Cancellation refunds the same scheduler/CPU reservation once.
The move-only ticket must be cancelled outside all runqueue locks.

Each ticket additionally records the exact destination rq address at installation;
consumption checks it before refunding anything. A same-CPU queue from another
scheduler instance is rejected. The borrowed scheduler owns a private stable Box
of queues and currently exposes no whole-rq replacement/hotplug operation. This
is concrete container identity, not a fabricated membership generation; future
layout replacement needs an incarnation protocol. Snapshot locks use explicit
local guards, with the rq guard declared after the IRQ guard, so cleanup order
does not depend on a tail temporary's edition-specific lifetime.

FAIR reserves the existing legacy-root task heap. RT reserves the same priority
in **both physical arrays**, since active/inactive can flip before commit. Every
ticket also reserves a throttle slot: eligibility can expire between selection
and publication. The caller must pin or revalidate policy/priority before using
the ticket; this prerequisite does not invent a membership generation or route
an unadmitted non-root Task to root. A closed prepared tree is explicitly refused.

Preparation snapshots queue needs under the destination lock, then allocates
empty replacement buffers with `try_reserve_exact` in sleepable context. Recheck
all actual needs under the same lock before installing anything. A stale snapshot
is retried cold, at most eight times; allocation/overflow or repeated growth
fails without publishing an affinity mask or detaching a Task. Install only
moves the original heap/deque/vector's elements into enough prepared storage;
it creates no second scheduler or runnable staging queue. Retired empty buffers
are returned for destruction after unlock and IRQ restoration.

The fixed nightly's `Vec::append`, `VecDeque::append` and `BinaryHeap::from(Vec)`
preserve sufficient prepared storage without growth. Installing or rebuilding
an existing queue is O(n) control-path work under the rq lock. This is not a
claim of constant IRQ latency; indexed queue redesign would be needed for that.

FAIR items retain the weight actually debited when they entered the queue. A
pending nice change may be consumed before a later arbitrary removal; refunding
the then-current attribute would leave phantom queued weight. Selection now
refunds the stored original weight while still consuming the pending attribute.
This is needed for future remove/restore tokens and does not reset virtual debt.

Serialized live policy administration, real affinity request generations,
current-task completed-switch publication, and synchronous success or rollback
remain separate. A storage ticket alone authorizes none of those operations.

Controlled kernel tests use actual Task objects and these production
queues: capacity retention during ordinary insertion/RT array flips, cold stale
preparation refusal, FIFO/storage/weight preservation, one-time cancellation,
prepared-root rejection and capacity-overflow failure. They are internal
container evidence, not physical migration or hardware-OOM qualification.
The final W3B stage must additionally pass the same current/queued/throttled
ordinary SMP scenarios which fail on the frozen W3A kernel.

## Actual removal and rollback prerequisite

Actual queue entries are removed by Arc identity. FAIR keeps its cached key and
accounted weight, reserving the vacated physical slot; restore consumes that slot
and reinstates the original item without reinterpreting a nice update. RT scans
the original two arrays and actual priority buckets rather than guessing from a
subsequently edited policy. Queue entries carry a checked monotonic arrival
sequence, so rollback restores FIFO order among remaining and newly appended
entries in the original physical bucket. A throttle token reserves only its
vacated vector slot and refunds no FAIR/RT queued weight.

The combined token binds the original CPU and exact rq address. It cannot remove
logical incoming, physical outgoing or a Wait/Exit retry as an ordinary queued
Task. Every live token must be restored or committed under its origin lock; the
live request transaction still needs to wrap that obligation in cancellation
RAII before enabling an entry point. Destination publication must disarm source
rollback before making the Task runnable, then refund only the old slot.

Cross-CPU FAIR placement translates positive relative debt from the source floor
to the destination floor. It neither copies a different CPU's historical floor
nor resets earned debt to zero. Rebase only an exclusively held, unpublished
Task; rollback restores its original value. These controlled helpers do not
change a Task's original CPUmax owner or create a fresh quota window.
