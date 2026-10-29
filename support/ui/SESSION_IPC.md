# Session IPC: development and technical contract

Session is the Linux host's single process-state owner. Shell/CLI request
Snapshot, Launch and Cancel through a private Unix socket. This is a host
prototype, not an Asterinas compositor or HOS2 authority service. See
[RUN.md](RUN.md) for dependencies and separate graphical acceptance gates.

## Ownership and source map

| Source | Responsibility |
| --- | --- |
| `ui/session/src/main.rs` | Runtime directory and lock, task identity, launch/cancel/reap, trusted startup |
| `ui/session/src/ipc.rs` | Bounded nonblocking connections and whole-frame deadlines |
| `ui/core/src/lib.rs` | Public request/response types, frame and task bounds |
| `ui/core/src/host_peer.rs` | Same-effective-UID peer checks |
| `ui/session/src/hepta.rs` | Original-runtime observation; not a writer |
| `ui/session/src/notes_bootstrap.rs` | Private inherited Notes descriptor transfer |
| `ui/session/src/desktop_bootstrap.rs` | Explicit inherited X11 connection and private original-owner descriptor handoff |
| `ui/session/src/bin/trill-ctl.rs` | Public host client |

The runtime directory and lock enforce ownership, private modes and one live
Session. Generation checks bind cancel requests to the Session and child
incarnation. Same-UID checks apply before parsing, and clients check the server
UID before using responses. They provide a host transport boundary, not a
distinction between mutually distrustful applications under one user account.
Public IPC cannot export a Notes/display descriptor or issue an effect grant.
The private X11 startup runs its native work on separate workers; its full
scope, trusted-server inputs and bounds are documented in [DESKTOP_X11.md](DESKTOP_X11.md).

## Fair main-loop service

Each tick first calls `Session::refresh()` to observe and reap children. It then
advances every accepted connection once and accepts at most eight new peers.
The outer loop sleeps 10 ms. There are at most 32 accepted connections; each
does at most one 8192-byte read and one 8192-byte write per tick.

The 500 ms input deadline starts when a connection is accepted and covers the
entire newline-terminated frame. Receiving more bytes never renews it. A reply
has its own 500 ms total deadline. A frame is bounded by the shared 64 KiB
maximum; oversized or malformed requests produce a bounded error or a closed
connection. Only one request is handled per connection. When capacity is full,
new clients remain subject to the kernel listen backlog until a slot becomes
available; this is not an unlimited admission or hard real-time guarantee.

This prevents a slow incomplete frame from monopolizing the state owner. The
loop is still synchronous for an already parsed command, and it does not
provide CPU scheduling guarantees against an unbounded number of local
processes. Changes to `Session::handle` and `refresh` must preserve bounded work
and avoid network or filesystem waits in these public request paths.

## Notes startup

Ordinary Notes launches receive a private application store selected by
Session. The default is `$XDG_STATE_HOME/trillionnium-ui/notes/<target>`, or
`$HOME/.local/state/trillionnium-ui/notes/<target>`. A new launch creates a new
document; there is no automatic Session task adoption or document picker.

Trusted parents can select `--notes-bootstrap-stdin` for the legacy single
effect descriptor, or `--notes-bootstrap-v2-stdin` for effect plus independent
recovery descriptors. V2 alone permits `--notes-new-document /absolute/path`
or `--notes-document /absolute/path` for creation or reopen. These options
require an inherited private bootstrap datagram socket on stdin; invoking them
in a normal terminal does not attach an owner. Paths never come from public
IPC or an effect payload. See [NOTES_PERSISTENCE.md](NOTES_PERSISTENCE.md) for
identity, ACK, storage and recovery semantics.

## Development and verification

From the repository root, after building the actual binaries:

```sh
cargo +1.88.0 test --manifest-path ui/Cargo.toml -p trill-session --locked -j 2
python3 tests/ui/test-session-fairness.py ui/target/debug/trill-session
```

Use the corresponding `debug` directory when `CARGO_TARGET_DIR` is set.
The Rust regression exercises an actual short-lived child while a peer drips
bytes, verifies valid snapshots and reaping, and asserts that the input deadline
does not move. The Python regression launches an isolated actual Session,
checks a valid client during a drip and after 32 idle peers, and closes only its
own process. `tests/ui/check-host.sh` includes that binary-level regression.

These tests do not establish kernel scheduling, graphical presentation or
original Hepta authority. The complete current-source CI gate must also cover
normal malformed requests, same-UID checks, singleton ownership, generation
fencing and cancellation; see [RUN.md](RUN.md).

## Explicit original Objective inbox

The generation-fenced `objective_list`, `objective_inspect`, `objective_submit`
and `objective_query` requests select preconfigured entries only. The optional
`--objective-config-fd` startup descriptor and dedicated bounded worker are
documented in [OBJECTIVE_INBOX.md](OBJECTIVE_INBOX.md). No raw envelope, endpoint
editor, signer, arbitrary command or retry route is exposed through host IPC.
