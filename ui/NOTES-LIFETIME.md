# Notes original Session lifetime (Linux)

## Product behavior and limits

A Session-launched Notes App retains a read-only pidfd of the actual Session
process. If that process exits normally or is killed, the document worker stops
accepting commands, drops its original NotesStore and asks the GUI to close.
The GUI does not cancel that close to preserve an unsaved draft. A completed
checkpoint remains recoverable under its original target and receipt. An input
method preedit or queued draft is not thereby promised saved. An in-flight sync
may finish without a reply; that outcome must be reconciled from the original
checkpoint, never retried as a new effect.

The pidfd names the process/TGID captured by Session, rather than the thread that
happened to call spawn. The implementation does not use PDEATHSIG. The sole
Notes document worker checks liveness before and after each command, and every
50 ms while idle. Filesystem calls retain their existing durability semantics;
this is not a real-time guarantee for a blocked filesystem.

An Agentd-only exit has a different boundary: the original private effect stream
returns EOF/read failure and that transport thread exits. The recovery lane is a
Unix datagram socket, where a timeout or empty packet does not prove owner death.
There is no reconnect/discovery/rebind API in either lane. When Session still
lives, the App can retain its document lock and local editing state. A product
owner recovery must first prove that original App retired, using a held lifetime
or explicit close; this change does not invent that proof or reconnect to an
old target. No PID read from disk is used to kill a predecessor.

## Versioned inherited contract

Session supplies both `TRILL_NOTES_SESSION_LIFETIME_FD_V1` and
`TRILL_NOTES_SESSION_LIFETIME_META_V1` only to its Notes child. The metadata is
bounded to 1024 bytes and contains schema 1, purpose
`terminate_notes_with_original_session`, the exact Notes target, actual Session
PID/UID/GID, boot ID, process start ticks and storage requirement. No principal,
Root authority, effect grant or reconnect permission exists in this contract.
The child independently requires its actual parent, credentials, boot and birth
to match, validates the inherited pidfd's kernel identity, and restores CLOEXEC
before GUI/store initialization. Unknown, duplicate, partial or changed metadata
fails closed. Both parameters absent preserve the legacy direct two-FD profile.

Only the child pre-exec closure clears this descriptor's CLOEXEC bit; the
Session parent's descriptor flags are not mutated across concurrent spawns.
Existing inherited Notes stdin bootstrap still transfers exactly the original
effect and recovery descriptors. Root Reserved still transfers zero rights.
Neither protocol accepts another descriptor or a lifetime field.

`trill-session --notes-root-bootstrap-stdin` additionally requires an existing,
canonical `TRILL_NOTES_STATE_DIR` directory owned by its actual UID with no group
or other access, before it accepts Root bootstrap or creates a Session socket.
The original NotesStore guard performs this check without creating a document.
This profile's App metadata marks `durable_required`; App checks that directory
again before creating its store. Missing configuration never falls back to
Memory. Ordinary Session and old direct fixture profiles retain optional storage.
The Root product supplies the dedicated user-owned `u/notes` below a Root-owned
parent; this variable is not shared with the human provider or native shell.

## Development and verification

The real-process tests live in `app-window/src/notes_lifetime_tests.rs` and use the
same lifetime factory and production document worker. They spawn App from a
Session worker thread, join that thread, prove the child and original store lock
remain live, then actually terminate the retained Session process (SIGKILL and
normal exit separately). They require the App process's held pidfd to become
readable and recover the same target, text, revision and exact original receipt.
Recovery still rejects effects. Negative subprocesses vary parent/UID/GID/boot/
birth/target/purpose/version, malformed metadata and missing required storage;
rejection must create no document. These fixtures do not claim a Root grant,
model turn, final packaged ELF acceptance, power loss or full owner recovery.
