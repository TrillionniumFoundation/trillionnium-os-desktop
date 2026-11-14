# Private namespace control driver guards

The owner r2 driver used 15 Python assertions for source custody, explicit invocation and result qualification. Python `-O` removes those checks. Five offline examples reproduced false success with the exact original source: a wrong CLI, wrong source hash, failed test command, live cgroup and changed protected authority.

The candidate replaces those assertions with explicit `RuntimeError` checks, requires a complete unique unit-property inventory and a valid invocation identity, checks inactive/dead state and a canonical retired cgroup, and derives the authority-change result from the captured snapshots. Actual result files are written before post-run qualification, including invalid unit readback and protected-state changes. The existing privileged command and ordering are preserved.

## Source and replay

`private-control-driver-guards.patch` applies to the exact 5645-byte owner r2 source with SHA256 `8d02b64233755ffdbe3dc35c66f258b937af0d142a59972fe78b19f67b762759`. The `.original.py` member is a pinned historical regression fixture only. It is never installed or directly executed by replay. The test loader removes only its final `main()` call and replaces the unit runner and protected-host capture before invoking any verifier path.

Run these offline controls as root to exercise actual root-owned temporary files:

```text
python3 -I -B test_private_control_driver_guards.py
python3 -I -B -O test_private_control_driver_guards.py
```

There are 33 tests in each mode, including five historical false-qualification subcases within one test. Every external command is handled by a fixture stub with no route to subprocess execution. File custody negatives use real files for mode, link count, symlink, FIFO, length, hash, read bound and path replacement. The non-root UID stat and effective UID are explicitly synthetic fields because the Cloud test namespace maps only UID zero. Unit replies, cgroups and protected snapshots are fixtures.

Both final executions passed 33/33 with no failures or errors. `verification.json` preserves the initial fixture-environment failure separately and records complete final test logs and stream hashes. These results qualify only the verifier logic; no privileged namespace test, production admission or Android app acceptance is claimed.

No live source, account, subid file, unit or user data was changed. The owner must still qualify its real private control and production admission separately.
