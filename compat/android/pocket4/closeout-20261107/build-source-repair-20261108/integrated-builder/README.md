# Frozen Native, Audio and combined builder sources

**Source reconstruction and focused Rust controls passed; full Android builds and deployment remain unqualified.** This directory publishes the exact retained Native 597-project input, the Audio 308-project candidate at `6eb50f3e0a2184cb822d0704c6f53f261ebd2de4`, and a separate combined builder with both source locks preserved. It does not replace either frozen input used for an existing full-build attempt.

Native 597-project source materialization is still pending while its transport is recovered. The actual Audio full host-r1 build failed in Soong bootstrap because `icu4j-tests` depends on the undefined `junit-params` provider. No complete Audio APEX was produced. The next provider repair is not included here. Final deployment remains false, runtime qualification remains false, and original whole-application acceptance remains **0/45**. [Build observations](build-observations.json) retain the exact failed terminal and retirement hashes.

## Three independent reconstruction choices

Each choice starts in a new empty Git directory. Set `PACKAGE` to the absolute path of this directory's parent, `build-source-repair-20261108`. Apply the shared base first, then one complete row below. The three final patches are alternatives; do not apply them on top of one another.

```sh
git init reconstructed-source
cd reconstructed-source
git apply --index "$PACKAGE/source-prerequisites/base-source.patch"
```

| Result | Further patches, in order | Retained files | Changes from its published predecessor |
| --- | --- | ---: | ---: |
| Frozen Native 597 | `source-prerequisites/native-prerequisite.patch`, `native-sparse-capacity/source.patch`, `integrated-builder/native-frozen-597.patch` | 450 | 9 |
| Frozen Audio 308 | `source-prerequisites/audio-prerequisite.patch`, `integrated-builder/audio-final.patch` | 409 | 17 |
| Combined builder | `source-prerequisites/native-prerequisite.patch`, `native-sparse-capacity/source.patch`, `integrated-builder/combined-builder.patch` | 476 | 44 |

For each further patch, run `git apply --index "$PACKAGE/<relative-path>"`. Compare every retained file's SHA-256, byte count and executable mode to the matching `*-source-files.json`; `git write-tree` must also equal the subset tree in [source-chains.json](source-chains.json). These subset trees identify the published file selection and are not invented upstream commits. Both Pocket4 and Mac independently performed all three replays; [Mac's exact replay summary](mac-replay.json) records the matching results.

The common base includes the Cargo workspace, Cargo.lock and licenses. The exclusions remain those of the published base: operator metadata, Git internals, a documentation screenshot and a zero-byte tool sidecar. AOSP projects and Cargo registry dependencies are separate inputs obtained from their pinned locks.

## Combined-source decisions

The Native lock remains exactly 597 projects with SHA-256 `2b699174977614e080cf99a991f3e648774b24581c4ecdc29f1bd53b7b01ef23`; the Audio lock remains exactly 308 projects with SHA-256 `bf5db84637fe0508be889aa7c7343e4478ed8a4a537099babc87bfba456ce94b`. The common project capacity is `ceil(max(597, 308) / 16) * 16 = 608`. Audio's own required capacity remains 320, derived independently. The original Native CTS selection keeps its bounded 288 sparse-path capacity, including duplicate, escape and over-limit rejection.

Native strict pair, typed-provider and normal routes retain their original provider bodies and restoration rules. Audio projection runs only in its explicit Audio mode; its Gatekeeper provider cones, purpose check, source lock, resource restoration and source-recovery route remain intact. New mixed-route tests cover the shared selection and SDK fallback. [Merge decisions](merge-decisions.json) and the source inventories identify the exact combined input; neither predecessor's binary qualification is transferred to it.

## Actual checks and retained failures

[Focused results](focused-results.json) bind the source inventory, counts, exact case names and normal release binaries:

- 29 source-library tests passed in attempt r2. The later repair changed only the recipe and two historical fixtures; the library inputs were proved unchanged.
- The recipe first failed one of six tests because a historical 268-project check accidentally included the current 597-project lock. That real failure is retained. The isolated fix pins the actual old 268 lock and the actual pre-generation library containing the 28-name allowlist. The frozen Native build tree is unchanged.
- All six recipe tests then passed. A normal invocation using the original superproject rendered exactly the actual frozen 597 lock, library and pair source hashes; its patch passed `git apply --check` against the historical inputs. [Recipe provenance](recipe-fix-provenance.json) records the real fixtures and render.
- 58 distinct updater tests passed: Audio, Native pair, fix18, SDK and mixed-route/CLI controls. The category sets overlap and must not be summed. The new executable's `--list` output contained each selected name, and each `--exact` invocation had to report exactly one passed test and zero failures; a zero-match exit code could not count as a pass.
- Both normal release tools built from the combined source. All 64 recorded r3 commands exited zero; all 476 source files were unchanged before and after. The owned unit and children were retired. The run used one CPU, 1.5 GiB maximum memory and zero swap; peak memory was 900,829,184 bytes with no max/OOM event.

The earlier pre-Cargo manifest-permission failure and the recipe failure remain recorded. These checks performed no AOSP materialization, Soong invocation, Android action or Main action. Full Native/ART and Audio APEX qualification, canonical deployment, a fresh runtime generation and all original application gates remain required. The repository A08 source-integrity gate checks source presence and syntax; it is separate from these Rust controls and from Android acceptance.
