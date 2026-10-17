# External no_std backend compilation fixture

This independent Cargo workspace imports `os-control` with default features
disabled. Its downstream `FixtureBackend` implements only the public
`LockBackend` / `ControlMutex` contract and instantiates
`ControlCoreWith<FixtureBackend>`. Its guard is deliberately `!Send` through
`PhantomData<*mut ()>`; a negative compile-time assertion fails if it becomes
`Send`. The owned core/view/token/authority handles are separately required to
remain `Send + Sync`. Core, weak-core and view cloning is compiled with a
backend that deliberately does not implement `Clone`.

The library type-checks native reservation, typed execution against a pinned
synthetic owner, result query and contiguous retirement. It neither runs an
executable nor supplies a kernel allocator, IRQ guard, scheduler or credentials.
The spin wrapper is compilation/model evidence only and does not prove actual
kernel IRQ/preemption/SMP behavior.

```sh
cargo build --locked --manifest-path tests/control/backend_no_std/Cargo.toml --target x86_64-unknown-none
cargo fmt --manifest-path tests/control/backend_no_std/Cargo.toml --check
cargo clippy --locked --manifest-path tests/control/backend_no_std/Cargo.toml --target x86_64-unknown-none -- -D warnings
```
