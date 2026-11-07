# Pocket4 Android — checkpoint 19

**0 of 45 applications are production ready. The old Main framework epoch is invalid. New UI and install admissions remain blocked; the newly observed framework processes do not yet form a qualified epoch.**

This checkpoint is fixed at **2026-11-06 05:14:25 UTC**, on parent commit `80e030d93be61d89550d8d3493d9eb60ddff45a2`. It preserves all 12,370 prior payload rows and 217,054,264 bytes, their order, historical metadata and inherited Git subtrees. The 78 explicitly authorized source/evidence trees contain 491 original text leaves. The two alternate tree names are aliases, and the previously published Bili R8 source tree remains at its exact checkpoint 18 mount.

## Current shared blocker

The original zygote and system_server identities are absent. Read-only diagnostics found the original daemon, Android init, presenter, launcher and surfaceflinger identities still present; the Main service identity and boot ID remained the same in those observations. A later fixed child-list observation found zygote PID 90360/start tick 96586437 and system_server PID 90516/start tick 96586493. These observations neither prove an exit cause nor authorize a new QA epoch. No daemon restart is claimed. See [the first identity review](packages/main-framework-identity-read01-evidence/main_framework_identity_read01/root-actual-review.json) and [the bounded new-identity review](packages/main-framework-identity-read02-evidence/main_framework_identity_read02/root-actual-review.json).

Bili R8's UI attempt failed at the old Main guard before creating its ROOT, FLOW, claim, source, worker or Android action. A separate fixed-path reader then observed both expected owned paths absent. This is a preserved failure and a bounded absence observation, with no automatic replay. See [the actual failure](packages/amazon-bestbuy-actual-and-bili-Main-failure/bili_r8_player_flow01/root-actual-review.json) and [the independent absence read](packages/bili-r8-absence-read01-evidence/bili_r8_absence_read01/root-actual-review.json).

## App evidence at the cut

| App | Actual evidence | Limit still open |
| --- | --- | --- |
| Bilibili | R8 static build completed 13 owned children, 22 Java and 32 Python controls; the historical install bound helper UID 10204. | The Android idle fix has not been observed. The UI attempt stopped at the Main guard, and new UI is blocked. |
| IHG | Seventy synthetic controls passed. One Search click request was admitted, but the helper rejected it with FOCUS_CHANGED_BEFORE_ACTION before attempting the click. | The flow's unknown outcome stays unknown; Destination never started. A fresh stability WIP has 89 unrun controls and no executable UI request. |
| Amazon | R2 static build completed 13 joined children and the same 22 Java plus 32 Python controls. | R2 has no install or UI result. Timing relative to the Main failure is not causal proof. |
| BestBuy | R2's read-only initial flow passed and retired its owned task. The historical public-role projection found 12 nodes, nine visible, no visible clickable node and empty visible text/description fields. | Public action roles and whole-app content readiness remain unqualified. Actual depth was eight, so the old depth-33 failure path was not exercised. A blank rendering or splash state is not established. |

The underlying reviews remain separate: [Bili build](packages/bili-r8-build-actual-and-ihg-failure-review/bili-r8-static-build01/root-actual-review.json), [Bili install](packages/bili-r8-four-install-originals-and-nonce-actual/bili_r8_install_four_read01/root-install-review.json), [IHG controls](packages/ihg-controls70-actual-and-ui-preflight/ihg_search_destination_controls70_01/root-actual-review.json), [IHG actual failure](packages/ihg-search-destination-failure-root-review/ihg_search_destination_ui01/root-actual-review.json), [IHG WIP status](packages/ihg-stability-SOURCE_ONLY-wip/android-ihg-search-stability-wip01/WIP_STATUS.json), [Amazon static build](packages/amazon-bestbuy-actual-and-bili-Main-failure/amazon_r2_static_build01/root-actual-review.json), [BestBuy initial inspection](packages/bestbuy-review-and-bili-install-preflight/bestbuy-r2-ui02/root-actual-review.json) and [BestBuy public roles](packages/amazon-bestbuy-actual-and-bili-Main-failure/bestbuy_r2_public_roles_read01/root-actual-review.json). All other apps retain their inherited ledger. Successful build or protocol controls do not establish business acceptance.

