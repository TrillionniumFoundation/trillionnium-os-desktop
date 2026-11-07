# DocumentsUI: smallest remaining release review

Flow11 already proves the scoped create → provider rename → Files UI rename/open → picker open → normal close/reopen → provider delete sequence, with all owned state clean. Keep that credit; do not rerun it just to replace historical failures. Whole-App readiness remains false.

| Remaining item | Concrete evidence needed | Current boundary |
| --- | --- | --- |
| Runtime identity / native-engine exclusion | Exact UID/PID/namespace/start-time attribution, executable ELF machine and complete mapped-object pins for DocumentsUI, ExternalStorageProvider and the file-operation service when used. | Same APK/UID/data-directory identities and v3 certificate are verified. No live engine mappings were collected. ABI=null and no embedded JNI are insufficient exclusions. |
| Complete supported feature contract | Resolve actual GET_CONTENT, OPEN_DOCUMENT_TREE, Downloads/archive routes and supported Files operations; exercise real Files UI Delete plus applicable folder/copy/move/multi-select/search/sort paths using only isolated generated fixtures. | Flow11 covers one text file and the primary provider; actual manifest also declares these other routes and a separate file-operation process. |
| Failure paths and bounded stability | Combine cancel, collision/invalid-name and missing/revoked-owned-URI paths with exact-UID crash/ANR/exit and bounded resource observations during necessary remaining sessions. | No Flow11 crash/ANR/exit delta or reviewed soak evidence exists. Task close/readback success does not supply it. |
| Data/permission and release reconciliation | Relevant permission/AppOps/grant before/after state, metadata-only unrelated-state preservation and final per-feature/gate review. | Own URI/file/package/task cleanup is proven; CE/DE inode equality does not prove arbitrary permission or database content preservation. |

Actual source and evidence hashes, manifest component/action projection, identity certificate and gate-specific criteria are in `DOCUMENTS_COMMON_GATE_REVIEW.json`. In particular, capture the declared `:com.android.documentsui.services` process during a supported file operation rather than inspecting only an idle picker. An observed absence of an ARM engine needs positive process/framework attribution; candidate07 isolated qualification is not proof of deployment in Main.

Normal task lifecycle and observed UI/input behavior already pass for Flow11's scope. Process-death/reboot, external providers and broader MIME/archives remain explicit unqualified scope; include them if the reviewed release contract supports them. Do not grant an unsupported exemption merely because a device/provider is absent. This checklist caused no new device calls, UI, storage mutations or package changes.
