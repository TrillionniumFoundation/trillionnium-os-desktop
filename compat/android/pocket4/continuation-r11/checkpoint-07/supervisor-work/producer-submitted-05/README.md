# Producer05: direct native unshare for explicit relay generations

This immutable submission changes only development.rs. The explicit Some(pressure_relay) path uses /usr/bin/ip and /usr/bin/unshare and omits the unsupported --forward-signals flag. The legacy None argv is preserved. One pure Rust argv control compares both complete prefixes.

The actual installed compatibility wrapper (SHA fe3a685034ed0dc948597436965dfd35ea183fc2b0519d9b0c5730c79d7c060b) forks subprocess.Popen without pass_fds. It therefore closes inherited capability FDs and inserts an extra process; the strict exact-Child/PPid contract must not be weakened to accommodate it. The CPU command helper is a direct Command plus optional affinity pre-exec, not another wrapper.

The actual producer04 build passed 121 supervisor Rust tests, 23 relay Rust tests, seven ordinary IPC controls, worker-origin controls, and the compiled entry ABI. Its exact 34,691-byte receipt is included, SHA 0a8db6485bd5352d120365c921a67d8d7332d6205c9609860390b996deb3ba5e. The full actual candidate source inventory SHA is a7ec8ffb7a1615b5d4f85bcd4dbec19e49042ea4d37fbcd4ac6f5bdd6adab006. This submission's preimage is the exact development.rs in that receipt; unchanged inputs remain its 31-file bound closure.

The matching build05 is not yet dispatched. Its planned exact counts are 122 supervisor and 23 relay tests plus seven ordinary IPC, worker-origin, and compiled ABI controls. The build script snapshots actual producer04 source and receipt create-only before applying this one overlay.

No host namespace or network test, Android init constructor, Android service, installed mutation, or Main action is qualified by this submission. The full-prefix actor and external coordinator are being reviewed separately; even their future successful stand-in control cannot stand in for executing the actual Rust Owner or Android init. Actual init enrollment, protocol audit, abandoned-generation recovery, and production activation remain open.
