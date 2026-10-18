# Process-guard evidence: 2026-10-17

These are byte-for-byte copies of the original review evidence captured at
**11:38 UTC on 2026-10-17**. This evidence-only addition did not rerun the tests,
build Rust, launch original Agentd, or modify the tested implementation.

**Result: six Linux process-guard tests passed, zero failed or skipped, in
0.225 seconds. The old-source probe observed the expected regression RED.**
Original Agentd qualification remains **`not_run`**. These disposable Python
child-process tests do not qualify an original daemon, Session, model turn,
authenticated objective, owner effect, or device control.

## Files and source identity

| File | Meaning |
| --- | --- |
| [receipt.json](receipt.json) | Original commands, working directory, UTC times, exit codes, source SHA256 values and log SHA256 values |
| [regression.log](regression.log) | Unedited output of the six passing tests |
| [old_source_red.log](old_source_red.log) | Actual ECHILD at the old code's intercepted first TERM call; no real signal sent |
| [probe_old_guard.py](probe_old_guard.py) | Safe RED reproduction: creates only its own disposable exit-1 Python child and intercepts `killpg`; never attempts PID/PGID reuse |
| [before_fix_run_original_agentd.py](before_fix_run_original_agentd.py) | Archived old harness source used by the RED probe; evidence input, not the supported launch entry point |

The receipt's five `source_sha256` entries match the exact file bytes committed
in **`f9f33ce61dd09ff4108ddb7256a501a0992a07a2`**:

- `tests/integration/hepta/run_original_agentd.py`
- `tests/integration/hepta/test_original_process_guard.py`
- `tests/integration/hepta/ORIGINAL_AGENTD.md`
- `tests/integration/hepta/EVIDENCE.md`
- `tests/integration/hepta/README.md`

The receipt was captured before that commit was created, so its `base_commit`
is the then-current parent **`a92d8ed242dc073738b5f7b85cd0af9d329dfce8`**. It
does not mean the six passing regressions tested the old implementation. The
five content hashes bind the actual fixed files that were tested and reviewed.
The archived old harness is byte-for-byte equal to
`git show a92d8ed242dc073738b5f7b85cd0af9d329dfce8:tests/integration/hepta/run_original_agentd.py`;
its separate `old_source_sha256` is
`8714516af855657c7d5b7b8a6891a7da9976d2010a00bd6f72a574a92fa6b2d8`.
The probe and both logs have their own hashes in the original receipt.

These commit IDs describe the original local revisions. A stacked integration
may cherry-pick the same bytes under new IDs. Preserve this source distinction
and verify the content hashes; this evidence does not claim that every file in
a later integration commit was executed.

The receipt retains the original absolute scratch paths and interpreter path
without rewriting them. In this archived directory, map each log or probe path
to the local file with the same basename. Every copied file was compared with
its original bytes, and the five fixed-source hashes, old source, probe, and
log hashes were rechecked while preparing this evidence-only commit.

## How to reproduce the checks

From a checkout containing the fixed implementation, on the standalone Linux
waitable-child profile described in
[ORIGINAL_AGENTD.md](../../ORIGINAL_AGENTD.md#process-group-identity-and-cleanup):

```sh
python3 -B -m unittest discover -s tests/integration/hepta \
  -p test_original_process_guard.py -v

python3 -B tests/integration/hepta/evidence/2026-10-17-process-guard/probe_old_guard.py
```

The second command intentionally imports the adjacent archived old source. Its
exit code **0** means it observed `expected_regression_red`: actual ECHILD after
the old `Popen.wait()` had reaped the child, before any intercepted signal could
be sent. It does not report the old implementation as passing. The archived
old harness must not be used as a launch or acceptance gate; the supported
entry point remains `tests/integration/hepta/run_original_agentd.py`.

To check the archived evidence without running any process test, read
`receipt.json`, compare each log's SHA256 using the basename of its stored path,
compare `probe_old_guard.py` with `probe_source_sha256`, and compare the archived
old source with `old_source_sha256`. Compare the five fixed-source hashes with
the files from `f9f33ce` or an integration retaining the same bytes. Subsequent
source changes require their own qualification; the archived receipt stays
unchanged.
