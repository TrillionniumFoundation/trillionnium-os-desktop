# Current source refresh after the original required39 merge

`SOURCE-REFRESH.json` selects the independently generated source-state successor
and its exact registry and freshness records. This layer preserves the original
publisher publication, the six-input closure, and the first required39 merge as
historical evidence. Those earlier records alone do not select the refreshed
Beike or United packages. The previous selection index is preserved byte for byte
in `history-before-united/SOURCE-REFRESH.json`.

## Actual source result

Beike is now 3.06.80 / 3068010. Its complete 230,624,085-byte APK was independently
qualified with the unchanged SDK37 verifier and the historical publisher signer.
The recorded source check read all 26,227 ZIP members and verified their CRCs.
Its 68 native members comprise 67 ARM64 ELF files and one explicitly identified
x86_64 shared library. This is source identity evidence, not native execution.

The original pocket4 successor execution completed successfully and recorded
all input and final APK identity bookends. `beike/actual/RESULT.json` is that
actual execution record. The three adjacent output documents are exact local
reconstructions from the fixed inputs and actual execution timestamp, checked
against every original output byte count and SHA-256. CI repeats this metadata
reconstruction; it does not repeat SDK verification or inspect the live APK.

The transport prefix, 50 HTTP range pieces, and two empty range directories were
deleted after the final APK and retained proof set were checked. They are not
installation dependencies. The final APK and 12 retained JSON proofs remain
bound by the source-state result.

## Additive United 4.2.104 source successor

United now selects 4.2.104 / code 3622. One original-profile Google Play delivery
produced one base and three declared splits. All four APKs passed the unchanged
SDK37 signature, badging and manifest commands for SDK range [37,37], complete
ZIP/CRC checks and the base/split dependency closure. Eleven ARM64 ELF members
are recorded. The 351,042,037-byte stored container is locally assembled from
the original delivery members; it is not a publisher-provided archive.

`united/inputs` contains the complete original delivery, SDK, cleanup and handoff
metadata plus exact copies of the prior Beike successor's three output files.
`united/override_united.py` joins only those fixed bytes. It does not repeat SDK
verification, read an APK, use the network or change the owner's CURRENT state.
The join keeps Python integer precision for all original F9 identities. Its
actual three output documents and metadata-only execution record are in
`united/actual`. Replaying in another output directory yields identical bytes.

Only United's required39 application record, its selected registry entry and
its freshness row change. The other 38 application states, other 28 required
registry entries, Play Store companion, Beike source and custody, all ten GSI
system entries, all three exclusions and the full installation-prerequisite
map remain identical. The old United 3621 registry/observations remain history.
The verifier first reconstructs the original Beike outputs and applies Beike's
original validator, then reconstructs and validates the additive United update.

## Latest-version observations

The public metadata matrix and separate DiDi supplement preserve the actual
HTTP observations, timestamps, package identities, and complete response hashes.
They cover 28 non-system applications directly; Beike has its separate source
qualification. Three public channels advertise an older version than the
already selected input, so those selected inputs are retained.

The original public matrix observed United 4.2.104 while the then-selected
qualified input was 4.2.103. That matrix remains unchanged. The additive United
SDK37 receipt now qualifies 4.2.104/code3622 and resolves that source-input item
in the current index. This does not establish that all39 applications are the
latest at activation. The original matrix still retains preliminary parser
failures and the first DiDi page with no live version; the supplement retains
the independent successful DiDi observation.

## Remaining runtime requirements

The requested scope remains 42 selected applications, 39 required applications,
and only the original three exclusions. The Play Store remains a separate
dependency. The complete Android 17 QPR1 GSI is the source of all ten system
applications; individual APK replacement cannot substitute for that cohort.

The Meituan signer and data migration requirement remains unresolved. These
files grant no installation, runtime, business, or production acceptance.
Activation still requires current destination custody, a qualified full Android
runtime, fresh installed identities and UIDs, and the required application
flows. The older 13-item preparation selector is not a 39-application business
acceptance result.

## Offline checks

Run `python3 -I -B verify_refresh.py` for the complete packet and actual output
replay, and `python3 -I -B beike/test_override_beike.py` for the twelve source
scope, history, and rejection controls. Run
`python3 -I -B united/test_override_united.py` for twenty United source controls,
including old-version substitution, missing/duplicate splits, SDK/signature
identity, complete scope/gate preservation, integer precision and independent
output-directory reproduction. These commands perform no network, SDK,
installation, or Android actions.
