# Preserve b05 failure and continue after a verified audit-tool repair

## Current evidence

Original batch 05 remains FAILED, job 1a1b16f06d5-fc05-78b1, exit 1. Its sole nonzero tool command was legacy AAPT badging on Calendar. The original batch contains four packages and six APKs, totalling 341,931,165 logical bytes:

| Package | Actual APK count |
| --- | ---: |
| com.MobileTicket | 1 |
| com.amazon.mShop.android.shopping | 3 |
| com.android.calendar | 1 |
| com.android.camera2 | 1 |

The independent official-tool comparison, job 1a1b26bfb80-fc05-7dfa, completed successfully. It observed the exact same Calendar APK bytes/stat/path and independently checked Fcitx as the control. Both official badging commands returned 0 with empty stderr. The legacy Calendar badging still returned 1. All eight children joined, 6,399 owned descriptors closed, and the owned wrapper's original child pidfd and parent descriptors retired normally.

This establishes that the observed badging failure depends on the parser for these bytes. It does not establish complete Calendar resource-table health or business readiness. The comparison binds two packages against the fixed 47-package reference; it does not reobserve all 47.

The current summary parser produced min_sdk=null for both Calendar and Fcitx. Neither value is decoded yet. No old result is to be filled in retrospectively.

## 1. Read existing raw artifacts before changing parsing

The fixed host reader in diagnostics/calendar-official-aapt2-raw-readback-r1 reads only the four already-published, pinned stdout files: official badging and legacy XML-tree for Calendar and Fcitx. It does not rerun a tool or read an APK/Main process.

The actual original bytes must first pass exact size/hash and held/path stat checks, full output capture, durable successful terminal, and FD closure. Then compare the concrete SDK fields in official badging with the concrete AndroidManifest.xml uses-sdk attributes. Keep absent, undecodable, explicit and defaulted values distinct. If the actual formats disagree, stop that field's interpretation rather than choosing a convenient value.

A new parser revision may then support the demonstrated format. A focused local check should use these exact raw fixtures and reject conflicting/duplicate SDK fields. Preserve permission names exactly; no stripping, rewriting or SDK/integrity override is allowed. Retain the old null outputs and all old raw files.

## 2. Make a narrowly revised collector

Build a new source revision from the frozen actual collector and the now-successful official-tool binding:

- Retain typed successor guard, selected-package complete APK set/stat/UID/CE-DE checks, action lease, timeout/join rules, signature verification, PM certificate comparison, exact raw stream capture and descriptor closure.
- Retain the known legacy tool/dependency pins for Java, apksigner and XML-tree. Bind the official AAPT2 executable and seven dependency ELF records separately, with its read-only controlled private RUNPATH layout and every required absent-library/dir check.
- Use official AAPT2 only for the badging operation. Keep a normal apksigner verify and original XML-tree command for each APK. The normal audit requires all three primary commands to succeed; it does not include an intentionally failing legacy badging command.
- Require clean official badging stderr under the same explicit policy proven by the comparison. Keep complete raw output and stop on any mismatch.
- Incorporate only the SDK parsing change demonstrated by actual raw output. Do not infer that the official tool version alone validates APK resources.
- Use the existing owned-libffi lifetime wrapper. Retain exact process descriptor identity and original child pidfd retirement; do not introduce an FD allowance.
- Keep no grant, install, UI, launch, input, lifecycle or ADB action. Effective permission grants and business readiness remain independent and unknown.

This is a new source and a new explicit corrective run; it is not a replay of the old failed job. The prior collector and all prior receipts stay immutable.

## 3. Close batch 05 with a complete corrective audit

Before advancing the original sequence, run one independently claimed corrective audit of the same four packages and all six APKs. Use the actual current typed guard and explicit scope; require their bytes, UID, data identities and signatures to match the pinned scope. No package is skipped because its previous row looked successful.

The corrective job must produce the expected 18 primary commands, complete per-base/split manifest/signature/declared-permission coverage, original stdout/stderr, full final descriptors/leases, and a complete authoritative successful terminal. Its new output root, source pin, request pin and job key must be linked to original batch 05 and its exact failed job. Unknown or failed corrective outcomes stop the sequence and cannot be automatically retried.

The successful two-package diagnostic cannot replace this six-APK audit. It has a different source and schema, eight rather than eighteen commands, and explicitly reports all_commands_succeeded=false because it preserved the legacy failure.

## 4. Admit continuation through a versioned gate, not a replacement success record

The existing r2 gate and its original state directory remain unchanged. Its recorded STOP is correct: check_success requires a successful terminal, the frozen original collector, three commands per APK and all_commands_succeeded=true.

A separately reviewed gate revision must read the original ledger and an additive, exact repair record. It must:

1. Revalidate original batches 01–04 with the unchanged original success checks.
2. Bind the exact original batch-05 intent, submission, failed terminal, raw stdout and decoded artifact. Preserve original_state=FAILED.
3. Require the explicit corrected collector/request/job for all four original packages and six APKs, and independently validate its complete success and all unchanged identity/integrity/resource constraints.
4. Record remediation_state=VERIFIED only for that specific successful corrective job. It must never rewrite the old job as successful or accept a generic waiver.
5. Offer the next original coverage partition only after this linked remediation is complete. The final report must distinguish original failures, corrective successes and current complete coverage.

The remaining b06–b13 coverage is 31 packages / 65 APKs. Their old unclaimed requests and keys remain unsubmitted. If the corrected collector is used for them, prepare an explicit linked plan revision with new source/request pins and new keys before any claim; keep the original planned entries as unsubmitted historical records. Do not edit those old frozen requests in place or create a fresh empty ledger that omits the failed predecessor.

No gate transition or runtime submission is performed by this plan. No production-ready or cleanup eligibility is asserted.
