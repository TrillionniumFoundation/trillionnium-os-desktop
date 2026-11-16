# Native643 producer source and original provider closure

This capsule carries the current Native producer from private recipe commit
`dc0288fbbee2688473ae8a61215222f598f97e86`, tree
`581f0ed04c58550811d7fddea81f736cfc3b1848`. It is intended for the maintained
Pocket4 A08 source checks in `TrillionniumFoundation/trillionnium-os-desktop`.
The producer repository is `denialwm/droidloom`; this capsule does not publish
changes to that third-party origin.

## Exact maintained predecessor

The latest Native producer found at maintained repository head
`1a87eb2a2a5b20d7e2bef2d479f740189f9217bb` was:

`compat/android/pocket4/continuation-20261109-2840/native/r12-flags-provider/source`

Its recipe commit is `c0522b7877485d786b58b67b02e8297e41d53c8c`, with 601
projects. `preimages/` contains the exact three maintained files. `source.patch`
replays them to the current Native643 source lock, producer module, and bounded
source-reader declaration. The verifier checks an actual forward application,
reverse application, and second forward application, including all final hashes.
When `--maintained-repo` is supplied, it also checks the actual maintained
predecessor against these preimages.

The native lock adds 42 projects at the original superproject's fixed commits
and extends selected cones in 30 existing projects. All 601 existing revisions,
source policy, release metadata, and eight root links remain exact. The last
increment adds the complete Uwb `ranging/tests/multidevices/snippet/uwb` cone:
five original files, 45,332 bytes, at Uwb commit
`7c9e03046ff41cc28cf794cc2eda306fbc40279e`. Its real `ranging_snippet` provider
serves the three existing multidevice consumers. No synthetic provider or
consumer removal is introduced.

## Complete current inputs

`producer/` contains 560 files, 8,764,312 bytes, captured from the actual frozen
638-file recipe. It includes the unmodified Cargo workspace and lock, all
workspace member inputs needed to parse that original workspace, the actual
update/source/image/Mesa crates, Android inputs, all Native pair fixtures, their
original-source provenance, and every statically included source input. It omits
build targets, compiler caches, installed packages, APK outputs, screenshots, and
unrelated top-level documentation. The remaining supporting source files are
captured inputs, not claims that those files changed from Native601.

`manifest.json` records every included file's SHA256 and Git blob identity, the
exact three preimages and postimages, the current recipe and source capture,
compile-time include references, and original ordinary compiler evidence.
`FILES.sha256` binds the complete maintained capsule, including its verifiers.

The Native reader retains its tested 643-project declaration and existing
16-project rounding rule (`MAX_PROJECTS = 672`). Audio536 has its own 536-project
reader and tests. This capsule does not replace or widen Audio536's source
boundary. The Native producer's v2 recovery and pre-mirror capture code has the
same semantics as the separately maintained Audio fixes; both actual producer
versions keep their own source and normal build evidence.

## Actual validation and remaining gates

Ordinary job `ai395/1a1d632b686-392-907` succeeded with 29 commands, 86 distinct
tests and 92 test executions: 47 pair controls, 7 permissions/actual-rsync
controls, 6 journal recovery controls, 26 source controls, and 6 focused repeats.
All original command trees retired. The job compiled both actual Linux ELF
CLIs, verified the current lock and 643-project/eight-link plan, and preserved
the complete source, recipe, toolchain and original lock bookends.

That job used the approved ordinary profile: 4 GiB memory maximum, CPU quota
200%, affinity 8/9, zero swap, one Cargo job, and the established host and disk
reserves. It peaked at 862,826,496 bytes with no OOM event. The original full
build profile and guards remain separate and unchanged.

The prior Full8f7 failure remains a failure. It reached the three unresolved
`ranging_snippet` consumers after passing the former Compose/Car provider
defects. Its source restoration and complete physical retirement succeeded.
The five-file source transaction and a new complete Native engine/ART build are
still required. This source capsule grants no Android runtime, CP3A source
equivalence, complete engine/ART pair, or production-readiness credit.

## Source replay and Linux CI

Run `verify.py --output <fresh-directory> --report <report.json>` to verify all
inputs and perform exact bidirectional source replay. Add `--maintained-repo`
for the maintained Native601 predecessor and `--inventory-sha256` for an
externally pinned capsule inventory. Use a destination outside this capsule.

`run-normal-controls.py --workspace <replayed-directory> --output
<fresh-evidence-directory>` compiles the real captured producer, executes the
same 86/92 test set, builds both CLIs, and checks the latest normal source plan.
It runs 23 commands; the six private-recipe Git checks from the original 29 are
replaced by complete maintained source inventory/replay checks. It never invokes
reconcile, materialize, Android full build, signing, installation, or deployment.
All raw outputs and a truthful terminal report go to the separate evidence
directory. Use `--offline` after populating the pinned Cargo dependencies.

`a08-host-step.yml` is the proposed A08 step. The exact source replay was checked
locally. The new CI entry remains a draft until run on the maintained Linux
runner; the original full 907 ordinary result is retained independently.
