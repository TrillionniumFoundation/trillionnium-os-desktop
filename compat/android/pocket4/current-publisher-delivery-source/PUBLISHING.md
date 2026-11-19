# Publication and custody

This directory publishes the exact frozen source-verification records for seven current Google Play applications. `SOURCE.tar.gz` contains 122 ordinary, read-only members: code, controls, actual SDK verification logs, public delivery metadata, candidates, receipts, and the freeze. It contains no APK bodies or local APK-set containers. `README.md` is the unchanged `PUBLISHER-DELIVERY.md` from that archive.

The repository copies of candidates and receipts retain their original paths and file identities. They are evidence of the actual run on ai395, not new destination custody records. `DATA-INPUTS.json` pins the 23 original APKs and the six locally assembled ZIP_STORED sets. IHG uses its original single APK. Installation on Pocket4 still requires independently verified destination files and a new destination custody record; rewriting a frozen source receipt would not establish custody.

`current-source-inputs.json` now uses schema v3 to represent both the eight earlier archives and the seven original-host input sets. Its previous 17 application/dependency entries and eight archive entries are unchanged. Twenty-three of the 29 required third-party applications have complete verified current input sets; six remain required. The total scope remains 42 selected, 39 required, with only TextNow, TextFree (`com.pinger.textfree`), and Uber excluded. Play Store Companion remains outside the 39-app denominator.

`availability/` preserves the actual original `UNAVAILABLE_COUNTRY` responses for Best Buy, Hertz, and National. It also preserves the Xiaomi public-flow assessment followed by the later normal-browser result: one Meituan download click produced a visible slider CAPTCHA and obtained no APK. The original tab was handed off. Douyin and Pinduoduo download buttons were not attempted after that provider challenge. These six applications are not additional exclusions.

Run `python3 -I -B compat/android/pocket4/current-publisher-delivery-source/verify.py` from a checkout to verify the complete publication inventory, frozen archive, source copies, and scope/custody reconciliation. CI separately executes the 39 new publisher-delivery controls while retaining the 146 earlier APK controls. The evidence replay command does not execute SDK verification on absent APK bodies, start Android, install an application, prove the selected device configuration, execute ARM64 native code, or validate a signed-in business flow. Those acceptance states remain false.
# Explicit current successor

The immutable seven-package publication below records the original 23 obtained
required inputs and six missing inputs. Its `MANIFEST.json`, `SOURCE.tar.gz`,
`SOURCE_FREEZE.json`, SDK receipts and transaction observations remain unchanged.
The exact two historical application registries are retained under
`historical-registry/`; their bytes must match the original manifest pins.

`CURRENT-SUCCESSOR.json` separately pins the 37 reviewed files from PR315.
`successor.py` requires the complete old 24 application/dependency records and
archive custody to remain unchanged, binds all six new candidate/receipt/native
input sets, and checks the current 29 obtained / zero missing source count. Only
the three explicitly updated gate documentation/manifest files use current pins;
all original executable gate and test sources still equal the frozen archive.
The old archive also retains every historical documentation byte.

`verify.py` runs this source replay plus the finite `test_successor.py` rejection
controls. It never repeats SDK verification or opens referenced APK, Android,
account or user-data paths. A recorded metadata observation must have been fresh
when its receipt was published. A later CI replay does not refresh that observation
or qualify a new activation; current metadata and destination custody remain
separate prerequisites. Meituan signer migration and all installation, native,
business, runtime and production states stay unqualified.
