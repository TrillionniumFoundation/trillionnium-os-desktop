# One current NDK APK: normal signature and manifest audit

This independent candidate audits only `com.example.ndk_tests`. It reads the actual immutable 48-package scope, protects that complete set before and after the work, and executes exactly three ordinary host tools against a held descriptor for the current NDK APK. It does not install or launch the package, enter Android, change permissions, modify a QA helper or change any previous FAILED/STOP/UNKNOWN record.

## Actual inputs and boundaries

The actual scope observation `1a1b31300b9-fc05-8095` completed with 48 packages, 88 APKs and 4,978,895,379 logical APK bytes. Its complete scope was then read back by `1a1b319fff6-fc05-80a0`. The new candidate requires the original 59,957-byte scope with SHA-256 `b184299ce0a39a998752ed980a43192b396099f780bcf60bcfe53d0edf92ffe4`; its assembler refuses a missing or different local input. It also pins the actual scope's complete outer stdout, durable terminal and unchanged original pure validator. The worker validates that normal owned-child joint before interpreting the scope as identity protection.

The exact additional package row is UID 10162, PM code 0, current base APK 1,397,258 bytes / `b3bf438dedbcdd5f3ac871733a273b3cece446db6be308df73f95b08cb46d164`, with PM certificate digest `a899ddfa8c4b57a962c2bb1ae885a44bd904d7b63f6fd301abf514edf70ad72c`. The actual full APK stat, path and CE/DE directory identities are fixed from the actual scope. These facts alone do not verify a signature or authenticate the package's origin. The new audit's source-trust result remains `UNKNOWN` even if ordinary signature verification matches the PM digest.

## Three ordinary commands

The inherited command definitions are unchanged from the successful b13 audit:

1. The fixed Java runtime invokes the fixed `apksigner.jar` with `verify --verbose --print-certs` and the held APK descriptor.
2. The actual qualified Google AAPT2 executes `dump badging` against the same descriptor.
3. The fixed original aapt executes `dump xmltree` against that descriptor and `AndroidManifest.xml`.

There is no API minimum override, integrity bypass, APK edit or command retry. All three must exit normally with code 0, complete captured streams, closed pipes and joined owned children. The same legacy 19-file dependency graph, additional official seven-file graph, fixed aliases and private RUNPATH directory verifier remain in use. Eight complete layout observations cover the initial bind, the three commands' before/after boundaries and the final check. The current APK is hashed and its full file/path identity checked before and after the tools. No raw APK bytes or certificate DER are exported.

## Actual manifest interpretation

The generic badging parser is byte-identical to the established audit. NDK has a new explicit parser contract; it does not inherit the old fixture's package-name exception or its 686/1,244-byte logs.

The new parser requires the exact scoped NDK row, the actual normal successful signature matching PM, the complete XML root from this very APK, a unique matching package, unique parsed root attributes and an observed following child that terminates the root-attribute block. Numeric version codes continue through the original parser and retain the observed XML root alongside them.

An effective default of 0 is available only if the new tool output actually has empty versionCode and versionName strings, no major code, and the complete current XML root actually lacks all three version attributes. Fixed PM code 0, the current APK identity and normal signature must all agree. The result preserves raw empty strings and declared null values separately from effective `long_version_code: 0`. Missing or partial XML, explicit conflicting attributes, missing badging fields or failed signatures are rejected. The primary Android missing-attribute references are copied unchanged from the reviewed b13 evidence; they are not represented as exact live ELF provenance.

No actual NDK manifest or signature result is claimed by the local controls. Those controls use explicitly synthetic language fixtures derived from the already observed fixture text, plus the real 48-scope joint for the historical evidence gate. The future target's real tools supply its actual result.

## Reused code and review surfaces

`INHERITANCE.json` proves 21 collector/tool/layout/parser definitions unchanged from the actual b13 source, including `run_tool`, `parse_signature`, `badging_manifest`, `xml_permissions`, tool binding and the existing layout adapter. Nine outer lifetime/readback/publication definitions are unchanged. Only the new operation, its scope qualification, the explicit NDK manifest contract and its final gate differ. The source stage uses the already executed explicit48 stage with fixed new names, pins and schema.

Useful narrow review files are `ndk_contract.fragment.py`, `audit-only-against-actual-b13.diff`, `main-only-against-actual-b13.diff`, `owned-against-actual-b13.diff` and `stager-against-actual48.diff`. The complete assembled worker is `audit_ndk_current.py`.

Ten local controls passed as actual UID/EUID 1000, with unchanged whole-process descriptor identities and empty stderr. They cover the actual scope joint, incomplete scope terminal, omitted protected package, preservation of null/empty/default values in a synthetic fixture, missing XML, an explicit version attribute, failed normal signature, changed UID, duplicate SDK aliases and missing badging versionName. No root identity was simulated, no APK tool ran and no device read occurred.

## Exact one-time request and failure semantics

`process-request.review-only.json` is the complete process request. It creates the fixed five-file source/input closure under:

`/home/alex/work/pocket4-ndk-current-apk-audit-source-20261106-r1`

The independent audit writes only a new private evidence directory:

`/home/alex/work/pocket4-ndk-current-apk-audit-20261106-r1`

The unique key is `app-history-20261106-ndk-current-apk-signature-metadata-r1`. The envelope retains the existing 1,100-second / CPU 100% / 1 GiB / nice 10 bounds. Root reviews and dispatches it; this directory contains no target execution result yet.

All original streams, parse failures and command outcomes are preserved. A partial receipt, successful signature alone or an inner worker result does not qualify the audit. Require the final exact outer stdout, all three normal tool exits, current complete 48-scope protection, all owned file/layout descriptors closed, normal held-pidfd worker exit, parent descriptor restoration and a complete durable external terminal with exit 0. Any failure is retained without automatic replay.

This candidate is bound to the pre-ZBJ-install `b184299…` scope. Run it before changing an App installation, or produce a separate revision using a newly observed complete 48 scope. Never update this frozen request to evade a changed-identity rejection. Business QA, permissions, latest-version/source eligibility, production readiness and cleanup remain separate and unqualified by this audit.
