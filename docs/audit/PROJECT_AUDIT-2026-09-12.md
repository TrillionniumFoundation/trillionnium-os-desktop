# TrillionniumOS Desktop project audit — 2026-09-12

## Scope and method

This audit compares the active d6 development plan, machine manifests, source tree,
qualification validators, and all 295 remote branch refs. The S02–S12 closure chain
was merged as one no-ff integration. `control/*`, `internal/*`, `lab/*`, export,
and evidence-only refs remain provenance; they contain repeated or self-modifying
workflow attempts and cannot be merged safely as product code.

## Module documentation coverage

The merged `manifests/modules.v1.json` is the authoritative index. Every Cargo
package has a README with the required API, dependency, state/concurrency,
security, testing, operations, and compatibility sections. The index also records
contracts, architecture references, tests, binaries, and features. Non-Cargo
surfaces (Linux adapters, update recovery, image overlays, systemd units,
workflows, and release tooling) are documented by their own architecture or
operations contracts and are intentionally tracked separately from the Cargo
workspace.

The index is a coverage gate, not proof of implementation maturity. A README or
validator pass does not establish a booted image, physical hardware behavior,
external effects, signing custody, or release readiness.

## Material findings

1. **Runtime is still mostly synchronous and bounded to one in-flight request.**
   `FramedUnixStream` performs blocking frame I/O and the AgentPort bridge admits
   one request per connection. There is no cancellation propagation, global
   in-flight budget, backpressure policy, or load benchmark. Adopt an async
   runtime or dedicated bounded worker pool, enforce per-peer and global byte/
   request budgets, and add repeatable latency/throughput gates.
2. **BrowserActor/Servo dispatch remains a qualification boundary.** The product
   supervisor now enforces generations, stale-reference rejection, crash-loop
   lockout, and no automatic replay, but the daemon still fails closed unless a
   separately qualified BrowserActor runtime is installed and activated.
3. **Session invariants need tightening.** Human focus can be granted in recovery
   or modal phases; navigation can begin while human control is active; and
   content input/navigation can be accepted before a recovered frame is ready.
   Require phase/control compatibility, monotonic generation checks, and explicit
   preemption transitions with property tests.
4. **Receipt recovery has memory amplification risk.** Recovery reads large
   journals into memory. Use bounded streaming validation, segment limits, and
   crash-safe compaction with an explicit disk quota.
5. **Canonical model duplication risks drift.** Browser contract types and codec
   wire types duplicate navigation/element semantics. Consolidate one domain model
   and make codec crates serialize it, with cross-crate golden vectors.
6. **Evidence is exact-head sensitive.** Older generated evidence and governance
   snapshots are historical after the integration commit. They must be rerun before
   any wider claim; stale snapshots never prove current branch protection or Rust
   qualification.
7. **Process and CI formalism remains a cost.** Minimum README byte counts and
   many temporary/control workflows can encourage boilerplate. Keep the generated
   index, but prefer concrete API/schema/test/runbook checks and delete transient
   workflow machinery after each gate closes.

## Recommended order

1. Re-run Python truth/documentation validators on the final `main` head.
2. Install Rust 1.93 and run locked fmt, check, Clippy, and all workspace tests.
3. Add session invariant tests and bounded async/backpressure benchmarks.
4. Consolidate browser domain types and regenerate golden vectors.
5. Qualify the D1/D2I image and S08 runtime on exact immutable heads before
   changing the documented claim ceiling.
