# Busy-lock output ordering, 2026-10-16

This is host-only evidence. It claims no Rust build, QEMU boot or clean-build
repeatability result. Baseline commit `0a533b92d4a4df8e8e4643c1b7de00e83ba0fd9d`
created `A01_RUN_DIR` and its parent before refusing a held workspace flock.
The busy call exited 1; after releasing the same lock, the identical command
again exited 1 because its required new output directory already existed.
The original observation, controller, both stderr files and empty stdout
files are retained unchanged. No separate original controller-stdout file
was saved; its printed observation is preserved in the written JSON.

The published fix is `5bcec614c1a075782b6ffaa5a5212fdee29be37d`, tree
`00e70e58dfa0dbf4718db55240136683f0a23310`. It acquires the persistent lock
before either explicit or default output creation. Two new tests exercise
busy refusal without path allocation and a successful identical-command
retry after lock release. The complete 33-test kernel runner/supervisor
suite passed under `-I` and `-I -O`. Both earlier suites passed as well and
remain in the raw archive; no failed suite run is invented.

The shell also records `RUSTFLAGS`, `CARGO_ENCODED_RUSTFLAGS`,
`CARGO_TARGET_DIR` and `ASTER_BUILD_TIMESTAMP` through quoted `%s` output;
unset values are marked `<unset>`. This records provenance without changing
the upstream build profile. A new arbitrary-value mirror test is not claimed.

`source-binding.json` checks the exact three frozen files against the actual
published Git object and the original publisher receipt. Four unchanged
fixture dependencies are included to reproduce the full host suite. The
retained three-file patch reconstructed exact published bytes with zero fuzz.
Every regular tar member was reopened and byte-compared against its input;
`raw-members.json` and `RAW_MEMBER_SHA256SUMS` index that coverage.

For the original baseline probe, extract `raw-evidence.tar.gz` and copy
`original/probe.py` into a new empty scratch directory. In an environment
where the repository Git object is still available at its recorded path:

```sh
python3 -I probe.py
```

Its exit 0 means the expected baseline failure was reproduced. Do not rerun
over an original evidence directory: the controller allocates new paths.
To relocate the repository, change only the copied controller's `repo` value
to a clone containing the recorded baseline commit; the archive's original
controller remains unchanged.

To reproduce the final suite without Cargo or QEMU, use extracted
`source-final/` as the current directory:

```sh
python3 -I -m unittest discover -s support/build/tests -p 'test_kernel_*.py' -v
python3 -I -O -m unittest discover -s support/build/tests -p 'test_kernel_*.py' -v
```

The test sources generate and remove their own disposable tools and workspace.
The two new tests' successful captured child output was asserted by unittest;
the full suite transcripts are retained, not separate per-fixture success logs.
