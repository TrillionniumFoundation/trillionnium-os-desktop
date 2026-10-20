# Normal kernel build environment host fixtures

This package retains actual host-fixture results, not kernel compilation or QEMU
acceptance. The tested subject is the exact frozen SHA256 closure in
`source-binding.json`, atop merged source base b1a15d9afc456346410af658d2164ee5fa085656.
No published source commit is inferred. The prior published runner is retained
byte-for-byte under `source-before/` from 79d7f0530f08237ab2581d70d44fe59130eced8b.
The eight dependency blobs are unchanged between those two bases. The original
upstream Makefile and project minimal.mk are retained in both closures, with Git
blob and SHA256 bindings. `source-after/` has only the two owned-file changes.

## Actual observations

The first independent reproduction used production kernel.sh, real GNU make 4.3,
the actual upstream Makefile and minimal.mk, and disposable external Rust/input
fixtures. `MAKEFLAGS=n` and `MAKEFLAGS=t` each returned zero with zero reported
run status while no `cargo osdk build` recipe executed. The empty-MAKEFLAGS
control did execute that recipe. The `i` record in this first experiment used a
successful recipe and is only a control, not evidence of swallowed failure.
Exact raw output, argv, Cargo calls and statuses are in `makeflags-results.json`.
`reproduce-makeflags.py` is the unmodified historical controller; its absolute
project/output paths are the original invocation context. It was executed before
the fix; rerunning it against a later checkout would test that later runner.

The new regression methods were also run against the old runner. Six methods
produced nine expected assertion failures including four dry-run/touch/question/
GNUMAKEFLAGS subcases; there were no harness errors. The raw red log separately
proves an exit-42 recipe was ignored under inherited MAKEFLAGS=i, that MAKEFILES
was parsed, and that MAKELEVEL=73 reached the recipe as 74. Both empty and nonempty
CARGO_ENCODED_RUSTFLAGS were accepted by the old wrapper. The exact historical
red controller and complete JSON/text output are retained; it reads the frozen
new test module and obtains the old wrapper with git show.

With the fix, runner 30/30 and supervisor 9/9 methods passed in each of Python
-I and -I -O: 78 method executions. Four raw logs are retained. The real-make
fixtures prove that recipes run, failures propagate, inherited MAKEFILES is not
read, retry succeeds, and children establish MAKELEVEL=1/2. The encoded-flags
cases prove exit 2 before creating a lock or output, then successful unset retry.
Shell syntax and the two-file diff check passed. This is a fixed-build invocation
contract, not a security sandbox; ordinary boot acceptance remains independent.

## Replay the saved test closure

From this directory on a host with GNU make, Bash and Python 3:

```sh
python3 -I source-after/support/build/tests/test_kernel_runner.py
python3 -I -O source-after/support/build/tests/test_kernel_runner.py
python3 -I source-after/support/build/tests/test_kernel_supervisor.py
python3 -I -O source-after/support/build/tests/test_kernel_supervisor.py
bash -n source-after/support/build/kernel.sh
sha256sum --check SHA256SUMS
```

The tests generate only temporary host fixtures. The source-before closure is
for the old-runner differential, not the new tests' acceptance suite. Nothing in
this package updates or substitutes the fixed upstream kernel source/version.
