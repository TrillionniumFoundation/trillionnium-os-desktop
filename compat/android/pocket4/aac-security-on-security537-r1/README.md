# AAC security producer on the complete Security537 parent

This capsule carries the exact tested producer change from Security537
`1a5eb38dd809a31b18284839add632a049578f68` to
`9785ba83d9d37509e02462a0aa7c84d1c991006c`. It changes two updater source files
and adds six source inputs. The complete parent contains 1,511 files; the new
producer contains 1,517. All 1,509 unaffected inputs remain exact, including the
Audio537 source lock, its source library and Cargo lock. IntentResolver's
previous security correction remains part of the unchanged complete parent.

The official AAC correction is commit
`6b8c6cbab2b747ffc0c39721ca18651cddc8a373` in
`platform/external/aac`. Its parent is the actual selected source pin
`41f344ffc0bacea87cac5bb1756bd40761265d1e`. The complete 4,443-byte upstream patch
has SHA256
`ab9f6ad9fc6bc32825ef2c3ae4e88e6aea7e5a1e3c43a379fb9b50665ac3eb7d`.
Both production changes are retained: the decoder frees only storage allocated
by the failing call, and the caller cleans up its retained decoder handle on
failure. The patch also retains upstream's Android.bp test declaration and the
complete `LibSbrDecTest.CreatePsDecResetUAF` regression source.

## Normal build entry and recovery

The fixed `aac-security-build` entry selects exactly
`com.android.media.swcodec` and `libSBRdec_test` on the original Audio537 source
profile, `droidloom_x86_64`, source release `cp2a` and `user` variant. Missing
dependencies remain errors and neverallow checks stay enabled. The command
accepts no arbitrary target, output, variant or source-lock override and uses
its own `android-user-aac-security-out` directory.

The complete four-file upstream delta is a temporary normal source projection.
The original three files and initially absent test enter the existing version 2
recovery journal. Exact original bytes, permissions and nanosecond modification
times are restored on both normal completion and interrupted recovery. The
effective Android.bp and other three fixed files are checked by complete SHA256
after the general source projection and before Soong. A changed source, patch,
alias or pre-existing foreign test is rejected before projection.

The shared source lock is unchanged: this correction does not advance the
selected superproject, substitute an SDK, relax provider checks or claim CP3A
source identity. An added test directory that was absent before an Android
build must be handled by the owned-directory retirement proof; removal of its
test file does not authorize deleting a pre-existing directory.

## Complete source authentication and replay

`base-files.json` and `head-files.json` describe every source file with its size,
SHA256, Git blob and Git mode. The raw commit objects in `git-objects/` bind
those full inventories to these original roots:

| Role | Files | Git root tree |
| --- | ---: | --- |
| Security537 parent | 1,511 | `c5add898f97018c61515441e689bb854efc793fe` |
| AAC330 successor | 1,517 | `c9e0b5771b9e2a169ca4236c5c379446e9592760` |

`preimages/` contains the two changed originals, `source/` contains all eight
complete postimages, and `aac-security.patch` is the actual tested producer
delta. The verifier checks both raw commit identities, reconstructs both full
root trees, checks the exact two-changed/six-added scope, and verifies every
postimage and preimage against its whole-source inventory. `official/` retains
the captured official packet, commit metadata, three original AAC files, four
fixed files and complete upstream patch; the verifier joins their whole hashes
and Git blob identities to the producer fixtures.

The containing workflow must pin `FILES.sha256` externally. The inventory
covers all capsule files, including the verifier, CI runner, ordinary evidence
and upstream inputs. An internal self-reported digest alone is not an external
pin. Reconstruct the published complete Audio537 producer and its Security537
successor first, then apply this capsule:

```sh
python3 -I -B verify.py --inventory-sha256 "$AAC330_INVENTORY_SHA256" \
  --security-source /absolute/verified-security537-producer \
  --output /absolute/new-aac330-producer \
  --report /absolute/new-aac330-replay.json
```

Only the parent producer's root `.git` directory is skipped during the complete
copy. Nested Git entries, aliases, hardlinks, unexpected files or empty
directories, altered modes and reused output paths are rejected. Every source
file and directory retains its F9 identity across copying and replay. F9 records
device, inode, mode, owner, group, link count, size and both nanosecond timestamps.
The replay reconstructs its own Git metadata and verifies actual Git root trees
after forward, reverse and second forward application. Git children use umask
0022 while the outer work directory may remain private.

## Actual ordinary evidence

`evidence/ordinary-329.json` contains the real successful 284 updater tests,
one separately executed original EROFS repack test, 42 source tests and two
release-queue integration tests. Both normal release tools were built and
their command entries executed. `ordinary-330.json` adds the real DMA layout
integration test against its private 103-file original minigbm source. That
vendor source identity is retained separately from the producer commit.

`independent-retirement.json` joins both proofs, all 56 original PIDs returning
ESRCH, three absent cgroups, all 1,517 preserved producer inputs and the two
single-link, mode 0555 release tools. Original staging, normal and DMA retirement
receipts are retained. These 330 historical executions prove the existing
ordinary qualification; they do not count as new CI executions.

## Fresh CI

`ci-job-snippet.yml` describes an independent Linux job after the existing Rust
and host build dependency setup. It authenticates and reconstructs all three
producer generations, executes the seven verifier controls, then runs
`run_ci.py` with a fresh Cargo target outside every input and report directory.

The runner compiles and executes exactly the four AAC Rust tests: official
four-file patch/recovery, changed-input rejection, the strict fixed normal
request, and CLI override rejection. It requires their four unique passing
identities and one complete successful Rust summary. Additional failures,
ignored tests, repeated records, extra successes and truncated summaries all
fail. Both release tools are then compiled afresh and their command entries
executed. Complete 1,517-file bytes, Git blobs, modes, directory membership and
F9 are checked again after CI, including failure paths. The runner retains raw
logs and a final report; it never reuses the historical host ELF binaries.

## Remaining artifact and runtime acceptance

The ordinary Rust tests and this capsule do not establish an Android APEX build,
execution of the official C++ regression, production signing, APEX installation,
binary semantic qualification, complete security-bulletin coverage or device
runtime acceptance. The fixed two-target build compiles the regression target;
running that original regression is a separate recorded action. APEX content,
ELF identities and the original library consumer chain must be checked on the
actual generated artifacts. All such acceptance fields remain false here.

The two `official/commit/*.gitiles-raw` files preserve complete original Gitiles
responses, including the anti-XSSI prefix. They are raw transport evidence;
removing the prefix would change the authenticated upstream response bytes.
