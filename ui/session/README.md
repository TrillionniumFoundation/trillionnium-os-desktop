# trill-session and trill-ctl

Session owns host application processes and serves the bounded host IPC socket.
The CLI is a client of that socket. Shell does not own the application process
table or infer task completion from a window.

## Code and lifecycle

[main.rs](src/main.rs) owns spawn, kill requests, wait/reap, Session generation
and finite task retention. [hepta.rs](src/hepta.rs) manages the explicitly
configured read-only observer. [notes_bootstrap.rs](src/notes_bootstrap.rs)
handles the trusted parent's private Notes bootstrap v2, including separate effect and recovery descriptors. [deadline.rs](src/deadline.rs) supplies one monotonic deadline across partial reads and response writes.

The socket is under an absolute private XDG_RUNTIME_DIR. Both peers check
kernel-reported UID; same-UID hostile processes remain outside this prototype's
trust boundary. A Session restart creates a new generation. Detached tasks
must not be represented as reattached or successfully cancelled.

An accepted connection has one 500 ms I/O allowance; partial progress does not renew it. The owner loop reaps exited children around every connection. This bounds transport occupancy, not Linux scheduling or process-creation time. A lost response after dispatch leaves the real action outcome intact and requires a fresh snapshot. The startup advisory lock protects competing Session starters; it is not a credential.

Standalone Session does not install a production Hepta effect owner. The
private Notes bootstrap is separate from public Snapshot/Launch/Cancel.

## Build, run and verify

Use [workspace setup](../README.md), then run trill-session and trill-shell
in the same owned graphical session. The CLI syntax is:

```text
trill-ctl snapshot
trill-ctl launch <personal|research|build> <notes|calculator|terminal>
trill-ctl cancel <task-id> <session-generation>
```

```sh
RUSTUP_TOOLCHAIN=1.96.0 cargo test --manifest-path ui/Cargo.toml -p trill-session --locked
```

[tests](tests/) exercise real process/socket lifecycle within their declared
scope. Use [HEPTA_OBSERVER](../../support/ui/HEPTA_OBSERVER.md),
[NOTES_ORGAN](../../support/ui/NOTES_ORGAN.md) and
[BOUNDARIES](../../support/ui/BOUNDARIES.md) when changing runtime integration.
