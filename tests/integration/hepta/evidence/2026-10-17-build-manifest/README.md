# Original build-manifest regression evidence

This directory qualifies Python manifest preparation against the unchanged
Hepta source at `f8c9419df6ddeb36ff8b522a50219981fb8d9345`. It does not qualify
Cargo resolution, a Rust build, or original Agentd execution. Original Agentd
remains **`not_run`**.

- [receipt.json](receipt.json) retains the original command, source path, UTC
  timestamps, before/after gate hashes, test hash, original workspace/lock
  hashes, exit codes and log hashes.
- [before_fix_regression.log](before_fix_regression.log) records the expected
  failure against the gate at parent `db1455a7d522ee68d762d58e95a265a7855e16e3`:
  the generated external workspace omitted the original explicit resolver 2.
- [after_fix_regression.log](after_fix_regression.log) records three passing
  tests in 0.161 seconds after the correction. No tests were skipped.

The positive case calls the actual `prepare_runner` function with the verified
complete original checkout. It checks resolver 2 survives in the external
workspace alongside the original profiles and unchanged seed Cargo.lock. The
negative cases change only a disposable copy of the workspace manifest; a
missing, unknown or incorrectly typed resolver must fail before creating the
runner directory. The original checkout was checked clean afterward.

Run the same small checks from the desktop repository root:

```sh
HEPTA_ORIGINAL_SOURCE=/absolute/fixed-hepta-private-ci \
  python3 -B tests/integration/hepta/test_original_build_manifest.py -v
```

The environment variable is required. Missing, dirty or wrong-version original
source fails the check; it is not replaced by a fixture or silently skipped.
This command generates temporary manifests and copies the original lock; it
does not invoke Cargo. Dependency resolution and original-process acceptance
must still complete through the separate `run_original_agentd.py --execute`
gate. The earlier process-guard evidence directory stays unchanged and binds
the earlier tested revision.
