# Per-invocation SDK isolation: host evidence

Published support code: `00a24cf5557d1b8e9663a19cc4961af81131d416`. These four published files match the exact
host-tested source hashes in `host-validation/private-sdk-validation-ready-v2.json`.
The pre-change code is archived at baseline `09aea79c71dc9f48ba519757078dd8a20f5c8fb3`.
The original GNU make probe read `cdf308e751e561328c556ca2ece86056d15809a0`;
its exact upstream Makefile and minimal overlay bytes remain in the bundle.

The prior ordinary path used a global cargo-osdk binary governed by mtime.
OSDK_LOCAL_DEV fixes OSTD's absolute source dependency at SDK compilation.
Actual GNU make with the original upstream Makefile and overlay skipped the
installation for a newer, foreign-root SDK in all three developer actions:
kernel, run_kernel, gdb_server. Each observed make status is 2 and the explicit
fake SDK's mismatch status is 73. The diagnostic phony-only experiment passes
all three host actions, without claiming concurrent global SDK safety.

The final support implementation instead creates a mode700 SDK prefix within
every new evidence directory, executes locked cargo install with --root,
and points both make's binary prerequisite and Cargo's external-command lookup
at that private binary. Shared CARGO_HOME/RUSTUP_HOME keep their values.
The installed binary hash is recorded. The selected Cargo home must be
absolute and contain no parent components; an unset CARGO_HOME uses an
absolute HOME default. No Cargo shim or upstream runtime change was added.

Fixed real Cargo 1.99.0-nightly, commit 3efb1f477e99b42974b982d939fd100303cdf7db,
was invoked with tiny fake external SDK commands in a private Cargo home.
Without an explicit home/bin PATH entry, Cargo selects the global command.
With private/bin followed by the literal home/bin entry, it selects private.
Independent real-Cargo checks found a counterexample for absolute paths
containing '..', including the default HOME path. The final entry rejects
those before a lock, output allocation, or SDK action. Normal, dot, symlink,
trailing slash, repeated slash, and double-leading slash forms select private.
A private command failing 47 propagates 47 without falling back to global.

Final host execution totals are separate: ordinary Python 40/40, Python -I
40/40, Python -I -O 40/40, supervisor -I 9/9 and repro profile -I 32/32.
That is 161 host test executions; only the first three modes rerun the kernel
runner suite. Its full upstream Makefile/overlay fixture checks all three
developer targets, fresh-prefix selection, a global replacement after private
installation, cache identity, ignored inherited SDK prefixes, installation
failure and owned-manifest cleanup. No-guest run/GDB fixture commands remain
rejected as boot evidence. The original lifecycle helpers are unchanged.
The independent final review approves the corrected source and includes
eight actual entry guard checks and seven focused host runner checks.

The first 38-test READY receipt and its exact bytes are retained as superseded,
along with the independent '..' counterexample. Earlier 37-test and baseline
30-test logs are intermediate observations, not final source acceptance.
The independent guard checker's first diagnostic-substring typo and the first
default-home probe's harmless printf newline typo are retained beside the
corrected raw reruns. Expected red reports are not rewritten as passes.

The schema4 descriptor-only probe also shows why identical virtual prefixes
alone do not establish independent-host reproduction: registry absolute paths
contribute to nonlocal producer identities, and then local consumer metadata.
Use the same literal registry/toolchain layout for a future cross-host attempt;
this phase does not claim that reproducing those paths is sufficient.

There is no SDK compilation, kernel compilation, or QEMU execution in this
phase. New full-build/boot acceptance must refer to its own actual producer
commit and logs. Historical first wrong-root SDK binary bytes were not retained;
its existing static path diagnosis cannot be upgraded into binary custody.
Mode700 private directories isolate normal installations between checkouts;
they are not an immutable sandbox against an unrelated same-user writer.
KVM/VMX, default AF_UNIX, independent-host/immutable environment validation,
and A05/A06/A07 native owner functionality remain outside this host fix.

To verify archived integrity without invoking the fixtures:

```sh
python3 -I support/build/evidence/2026-10-17-private-sdk/verify.py
# Also compare the four source files in the local published Git object:
python3 -I support/build/evidence/2026-10-17-private-sdk/verify.py --repo .
```

Fresh host regression commands from the repository root:

```sh
python3 -m unittest discover -s support/build/tests -p test_kernel_runner.py -v
python3 -I -m unittest discover -s support/build/tests -p test_kernel_runner.py -v
python3 -I -O -m unittest discover -s support/build/tests -p test_kernel_runner.py -v
python3 -I -m unittest discover -s support/build/tests -p test_kernel_supervisor.py -v
python3 -I -m unittest discover -s support/build/repro -p test_profile.py -v
```

The raw diagnostic scripts preserve their original absolute scratch paths;
they are provenance records, not path-independent launchers. Symlink fixture
targets are indexed in manifest.json rather than reproduced as archive links.
