# Main host regression recheck — 2026-10-17

Verified exact starting main: `146dedf75c5729ef1930c845eeb60e31e8111c60`.

Independent read-only checkout on an authorized Linux build host; root `README.md` remained zero bytes. Executed each command against this exact worktree with cached Cargo dependencies and distinct target directories.

| Component | Command | Exit |
| --- | --- | --- |
| HOS2 ABI | `cargo test --offline --manifest-path libs/os-abi/Cargo.toml` | 0 |
| HOS2 ABI | `cargo clippy --offline --manifest-path libs/os-abi/Cargo.toml --all-targets -- -D warnings` | 0 |
| HOS2 ABI | `cargo fmt --manifest-path libs/os-abi/Cargo.toml -- --check` | 0 |
| HOS2 control | `cargo test --offline --manifest-path libs/os-control/Cargo.toml` | 0 |
| HOS2 control | `cargo clippy --offline --manifest-path libs/os-control/Cargo.toml --all-targets -- -D warnings` | 0 |
| HOS2 control | `cargo fmt --manifest-path libs/os-control/Cargo.toml -- --check` | 0 |

Full command stdout/stderr retained on authorized execution host in `/home/qian-qi/.local/state/trillionnium-os-organ-next-20261016/evidence/main-20261017-{abi,control}-{test,clippy,fmt}.log`. This report is not full logs reproduced into Git.

**Scope:** host Rust compilation/tests and lint only. The run did **not** rebuild Asterinas, boot its changed kernel, execute HOS2 ioctls, validate A05 process/exec sessions, confirm A06 end-of-life CPU debit, or run Hepta persistent-effect recovery. PR #138/#139 and other draft patches require exact-head QEMU/kernel evidence. Do not mark G1/G2 or production-ready from this host check.
