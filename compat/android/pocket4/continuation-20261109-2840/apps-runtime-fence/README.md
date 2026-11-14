# Complete application dispatch: one current runtime and sticky failure

This capsule extends the published application runtime entry with a read-only runtime precondition and generation fencing. It does not deploy a daemon, start Android, install an application, or grant application acceptance. All 42 runtime acceptances remain pending.

## Source identity

- Private source commit: `deacfc207c99a74a8aac056b086dc1b8f7e8f0c2`.
- Parent: `4e16058cc0f6de83fabae68736dad7eb91edbc47`.
- Tree: `fa7b71a494adeaebcef412d61c2f23600ab87e38`.
- Branch: `fix/pocket4-runtime-preflight-20261109-2840`.
- Patch SHA-256: `76ab9968be750f09b9b75e932df47c6cae637774d25910a073bdafdb20640c0f`.

The patch changes six files relative to the parent: the applications module declaration, runtime plan, new runtime fence, supervisor control protocol/handler, observation types, and tool documentation. The source commit job verified the exact tested hashes before committing and ended with a clean worktree. `source-publication.json` contains every changed source hash. Other copied source files are unchanged dependencies from the preceding frozen capsule, loaded by the same-file CI harness.

## Behavior

One `ObserveRuntime` request precedes the complete selection. The daemon authorizes the current active cell and reads the already-ready owned runtime; it does not start or qualify it. An unavailable, older, or mismatching runtime produces every requested row as blocked with no package queries.

The currently implemented daemon owns `DevelopmentCell`, so the observation enum has only `Development`. No production enum value, HostAdmission token, or admission boolean is invented. Production integration requires the genuine running production lifecycle owner described in `audit/production-and-leaf-integration-review.md`.

The client's fence is sticky. A physical generation change or socket/protocol failure stops all later application calls. Package-specific failure can perform a fresh read-only runtime observation; it never replays the failed operation. If that observation changes or becomes unavailable, the remainder stops. Once invalidated, all rows are blocked, including earlier partial browser observations; their evidence remains available as diagnostics. The report still has `accepted_applications: 0`, `runtime_qualified: false`, `production_ready: false`, `automatic_retry: false`, and all required gates pending.

`runtime_preflight` and `observations_share_expected_epoch` describe physical observations only. `main_qualification_semantics_checked` remains false: the plan and Main file bytes are pinned, but this entry does not parse or grant Main release qualification. Installed signer verification remains an independent required evidence chain. The only business invocation is still the partial Firefox implicit-HTTPS entry; document/input/image, media, return/reopen, recovery, and common gates remain pending.

Both daemon and applications client must be deployed together. The client fails closed when an older daemon rejects the new request or omits the new observation. No deployed executable or canonical shared registry was changed by this capsule.

## Actual verification

`evidence/normal-and-samefile-tests.json` records job `1a1c11119fc-336d-59`, authoritative succeeded 0, output complete and durable. It ran the actual private workspace as UID 1000 on CPU 2 with one Cargo job, 100% CPU quota and 2 GiB memory limit:

```sh
cargo test --locked -j 1 -p droidloom-supervisor --lib application_ -- --test-threads=1
cargo test --locked -j 1 -p droidloom-applications
cargo build --locked -j 1 -p droidloom-applications
```

Results: 14 supervisor tests passed, with two explicitly root-only controls ignored; 36 application library tests and three CLI tests passed. The same-file isolated harness then passed 29 tests, with the same two root controls ignored. These counts overlap and must not be added as distinct tests. The isolated harness has one expected dead-code warning for the namespace capture constructor, which is called by the full daemon but not this isolated module harness; the actual workspace run had no warnings.

`evidence/actual-cli-preflight-negative.json` records job `1a1c11a1970-336d-6e`, succeeded 0, output complete and durable. The actual compiled CLI read the real 42-package registry contract and received a failure from an owned test Unix socket. Exactly one `{"command":"observe_runtime"}` request arrived; package calls were zero; all 42 rows were blocked; acceptance and partial counts were zero; the CLI returned the expected exit 1 in approximately 4 ms. Its Main input was explicitly synthetic, no Android operation occurred, the test thread joined and its temporary directory was removed.

The earlier FD/cgroup host controls are not repeated or relabeled here. Their transport source is unchanged, and their prior exact-byte evidence remains in the preceding capsule. They are not production Android evidence. Independent source review found no remaining R3 blocker and confirmed that future lifecycle enum expansion must bind lifecycle in every per-application observation.

## Reproducible CI entry

The isolated harness imports the actual source modules by path. Its only compatibility adapters are visibility forwarding of the real PIDFD helpers and a crate-name/type re-export; process behavior and daemon responses are not mocked in those modules. The full dispatch tests above ran in the actual workspace and are not falsely counted as isolated-harness tests.

```sh
cargo test --locked --manifest-path compat/android/pocket4/continuation-20261109-2840/apps-runtime-fence/harness/Cargo.toml --lib -- --test-threads=1
```

Expected ordinary CI result: **29 passed, 0 failed, 2 ignored**. The exact Cargo lock SHA is `94d5485165fa970400ddbcca6ac38d63e46e14c4ca1aea7054d6d18a5706f625`. All 33 external package records and checksums are unchanged from the previously published lock. GitHub CI publication/execution of this successor is pending until independently observed; the remote run above is already complete.

## Audit and cleanup boundaries

The included audit pins the actual 13 selected leaf preparations and explains their seven-application partial coverage, older exact identity inputs, current QPR1 port candidates, and safe transport reuse boundaries. Unsupported profiles remain explicit. No account actions, external messages, calls, purchases, or reservations were performed.

The previous capsule remains frozen. The private source checkout is retained until this successor is persistently published and all live process, open-file, mount and coordination references have been checked. A completed test job alone is not proof that a whole source root can be removed. User data, signing dependencies, active owner roots, and selected canonical inputs are outside retirement scope.
