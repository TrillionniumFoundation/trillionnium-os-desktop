# IntentResolver security producer on Audio537

This capsule is the exact six-file security delta from the complete Audio537
producer `e85ad204e6286be5cba173cc5037884e9fa1ac83` to
`1a5eb38dd809a31b18284839add632a049578f68`. The base contains 1,508 files and the
security producer contains 1,511 files. All 1,505 unaffected files remain exact.
Audio537's source lock, source library, maximum 537 projects and Cargo lock remain
unchanged. Native643 retains its separate producer and capacity constraints.

The delta adds the fixed `intentresolver-security-build` command, its original
IntentResolver provider fixtures and the official caller-package patch already
qualified by the ordinary tests. It changes three updater files and adds three
compile-time source inputs. The actual upstream Kotlin patch is 721 bytes with
SHA256 `0e66877febce78d36d50a71e7787a844593f4c728744cade66d8d7833b6ee752`.
It binds URI caller checks to the launching activity's package. The original
Android.bp, privileged status, platform APIs and signing selection remain exact.
Normal and interrupted recovery restore the original source bytes, permissions
and timestamp. Source, provider or patch drift is rejected before projection.

The command selects the actual `IntentResolver` Soong target using the existing
Audio source and projection machinery, fixed CP2A source release, `user` variant,
strict missing-dependency checks and enabled neverallow checks. It accepts no
target, output, source-lock or variant override and uses its separate
`android-user-intentresolver-security-out` directory. The dependency declaration
includes `setfattr` from the existing `attr` package.

## Complete source authentication and replay

`base-files.json` and `head-files.json` list every original source file, byte
count, SHA256, Git blob and mode. `git-objects/` contains the actual raw base and
head commit objects. The verifier authenticates each commit hash and its root
tree, reconstructs complete Git tree objects from both full inventories, and
checks that exactly the declared six source files differ. `preimages/` contains
all three changed originals and `source/` contains all six complete postimages.
`intentresolver-security.patch` is the exact actual tested patch, with SHA256
`28c100170be847558adaf82103573d080c8aa34181f7d823c37f4d89f25bf5d3`.

The workflow must pin the SHA256 of `FILES.sha256` outside this capsule. The
inventory covers all members, including the verifier, CI runner and evidence;
the verifier rejects extra, missing or changed capsule inputs. A hash merely
read from inside the capsule is not an external pin.

First reconstruct the complete base using the separately published
`audio537-libexif-vendor-bundle-source-r1` capsule. That capsule's inventory is
fixed at `486300e2a033679a87776c68bff4324eff11b53459de3c9712122788f2a76572`.
Then invoke this verifier with the externally pinned security inventory:

```sh
python3 -I -B verify.py --inventory-sha256 "$SECURITY537_INVENTORY_SHA256" \
  --audio-source /absolute/verified-audio537-base \
  --output /absolute/new-security537-producer \
  --report /absolute/new-security537-replay.json
```

The Audio source is copied to a fresh independent destination. Only its root
`.git` directory is omitted; nested metadata, extra files, extra empty
directories, symlinks, hardlinks, aliases and changed modes are rejected.
Every original input file and directory retains its F9 identity across the
copy and full replay. F9 records device, inode, mode, owner, group, link count,
size, nanosecond modification time and nanosecond change time. The input Git
directory is not operated on or copied.

The verifier initializes private Git metadata, stages all original files and
requires the actual base root tree
`e680ae246de9a0edfb1c8aaa9b3e1be392e5d465`. Normal Git check/apply, reverse-check,
reverse and forward replay must produce the complete head tree
`c5add898f97018c61515441e689bb854efc793fe`, base tree, then head tree again.
Every stage also verifies actual bytes, modes, Git blobs and full membership.
Git children use umask 0022 even when the private outer operation uses umask
0077. This controls new source file modes while preserving private work-directory
permissions. The verifier authenticates the raw commit objects; it does not
claim to have reconstructed all historical Git ancestors.

After compilation, `verify.py --producer /absolute/security537-producer`
revalidates all 1,511 actual files and the complete root tree. It can also parse
the actual four-test output with `--tests-log`; parsing a supplied log does not
itself claim a new execution.

## Existing actual ordinary evidence

The original, unchanged evidence is under `evidence/`. `ordinary-325.json`
records 280 updater tests, the separately executed original EROFS repack test,
42 source tests and two release-queue integration tests. Both release tools
were actually built and their command entries executed. `ordinary-326.json`
adds the original DMA layout integration test. That test has its own exact
103-file minigbm source and is linked to the same original 325-test proof; its
vendor commit is not mislabeled as the security producer commit.

`independent-retirement.json` binds both actual proofs, records all 38 original
PIDs returning ESRCH, three cgroups absent, both retained release tools and all
1,511 producer inputs preserved. Staging, normal and DMA retirement receipts are
included unchanged. Historical ordinary evidence is preserved for provenance;
it never substitutes for newly executed CI.

## Fresh CI

`ci-job-snippet.yml` is intended for an independent Linux job after checkout,
Rust setup and the existing host dependencies. The containing workflow supplies
the external security inventory pin. It reconstructs the complete published
Audio537 base, applies this exact security delta and runs `run_ci.py` with a
fresh Cargo target outside every input tree.

The runner actually compiles and executes all four security-specific tests,
strictly requires their four unique passing identities and one complete
successful Rust terminal, then builds both release tools and executes their
help entries. A failed, ignored, extra, repeated or truncated test record fails
the job. Entire producer membership, SHA256, Git blobs, modes and file/directory
F9 are checked again after all commands. Reports and logs use fresh independent
paths; existing targets and alias paths are rejected.

`test_verifier.py` retains the original ten contradictory-log counterexamples
and path-alias controls. It adds malformed or repeated harness records,
duplicate JSON keys, whole-source mode/membership/F9 changes, nested Git entries
and fresh Cargo target boundaries. These verifier controls do not count as Rust
tests or Android acceptance.

## Acceptance still required

This source capsule and its ordinary tests do not establish a completed Android
APK build, CP3A identity, production signing, full November bulletin coverage,
installation or final-device runtime acceptance. The manifest and replay/CI
reports keep Android builds and installs at zero and runtime/production false.
Those gates require their actual artifacts, binary inspection and device tests.
