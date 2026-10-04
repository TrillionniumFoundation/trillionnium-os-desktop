# Managed source and artifact reading

The additive `open_managed_regular_beneath(root, path, *, label,
after_component=None)` returns a `ManagedSourceReader` whose private descriptor
owner remains attached through opening, reading and object delivery. Use it in
a `with` statement. `read(size=-1)` returns bytes, `stat()` returns metadata,
and `close()` retires the owned descriptor. The reader has no public `fileno`,
detach or raw-FD transfer operation. `artifact_evidence.open_managed_file(path)`
uses the same reader and retains the artifact regular-file/single-link check.
The exact signatures, migrated functions, bounds and limits are recorded in
[`shared-managed-reader.v1.json`](../../contracts/shared-managed-reader.v1.json).

Standard shared byte/text/JSON reads and file-existence checks now retain this
owner. The artifact size, digest, JSON and file-reference checks also use it.
Reading calls `os.read` directly, with no `os.fdopen` ownership transfer. The
new managed object is registered before acquisition; the private walker still
owns each directory and leaf. Losing a managed-object return therefore leaves
its descriptor reachable for object cleanup, while losing a data return cannot
detach that descriptor from its reader. Context cleanup and finalization use
the existing detach-before-native-close owner. An integer whose close was
attempted is never retried, including after the actual number is reused for a
different file. No finalizer shuts down, unlocks, unlinks, repairs or reloads
an authority path.

Public reading, metadata, entry and close operations require the creator PID
and the actual creator `Thread` object. Foreign operations are refused before
descriptor access, so another thread cannot close and reuse an integer between
read chunks. Read/stat operations also reject same-thread reentrant operations.
Public context exit follows this same guard, including when a callback presents
a real exception. A busy reader checks up to 1024 frames of the creator thread's
current call chain for an executing read/stat on that reader, and refuses if the
check exceeds that bound. A genuinely unwound operation's retained traceback is
not an executing frame. Its stale busy flag can be cleared for ordinary context
cleanup, while a suspended read cannot have its descriptor closed by reentrant
context exit. This check supplies no peer or application execution authority.
This does not provide a cross-thread reader: ordinary shared/artifact helpers
still construct and consume their reader on whichever thread called the helper.
The destructor performs only original descriptor cleanup, including when the
last reference is collected on a foreign thread or in a fork child. An active
method retains `self`, preventing concurrent last-reference disposal. Exceptional
context exit retires the reader even if an interruption prevented busy-state
cleanup; it cannot authorize a further read. Direct manual calls to private
cleanup or the destructor are not supported reader operations. A prior attempted
close clears the private owner, preserving a reused foreign descriptor on later GC.

`read` accepts an exact integer: `-1` reads to EOF, zero reads no bytes, and a
positive value reads up to that count. Other negatives, booleans and values
above `sys.maxsize` are refused. A short native read continues until the count
or actual EOF; a native exception propagates with ownership retained. Existing
shared whole-file reads retain their existing unbounded byte semantics; this
API does not invent a source-wide limit. Artifact JSON keeps its 8 MiB bound
and artifact hashing its 8 GiB bound, with before/after metadata and actual
byte-count checks. Shared text decoding remains strict UTF-8 with universal
newlines; strict JSON rejects duplicate members and nonfinite values. Supplied
roots, no-follow directory/leaf lookup, and pinned-parent rename behavior keep
their existing meanings. An artifact reader walks from `/`, while a generic
shared root does not itself prove every absolute ancestor.

The original public `open_regular_beneath` and `artifact_evidence.open_file`
still return raw integers for compatibility. Their final raw result and later
caller `fdopen` delivery gaps remain open, as demonstrated by the preserved
raw-return regression in
[`test_shared_source_reader.py`](../../tests/test_shared_source_reader.py).
Other consumers that call those raw APIs are not migrated or qualified by
this package. Python private attributes are not an isolation boundary against
trusted Python code. The managed mechanism closes the tested ordinary-line,
owned-object/result and native-close/reuse cases; it does not claim every C
call, opcode or repeated cleanup interruption is protected.

The actual private-file/FD regressions are
[`test_shared_managed_reader.py`](../../tests/test_shared_managed_reader.py) and
[`test_shared_managed_context.py`](../../tests/test_shared_managed_context.py).
The older artifact parent-swap test changes only the two opener seam names to
the managed opener, preserving its real directory rename, symlink and assertions.
These source I/O checks supply no peer, principal, signature, journal, Servo,
installed, boot, hardware or release authority. Product activation and
`production_ready` remain false.
