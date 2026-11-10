# Gallery rotation setup and exact cleanup history

This snapshot ends at **2026-11-05 21:54:28 UTC**. The first rotation attempt stopped during temporary-helper seeding, before any Gallery launch or UI input. It adds no Gallery business gate and does not invalidate prior, separately qualified Gallery scopes.

## Observed chain

| Attempt | Actual outcome | Qualification |
| --- | --- | --- |
| rotation flow01 | One generated PNG was written as an unpublished MediaStore row. The helper incorrectly required the final pathname while `is_pending=1`; it stopped with durable pending state. | Setup failure; 0 Gallery inputs and 0 rotation. |
| cleanup01 | Provider rejected a `SELECT` token in the directory predicate. No delete, rmdir, or uninstall was sent. | Zero-effect failed preflight. |
| cleanup02 | One exact image92 delete returned rc0. The subsequent deleted FUSE file-descriptor observation failed. | Original FAILED/unknown remains unchanged. |
| read-only reconciliation | Saved command/journal and two fresh reads agreed that row92 and both pending/final PNG paths were absent. Only the original empty directory91 and helper10194 remained. | Independent resolution of actual effect; no mutation and no rewriting of cleanup02. |
| cleanup03 | One empty-directory rmdir, one exact directory-index delete, and one exact helper uninstall completed. The held backing inode reached nlink0; both path views, media namespace, package and CE/DE were absent. | Cleanup verified; 0 App business/UI-delete credit. |

The last receipt preserves Gallery APK/UID/data identities, permissions, the original-media metadata fingerprint, task851 and the strict Main identity. Image92 deletion was not replayed. Old failures and unknown receipts are copied byte-for-byte.

## Source reasoning and next candidate

The installed MediaProvider APK/DEX was captured and pinned. The selected delete path does not recursively walk the fixture directory or expand the exact selection to descendants. Its source selects rows and later deletes by selected ID, so this bundle explicitly makes no cross-row atomicity claim. The actual trash-parent branch is excluded by the fixture's non-trash paths. The source review is a historical frozen document; its “not submitted” sentence describes its original review time, not the latest execution status.

Helper03 changes only the unpublished-row final-path assumption. Published images still require the exact final path, and pending images still require the exact URI/owner/name/relative path/state plus full payload and decoded-pixel verification. Its actual signed host build passed, but it has not been installed or run. The next controller remains a local draft pending separate admission; no Gallery rotation success is inferred from compilation or cleanup.

`SCOPED_RESULT.json` is the current machine-readable result. `evidence/` retains the small original terminal results and explicitly marked projections; each projection pins its complete private source. Original media contents, environment dumps, raw UI captures and base64 execution payloads are excluded. `source/` contains selected execution source, the narrow changes and complete dependency hashes; it is an audit selection, not a standalone deployable bundle.
