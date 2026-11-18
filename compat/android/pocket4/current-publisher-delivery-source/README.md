# Current publisher delivery APK verification

This increment adds a separate, explicit source identity gate for APKs delivered as individual files by Google Play through the official Aurora client. It does not change the existing 20 gate files or the meanings of their schemas.

## Actual result

On 2026-11-18, the fixed original transaction supplied seven applications as 23 APKs totaling 942,526,044 bytes. SDK 37 verified every APK signature against the external current GET_ITEMS certificate set. All publisher delivery SHA-256 and SHA-1 digests matched the actual files. Full bounded ZIP decompression and CRC checks completed for every member. Every native member has its own byte count and SHA-256 in the receipts.

| Application | Android package | Version | Version code | APKs |
| --- | --- | --- | ---: | ---: |
| Hyatt | com.Hyatt.hyt | 26.11.1 | 26111078 | 3 |
| Hilton | com.hilton.android.hhonors | 2026.11.3 | 1034 | 4 |
| Marriott | com.marriott.mrt | 10.82.0 | 680 | 3 |
| United | com.united.mobile.android | 4.2.103 | 3621 | 4 |
| IHG | com.ihg.apps.android | 5.111.1 | 50023808 | 1 |
| StreetEasy | com.zillow.android.streeteasy | 2026.47.0 | 23075 | 4 |
| ANA | jp.co.ana.android.tabidachi | 7.7.1 | 343 | 4 |

The current version and expected signer came from the external original Google metadata, not from the APK being tested. The version observation is scoped to the original transaction and unchanged device/profile/channel. This increment does not claim global release availability or authorize a different region/profile retry.

The six multi-APK groups were assembled locally into deterministic ZIP_STORED containers. Google did not provide these archives. Their source records say so explicitly. IHG uses its original single delivered APK.

The original 146 controls and 39 new controls all passed. Source and SDK tool identities were checked before and after the actual run. The actual seven-package run completed with exit 0. The detailed signed-input receipts and original small metadata are included in this package; the APK bytes and large local containers are referenced by exact paths, sizes, and hashes and remain outside this source/evidence archive.

## New schemas and trust boundaries

Candidates use one of:

- pocket4-publisher-delivery-apk-set-candidate-v1
- pocket4-publisher-delivery-standalone-candidate-v1

Receipts use pocket4-verified-publisher-delivery-source-receipt-v1.

The candidate itself requires an external SHA-256. It pins the exact metadata file, per-package delivery record, complete original transaction, every delivered member's SHA-256 and SHA-1, the native ABI inventory, and the local container when one exists.

The verifier holds the original candidate, evidence, delivery APKs, and local container through verification. File type, single-link ownership identity, complete content hashes, and named-file/inode bookends are checked before atomic receipt publication. Replacing a held source with identical bytes at a different inode fails.

Current metadata must have GET_ITEMS origin, AVAILABLE restriction, the expected package/version, and the literal certificate set. It must exactly agree with the original per-package record, and that record must occur exactly once in the original transaction. A stopped transaction, unavailable region result, paid offer, malformed certificate encoding, missing delivery member, or digest disagreement fails. This is an offline check of externally pinned evidence; it does not reacquire credentials or replay authenticated transport.

The locally assembled container has a fixed member order and names, no directories or extra members, ZIP_STORED compression, fixed metadata, exact local ZIP64 size fields, and bounded central-directory/EOCD boundaries. It cannot be described as a publisher archive. Every extracted APK must match both original delivery digests.

The actual signature and SDK process is the existing verify_apk.verify path, including SDK 37 aapt2 and apksigner, binary AXML identity, and actual signing-block certificate matching. The six split groups reuse the existing strict binary member and dependency closure implementation. Required split types, feature/config dependencies, common package/version/signers, and all native member identities must agree. There is no base-only fallback.

Full member CRC checks are performed after SDK verification. The receipt records an aggregate over canonical sorted identity records for all ZIP files and an explicit byte-count/SHA-256 record for every native member. The original whole-APK hash is checked again afterward.

## IHG and legacy ABI observation

IHG is a complete standalone APK with 28 native files across arm64-v8a, armeabi-v7a, armeabi, x86, and x86_64. Eight of those files are ARM64. It is not a no-native APK.

The new standalone schema has a finite, explicit observation for legacy armeabi bytes: ELF32, little endian, ET_DYN, and EM_ARM. It records those bytes and their exact hashes. It does not claim support for executing that ABI. The old ABI map, old schemas, and old rejections are unchanged.

Every new candidate must actually include an ARM64 payload. Legacy-only/ARM32-only candidates fail. The reviewed input ABI is ARM64; the actual Android ABI selection, translation, loaded libraries, and business behavior still require runtime observation. IHG's other ABI files remain part of the intact publisher-signed APK and its full source inventory.

## Consumer integration

The verifier returns the existing application.expected_input shape:

- version_code
- apks: complete normalized names, byte counts, and SHA-256 digests
- source_receipt: absolute path, bytes, and SHA-256

The production runtime_plan consumer pins the receipt file as opaque bytes and matches the actual installed input against the complete expected APK set. It does not reinterpret this new receipt as an older publisher archive schema. Source verification responsibility remains with this explicit producer gate. Consumer pinning alone does not verify publisher identity or grant readiness.

Invoke the new gate with an externally pinned candidate:

    python3 -I -B gate/verify_publisher_delivery.py INPUT \
      --build-tools SDK37 \
      --candidate CANDIDATE_JSON \
      --expect-candidate-sha256 EXPECTED_SHA256 \
      --receipt-output NEW_ABSOLUTE_RECEIPT

For a set, INPUT is the explicitly local container. For a standalone APK, INPUT must be the original delivered path. Existing receipts are never overwritten. Receipts are bounded to the same 8 MiB consumer limit.

## Controls and retained failed attempts

The original 20 source files are unchanged. test_candidate.py requires two adjacent public fixture JSON files from current-app-acceptance; the exact published Firefox and SZZC fixtures were restored from commit 088196e9c761d51da7a4ee5fe0b372aef490bb40 and checked against their Git blob identities.

The first resource preflight exited before tests because this user scope does not expose cpuset.cpus.effective. The next attempt used actual scheduler affinity plus memory.max, memory.swap.max, and cpu.max; it exposed the missing fixture files. Those failures remain in the evidence. No old test was removed, renamed, or weakened.

The final run passed all 146 original controls and 39 new controls. The new controls include external signer/version/availability rejection, delivery/transaction mismatch, missing splits, SHA-1 verification, malformed local container boundaries, full-resource CRC corruption, legacy-only input rejection, wrong legacy ELF class/machine, source replacement with identical bytes, existing receipt protection, and receipt size bounds.

All source receipts and output fragments explicitly leave installed, runtime_qualified, and production_ready false. Native compatibility, device profile matching, and legacy armeabi execution support also remain false. No application code was executed, no account was accessed by this gate, and no Android package was installed.
