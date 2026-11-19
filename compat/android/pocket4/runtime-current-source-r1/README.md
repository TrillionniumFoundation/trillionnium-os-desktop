# Pocket4 current complete source packet

This packet reconstructs producer tree `28c270a8e32478e6789c8319b0df164b67268224`
with **2,350 files / 44,156,524 bytes**. It preserves the complete source capsule,
all original targets and all ignored cases. The cumulative overlay remains
bounded by the original 5 MiB expansion and 64 MiB decoder limits.

## Changes

The successor contains twenty frozen runtime source changes, including six new
files, for the original apexd task identity and compressed APEX request inputs.
The source binds the actual requesting thread, original process and file
identities, label observations and the requested file description. It preserves
the original request bytes and distinguishes observed configuration from an
issued loop handle. The source also retains the exact default namespace and
bootstrap state established by the preceding packet.

The packet contains the complete source after the actual formatter and tests.
Every formatter change is tied to its original frozen preimage; no new source
patch is applied during packet preparation. Later unfrozen APEX work is excluded.
The preceding r7 worker's failed orchestration receipt and its separate
successful finalization remain unchanged. The r8 validation itself succeeded
with all six original commands and their original PIDFDs reaped.

## Exact verification scope

The affected complete supervisor harness actually passed **557 ordinary cases,
zero failures and 25 unchanged ignored cases**, with complete source identities
matching across execution. This adds nineteen cases to the preceding 538-case
supervisor catalog. No existing test was removed, renamed or newly ignored.

The full current runner requires **49 harnesses / 1,514 ordinary cases /
30 unchanged ignored cases**, nine separate recipe tests, 19 normal release
binaries, three compiled examples and 20 documentation targets. The full CI
must pass on this exact packet; the local supervisor result is not a substitute.
Example mains and hardware-specific ignored branches are not claimed executed
by those gates.

The immediately preceding producer tree was
`7950a18a37330bf3d97e6bb3847b7163fb88a82a`, with packet inventory
`ade5eb3c468b340c05aecfd2b48907c50f2dbe0f21eb583fca3f01ebf176e3a7`.
Its complete run
[44468318318](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/44468318318)
passed 1,495 ordinary cases and built 19 normal release binaries. That result
belongs to the preceding tree. All unchanged recipe targets and source repairs
remain in this successor.

## Reproduction

Use the FILES.sha256 digest pinned by the reviewed commit's workflow and source
guard. The inventory covers all thirteen other packet files. Run:

```text
python3 -I -B verify.py --inventory-sha256 <reviewed-inventory-sha256> --output <fresh-source-directory> --report <fresh-report.json>
python3 -I -B test_verifier.py
python3 -I -B test_runner.py
```

The unchanged preparation script and run_ci.py retain their normal locked build,
complete catalog, complete terminal, ordinary release, recipe and source
bookend checks. SOURCE-CAPSULE.tar.xz, EXPECTED-BINS.json, EXPECTED-TARGETS.json,
EXTRA-TARGETS.json, UPDATER-EXACT64.json, prepare_ci.sh and test_runner.py are
byte-for-byte unchanged from the preceding packet.

## Open acceptance gates

This is a tested source packet. The local run issued zero successful guest ioctl
replies and does not establish a guest loop handle provider. Its ordinary tests
and source replay do not establish original apexd activation, privileged runtime
execution, complete vendor build, Android boot or application acceptance.
Those production gates remain separate. The frozen vendor R12 controller and
inputs are unchanged. The three permitted app exclusions remain TextNow,
TextFree and Uber. **Android starts in this packet preparation: 0.
Production ready: false.**


## Cumulative overlay

106 paths; 648532 compressed bytes; SHA256 `b0d7468131ae5a43c29b7188d2e2633810333693c603c0b4c5a422ac5513b7d0`. Expanded bytes: 4884480; SHA256 `c518eb2c15160645506d15167c5a0f2b19ac0d89b24f1b3178e1ce54f6ed78d6`.