IHG's failed Search after-state completed and matched, but failed-sequence restoration was not qualified. The independent post inspection completed with 66 nodes and qualified restoration; task 1031 retired while baseline task 851 remained. The reported focus rejection is not independent proof of a focus move. The original failure, flow uncertainty and distinction between admitted flow action and unattempted helper click are retained.

## Owner diagnosis

Actual BuildId-matched libmemevents instructions tie the captured LMKD abort PC to the branch where `__system_property_get("ro.build.version.sdk_full", ...)` returned a nonpositive value. The fixed host and image build.prop files each contain one `37.0` value, so these reads do not support replacing a missing key. The exact preload's complete 28 named dynamic symbols contain none of the eleven fixed property APIs; runtime property visibility and full symbol resolution remain unresolved. See [the original instruction/source proof](packages/owner19-branch-source-proof/android-owner19-memevents-property-abort-proof01/report.json), [Root's independent proof](packages/owner19-root-branch-proof-native-git02-preflight/owner19-memevents-root-proof/root-verification.json), [the host/image property read](packages/owner19-buildprop-actual/owner19_fixed_buildprop_read01/root-review.json) and [the preload review](packages/owner19-preload-and-ihg-five-actual/owner19_fixed_preload_read01/root-actual-review.json).

Owner20's dependency read qualified one actual build receipt plus three fixed anchor files and seven explicit CRT/header candidates, closed 43 held descriptors and launched no child. Its two full reads and named/held identities matched. The actual collection separates the receipt from its three `anchors`; the allowlist's four-authority wording is retained verbatim in root-cut-scope.json. No accessor compilation, executable startup or Owner20 runtime has run at this cut. See [the dependency review](packages/owner20-accessor-dependencies-read01-evidence/owner20_accessor_dependencies_read01/root-actual-review.json) and [its complete original](packages/owner20-accessor-dependencies-read01-evidence/owner20_accessor_dependencies_read01/stdout.original.json).

## Native source repair

The original strict normal Soong failure remains failed. The six-file Maven/SDK read passed, while Git02's two missing local blobs remain a failed collection; missing local blobs are not treated as upstream absence.

The new builder468 compile02 package is **SOURCE_ONLY and UNRUN**: 224 locked projects, 24 full Blueprint fixtures, 59 unchanged upstream provider stanzas and a 491-file builder map. The map retains 464 parent files, replaces two Rust files and adds 25 text files. It preserves both original failing consumers, `ALLOW_MISSING_DEPENDENCIES=false`, and the two normal targets `framework-minus-apex` and `libandroid_runtime`.

Robolectric's fixed Soong implementation adds implicit dependencies; the source candidate includes the observed runner, collector, tracinglib and corresponding genuine providers. The locked misc/robolectric-native-prebuilt directory is selected unchanged, but its Blueprint body remains unobserved. Rust compilation, global Soong variants/visibility, the implementation JAR and Android JNI object/header/link qualification remain pending. See [the actual Maven read](packages/native-maven-read02-actual/native_maven_sources_read02/root-review.json), [the complete source proof](packages/native-provider-closure-compile02-SOURCE_ONLY/typed-ingress-builder468-provider-closure-compile02/provider-closure-proof.json) and [the immutable source preservation verification](packages/native-provider-closure-compile02-save-verification/typed-ingress-builder468-provider-closure-compile02-preservation/verification.json).

## Preservation and review

- [status.json](status.json) is the current structured status. Older checkpoint metadata stays historical.
- [root-cut-scope.json](root-cut-scope.json) is the exact Root allowlist, including its correction of an unadmitted earlier tree-SHA transcription.
- [payload-index.json](payload-index.json) records every new payload's exact bytes, SHA256, Git blob and original tree/path.
- [exclusions.json](exclusions.json) records private-data, alias and after-cut boundaries.
- [handoff.json](handoff.json) carries the current admission halt and pending work.
- [assembly/verification.json](assembly/verification.json) records tree/content checks; the actual final tree readback is in the separate preservation receipt.
- [assembly/lossless-manifest.js](assembly/lossless-manifest.js) preserves untouched root values and the original file-array prefix without reserializing historical numeric values.

Only safe text sources and authorized originals/derivatives are added. Owner19 captured_hex, raw crash packets, private init log bytes, private App UI/assessment trees, binary artifacts, keys, caches, unlisted trees and after-cut facts are excluded. No source/evidence payload byte was rewritten. This assembly creates no commit, ref, PR update, device job, restart or runtime authorization.
