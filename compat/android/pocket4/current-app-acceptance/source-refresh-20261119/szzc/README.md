# SZZC current publisher source, code 330

This packet selects the actual publisher APK `com.szzc` 9.6.3 / code 330, replacing only the previous source record 9.6.3 / code 329. Its complete 220,498,418 bytes have SHA-256 `1461b66c3dc3497989eb4a71361b56584dca1caa6b8120ebc5c4c1f240782c03`. SDK37 verifies its manifest identity and the retained official signer `d85bed4d2a7c08e1b6b5f0097d6c66a79a5b12b58d97e794d3b5c5bff2aeaf44`.

## Actual original verification

The original SDK run completed three commands, each with exit 0, its original PIDFD held through reap, and ECHILD afterwards. All 28 source/tool full-SHA and F9 bookends passed. All 13,881 original ZIP members have complete EOF/CRC and SHA records. Independent retirement checked all five original clients and units, re-read the complete original APK once, and retained both network timeouts and the first strict native-inventory failure as failures. `inputs/source-receipt.json` is the complete original 4,231,750-byte proof; it is not a shortened inventory.

## Native runtime blocker remains

The original publisher APK contains 118 native members. Four named x86 helper payloads have an ELF architecture different from their packaging directory: `libexecmain_x86.so` and `libexec_x86.so` under both `arm64-v8a` and `armeabi-v7a`. The two files under the selected ARM64 directory are ELF64 / machine 62; the two under the ARM32 directory are ELF32 / machine 3. The full original diagnostic, exact whole-APK and member hashes, header bytes, and all 118 rows are retained and consumed. The generic native validator is unchanged and still applies to the other 114 members. The four cross-ABI records explicitly have `generic_native_guard_passed=false`. No helper or library was executed.

`native_source_layout_qualified`, `native_compatibility_qualified`, `installed`, `runtime_qualified`, `business_qualified`, and `production_ready` remain false. `native_runtime_blocker_retained` is true. Both cross-ABI files in the selected ARM64 directory remain visible in the selected registry and business preflight.

## Current-source consumer

`override_szzc.py` deterministically reconstructs four current metadata outputs. Only the SZZC source row and provenance references change; the other 38 state/preflight rows, other 28 required third-party records, companion, three exclusions, installation/migration/runtime gates, and existing history remain unchanged. `verify_current_inputs.py:verify()` consumes fixed original evidence and reproduces all four selected outputs. It does not rerun SDK, read an APK, or refresh a network observation.

The top-level source-refresh consumer must select these four outputs while retaining the original United and provider reconstruction. Public metadata does not renew the restricted Play TTL for Best Buy, National or Hertz. The latest release must be rechecked before activation. No owner CURRENT pointer or Android user data was changed. The old physical package remains retained pending a separate exact dependency/cleanup review.
