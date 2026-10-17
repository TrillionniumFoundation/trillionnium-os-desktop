# A08 source recovery and host regression — 2026-10-17

## Source identity and scope

The normal and optimized Python tests ran at code commit
`578b42363eb981a044b640cc1f9aecfcac1fbaae`, tree
`200d55c5aadaf4c61c367f75111f2ff9b7c338d1`. The one subsequent Java/JNI host
gate rerun used `5fd85f8632308507cd3368607fc37917075c46e4`, tree
`5d69a3fc1c7eff6a0449a0d9d7b36c9370f6cca3`; that commit adds the initial
evidence without changing executable sources. `source-snapshot.json` lists all 107
tracked A08 files at the tested commit with Git blob SHA1, SHA256, size and
mode. The root README is still 0 bytes. Changes are confined to
`compat/android/`, `support/android/` and `tests/workloads/android/`.

This is source restoration plus Linux host regression. No AOSP source sync,
AOSP image/APK build, Cuttlefish boot, Android-on-Asterinas execution, physical
device operation, Hepta integration or CTS/VTS certification took place.

## Recovery provenance

Base PR #7 was frozen at `41a8c32b435f2fa9dd750ded40bd4b37cb7606c6`,
tree `a452c9a65b43f2575817a1c576e8328205dc3f79`.
The recoverable historical source is
`37466a93823b9b10ace81759ec6decb59bb5a140`.

The complete historical A08 tree contains 105 files; the base contains 66.
There are 39 omitted paths, four changed blob contents and two changed
executable modes. The other 62 file contents are identical, and the base has
no A08 paths absent from the historical snapshot. This comparison establishes
that restoring the A08 subtree does not discard a distinct newer source file.

The four changed contents are the AOSP profile, log capture script, APK test
module and a historical host test log. The first three cannot be decoded as
UTF-8. The recorded Git blob hashes and sizes were verified directly against
the raw base Git objects. `recovery-provenance.json` contains their exact
failure offsets, every omitted path, the before/after blob hashes and modes,
and the 105-file verification inventory. All recovered contents matched their
historical Git blobs before the new guard and README edits. The historical log
was restored as historical evidence; it is not reused as current test output.

## Actual regression results

| Run | Actual result | Evidence |
| --- | --- | --- |
| Unmodified base discovery | Exit 1; 25 discovered entries, including three import errors | `baseline-unittest.log`, `baseline-result.json` |
| Complete historical source restoration | 166/166 passed, no skips | `historical-restore-unittest.log`, `historical-restore-result.json` |
| Current code, normal Python | 176/176 passed, no skips | `unittest.log`, `unittest-result.json` |
| Current code, optimized Python | 176/176 passed, no skips | `unittest-optimized.log`, `unittest-optimized-result.json` |
| Source integrity | 63 explicitly required inputs present; 70 source inputs checked, no errors | `source-integrity.json` |
| Complete host gate before JDK installation | Exit 1; Java/JNI tools absent; 176 unit tests pass | `host-gates.json`, `host-gates-result.json`, `host-gates.log` |
| Complete host gate with isolated Java/JNI tools | Exit 0, host_passed_only; 176 unit tests pass; actual JNI library and Java harness compile and load | `host-gates-with-jdk.json`, `host-gates-with-jdk-result.json`, `host-gates-with-jdk.log` |

Commands are recorded as argv arrays in each result file. The full Python
commands, run from the repository root with Python 3.12.14, are:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests/workloads/android -p 'test_*.py' -v
PYTHONDONTWRITEBYTECODE=1 python3 -O -m unittest discover -s tests/workloads/android -p 'test_*.py' -v
python3 support/android/verify_source_integrity.py
PYTHONDONTWRITEBYTECODE=1 python3 support/android/verify_host.py --out /tmp/a08-host-gates.json
```

The original 166 tests were recovered without weakening their assertions.
Ten new tests exercise missing runtime scripts, missing test modules, invalid
UTF-8 in each previously corrupted file, valid UTF-8 with truncated Python or
JSON, all four shell scripts individually, missing executable modes, new
unlisted malformed source and nonzero CLI failure reporting. The inventory
prevents discovery from silently losing test modules. The host runner now
uses that check instead of a partial Python file list and a single `bash -n`
call whose extra file arguments were not separately parsed.

## Remaining platform boundaries

The host tests compile and execute actual C probes for Linux memory mapping,
memfd, SCM_RIGHTS, futex, signals, Binder UAPI layout and child-only seccomp.
Binder device open returns BLOCKED/77 because the host has no Binder device;
this is not a successful Binder transaction. The source audit continues to
return exit 2 with Binder, seccomp and MAC blockers for Asterinas.

The full host gate additionally needs compatible `javac`, `java`,
`include/jni.h` and `include/linux` inputs to build and run the host Java/JNI
harness. The initial run had a JRE but lacked the compiler launcher and JNI
development headers, so it correctly remained blocked.

The integration owner supplied an isolated official Ubuntu OpenJDK 17
`javac` launcher and JNI headers, reusing the host's existing OpenJDK 17.0.20
runtime/compiler modules. This is not a complete newly installed JDK.
`jdk-installation.json` records the official package URL, SHA256, extracted
files and reused module path. With the exact PATH prefix and JAVA_HOME in
`host-gates-with-jdk-result.json`, a single rerun returned exit 0 and
`host_passed_only`. All three JNI stages passed: native shared-library
compilation, Java harness compilation, and real host loading with
`HOST_JNI_INTEGRATION_PASS`. Binder remained BLOCKED/77, and the Asterinas
source scan remained blocked. The initial failed host gate is preserved.

Several unit tests intentionally use synthetic ELF, fake QEMU transport,
fake ADB and fake VINTF tools. Their printed success labels describe those
fixtures, not a real Android guest. The immutable AOSP selection is preserved;
the actual product build, full manifest, partition hashes, VINTF runtime,
APK execution and Android compatibility remain unqualified.
