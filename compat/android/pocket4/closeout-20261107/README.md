# Pocket4 Android closeout continuation

Current state: **`BUILD_SOURCE_REPAIR_IN_PROGRESS_NOT_DEPLOYED`**. The ABI-qualified Sensor library is staged in the canonical candidate. Full Native/ART and Audio artifacts, final deployment, fresh runtime checks and original whole-application acceptance remain pending; applications remain **0/45**.

The [current state](continuation/state.json) and [latest build observations](continuation/build-observations-20261108-native-tls-audio316.json) distinguish actual completed work, preserved failures and remaining gates. The [source repair package](build-source-repair-20261108/README.md) contains independently reconstructable frozen Native, current Audio316, historical Audio and separate combined-builder source chains.

Previous states remain byte-for-byte in [continuation history](continuation/history/). Original Storage, camera, source, cleanup and test records keep their original scope. The user data images and accounts remain protected.

## Qualified source tool and Sensor staging

The [bounded source transport repair](build-source-repair-20261108/native-transport-retry/README.md) passed its four focused tests, normal offline release build and retirement checks. Its six-patch source chain reconstructs the latest 451-file public tree, including the exact GnuTLS failure classification. The two recorded Mac replay stages checked every resulting byte and executable mode. The original frozen full Native builder remains unchanged.

The earlier normal source attempt failed on a CrossDeviceSync TLS transfer with an incomplete inner error prefix and one nonzero adopted child; its failed result and retirement are preserved. The subsequent normal source owner also failed, this time on a curl 56 receive timeout with early EOF during a promisor fetch. Its inner capture was complete; all 60 adopted children exited zero and were reaped, and the original owner, cgroup and six-lock retirement were verified. It retained the original CLI and lifecycle contract, and the materialized publication remains at 268 projects. Source materialization, the original physical fixedpoint and full Native/ART qualification require actual successful records.

The [Sensor staging proof](sensor-canonical-stage-20261108/verification.json) records the qualified 482,440-byte library and the matching 1,032-byte allocation/layout contract. Canonical staging passed 43 checksum checks, with 28 install targets and 47 Android file overrides. This did not change production or start services. Installed Sensor Binder identity and death behavior still require a fresh runtime generation.

## Current Audio provider repair

The actual normal 308-to-309 migration completed on the recorded source lineage. The subsequent full Audio host-r2 build removed the earlier JUnitParams failure and exposed the original SDK35 and CTS providers still needed by its graph. That failed build preserved complete output, successful source verification/restoration and resource/process retirement; no Audio APEX qualification is claimed.

The [current Audio316 source package](build-source-repair-20261108/audio-api35-cts316/README.md) reconstructs the actual 308-to-309-to-316 lineage with five patches and exact 409-, 411- and 431-file inventories. It follows the original SDK35, CTS, ATS, dEQP and supporting providers at their pinned commits. Its nine focused checks and two normal dev-profile CLI builds passed; it performed zero release builds. The first source entry was refused at the original Native lock before any normal source command or mutation; full Audio did not start. The new entry binds the latest failed Native owner's original result, complete output, physical retirement and unchanged manifests. At the recorded observation it had passed fresh six-lock admission, normal verification of the old 309-project source and verification of the new 316-project lock, and was running normal reconcile. Earlier public prepared 309 results retain their historical scope. Current source migration, complete Audio APEX and matching payload qualification remain required.

[Native attempt 12](continuation/native-attempt12-reconciliation.json) remains FAILED and retired because Soong could not resolve `PermissionUtils`. Earlier failed source and build attempts are preserved; cleanup observations do not turn them into successful builds.

## Camera video mode restoration

The [Camera video state module](continuation/camera_video_state.py) now accepts
both permitted completion orders: restore Photo before playback verification,
or restore Photo after playback verification. Previously the latter reached
MODE_RESTORED but the terminal check required PLAYBACK_VERIFIED, rejecting an
otherwise completed sequence.

The [regression test](continuation/camera_video_state_test.py) exercises nine
public-API state-machine cases. It reproduces the original ordering failure and
preserves rejection of missing audio/playback evidence, incomplete retirement,
unclosed tasks, changed state and an unacknowledged restore action. The
[source repair record](continuation/camera-video-state-repair.json) binds the
original and fixed module hashes. These are synthetic state-machine tests;
actual Camera video/audio recording and same-URI playback still require the
complete entry and a fresh final Android runtime.

## Verified application experiment cleanup

The latest scoped cleanup accounted for all 807 candidate roots across 17 batches: 723 were actually removed, representing 5,150,584,832 allocated bytes (about 4.80 GiB), and 84 were retained for current dependencies. Deleted original and isolation paths were verified absent, retained identities and protected current state were unchanged, and the remaining reference reasons were rechecked. This byte count measures removed objects; it is not a filesystem-free-space measurement during concurrent builds.

[The compact cleanup summary](cleanup/app-retirement-20261108-summary.json) records each original receipt hash and the final audit. Current source/provenance dependencies must be released and checked again after final deployment and qualification before the retained roots and remaining build/payload history are retired. Android deployment and original whole-application acceptance remain pending.

A separate [obsolete transport cleanup](cleanup/obsolete-transport-retirement-summary.json) removed eight unreferenced transport files (516,096 allocated bytes): six exact readonly duplicates and two obsolete failed Audio308 snapshots. Original failure records and the actual Audio309 source remain available. Fresh reference, process, mount and Git checks passed before isolation and again before deletion; protected production and user-data identities stayed unchanged. This is additional to the 807-root batch and does not retire its 84 current dependency roots.
