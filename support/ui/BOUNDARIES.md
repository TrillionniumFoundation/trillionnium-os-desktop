# A10: host desktop prototype boundaries

> **Reading note — 2026-10-22:** “Hepta is unconnected” below describes the
> earlier host prototype. Implemented Linux-host paths now include the opt-in
> [read-only Hepta observer](HEPTA_OBSERVER.md) and
> [private Notes bootstrap and destination](NOTES_ORGAN.md).
> The [final C receipts](../../results/integration/2026-10-22-organ-combination/c-qualified-receipts.json)
> bind host results to their specific source. These paths and receipts do not
> supply production grants or FinalUse authorization, qualify a production
> original-owner effect loop, or establish Asterinas execution. The original
> boundary text below is retained.

The Cargo workspace lives in ui/. It is **not** a new kernel session ABI,
authorization/permissions protocol, compositor or HOS2 codec.

The three executable processes are:
- trill-shell: unprivileged Rust eframe/egui graphical shell.
- trill-session: separately started host-local service owning child process
  spawn/kill/reap (including reaping while the shell is offline) and reporting
  actual exit statuses over a bounded, private
  Unix-domain socket under XDG_RUNTIME_DIR.
- trill-app-window: separate native Rust GUI clients (Notes, Calculator).
An existing Linux host Wayland compositor owns windows, keyboard focus, buffer
lifetimes and client connections. The session service does not manage those
privileged compositor resources. Shell exit must not kill the session or clients.
Host IPC mutations carry an OS-random, fail-closed 128-bit generation;
an unavailable /dev/urandom prevents startup rather than substituting a
PID/timestamp. Generation is a freshness fence and not an authentication
credential. Numeric task IDs alone
cannot authorize cancellation across restarts. This is a generation check,
NOT an authentication mechanism or substitute for A05 process capability. Session restart is different:
the session generation changes, stale task IDs are discarded and detached
clients are not claimed to have been reattached.

Workspace IDs are UI labels ONLY. The host shares one UID, clipboard,
Xwayland instance and security namespace: no cross-workspace isolation is
claimed. The session limits un-reaped children to 24 and retains at most 96
ephemeral task entries. It evicts only terminal entries and returns a
truthful resource error when in-flight/unknown entries cannot be removed.
Neither UI history nor the IPC socket is a persistent effect ledger.
The socket is a UX prototype control channel and is NOT secure
against malicious processes under the same UID. Before parsing requests,
Session checks the kernel SO_PEERCRED reported peer effective UID; Shell/CLI
check the returned SERVER peer UID before transmitting a request or
accepting a task snapshot. Both sides share the single Rust implementation
in `ui/core/src/host_peer.rs`. A foreign UID is refused, not treated as
an authenticated Hepta or A05 CapSpace operation. A same-UID adversary
remains outside this prototype's trust boundary. Do not expose this channel
as a capability grant or forward it over a network.

Shell IPC uses a separate bounded user-action queue (capacity 8) and a
single coalesced passive snapshot slot. Worker prioritizes actions, and
failed enqueue is displayed as NOT QUEUED. Requests can still be delayed by
one in-flight 2s transport timeout; this does not imply execution success.
A native app emits one fixed marker on a parent-owned stdout pipe after
its first egui App::update layout completes, stored as ui_first_frame_unix_ms. Missing marker
means UI readiness is UNOBSERVED despite a running host PID. The marker
is process-specific provenance, not proof of a mapped Wayland surface,
composited pixels, hardware acceleration or an authenticated permission.
All task states shown by session are derived from actual spawn, kill request
and wait/reap results. Hepta is unconnected, and its effects are UNKNOWN.
Host /proc metrics are labeled Linux host readings, not A02/A07 HOS2 samples.
OS permission prompts, screencasting, microphone, camera, file portal, D-Bus,
Xwayland isolation, Android SurfaceFlinger and GPU reset are not implemented.
`support/ui/src/permission.rs` contains only a consumer cache of externally
observed permission decisions. The cache is keyed by an opaque A05-supplied
scope plus capability, so a grant from one workspace/trust-domain scope
cannot authorize another. Unknown/denied/revoked/expired decisions are
fail-closed; the cache cannot issue a grant or derive scope from a workspace
label, process PID or assistant message. It is not an A05 portal or
authorization protocol.

Future trusted session/compositor integration requires A05 process identity
and grant lifetime, A07 authenticated task view (K/D history/ack and
unambiguous partial/unknown/cancel_requested), A08 Android display surfaces
and fences, and A00 coordination for any shared ABI change. Never infer
operation success from assistant text or a process showing a window.

The session creates its socket subdirectory with an atomic 0700 mode via
DirBuilderExt rather than a create-then-chmod window. Existing directories
are checked with symlink_metadata and rejected if insecure; no automatic
relaxation or following of symbolic links.

Local chat drafts may be explicitly exported/imported under the user's
own XDG state directory, with a 0700 app subdirectory and 0600 bounded
plaintext JSON snapshot. There is no background save, external file picker,
Hepta submission, cross-UID security claim or A05 file-portal grant.
Import refuses to modify a nonempty chat/composer. A same-UID malicious
host process is outside this provisional UI storage trust boundary.

The Session request parser performs an independent strict JSON-map
schema check before deserializing the known Request enum, rejecting duplicate,
missing, and unknown keys for Snapshot, Launch and Cancel. A real earlier Rust
binary accepted a Snapshot with extra data; the blocking native Session
wire-regression fails against that older executable. Host frames remain
strictly bounded to 64 KiB and are not a durable ledger.

Each accepted local connection has one 500 ms monotonic I/O deadline shared
by request reads and response writes. `ui/session/src/deadline.rs` recomputes
the remaining socket timeout before every operation; a successful partial
read or write never renews the allowance. Session checks the remaining budget
again before dispatch. An expired or incomplete request closes without
dispatching a host action; an action already dispatched keeps its real
lifecycle outcome even if the response cannot be delivered. Clients must
obtain a fresh snapshot before deciding whether to retry an action whose
response was lost. The single owner loop refreshes child exits before and
after every connection, including timeout, parse and response errors. This
bounds transport occupancy and preserves reaping between queued peers; it
does not impose a real-time scheduling guarantee on Linux process creation
or local filesystem reads. The public Request/Response schema, same-UID
peer check, 64 KiB limit and two-second client socket timeout are unchanged.

Startup is protected by a Linux kernel advisory exclusive session.lock
(0600, O_NOFOLLOW), acquired before stale Socket cleanup or UnixListener
bind. Two simultaneous service starters cannot unlink one another's live
socket. The lock releases on process exit, including SIGKILL; the file is
not a credential, A05 capability, or protection from same-UID adversaries.
