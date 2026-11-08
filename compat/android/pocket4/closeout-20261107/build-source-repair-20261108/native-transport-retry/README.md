# Bounded Native source transport retries

The latest isolated `droidloom-source` candidate passed four focused tests and its normal locked, offline release build. Its public source chain contains 451 files. The frozen full Native builder, original full-build tools, Cargo.lock and exact 597-project Android lock remain unchanged.

## Change

Normal `materialize` and `reconcile` retain a one-attempt default. A caller may opt into at most three total attempts for a fetch or promisor checkout with a specifically recognized transient transport failure. Recognition covers the earlier curl 56 receive timeout/reset cases and the added Git exit 128 diagnostic containing both `GnuTLS recv error (-110)` and non-proper TLS termination.

The complete direct Git stderr is checked for authentication, certificate, missing-reference, corruption, disk, permission and lock errors before any transient match. These failures stop the operation. Signals, process creation/wait failures and journal failures also stop it. A retry uses the same executable, arguments, working directory and environment, with one-second and three-second backoffs.

```text
droidloom-source reconcile --lock <frozen-lock.json> --output <source-tree> \
  --git-transport-attempts 3 --git-attempt-journal <absolute-private-directory>/git-attempts.jsonl
```

The journal is create-only, outside source/output staging trees, under a private directory. Its mode is 0600 and its parent is 0700. Each attempt start is synced before Git runs; complete stdout/stderr, process identity and the decision are synced before another attempt. Environment values are represented by their hash. The tool does not retry a whole source sequence or durable job.

The separate outer controller's nonzero adopted-child gate is unchanged. The earlier CrossDeviceSync failure contained an incomplete inner stderr prefix and one nonzero adopted child; those facts remain failures. Adding this classifier does not turn that earlier attempt into a complete or successful source run.

## Source reconstruction

Apply the six patches listed in [source-chain.json](source-chain.json), in order, to an empty Git worktree. The first four reconstruct the frozen 450-file public Native base. The fifth adds the bounded retry implementation and produces `e3a894768cbc93ed8bbec3e84c25528db3271781`. The sixth changes only `tools/droidloom-source/src/git_retry.rs`, including its parameterized controls, and produces `31d9c2d58cab931a5e914cb18df7b139a76e3f0b`.

[compiled-source-files.json](compiled-source-files.json) records all 451 retained files' bytes, SHA256 and executable modes. The [Mac replay proof](mac-replay-proof.json) links the previously completed first-five-patch replay and its exact current tree to the newly applied sixth patch. Both stages checked every resulting file and mode. The complete private compilation input inventory contains 457 files; the public proof records the narrow exclusions.

## Actual verification

[public-proof.json](public-proof.json) binds the actual latest source inventory, four tests, normal release output and physical retirement:

- Transport classifier parameterized test: one passed.
- Retry and durable journal parameterized test: one passed.
- Exact local Git fetch and manifest-link verification: one passed.
- Dirty materialized-project rejection: one passed.
- Normal release: `--locked --offline`, one compilation job, isolated network namespace.
- Resources: one CPU, 1.5 GiB limit, 536,969,216-byte peak, zero max/OOM/swap events.
- Retirement: complete durable terminal output, absent build cgroup and no remaining candidate build tools.

The latest isolated tool has not executed a network materialization or Android full build. The subsequent normal source owner failed on a curl 56 receive timeout, early EOF and an unsuccessful promisor fetch under its original unchanged CLI and lifecycle contract. That attempt retained complete inner and outer output, reaped all 60 adopted children with zero status, and passed its original process and lock retirement checks; the current publication remains at 268 projects. Source closure, full Native/ART artifacts and runtime/application acceptance remain separate requirements, recorded in the [latest observations](../../continuation/build-observations-20261108-native-tls-audio316.json).

AOSP checkouts, Cargo registry contents, compiled binaries, APKs, account/device data and private runtime records are excluded.
