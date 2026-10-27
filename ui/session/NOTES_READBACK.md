# Original Notes readback after App exit

Root-reserved Session retains the initial App's recovery datagram peer, without
an effect stream. The original Agentd already owns the other end of this same
pair. No target, operation, writer, grant, Root service or issuer is recreated.
Standalone and direct-bootstrap Sessions do not enable the continuation.

## Startup and lifetime

`product_root/session.rs::Session::spawn` supplies the fixed packaged helper's
actual SHA-256 separately from the native human UI environment. Reserved Session
derives its fixed `trill-notes-recovery` sibling, validates the original durable
store and prepares `notes_readback::Standby` before launching the first App.
The digest is trusted launcher metadata and grants no authority. Public Session
requests cannot select a helper, path, target or descriptor.

`Standby::prepare` checks type, owner, single link, nonshared write mode, canonical
path, bounded ELF bytes and digest. It seals a private memfd, then verifies the
same File's full seals, type, UID, mode, anonymous link count, length and actual
readback SHA-256. Disk replacement cannot change that image. The helper bound
remains 128 MiB. `bind` retains only the App-side recovery peer and original
first target. Original two-FD bootstrap and metadata-only Reserved are unchanged.

Immediately after original spawn, `pin_original` retains the owned Child's actual
pidfd. Failure stops and reaps only that child. `Session::refresh` observes the
original Child wait; `after_reap` independently requires that same Child ID,
completed wait and readable original pidfd before consuming the slot once.
A live or different child cannot start recovery. The helper inherits the same
recovery peer, original store and complete target; no effect FD, control socket,
signer or replacement operation is supplied. `NotesStore::recover` must acquire
the original incarnation lock, so any other live holder still blocks opening.

Sealed execution, parent-death SIGKILL, immediate parent check and close-on-exec
bind the helper to the actual Session. Session owns/reaps only this helper;
dropping its slot or Session exit ends it. No Root/writer/human/issuer/Agentd
lifetime is extended. One two-second monotonic start/readiness budget begins
before spawn. Setup and nonblocking polls share that end without renewal.
Failed spawn, malformed/late ready, helper exit or store failure consumes the
slot and remains unavailable. No automatic helper restart or effect rearm occurs.

## Results and validation

The original writer's existing recovery channel reads the exact receipt and
performs only the original idempotent terminal acknowledgement. The helper
rejects effects. Ready only means the store opened; it is not an application
receipt, authority or durable owner terminality. Missing/mismatched receipts
stay Unknown; I/O retains Unavailable/Indeterminate. No outcome permits replay.
The App remains exited, with no replacement editable incarnation. Full Session
or owner recovery retains the [product recovery rules](../../services/hepta-session-host/src/product_root/RECOVERY.md).

[Implementation](src/notes_readback.rs), [negative custody/process cases](src/notes_readback_tests.rs)
and [real helper component](../app-window/tests/notes_app_readback.rs) are separate
from installed qualification. The component persists once, normal-exits or
SIGKILLs its owned App, verifies the same peer's complete original receipt,
rejects an effect, queries again and checks unchanged target/text/revision and
lock release after helper drop. Cargo cache hard links are copied into a new
private installed inode with identical bytes; custody guards are not relaxed.

From the repository root with the selected source pair's generated locks:

```sh
RUSTUP_TOOLCHAIN=1.96.0 cargo test --manifest-path ui/Cargo.toml -p trill-session --bin trill-session --locked -- --test-threads=1
RUSTUP_TOOLCHAIN=1.96.0 cargo test --manifest-path ui/Cargo.toml -p trill-app-window --test notes_app_readback --locked -- --test-threads=1
RUSTUP_TOOLCHAIN=1.96.0 cargo clippy --manifest-path ui/Cargo.toml -p trill-session -p trill-app-window --all-targets --locked -- -D warnings
```

The ignored child fixture is selected only by its owning process test. Actual
App-only acceptance still needs exact installed ELF identities, original App
pidfd/exit, same Session/writer, unchanged operation/target/payload/receipt and
revision, original thread readback and absence of duplicate effects. No component
or lint result qualifies Root, human, model, display or accessibility execution.
