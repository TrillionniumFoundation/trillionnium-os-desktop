# Session consumes the existing default-deny Broker

The tested implementation is local source commit
`bd8fb8f2f84825c302da262f4f4919ef5897d81f`, tree
`6138e039d4b881dafd301df1a35d9f8a17ed01bc`, based on the existing
Broker owner `24dc73185d739695ef755c6bbd9d22ee38acf9be`.
The receipt binds all nine changed source files by SHA-256 and Git blob.
This directory adds evidence only, so its commit has a different tree.

## Behavior and actual validation

The actual Session executable now serves the original Broker over a private
`organ.sock` beside the original `session.sock`. It obtains real SO_PEERCRED
before reading a hello, reads one bounded frame through EOF before admission,
deserializes the original bytes with strict typed Serde, and closes each
admitted session before writing its reply. One owner loop and a fixed complete
read/write deadline bound active transport work. The existing Host listener
uses the same deadline, and startup probes only remove an endpoint after real
ConnectionRefused. Full listen queues cannot indefinitely block either the
client connect or startup probe. Existing private-directory and instance-lock
checks remain in use.

On Rust 1.88.0, the exact final source passed:

- Standalone Broker: 33 tests, zero failures or ignored tests. This specifically
  verifies that the Broker does not require feature unification from Session.
- Original Broker plus Session command: 74 tests, zero failures or ignored tests,
  including real Unix sockets and the actual Session executable. The 33 Broker
  tests are included in this total; they are not 33 additional distinct cases.
- All-target Clippy with warnings denied and `cargo fmt --all -- --check`.
- Three isolated old-behavior controls. Each compiled, executed exactly one
  real-socket regression, and failed at its expected runtime assertion:
  old per-read Host timeout, old blocking startup probe, and blocking client
  connect. Each returned Cargo exit 101 with zero passed and one failed.

Source hashes remained unchanged during all final executions. The tests used
one build job, disabled incremental compilation, and did not record an OOM.
Socket tests ran with permission for private AF_UNIX fixtures. The packet
contains complete stdout/stderr bytes as deterministic gzip, including the
earlier failures. `python3 verify.py` checks those saved bytes, summaries,
control mutations and current source hashes; it does not rerun Rust tests.

## Earlier failure preserved

An earlier joint-source test at `0e4a0025` passed, but a standalone Broker check
failed with E0277: socket2's direct std UnixStream/UnixListener conversions
require its `all` feature. Session's existing dependency graph had implicitly
provided that feature. The first client-connect negative control therefore
failed to compile and was not a valid runtime control. Both outputs, the first
control series and their exact source receipts are preserved here. The final
three-line conversion fix moves each Socket through standard OwnedFd, without
adding a feature, duplicating a descriptor, or changing transport semantics.
Both independent reviews are preserved as source reviews with their original
timestamps; their then-pending test statements are not retroactively edited.

## Reproduce the final positive checks

From the repository root with Rust 1.88.0 and the locked dependencies available:

```sh
cargo test --manifest-path ui/Cargo.toml --locked --offline -p trill-ui-broker
cargo test --manifest-path ui/Cargo.toml --locked --offline -p trill-ui-broker -p trill-session
cargo clippy --manifest-path ui/Cargo.toml --locked --offline --all-targets -p trill-ui-broker -p trill-session -- -D warnings
cargo fmt --manifest-path ui/Cargo.toml --all -- --check
```

The receipt records the exact before/replacement text and resulting hash for
each negative control. Apply each mutation only in a separate source copy and
run its recorded single-test command. Fixture watchdogs release their own
sockets and child Session process; no unrelated process or build is stopped.

## Qualification still required

The final published head and current base require the original A10 CI. Local
tests do not replace that gate, original owner CI, a native kernel boot,
production A05/A07 assembly, a real authority issuer, a recovered durable
writer, K-to-D fault/recovery qualification, or physical desktop/ADB/GPU
evidence. Submit and Cancel still return denial, drafts remain LocalOnly, and
unavailable owner history remains Unknown. Issue 111 remains open. This host
transport adds no production effect capability or bootstrap authority.
