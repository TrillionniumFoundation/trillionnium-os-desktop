# Current source refresh after the original required39 merge

`SOURCE-REFRESH.json` selects the independently generated source-state successor
and its exact registry and freshness records. This layer preserves the original
publisher publication, the six-input closure, and the first required39 merge as
historical evidence. Those earlier records alone do not select the refreshed
Beike package.

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

## Latest-version observations

The public metadata matrix and separate DiDi supplement preserve the actual
HTTP observations, timestamps, package identities, and complete response hashes.
They cover 28 non-system applications directly; Beike has its separate source
qualification. Three public channels advertise an older version than the
already selected input, so those selected inputs are retained.

United's current public listing is 4.2.104 while the qualified input is 4.2.103.
The new payload must still be obtained and qualified. The original matrix is
retained unchanged, including preliminary parser failures and the first DiDi
page with no live version. The supplement records the successful independent
DiDi observation without rewriting that history.

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
scope, history, and rejection controls. Neither command performs network,
SDK, installation, or Android actions.
