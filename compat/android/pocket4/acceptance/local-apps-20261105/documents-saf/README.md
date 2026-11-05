# DocumentsUI / SAF acceptance, continuation r12

**Actual CREATE_DOCUMENT Save, one 87-byte ContentResolver write/read and provider rename have passed. Files reached its real Rename dialog. Full Files UI rename/open, OPEN_DOCUMENT and close/reopen persistence remain unqualified.** `SCOPED_RESULT.json` records the exact current gates. Whole-App readiness remains false; the temporary no-launcher client is excluded from the 45 tracked apps.

## Latest completed trial

Flow08, job `1a1ab56e186-fc05-4cc4`, actually failed with exit 1 and complete, durable output. Its 11 actions included one launch and normal removal of tasks 933/932. Files followed the real More → Select all → one selected file → selection-toolbar More → Rename path. The text action stopped **before dispatch** at `FULL_EDITOR_NODE_CHANGED_BEFORE_TEXT`.

The saved original and fresh editor nodes differ only in native accessibility `window_id`: 6556 → 6576. Every other field, including text, bounds, focus and capabilities, is identical. Each helper dump invokes separate instrumentation. The old comparison incorrectly required a connection-scoped number to stay equal across those dumps.

Exact cleanup independently passed: the known 87-byte file was hash/identity verified then removed, every permitted name was absent, the original empty directory was removed, the new package was uninstalled and verified absent, and its staged APK was removed. Pending effects and cleanup errors were empty. **Cleanup does not convert this failed business trial into a pass.** See the original `flow08-result.json` and `flow08-job-status.json`.

Flow09 was submitted once as job `1a1ab5d9616-fc05-4d05` after Clock released the UI. Its terminal result is not part of this checkpoint. Current `run_saf09.py` / `ui_adapter02.py` require valid integer connection IDs but exclude only that field from cross-dump equality. Every other node field, both complete snapshot checks, exact WM token, owned task, final focus and native text readback remain required. The prior08 cleanup and permanent stage02 fence are pinned before a new installation and directory birth.

## Preserved actual history

| Attempt | Actual boundary | Cleanup / qualification |
| --- | --- | --- |
| 01 | URI-permission parser rejected the actual multi-section package dump before launch. | Zero UI; package, empty directory and staged APK removed. |
| 02 | Transport launch unknown; same-key reconciliation reused the job; cancellation unconfirmed. | Durable exclusive fence blocks its original first-effect entry. No claim that the old job was terminated. |
| 03 | Real picker Save, exact returned URI, one App write/read of 87 bytes passed; old held-directory enumeration did not refresh. | Task919 closed; document/package preserved. |
| Read-only reconciliation | Three fresh/rewound handle observations with the same original directory birth found the sole correct file/hash. | Zero UI/content writes. No data-loss claim. |
| 04 | A nanosecond identity pin had been rounded through JavaScript JSON. | Zero UI; preserved original fixture. Raw UTF-8 proves the exact integer. |
| 05 | Original 1,200-second App lease lacked sufficient remaining time. | Business failed; zero-UI exact file/directory/package cleanup succeeded separately. |
| 06 | Fresh trial passed create/write/read and provider rename; Files card lacked long-click capability. | No guessed long press; both tasks and exact fixture/package cleaned. |
| 07 | Real menu Select all established one selected file; two More nodes remained in the native tree. | No ambiguous input; both tasks and exact fixture/package cleaned. |
| 08 | Actual toolbar containers disambiguated More; real Rename dialog reached. | Connection-ID equality stopped before text input; exact cleanup passed separately. |

All failed terminal results remain failed. `flow03-directory-enumeration-evidence.json` distinguishes the old enumeration behavior from an independently printed getdents result, which was unavailable. `flow04-integer-precision-evidence.json` preserves exact `1793872497685431975` versus rounded `1793872497685432000`. Subsequent raw JSON is saved as UTF-8 bytes and parsed with Python integers; public nanoseconds are decimal strings.

## Package/build pins

