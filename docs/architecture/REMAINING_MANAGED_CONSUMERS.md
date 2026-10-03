# Remaining source and evidence consumer ownership

The versioned [consumer inventory](../../contracts/remaining-managed-consumers.v1.json)
covers seven functions in five existing tools. Repository JSON, platform registry
inputs, S12 evidence bytes, native input checkpoints, namespace hashes, namespace
packets and the namespace contract now consume the existing
`ManagedSourceReader`. Their parameters and result values stay unchanged.

The additive `ManagedSourceReader.read_some(self, size: int) -> bytes` performs
one native read. It accepts only exact integers from zero through `sys.maxsize`,
rejecting booleans and other types with `TypeError`, negatives with `ValueError`
and overflow with `OverflowError`. It requires the same creator process/thread,
an open owner and no active read/stat operation. Native errors and interruptions
propagate while the owner retains cleanup. Read, read_some, stat, close and
context-exit callbacks refuse reentry on this owner. The existing `read` signature
and fill-until-count/EOF behavior remain unchanged.

Namespace hash/packet and native checkpoint consumers retain their original
single-syscall short-read behavior through `read_some`. In particular the hash
consumer checks its original 60-second deadline after each kernel read, including
a one-byte short read. The former buffered consumers keep `read`. The rejected
first migration used buffered fill reads for the hash; an actual 4096-byte file
with one-byte reads and a deterministic advancing clock demonstrated 4097 calls
before refusal instead of the original 60. That failed candidate remains
unpublished; its observation is not a measurement of elapsed wall time.

Each acquisition retains a cleanup owner through factory return and context
entry. Reads and metadata checks operate on that owner; they never hand a raw FD
to `os.fdopen` or publish one to their callers. Namespace pathname rechecks use a
second retained reader, keeping both independently acquired owners available for
cleanup. The original regular-file, no-symlink, single-link where required,
owner/mode, size, complete-read, metadata/name recheck and time limits remain in
their original consumers. This migration does not add a link restriction to the
repository JSON reader or a new trust root to release evidence.

The [actual Linux FD corpus](../../tests/test_remaining_managed_consumers.py)
checks all seven positive results and interrupts actual factory-result and
read-result delivery, plus the six existing public metadata-read paths.
Repository JSON originally has no such metadata read. The corpus also lets a native `os.read`
complete before raising. Every case compares actual `/proc/self/fd` device/inode
censuses after garbage collection. It never retains the returned owner or a
traceback in its fault injector. Probe cleanup of a predecessor's observed leaked
FD does not turn its failing assertion into a passing result.

`open_regular_beneath` and `artifact_evidence.open_file` keep their historical raw
integer ABI. Their undelivered raw-result window remains outside this package's
guarantee; callers outside the enumerated functions need their own review. All
native-call/opcode and repeated cleanup interruption windows remain outside the
ordinary Python ownership scope. These changes grant source I/O cleanup only,
and provide no installed, Servo, hardware, signing or production qualification.
