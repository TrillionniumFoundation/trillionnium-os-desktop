# trill-session

Linux host process owner for the Shell and application windows. `src/main.rs`
owns task generations, launch/cancel/reap and private Notes startup;
`src/ipc.rs` serves bounded nonblocking public requests. `src/hepta.rs` observes
the configured original runtime. `src/notes_bootstrap.rs` transfers private
destination descriptors to an explicitly configured trusted parent.

The `trill-ctl` binary is a client of the same public host protocol. Public
Snapshot/Launch/Cancel has no Notes edit, arbitrary command, descriptor export
or authority-minting request. Same-UID transport checks are not Final-use grants.

From the repository root:

```sh
cargo +1.88.0 test --manifest-path ui/Cargo.toml -p trill-session --locked -j 2
```

Development and technical contracts: [Session IPC and lifecycle](../../support/ui/SESSION_IPC.md),
[Notes persistence and recovery](../../support/ui/NOTES_PERSISTENCE.md),
[runtime observer](../../support/ui/HEPTA_OBSERVER.md),
[host build and acceptance](../../support/ui/RUN.md).
