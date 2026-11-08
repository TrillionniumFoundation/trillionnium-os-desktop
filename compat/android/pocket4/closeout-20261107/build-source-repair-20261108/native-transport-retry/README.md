# Bounded Native source transport retries

The isolated `droidloom-source` candidate passed four focused tests and its normal locked, offline release build. Its public source chain contains 451 files. The frozen full Native builder, its original tools, and the 597-project Android source lock remain unchanged.

## Change

Normal `materialize` and `reconcile` keep their one-attempt default. The caller may opt into at most three total attempts for a fetch or promisor checkout that fails with the specifically recognized transient Git transport error. Retries retain the identical executable, arguments, working directory and environment, with one-second and three-second backoffs. Authentication, certificate, missing-reference, corruption, disk, permission and lock failures take precedence and stop the operation. Signals, process creation/wait failures and journal failures also stop it.

The opt-in form is:

```text
droidloom-source reconcile --lock <frozen-lock.json> --output <source-tree> \
  --git-transport-attempts 3 --git-attempt-journal <absolute-private-directory>/git-attempts.jsonl
```

The journal must be new, outside the source/output staging trees, and inside a private directory. It is created with mode 0600 under a 0700 parent. Each attempt start is synced before Git runs; the complete stdout, stderr, process identity and decision are synced before another attempt. Environment values are not serialized; the journal binds their hash. There is no automatic retry of an entire source sequence or durable job.

## Source reconstruction

Apply the five patches listed in [source-chain.json](source-chain.json), in order, to an empty Git worktree. The first four reproduce the existing 450-file public Native base. The last patch changes three Rust files and produces Git tree `e3a894768cbc93ed8bbec3e84c25528db3271781`.

[compiled-source-files.json](compiled-source-files.json) records every retained file's bytes, SHA256 and executable mode. The [independent Mac replay](mac-replay-proof.json) compares all 451 resulting files and modes with that inventory. The complete private build-input inventory contains 457 files; its documented public exclusions are unchanged.

## Actual verification

[public-proof.json](public-proof.json) binds the actual source inventories, test results, normal release binary and physical retirement:

- Transport classifier parameterized test: one passed.
- Retry and durable journal parameterized test: one passed.
- Exact local Git fetch and manifest-link verification: one passed.
- Dirty materialized-project rejection: one passed.
- Normal release build: `--locked --offline`, one compilation job, network isolated.
- Resource and retirement checks: one CPU, 1.5 GiB limit, 564,776,960-byte peak, zero OOM or swap, complete durable output and no remaining build processes.

The source patch, focused controls and source replays establish only this tool candidate's qualification. They do not establish a completed Android materialization, full Native/ART build or runtime acceptance. The later source entry using this candidate was refused at the original lock before any normal source command because an existing Native source owner was already running. Its failure is preserved in the [current build observations](../../continuation/build-observations-20261108-native-audio-sensor.json).

AOSP checkouts, Cargo registry contents, compiled binaries, APKs, device/account data and private runtime records are excluded.
