# Pocket4 full carrier source candidate

This directory contains the final source-only full carrier repair and the modules it directly or transitively uses. The 23 source/specification files are exact copies of the reviewed candidate; `SOURCE-MANIFEST.json` pins their bytes. They bind producer commit `9ecce4f94dec80500c05322106907e48a0668b05`, tree `12fe22ce02be9759963835faa4e7a7d0a762ddc2`, with 2,118 tracked files.

The candidate fixes the missing framework completion function, uses the six-target `framework-security-build` route, validates current framework/AVB/libpng/WM input and result receipts, checks services.jar/module-info/official test APK output identities, includes the two missing security projection lanes, records complete recipe/Git directory membership, and verifies the static recursive ELF dependency closure for the produced secilc. Its bounded readers reject FIFOs without blocking.

The original source-only execution gate remains unconditional. This directory supplies no storage admission, live owner, native unit authority or production acceptance. Historical fixed paths inside the frozen source are not current deployment authority. No runtime override is provided for CI.

## Run from a clean checkout

Requirements: Linux x86_64, Python 3.10 or newer, and an actual C compiler available as `cc`. The tests use only the Python standard library and local compiler/linker. They require no Android SDK, network access, SSH, account, privileged service, mounted build volume or VM.

From the repository root:

```sh
python3 -I -B compat/android/pocket4/current-full-build-carrier/tests/run_core.py
```

The same command can be used in an existing Linux x86_64 CI job. It verifies the complete public source hashes, then runs **44 public core tests**, with zero allowed skips. Test fixtures use temporary directories that are removed at completion. Generated ELF fixtures are parsed but never executed. FIFO cases use independent processes with a two-second outer timeout. The command writes its result to stdout/stderr and does not generate tracked output files.

## Public and private validation scopes

The public suite generates its own artifact, metadata, FIFO and linked ELF fixtures. It covers strict receipt/source rejection, complete framework artifact identities, malformed or escaping outputs, nonblocking readers, recursive dependency failures, exact ORIGIN token handling, current command/observer consistency and the unconditional execution gate. The ELF regressions include an actual library replacement between selection and queue processing, and fixed independent dynamic-segment fixtures for shadow offsets, incomplete or ambiguous mappings, partial overlaps and address overflow. The normal linked dependency closure remains a positive control.

The current private regression run contains **57 cases**. The public suite does not load or publish real qualification RESULT files, retirement records, owner/PID evidence, source F9 snapshots, original controller copies, runtime logs or compiled artifacts. Eight private qualification-class cases, five cases using the complete 49 real patch files, and one original-base comparison are excluded. The one evidence-independent execution-gate case from the private qualification class is retained separately: **57 − 8 − 5 − 1 + 1 = 44**.

Passing public CI does not replace those private checks or establish an actual Android build. Public test artifact files are explicit fixtures. The actual producer's qualification counts and source/result requirements are unchanged by this split.

## Files and maintenance

`src/` contains only the frozen carrier, verifier, observer and supporting modules required for this repair. `tests/` contains the portable public runner and self-contained core tests. Obsolete storage/overlay orchestration entry points and the original base snapshot are not included in this source publication.

See [MAINTENANCE.md](MAINTENANCE.md) for the remaining execution bindings and review rules. `SOURCE-MANIFEST.json` is a source integrity record, not authorization to start an importer, compiler or Android runtime.
