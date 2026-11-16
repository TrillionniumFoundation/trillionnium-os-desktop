# Native597: preserve the explicit normal Go budget

The upstream Blueprint entry point called `runtime.GOMAXPROCS(runtime.NumCPU())`
unconditionally. The ordinary Native engine/ART producer also launches its Go
analyzer through a cleared environment. An inherited `GOMAXPROCS=2` setting
therefore did not establish the actual analyzer scheduler budget.

The three-file source patch fixes the normal ordinary-pair projection. It adds
the exact original Blueprint entry-point fixture, applies the reviewed explicit
budget patch, and supplies `GOMAXPROCS=2`, `GOMEMLIMIT=5GiB`, `GOGC=50`, and the
existing GC diagnostics in the actual analyzer environment. Blueprint retains
upstream behavior when no explicit scheduler limit is configured. If a configured
limit is malformed or the actual runtime does not honor it, it returns an error.

The entry point records Go's actual scheduler, memory and GC metrics on entry
and exit. The included consumer requires both observations, their expected
values, and a PID observed in the actual Soong process generation. Environment
strings alone are insufficient. Entry and exit observations do not claim
continuous runtime sampling.

The source lock remains the same 597-project lock. The normal targets remain
`libberberis_arm64` and the whole `com.android.art` APEX, with Strict dependency
handling. The ordinary-pair gate, exact source preimages, effective-source hashes
and normal projection restoration remain enforced. A source drift or a different
build mode fails before this projection mutates source.

## Source and actual validation

`native-pair-explicit-go-budget.patch` contains the three production/source-test
changes, including the two normal Rust test functions and the original Apache
licensed Go fixture. `source-pins.json` gives the exact preimage, updated source,
effective projected source and patch hashes.

The previously qualified producer had 456 complete working-source files in
addition to historical Git metadata. Its historical HEAD did not by itself name
those working bytes. The normal build first committed that exact qualified
working snapshot, then committed this three-file delta. The new source has
458 files, a clean normal Git tree, and independently copied Git objects.
`validation.json` records both commits and the actual tested binary hashes.

The normal Rust 1.93 tool build completed all 24 owned commands. The three
requested test filters passed 26 source-tool tests, 20 ordinary-pair tests and
12 pair-producer tests; these filter counts can overlap. Source before/after
checks preserved the original 456 files and the 597-project lock. The 4 GiB
bounded tool-build job peaked at 1,315,045,376 bytes, with no OOM or swap use.

The new tools were then copied to the independent build host and executed there
for actual loader and normal lock validation. All 38 host control tests passed
with zero skips, including real pidfd lifecycle and executable-identity controls.
Those observations are recorded as a new host generation. This capsule contains
only compact results and public source hashes, without raw host or account logs.

## Reproduce the portable consumer controls

From any working directory:

```sh
python3 -I -B /path/to/native597-explicit-go-budget-r1/tests/test_go_runtime_budget.py
```

The eight controls execute the same runtime-metric consumer used by the new
Native full controller. They reject an eight-CPU override, a memory-budget reset,
missing/reversed/duplicate observations, an unobserved PID, Boolean PID values,
malformed markers, and disabled GC. The normal Rust patch tests additionally
exercise exact projection and full byte/mtime restoration using the real source
fixtures.

The normal tool build and new-host controls do not compile the Android pair.
Actual Native Soong metrics, compiled translation units, whole-artifact signing
and payload qualification still require the separate normal full attempt and its
consumers. This source change grants no QPR1, installation, application or runtime
qualification.
