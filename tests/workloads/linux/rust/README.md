# a04-tokio-workload

This is the small Rust/Tokio executable used by the Linux ABI workload suite.
[main.rs](src/main.rs) checks four std threads and their shared atomic counter,
one Unix-domain ping/pong, asynchronous file write/read/removal and sixteen
yielding tasks on a two-worker Tokio runtime. It owns only files and the socket
inside the caller-selected scratch directory.

## Build and run

From the repository root:

```sh
cargo build --locked --manifest-path tests/workloads/linux/rust/Cargo.toml
mkdir -p /tmp/a04-tokio-current
tests/workloads/linux/rust/target/debug/a04-tokio-workload /tmp/a04-tokio-current
```

Use a fresh private scratch directory, and select the binary path from
`CARGO_TARGET_DIR` if configured. The
[Linux workload driver](../README.md), [full profile](../FULL_UBUNTU_PROFILE.md)
and [rootfs instructions](../../../../support/rootfs/README.md) describe ELF,
guest and full-suite inputs. A host run establishes host behavior only; the
guest profile must execute the exact packaged binary and retain its raw result.

## Error, permissions and cleanup

Any failed thread join, unexpected byte/counter, missing task completion or I/O
failure exits with an error. A successful run prints one JSON result and removes
its socket and data file. A crash can leave those files behind; use a new scratch
directory and retain the failed inputs before an explicit cleanup. Never point
the probe at production notes or an arbitrary user's directory.

The binary uses its caller's ordinary filesystem/socket permissions and has no
grant, issuer, Hepta owner or device control. Passing this probe does not qualify
the original Agentd, a desktop session or the complete Linux/Android ABI.
