# Producer14: repair two test-fixture assumptions

The actual producer13 compile succeeded, but its ordinary relay run passed 35
of 37 tests and exited 101. The supervisor library, IPC and ABI commands were
not executed after that failure. The original receipt and full 4,483-byte relay
stdout are retained unchanged here. This package does not reclassify that run.

Both edits are inside `#[cfg(test)] mod tests`. Production code before those
modules, the pressure-audit codec and lifecycle_relay.rs remain byte-identical
to the actual producer13 input. No authority, deadline, pressure threshold,
nonce/scope validation, terminal drain, exact child-exit or poison rule changes.

The faulted terminal fixture previously set `faulted=true` while retaining
`incomplete=false`. The unchanged codec correctly rejects that combination;
`stop_reason=0` is legal and was not the defect. The new test first requires that
old invalid encoding to remain rejected, then sets `incomplete=true` and sends
the same real Rust codec/status through the original owned-child fixture.

The dead-proc fixture assumed ENOENT while Pocket4 returned ESRCH. It now issues
raw SYS_openat with the same held procdir, relative name and O_RDONLY|O_CLOEXEC,
captures that errno before any other operation, requires ENOENT or ESRCH, and
requires the production contextual error to preserve that exact kernel value.
The child must already be exactly reaped and its held pidfd dead. Unexpected
successful raw opens are closed before failing the test.

The expected ordinary suite remains 37 relay and 122 supervisor tests, two
original targeted public retirement tests, seven IPC controls, worker-context
and entry ABI3. No Rust tests or Android runtime were executed while freezing
this source. Matching compile and ordinary execution need a fresh root and
separate actual receipts; no NORMAL13 runtime was prepared or dispatched.
