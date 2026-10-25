# Linux display input and capture: development and technical contract

This backend extends the private Notes destination with real Linux X11 input
and screenshots. The original Hepta owner retains its durable operation writer,
FinalUse verifier and issuer connection. Desktop provides a destination and
observation capability. It creates no signer, grant, operation ledger, shell,
network command channel, model turn, or production authority.

An `injected` receipt means **the selected X server processed the input
requests**. It does not mean a third-party application saved a document,
completed a business operation, presented pixels, or committed durable data.
Hepta names this operation's semantics `x11_server_injected`; its original
operation terminality and a separately observed application result remain
distinct. The stock `xmessage` exit-code check in the acceptance test is such
independent application evidence.

## Trusted startup and scope

The trusted launcher opens one local X11 Unix connection and passes the
uninitialized connection as an inherited descriptor. Session is started with:

```text
--desktop-bootstrap-stdin
--desktop-x11-fd <connected-X11-stream-fd>
--desktop-x11-server-pid <actual-selected-server-pid>
--desktop-window <selected-top-level-XID>
[--desktop-x11-cookie-fd <regular-file-containing-exactly-16-cookie-bytes>]
```

Stdin must be an unnamed Unix datagram pair. The X11 descriptor must be a
Unix stream whose kernel-reported UID and PID match the current UID and exact
trusted server PID. All inherited descriptors are taken into ownership and
marked close-on-exec before Session can launch a child. The optional private
cookie file supplies MIT-MAGIC-COOKIE-1 authentication; it is read once and
never included in snapshots or protocol requests. There is no `DISPLAY`, TCP,
filesystem endpoint, executable, or arbitrary argument in the input payload.
Only screen zero is supported by this first backend.

An X11 connection is authority over the **entire selected display domain**.
XTEST and the cookie do not isolate an application window or mutually
distrustful same-UID processes. `expected_window` is a strict precondition and
observation correlation field, not a per-window security boundary. A production
launcher must select and authorize the appropriate display domain. The tests
create their own isolated Xvfb, applications and credentials. They never attach
to the user's current desktop. The first development probe used `-ac` only in
its disposable fixture; the current acceptance harness uses a fresh private
MIT cookie and exact server PID/UID checks.

The startup sends one offer and exactly two SCM_RIGHTS descriptors in order:
`[effect: SOCK_STREAM, observe: SOCK_STREAM]`, both unnamed pairs. ACK must bind
schema version 1, profile `trill.desktop.x11.v1` and the exact target, contain no
descriptors, and return `attached`. Failure shuts down both capabilities.
Desktop and Notes bootstrap profiles are mutually exclusive for one Session.
Desktop startup does not launch Notes or another application. Applications are
chosen and started by the trusted host; public Session IPC gains no new command.

## Identity, input and observation

The [cross-repository golden](../../tests/ui/desktop-x11-v1.json) supplies exact
UTF-8 request/receipt bytes, descriptor order and independently reproducible
digests. `DesktopTargetIdentity` has three random 32-character lowercase hex
fields: `session_instance`, `incarnation` and `display_epoch`. No field is
reused by a new attachment, even when the same X server and window remain.

- Destination: `trill.desktop:<session>:<incarnation>:<display_epoch>`.
- Scope digest: SHA-256 of `trill.desktop.scope.v1\0` followed by the three
  identity strings separated by NUL, without a trailing NUL.
- Predecessor digest: SHA-256 of `trill.desktop.predecessor.v1\0` followed by
  the same three strings and the decimal input sequence, separated by NUL.
- Operation topic: `trill.desktop.input.v1`; payload digest covers the exact
  raw JSON bytes. The original owner persists and authorizes those same bytes.

Both stream lanes use a four-byte big-endian length followed by exact JSON.
Requests are at most 8192 bytes, receipts 2048 bytes, and capture replies 8 MiB.
Schema parsing rejects duplicate/unknown fields and invalid bindings. Input
supports only pointer motion, buttons 1–5, and X11 keycodes 8–255, with at most
32 events. Key and button presses/releases must balance within the batch;
stateful held-input sessions are not supported. Keycodes refer to the selected
server's layout, not an asserted Unicode text or IME contract.

Before the first XTEST request, the adapter checks sequence CAS, exact window,
viewability, current focus, already-held keys/buttons, screen coordinates and
the top-level window under each requested pointer location. Focus must equal
the selected top-level window; the backend does not steal focus. A server grab
serializes other X clients' window/focus requests with validation and input.
It cannot turn a shared display into an isolated device or exclude physical
input. Screenshots use the same lifecycle boundary.