| Package | UID / code | APK SHA-256 |
| --- | --- | --- |
| com.android.documentsui | 10022 / 37 | 757feffc32440dd371eaab4fb91f45273a621ee45b848e2dc734b386ac6e2086 |
| com.android.externalstorage | 10024 / 37 | 50d1e6f2be950e049cdc898dd812c8e609f421cc167013d4ee2c795dcdc0e5ea |

The same R16 Main/init/epoch is held throughout. Installed APK, UID/version/user state and CE/DE inode ownership are checked. `harness02/` is the complete temporary client source. Build02 job `1a1aaf03182-fc05-48dd` actually succeeded with 15 Java classes and all 11 compile/package/sign/verification steps. `BUILD_PROVENANCE.json` selects original receipt hashes, source/tool dependencies and results without repeated command envelopes or signing material.

- APK: 16,588 bytes; SHA-256 `3b2b8d01b551f68256a25c351b34f2a6c74f74cbfc9b44b226ea708dba9fffe6`.
- Certificate: `f772d334443bb5cd71abcc179d04e21ee3e70d424290df69828b94e42bc448f2`.
- Source manifest: `a11b394b97cb1e250abe941ccf6fae133ffb0669d717357d18b7037548dde311`.
- No requested permissions, launcher, service, receiver, provider or native library. Test-only, no debug/backup; one exported Activity has a VIEW filter restricted to the final owned URI.
- SDK31 compile/min, target33, pinned JDK21/tools. One CPU and 512 MiB; peak 345,993,216 bytes, no OOM. Not all host native shared libraries were frozen.

The package must be absent even from uninstalled entries. Installation explicitly uses `pm install -R -t --user 0`; retained actual help proves -R disallows replacement. New trials require verified previous cleanup, a new request/stage/output directory, a new installation identity and exclusive fixture-directory birth. A fully uninstalled verified APK can be reused; unknown operations cannot be replayed.

## Business and ownership scope

The flow has a 720-second/36-action bound, shared UI lock and fixed b227 held-session transport. Host fixture setup creates only a unique empty directory; it earns no App creation credit and writes no file contents. Actual CREATE_DOCUMENT Save must return the exact URI and persistable grants before the App writes its fixed 87-byte Unicode payload. SHA-256 is `5e8ee8b6e154ade076e1f62e1ff0bc206ae69ba41982ac1c7a048c303f0503e7`; reads are limited to 1,024 bytes and the exact owned URI.

Provider rename is separate from Files UI rename. Select all is allowed only inside the identity-bound sole-file folder. More buttons are bound to the real toolbar resource ID, same native window and contained bounds; action mode also requires the sole owned card selected and title `1 selected`. Pointer inputs retain complete frame/scope/context checks. Text entry retains all node fields except the independently connection-scoped number.

Remaining gates require actual Files rename/open, OPEN_DOCUMENT selection, normal close/reopen and persisted-grant/hash readback, then provider delete followed by real ENOENT and an empty URI-grant section. ACK or access revocation alone never proves deletion. Close/reopen does not establish process-death or reboot persistence.

Only a source-bound acknowledged action may admit the exact new Files/Resolver leaf. Other tasks are preserved. Normal close sends one remove with bounded read-only convergence. Unknown inputs/install/uninstall or pending provider work preserve the fixture for reconciliation. Known-failure cleanup is restricted to its exact identity/hash and earns no provider/UI-delete credit.

## Publication and meaningful regression

`PUBLICATION_MANIFEST.json` is the compact set: original01/current09 runners, baseline/current adapters, necessary patch chain, selected real results/cleanup proofs and complete fixture source/build provenance. Full environment/PackageManager dumps, raw UI trees/PNGs, repeated intermediate runners, encoded requests and private signing material are excluded. Originals remain private to the coordinator.

The six `test_editor_connection09.py` cases exercise the real input method with a minimal generated-editor fixture: old false rejection, corrected single dispatch with two snapshot checks, any other node-field change, invalid connection ID, final WM change and second-frame failure. Zero device calls. The fixture contains only our generated filename editor and required snapshot identity fields, with original receipt hashes. The earlier actual-tree toolbar cases reject duplicate active buttons, changed containers, multiple selection and unselected cards. Harness checks alone confer no App readiness.
