# A08 main integration: actual Linux host acceptance

This record covers the A00 integration of recovered A08 source and host tooling
with main `18d9fca65381f0e84f130c76fa289d5186894d85`. It grants **host-only**
acceptance. Android boot, APK execution and Asterinas Binder/seccomp/MAC remain
unqualified.

## Immutable source identity

| Identity | Value |
| --- | --- |
| Local commit actually tested | `5a5f03390901c8393d0336f6b5e194e2dfc5eb3e` |
| Published source commit | `194c41d0b2c8f1fabb7b6de4fac8967b862518a6` |
| Identical full Git tree | `836d3907854eb125eba1fdb492e6baff65ad4c45` |
| Main parent | `18d9fca65381f0e84f130c76fa289d5186894d85` |
| Published A08 repair parent | `25c76c1f294a3bf0ccf541f0063b0278899bf979` |

The published source commit preserves both parent histories. GitHub API commit
metadata differs from local Git metadata; the full tree identity is checked,
not inferred from a similar diff. The subsequent evidence/documentation commit
does not change the tested Android source. The A08 owner branch is untouched.

## Commands actually completed

Run from the integration checkout on Linux x86_64, Python 3.12.14. The existing
isolated OpenJDK 17.0.20 launcher/compiler and authentic JNI headers were used;
their installation provenance is preserved in the A08 recovery evidence.

| Command | Actual result | Raw evidence |
| --- | --- | --- |
| `python3 support/android/verify_source_integrity.py` | exit 0; 63 required / 71 checked files | `check-01.log` |
| `python3 support/android/verify_host.py --out <evidence>/host-gates.json` | exit 0; `host_passed_only`; 184 unit tests; JNI C build, Java compile and actual library load passed | `check-02.log`, `host-gates.json` |
| `python3 -O -m unittest discover -s tests/workloads/android -p 'test_*.py' -v` | exit 0; 184 tests, no failures/errors/skips | `check-03.log` |
| `python3 support/build/verify-source.py` | exit 0; 118 checked inputs; existing kernel derivatives preserved | `check-04.log` |

`receipt.json` preserves the executed argument vectors, elapsed times and raw
log SHA-256 values. `publication.json` adds local-to-published source identity
and hashes of the copied raw files. Logs are copied without editing.
The normal suite is executed inside the host aggregator; its actual count and
output are recorded there, not borrowed from an earlier owner commit.

The actual JNI marker is `HOST_JNI_INTEGRATION_PASS isa=x86_64 pid_equal=true`.
The Binder executable returned **77 / `binder_blocked_no_device`**; that result
is explicitly excluded from host success and is not converted to a pass.
The aggregate also retains `binder`, `seccomp` and `mac` as Asterinas source
blockers. Successful Linux seccomp probes are not Asterinas runtime evidence.

## Changes and qualification

The integration adds 151 paths relative to its main parent, restricted to
`compat/android`, `support/android`, `tests/workloads/android`, plus A00's
`.github/workflows/a08-host.yml`. It recovers missing historical source and
execution modes; adds a fail-closed source inventory; fixes whole-script shell
syntax checking; and makes source audits read immutable selected-commit blobs.
Schema 3 verifies the selected commit's actual upstream lock rather than simply
restating expected pins. Original failures and the final 184-test A08 repair
results remain under `tests/workloads/android/evidence`.

The root README remains exactly zero bytes. `support/upstream-lock.json`, the
fixed Asterinas v0.19.0 commit/toolchain and fixed Hepta commit are unchanged.
No kernel source is changed by this integration. Cloud workflow queue state is
reported on the PR separately; no queued run is used as a successful gate.

This source/tooling integration does not complete G1/G2/G3, supply an AOSP
product build, boot Android, or authorize effects on a device.