Structure notifications permanently fence destroyed windows, including XID
reuse. An event backlog exceeding the bounded drain also permanently fences
that window instead of skipping potentially relevant lifecycle evidence.
Mapped-state, focus and pointer mismatches return `not_injected` only before
any XTEST call. Any error after injection begins is `unknown`. A partial batch
may already have affected the server, including a held key; the adapter does
not reconnect or run an ungranted cleanup/retry sequence.

Input sequence increments once after a fully confirmed batch. Exact replies
are retained before transmission in a bounded, live-process cache of at most
128 operations. Duplicate exact requests replay bytes without input; changed
payloads for a retained operation are refused. Capacity exhaustion refuses
new input and never evicts earlier evidence. This cache is not durable storage
or a second Hepta ledger. There is no receipt retirement API in this version.
Reattachment starts a new identity; lost historical results remain `unknown`.

The independent observe lane accepts only `observe` and `capture`. Receipt
queries return the original exact bytes when available; absence returns
`unknown`, never `not_injected`. Capture returns the selected window's current
RGB8 bytes as lowercase hex, dimensions, SHA-256 and the adapter input sequence.
Dimensions are limited to 1024×768 before requesting image bytes. This backend
supports the explicit 32-bit true-color X11 visual layout and rejects others.
Pixels are observations, not operation receipts. They cannot turn unknown
input into a terminal outcome or authorize another operation.

## Progress and failure behavior

Bootstrap has a two-second total deadline. A private stream's two-second frame
deadline starts on the first byte and includes its complete request, backend
work and reply; slow bytes do not renew it. Idle streams do not consume Session
main-loop work. Each native X11 transaction, including setup, has a 500 ms total
deadline enforced inside its stream poll/read/write implementation. An unknown
native outcome disables further input and disconnects that native connection.
The observation lane can still read retained receipts without reconnecting X11.

Input/capture run on private workers, serialized around the native connection;
they never execute in Session's public main loop. Slow private readers have
bounded replies. Worker exit shuts down its socket even if a duplicate is held.
Session still refreshes/reaps children before serving bounded public peers.

## Source and verification

| Source | Responsibility |
| --- | --- |
| `ui/core/src/desktop.rs` | Exact schema, byte/dimension bounds, identity and digest rules |
| `ui/session/src/desktop_bootstrap.rs` | Trusted inherited descriptors, server identity, one-time original-host handoff |
| `ui/broker/src/desktop.rs` | Independent lanes, exact live receipt cache, sequence and uncertainty fences |
| `ui/broker/src/desktop/x11.rs` | Real X11 setup, lifecycle/focus validation, XTEST, XGetImage, native deadlines |
| `tests/ui/test-desktop-x11-ipc.py` | Private authenticated Xvfb and stock xev/xmessage acceptance |

Build the Session binary with Rust 1.88 and run:

```sh
cargo +1.88.0 build --manifest-path ui/Cargo.toml -p trill-session --locked -j 2
python3 -B tests/ui/test-desktop-x11-ipc.py \
  ui/target/debug/trill-session /absolute/new/evidence-directory
```

Use the actual `CARGO_TARGET_DIR/debug` path when configured. The script requires
Xvfb, xev, xmessage, xdotool, libX11 and Python Pillow. It preserves exact binary
hashes before/after, structured results, per-process logs and captured PNGs.
It verifies native keyboard/pointer events, exact duplicate/lost-ACK handling,
focus/window/sequence rejection, Session progress under 32 slow peers, real
third-party application response, bounded cache/capture, lifecycle event flood,
and unknown outcomes when the owned X server is paused. CI runs the same script
after the existing UI build; it does not rebuild or target an existing display.

The original Hepta repository separately consumes the same golden and exercises
its own durable writer and FinalUse dispatcher against these private endpoints.
Neither the local fixture nor a test issuer qualifies a deployed production
issuer. This Linux X11 backend does not claim Wayland portal/libei, physical
hardware, Android, Windows, Asterinas graphics or Unicode/IME support. Those
backends require their own explicit device selection, authority and real tests.

Shell conversation save/import/export remains local. It neither calls this
effect lane nor submits an Objective. See [CHAT_WORKSPACE.md](CHAT_WORKSPACE.md)
and [SESSION_IPC.md](SESSION_IPC.md); a later signed-Objective entry must preserve
the original producer/issuer and keep drafts recoverable on rejection/unknown.
