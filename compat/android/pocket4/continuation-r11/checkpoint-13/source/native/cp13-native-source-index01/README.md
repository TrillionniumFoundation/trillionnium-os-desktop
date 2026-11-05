# CP13 native source additions

Aggregate unreferenced tree: `273ce61a22a806a15d6adb6486289e1f999fc7d2`. It contains 19 source prefixes and 211 UTF-8 files. Every local payload was checked against its Git blob SHA and length. CP12's 5,380 existing payloads remain unchanged.

| Prefix | Files | State and scope |
| --- | ---: | --- |
| art-normal-projection-next03 | 25 | SOURCE_ONLY — Normal ART source-projection integration; no actual Rust462 or ART full TU build. |
| paired-builder451-compile01 | 25 | ACTUAL_FAIL — Actual compilation and selected tests reached test19 rc0; runner rejected interleaved stdout. Original overall failure retained; not all22 qualified. |
| candidate07-build01-readonly01 | 6 | ACTUAL_READER_FAIL_SUPPLEMENT_SEPARATE — Reader rejected 332929B terminal above131072 bound; root separately supplied exact terminal and completed8-artifact closure. Original reader remains FAIL. |
| engine-qualification07-host-bound01 | 16 | ACTUAL_STAGE_FAIL — Before mkdir: /home/alex/work mode0775 rejected; no check/run for old nonce. |
| qualification-stage-parent-read01 | 5 | ACTUAL_READ_PASS — Fixed held metadata proved native-owned-01 mode0700 and old target absence. |
| engine-qualification-template-04 | 36 | SOURCE_ONLY_LOCAL_DERIVATION — Only input root changed from template03; execution references unchanged. |
| engine-qualification07-host-bound02 | 18 | ACTUAL_HOST_PASS — Corrected stage/check/run passed:3793 registered,3791 executed,3788 completed,2disabled3baseline-policy skips,0failed. |
| engine-qualification07-android-template01 | 4 | SOURCE_ONLY_SUPERSEDED — Old nonce template; no Android execution. |
| engine-qualification07-android-template02 | 4 | SOURCE_ONLY — Corrected private input-root template; UID2407/subid14600000 are proposals, not reservations. |
| engine-qualification07-android-bound01 | 15 | ACTUAL_STAGE_AND_INPUT_CHECK_PASS_ROOT_REPORTED — Root reports stage and input-check PASS; preparation start in progress, no Android runtime result yet. |
| candidate07-host-result-read01 | 5 | ACTUAL_READ_PASS — Complete27332B host result67d0f1a2… observed held/named stable. |
| art-enabled-call-chain-review01 | 1 | SOURCE_REVIEW_ONLY — Role/caps/preload/parent resume/transition analysis; no production source changes or ART runtime qualification. |
| candidate07-android-prepared-read01 | 6 | SOURCE_ONLY_NOT_DISPATCHED — Fixed root-owned prepared.json reader; no collection observed. |
| native-peer-holding-abi3-source01 | 1 | SOURCE_PEER_REVIEW_ONLY — Exact ABI3 holding-view delta review; no execution by native agent. |
| paired-builder451-compile02 | 31 | ACTUAL_RUNNING_ROOT_REPORTED — Root admitted job1a1aa65028c-fc05-425d; final result not observed at this index freeze. |
| qualification-private-parent-deriver-draft01 | 1 | SOURCE_ONLY_LOCAL_DERIVATION — Saved source used to derive private-parent input layout; no remote execution. |
| native-generation-image-tools-read01 | 4 | ACTUAL_READ_FAIL — Required debugfs absent from original controlled PATH; no tool execution. |
| native-generation-image-tools-read02 | 7 | ACTUAL_READ_PASS — Nine image tools and fixed wrappers/backend metadata held/pinned; zero tool execution and no image-test pass claim. |
| peer-leaf-source01 | 1 | SOURCE_PEER_REVIEW_ONLY — Exact bootstrap leaf source review; no execution by native agent. |

These counts include immutable references repeated to keep complete source packages rebuildable. `SOURCE_FILE_ALLOWLIST.json` explicitly maps byte-identical CP12 content. The index does not convert any reader or runner failure into PASS. Actual root-owned runtime/build receipts are added separately by root. Android preparation/runtime and compile02 remain pending until their own complete actual results are received. No enabled ART or all-app production claim is made.
