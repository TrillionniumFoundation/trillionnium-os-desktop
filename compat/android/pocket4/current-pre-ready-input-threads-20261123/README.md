# Pocket4 pre-Ready input thread observation

The normal A08 producer builds the R41 input observer and the ordinary supervisor test helper together. The observer borrows the existing init and framework witnesses. It checks InputReader and InputDispatcher identities and samples their effective scheduler, timer slack and cgroup placement. For the R15 FIFO priority 2 profile, the Linux 6.18.64 timer-slack readback is zero. The production entry still returns the existing unqualified outcome.

`RESULT.json` identifies the three R41 source changes, four ordinary regression tests, original patch and ai395 source inputs. The original focused and full serial logs identified by digest are retained under `ai395:/home/qq/work/p4-r41-input-observation-20261123-ef8224/`. These results cover the R41 supervisor library before combining the separate test helper change.

`THREAD-FIXTURE-PROC-EXIT.patch` updates only the test child. It waits for the joined worker's recorded TID to disappear from procfs before acknowledging removal. `THREAD-FIXTURE-VALIDATION.json` records separate R40 comparisons with this test-only change. Rust compiles the helper into the supervisor test binary through its existing test configuration.

The complete A08 job reconstructs the combined source and requires 1,633 ordinary cases, 31 listed-only ignored cases and 19 normal release binaries. Real Android input-thread observations, production admission and application qualification are pending.
