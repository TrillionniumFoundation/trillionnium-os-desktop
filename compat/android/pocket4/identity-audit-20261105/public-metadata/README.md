# Current identities and APK signatures for all 45 launcher Apps

All 45 selected installed packages now have qualified package identity observations, and all 86 observed APK files passed the real pinned `apksigner verify --verbose --print-certs` command. The set contains 45 base APKs and 41 splits. Each package's base and splits have matching signer certificate fingerprints. No signature rejection was observed.

These are file identity and signature results. This audit adds no business-flow passes, does not prove a running ARM translation engine, and does not mark any whole App production ready.

## Actual observations

The original audit ran from 2026-11-05 11:02:52 to 11:04:20 UTC against the fixed, held Main epoch. Fresh PackageManager queries covered the same 45 launcher packages before and after the run. Their UIDs and versions were unchanged. Each installed base/split file was opened through the held Android root, streamed into SHA-256, and passed by inherited descriptor to the actual host verifier. Before/after hashing and fresh installed-path inode readback qualified file stability. The selected SDK/JRE/signer dependency hashes were checked before and after use.

The original wrapper exited **2**, with only **34/45** combined identity/manifest gates passing. That original outcome is preserved. The underlying 86 signature checks had all passed. Ten system Apps encountered resource-table warnings and `android:icon` lookup errors in the pinned legacy `aapt` badging reader. The remaining test fixture emitted an empty `versionCode` field and the strict original parser stopped before its final file readback.

The gaps were resolved through separate observations:

- A retained-output reader exported the original tool outputs without invoking Android or a signature verifier again.
- A targeted read at 11:18:22–11:18:24 UTC captured the binary manifest and stable current path of the same exact APK bytes for nine packages. This independently filled the fixture's missing after-readback. It ran zero signature-verifier commands.
- The separately completed Calendar/Gallery metadata capture supplied those two exact APK manifests. Their hashes match the original verified files; their original full-file stability checks had already completed.
- The existing pinned binary-XML decoder successfully decoded all eleven exact manifests without a decoder change. Package names, numeric declared versions and SDK fields agree with the PackageManager observations. `local.pocket4.fixture` actually has **no declared versionCode**; its observed PackageManager version is **0**. Both facts are retained without inventing an attribute.

`installed-app-identities.json` records the resulting package-level projection and each APK's hash, signer certificate SHA-256, verified signature schemes and manifest source. `manifest-gap-projection.json` records the selected attributes from the independent binary-XML evidence. Neither projection edits the original failure receipt.

## Resource evidence

The original unit was bounded to one CPU, CPU 20, 768 MiB memory, zero swap and a 720-second lifetime. Its actual peak reached **805,306,368 bytes**, and `memory.events.max` reached **25,708**. OOM and OOM-kill counts were zero. These numbers show memory-limit reclaim pressure; this was not a zero-pressure run. The collector streamed 10,338,313,993 hash-input bytes, including before/after passes.

The targeted nine-package reader used one CPU, 256 MiB, zero swap and a 300-second limit. Its measured peak was **111,755,264 bytes**, with all recorded memory events zero. Both processes completed without a tool timeout. Main was neither restarted nor reconfigured.

## Scope and limits

The observations span several bounded per-App windows; they are not one atomic snapshot of all packages. All calls bound the same held Main epoch. No App was installed, resigned or launched by this audit, and no existing App permission was changed. It read installation files, technical PackageManager metadata and its own retained receipts. It did not read accounts, private keys, messages, photos, calendar event content or other user documents.

The ten original `aapt` resource-table/icon errors remain explicit metadata warnings. Successful binary-XML identity decoding does not qualify every resource or actual App rendering. Actual UI behavior belongs to separate business acceptance.

The certificate fingerprints and successful verifier commands establish cryptographic integrity of the observed APKs under the pinned verifier's checks. They do not establish publisher trust or source authenticity. Selected SDK/JRE/signer dependencies were frozen, but the entire host native-library set was not.

ABI fields are observations from PackageManager, with available APK-native-code metadata recorded separately. They are not evidence that a specific ARM engine is mapped in a running process. Runtime engine mapping remains unqualified by this audit.

## Review and publication

The public projection excludes installation paths, raw package dumps, certificate distinguished names, raw process maps, binary manifests, APKs and private journals. The original receipts and full manifest bytes remain in the private workspace. The local reconciliation code checks their exact hashes. `source-manifest.json` pins the frozen collector, the separate readers, the local reconciliation, the parser regression and the selected public files.

The retained-output export initially omitted `fchmod` after a restrictive umask, so the operator reader could not open the new gzip file. The targeted reader corrected only that new, hash-pinned technical export to its intended `0640` mode. Original private journal permissions and Android file permissions were unchanged. This access correction is preserved in the targeted receipt.
