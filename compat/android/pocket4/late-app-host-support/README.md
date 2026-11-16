# Pocket4 QuickSearch, Settings and WebView host support migration

This is a source review and CI capsule for three existing qualification adapters. It contains all 57 production files listed by their captured preparations: QuickSearch r2 (18), Settings r1 (17), and WebView r1 (22). It is not a device deployment or a new qualification result.

## Why this change is needed

The three captured adapters use the same old `app_common.py` (SHA-256 `468e0fa093ec1c741547912b8fef41560e1ea9b1e124a76113ec97da7fe03420`). Its active support references point at business-support r9 and clock support r10. Each entry compares the qualification's support manifest with that old constant before collecting identity, so an exact current host qualification is rejected.

The three common files are replaced with the already reviewed current business-app r4 common (SHA-256 `6003e96be02cd0c6328340865bbb2962d39967f2b823656af258ed5a48f598d0`). The only changes are the standard and clock support paths and hashes. The rest of each common AST is identical. WebView also changes its old R9 diagnostic to HOST while preserving the comparison. The other 53 production files are byte-identical to their captured originals.

`source-manifest.json` records every production file and its original exact source reference. `PRODUCTION-INVENTORY.md` is the readable full listing. `host-support-migration.patch` applies to the original three packet directory names. `validation/source-preservation.json` records the full comparison.

## Run the controls

From this capsule's directory, with Python 3 and only its standard library:

```sh
python3 -B -m unittest discover -s tests -p 'test_*.py' -v
```

The 15 controls reproduce each original rejection, check all seven identity roles against the new reference, reject legacy/clock/tampered qualification manifests, execute each real `inspect-source` CLI with a local source-only preparation, and reject a common file changed after its digest was recorded. Identity controls substitute bootstrap and the final collector. Their qualification JSON is synthetic and created inside a temporary directory. Composition controls run the actual CLI against the local production files and an explicitly synthetic preparation.

The recorded run passed 15/15 on the local Linux executor. No BusinessBaseline instance, Main process, Android action, network fixture, package mutation, or app acceptance is produced. The previously completed Editor/Probe controls are separate and were not rerun here.

## Assets and device dependencies

All preparation-listed production files are Python. WebView's HTML/CSS/JavaScript text is embedded in the unchanged `webview_assets10.py` and `webview_assets11.py`. There is no omitted separate HTML or JavaScript file in the production lists.

Device execution still requires the exact current host support and host-clock source closures, a new source-bound preparation sealed at the selected Pocket4 destination, and the original provenance and gate references. `runtime-dependencies.json` lists their fixed identities. WebView media11 also requires its original 58,199-byte video with SHA-256 `7148402273737217b6906704ac430fcfd77268e9f0dbfe19d5f334a496a58d69`; its bytes are not included. No APK, binary media, user data, private qualification fixture, or original raw execution log is included.

The old r9 manifest in QuickSearch/Settings preparation origins is historical provenance. Preserve the original origin checks when resealing; it does not remain the active support constant after this patch. The existing source manifest's additional provenance/audit entries are legitimate and are not replaced with the smaller production list.

No new Pocket4 preparation or actual Pocket4 `inspect-source` result for these three candidates is claimed by this capsule. The main owner must reseal and inspect the new packets before using them with fresh Main-bound baseline, qualification, action lease/lock, installed package identity and owned task evidence. Original 45-app acceptance remains outside this source change.
