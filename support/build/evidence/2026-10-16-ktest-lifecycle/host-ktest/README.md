# Host ktest lifecycle evidence

This archive proves host process ownership behavior using Python fixtures.
It does not claim a Rust kernel build, QEMU boot, or kernel-test pass.

The original public ktest CLI exited -15 after TERM and released its workspace
flock while its leader and descendant pidfds remained live and the TCP lease
remained busy. The controller observed that failure before cleaning both owned
pidfds. The final repaired CLI returned 143, kept actual child status -9 in
`raw_exit_code`, reaped its direct leader, released the fixture TCP lease,
and wrote `passed: false`. Both fixture pidfds exited. `exit_code` records the
effective status; it does not replace raw child evidence.

The final 15 host tests passed under `-I` and `-I -O`; the latter also starts
the copied production CLI in optimized mode. One test exercises TERM at all
eight subprocess stages. The raw archive preserves all intermediate suite
logs, original failure receipts, both repaired-source snapshots and the raw
versus effective status correction. Intermediate suites passed; no additional
failed suite run is claimed.

`source-binding.json` verifies all three final files against local commit
94fca562365267d8f7415f8c9580ce2dcb891c98. The publisher verified its equivalent remote commit
efb02440ad6fff3b7a1a5d5019f660743d74ab32 with the same tree and parent;
the original publisher receipt is retained as `publication-receipt.json`. Every regular
tar member was reopened and byte-compared with its input, with sizes and
SHA256 recorded in `raw-member-index.json` and `RAW_MEMBER_SHA256SUMS`.

To reproduce the actual baseline and final host probes, extract
`raw-evidence.tar.gz`, then copy only `baseline.py`, `patched2.py`,
`run-before.py`, and `run-after.py` into a **fresh empty scratch directory**.
Run there:

```sh
python3 -I baseline.py
python3 -I patched2.py
```

Both controllers exit 0 when their expected observation is reproduced; the
baseline's expected observation is the real CLI ownership failure. They
create their own project/output paths, so do not rerun them over retained
original evidence directories. Controllers use only their newly created
fixtures and retained pidfds for emergency cleanup.

For the final host suite, copy `source-final/run.py` and
`source-final/test_runner_lifecycle.py` together into another fresh directory:

```sh
python3 -I test_runner_lifecycle.py -v
python3 -I -O test_runner_lifecycle.py -v
```

The baseline/patched controllers bind the TCP lease in their fixture leader;
the final suite binds it in the TERM-ignoring descendant. All fixtures stay
in one PID namespace, without `/proc` inference. Only the direct leader is reaped;
descendant exit is asynchronous and observed with bounded pidfd and fresh
TCP-bind checks. Descendants escaping their original process group are
outside this ownership contract. Original absolute paths in raw records
are historical receipts, not required report destinations.
