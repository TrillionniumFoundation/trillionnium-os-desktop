# Clock and Documents live UID/GID mapping

This is a source-only successor for the four Clock/Clock-IHG/Documents preparation graphs. It fixes five definite host/guest identity comparisons before the next native application cohort is built. It does not modify the frozen native PR 322, its CI inputs, the canonical CURRENT, installed APKs, Android images, or application data.

## Observed failure

The existing `HeldTarget.open_root` opens a guest path through the held root FD while the caller remains in the host user namespace. Consequently, `os.fstat` reports host ownership. The selected Clock protection readers, Clock alarm database reader, and both Documents package identity readers compared that ownership directly with the Android guest UID/GID.

A bounded read of `/etc/droidloom/cell.json` found `subordinate_uids` and `subordinate_gids` both `{start: 100000, count: 100000}`. The protected configuration is 7,656 bytes with SHA-256 `f64a9f9a63e76ac2bf765e8f98bb2f9a91a326b38f86b6e3c4ac512d60303bdc`. It was unchanged before and after observation. For this mapping, guest Clock UID 10063 maps to host UID 110063; guest Documents UID 10022 maps to 110022. A correctly owned directory therefore failed the previous comparison.

The configuration observation explains the defect; the new reader never uses configuration JSON as runtime authority. It opens `ns/user`, `uid_map`, `gid_map`, and the GID metadata in `status` relative to the already held Main proc FD. The original `MainView` guard and target lease remain in force. Kernel namespace type, actual map bounds, original Main root UID, live Main root GID, namespace identity, map bytes, and file metadata are checked around the observation. The first successful namespace/map binding is retained in the same process-local view and must remain identical on subsequent calls. All new metadata FDs close in `finally`; none is passed to a child or added to the original seven execution authority descriptors.

## Narrow source changes

| Preparation index | Existing scope | Changed business reader |
| --- | --- | --- |
| 4 | Clock timer remaining, expiry, alarm | `clock_protection.snapshot`, `clock_alarm_reader.data_identity` |
| 5 | Shared Clock timer / IHG coordinator | `clock_protection.snapshot`; IHG behavior is unchanged |
| 6 | Documents SAF | `documents_saf_core.identity` |
| 7 | Documents search and sort | `documents_package_fixture.identity` |

The four `app_common.py` copies retain their complete original byte prefix and append the same metadata helper. Of the 106 original source files, 97 are byte-identical. The other five files change only the listed ownership observations and comparisons. Existing package UID/version/SHA checks, inode checks, permission gates, guest UID use in Android commands and diagnostics, original business state machines, cleanup, cancellation, unknown-outcome handling, and false whole-application acceptance flags remain in force.

## Verification and limits

`HOST-CONTROLS-FINAL.json` records six focused controls on Pocket4 under a bounded root host process, using actual proc, namespace, map, and file descriptors. They cover valid mapping, distinct UID/GID bases, malformed or ambiguous maps, boolean/out-of-range IDs, a foreign Main binding, changed maps or file metadata, wrong namespace type, and descriptor closure. The Main guards in these isolated controls are explicitly modeled; these controls grant no Android runtime credit.

All four source graphs pass their original bootstrap validation with exact external preparation pins, and the wrong-pin control refuses. The original IHG entry has no `inspect-source` command. An initial audit invocation using that absent command failed with argparse exit 2; `HOST-CONTROLS.json` retains that failure. The follow-up invokes the existing `bootstrap(args)` function without entering a runtime mode. No source or runtime gate was changed to accommodate the incorrect audit command. The earlier local test environment had UID 1000 and a single-ID user namespace, so the host descriptor controls were completed on Pocket4 root rather than credited from that environment.

`adapt_sources.py --output <empty-directory>` reproduces 111 source/preparation outputs byte-for-byte from the published, hash-checked inputs. `prepare_selection.py` stages a complete 13-entry selector and compiled-catalog candidate over the reviewed Calendar/Gallery proposal, replacing only indexes 4–7. It does not adopt either file. The native owner must compile the new catalog into a subsequent cohort and complete the original release adoption protocol before these sources are executable through the selected native driver.

The prestart audit also checked the latest inventory versions and APK-role sets against the dispatcher and selected profiles. The dispatcher supports a 39-application required set, and the Clock and Camera v3 requirements match the existing SDK37 signature records. Missing business executors, the protected Meituan signer migration, delivery metadata refresh, and actual Android business validation remain their existing separate blockers; this source repair does not claim to close them.
