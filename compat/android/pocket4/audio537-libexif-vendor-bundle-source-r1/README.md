# Audio537 original libexif and vendor policy bundle producer

This capsule completely reconstructs the current Audio producer from the published Audio444 recipe. It carries the original provider closures, source recovery v2, capture of seven vendor originals before rsync, the fixed SDK14 dependency exception, and the normal vendor policy bundle entry. It adds the actual missing camera dependency `libexif` from the same pinned Android superproject.

## Exact producer identity

| Role | Commit | Complete root tree |
| --- | --- | --- |
| Published Audio444 | `5f8097c23b8ff8dad107f3df2db5a219ff0b6b27` | `5d6fa7d51133efb5e91a5b1734de6aa597f1949e` |
| Qualified Audio537 | `e85ad204e6286be5cba173cc5037884e9fa1ac83` | `e680ae246de9a0edfb1c8aaa9b3e1be392e5d465` |

The complete patch contains 979 changes: five modifications and 974 additions. The inventories enumerate all 534 base files and all 1508 current files, with modes, whole SHA256 and Git blob identities. All compile-time fixtures are included. These are independent device recipe identities, separate from the maintained aggregate repository's branch commits. The Audio project bound is exactly 537; the Native producer has its own independent capsule and capacity.

## Actual missing provider repair

The real strict CP2A/user bundle attempt `desktop/1a1d64f13a7-392-927` reached Soong and failed because `libcameraservice_device_independent` could not find `libexif`. That failed attempt and its complete recovery are preserved. This successor retains the previous 536 project objects unchanged and adds only `platform/external/libexif` at `e180c53a25cc0f26e6e0caf4a2708c41b8ec5214`, selected by the original superproject `28f0bbddc24d56c8ec5a8df5342ac7a292184039`.

The single `libexif` cone includes 68 original files, 1,500,241 bytes, including root build, configuration and license files. No new large-file exception is introduced. The original shared-library definition, camera consumer and all 14 direct native/aconfig provider definitions remain present. Whole original bytes, missing files, symbolic links, hard links, executable-bit changes, project pin changes and scope changes are exercised by the new tests. The existing SDK14 exception remains fixed to the original 17,704,039-byte jar's exact SP, commit, path, blob, size and SHA; the general 16 MiB bound is unchanged.

## Reconstruct and run the current ordinary tests

After verifying the externally pinned `FILES.sha256`, choose new absolute work, report and Cargo target paths outside the capsule and recipe:

```sh
sha256sum -c FILES.sha256
python3 -I -B replay_capsule.py --capsule "$PWD" --work /absolute/new/audio537-recipe --report /absolute/new/audio537-replay.json
python3 -I -B run_ci_tests.py --capsule "$PWD" --recipe /absolute/new/audio537-recipe --report /absolute/new/audio537-tests.json --target /absolute/new/audio537-cargo-target --jobs 2
```

The replay verifies the original commit objects and reconstructs both complete root trees. The CI runner compiles the six selected Rust harnesses from the fresh producer, requires the exact 42 source and 111 updater identities, validates every terminal line and complete summary, and verifies all producer files, modes, whole hashes and filesystem identities before and after. Git and rsync are required. The historical receipt is not counted as a new CI run.

## Existing actual qualification and boundaries

`normal153-proof.json` binds desktop job `1a1d68b1d58-392-950`: all 153 distinct current tests and all 149 previous names passed; both release tools, the fixed lock and plan, the fixed bundle CLI, and the actual v2 recovery command passed. All 25 owned commands retired. Independent retirement `1a1d68f2daa-392-958` verified 27 original PIDs absent, original cgroups absent, all three source locks and the private cache lock jointly available and released, all 84258 predecessor source files unchanged, and all 1427 old plus 1508 current recipe files unchanged.

The normal bundle command selects exactly `selinux_policy_vendor`, `vendor_manifest.xml`, `vendor_compatibility_matrix.xml` and `checkvintf`, using the Audio source mode with strict CP2A/user inputs. This capsule does not qualify an emitted vendor bundle, CP3A policy compatibility, VINTF compatibility, installed applications, runtime security or production readiness. The separately reviewed IntentResolver security delta is applied as a later successor. No APK, APEX, compiler cache, credential or raw projection journal is included.
