# CP3A CalendarProvider cleanup review

The original CP3A CalendarProvider uses the same selection and arguments for its final SQLite delete as for its initial candidate query. This review covers the collection URI used by the Calendar core and reminder Main paths.

## Original inputs and comparison

The provider was read directly from `/system/priv-app/CalendarProvider/CalendarProvider.apk` in the unmounted official CP3A system image with SHA-256 `dc781249bb4724b7a0777e5077321b84576db46f61abb4b9086b81077bfd0ab4`. The prior binary was read from the base native runtime extraction. The pinned current image-member receipt, prior seven-method review, both APKs, both DEX members and each compared method are identified in [review.json](review.json).

| Input | APK SHA-256 | APK bytes |
| --- | --- | ---: |
| Prior extraction | `eebf12f81981f7d8c59a9b9ed465945818d2ab0208c121d858cbc4e6426f5fff` | 340711 |
| CP3A image member | `1ae37944b4f5f24d8d7bc849c76bd80c678d19cc3f5647ccaebd1254d8508744` | 336615 |

Disassembling both originals reproduced all seven prior method hashes. Fifteen complete methods matched byte for byte after removing only numeric smali `.line` directives. This comparison includes method signatures, registers, instructions, operands, branches, exception handlers and return values. The sixteenth method, the static initializer, changed. Its URI matcher still assigns `calendars` to 4 and `calendars/#` to 5. CP3A adds the authority root and numeric root path as 41 and 42. Each entire initializer has its own digest.

## Transaction and row identity

1. For an ordinary single delete, `CalendarProvider2.delete` records the calling UID. `SQLiteContentProvider.delete` starts a write transaction, calls the in-transaction delete, marks success after it returns and ends the transaction. A batch uses its surrounding transaction.
2. `verifyTransactionAllowed` allows selection for the calendar collection (4). The calendar item route (5) rejects a nonempty selection. The caller uses the collection URI with the sync-adapter flag and the local account name and type.
3. The provider reads and SQL-escapes the account values and appends the caller's parenthesized predicate with `AND`. Both Main callers include the bound row ID, account name and type, internal name, display name, owner, and an absence check for events referencing that ID.
4. `deleteMatchingCalendars` passes the selection and its arguments to a query returning calendar IDs. For each returned ID, it calls `modifyCalendarSubscription(id, false)`. It then passes the same selection and arguments to `SQLiteDatabase.delete("Calendars", selection, args)`, which reevaluates the full condition and returns the affected count. The initial list of row IDs supplies the subscription operation.
5. With an account present and subscription state changing, `modifyCalendarSubscription` can call `CalendarDatabaseHelper.scheduleSync`. That helper calls `ContentResolver.requestSync`. The installed environment and resulting sync effects require observation.

## Reproduction

From this directory in the repository, supply the two original APK files and the reviewed baksmali build (`2.5.2.git2771eae-debian`).

```sh
python3 -I -B verify.py --previous-apk "$PREVIOUS_PROVIDER_APK" \
  --current-apk "$CP3A_PROVIDER_APK" --current-calendar "$CP3A_CALENDAR_APK"
python3 -I -B test_callers.py -v
```

The binary verifier completed against both Pocket4 originals with 7 prior hashes reproduced, 15 equivalent method bodies and both generations of URI route IDs checked. The caller tests import both Main models and execute their actual generated SQL on in-memory SQLite. They check unrelated rows, each ownership field changing after candidate selection and an event appearing before deletion.

This evidence qualifies the static provider implementation for the two reviewed inputs. Installed Calendar identity, capabilities of the CP3A client, current Main and provider identity, permission checks, the owned transaction, sync effects, post-delete readback and app acceptance still require device evidence. The existing standalone Calendar installation receipt describes the earlier installation.

## Current Calendar client

The CP3A client in the same system image is `/system/product/app/Calendar/Calendar.apk`, version 37, SHA-256 `726241395b485794badd1a1fdcef4298ebb284f67826d73a7e2648f2b7a5382e`. The optional `--current-calendar` check verifies the full APK, its DEX and resource table, and the complete disassembled account-query callback. It also checks each of the 669 decompressed ZIP members for the five fixed strings required by the former local-calendar flow in both UTF-8 and UTF-16LE.

In `AllInOneActivity$QueryHandler.onQueryComplete`, a non-null empty query result while the activity is active closes the cursor, sets `allowSkip`, and requests `AccountManager.addAccount("com.google", "com.android.calendar", …)`. The core and reminder drivers require the English button `Create local calendar`, the field hint `Calendar name`, the initial value `On this device`, the account owner `Droidloom local calendars` and the internal name prefix `droidloom-local-`. None of those literals occur in the selected APK. A fresh successful provider review therefore leaves the client first-use case open.

The AOSP Calendar source checkouts on Pocket4 and ai395 both point to clean commit `7a9e63dea83dfdab46db04fed58642bd8856dede` from 26Q2. The original source at `src/com/android/calendar/AllInOneActivity.kt` contains the same account request. Its default `res/values/strings.xml` directs users to add a Calendar account and make a calendar visible. Read-only upstream ref lookup returned this commit for both `android17-release` and `android17-security-release`. The Android 17 tag returned was `android-17.0.0_r1`. These upstream Kotlin sources omit local-calendar creation. The R38 cohort separately retains a functional port built from the CP3A binary and reviewed smali source.

```sh
git ls-remote --refs https://android.googlesource.com/platform/packages/apps/Calendar \
  'refs/tags/android-17*' 'refs/heads/android17*' 'refs/heads/*26Q3*' 'refs/tags/CP3A*'
git show 7a9e63dea83dfdab46db04fed58642bd8856dede:src/com/android/calendar/AllInOneActivity.kt
git show 7a9e63dea83dfdab46db04fed58642bd8856dede:res/values/strings.xml
```

## Rebuilt local-calendar candidate

R38 retains the complete smali patch inputs for a local-calendar port based on the exact CP3A Calendar APK above. The release compiler uses smali. The retained reconstructed Java files document the helpers, and the five pure Java models have executable tests. The original Java implementation is missing.

On Pocket4, the retained-manifest SHA-256 was `eb3c1953881101363283ebd7c4fd246cf8e8265be3fd2545a79b0adb110315cb`. Replaying the retained unsigned builder against the original system image produced the same 2,608,664-byte output, SHA-256 `fd57ab87c63925c59bfe4429ad3aa118861f468355aa1756687ceef40648eb24`. It changed 16 methods in six classes, checked 445 original primary classes, preserved all 439 untargeted classes, and round-tripped 60 helper classes. The only changed original ZIP payload is `classes.dex`. The added payload is `classes2.dex`, which contains all five literals required by the Main callers.

The retained 2,672,653-byte signed candidate is `apps/Calendar-QPR1-functional.apk`, SHA-256 `8d3ca352655a27c25e9c0da12edd2fcd18bf26816fc53d04a209cf7ff7717b9f`, package `com.android.calendar`, version code 37. All 670 rebuilt ZIP payloads match its payloads. Its three additional entries are signature metadata. `apksigner verify --verbose --print-certs` passed with scheme v3 and one certificate, `a40da80a59d170caa950cf15c18c454d47a39b26989d8b640ecd745ba71bf5dc`, matching the current client profile.

The actual helper DEX implements the editable calendar name and confirmation dialog. Its store creates the local row with the account name, type, random UUID prefix, display name and owner required by both Main callers, checks that the scoped row is absent, then reads back the returned provider row ID and identity. The five retained pure Java tests were recompiled and executed with Android PDK JDK 21.0.4. All 116 checks passed across AlertIdentity, EventDraft, EventReference, ProviderReceipt and SnoozeState.

Run the retained builder in a new temporary directory. Set `COHORT` to the R38 QPR1 CP3A cohort directory and run the Java model tests with a JDK supporting `--release 8`, such as JDK 21.

```sh
ports="$COHORT/app-ports-20261108-8b88-r1"
workdir=$(mktemp -d)
python3 -B "$ports/source/calendar/build_unsigned.py" --image "$COHORT/official/system.img" \
  --tools-dir "$ports/tools/smali" --zipalign "$ports/tools/android37/zipalign" --output "$workdir/build"
python3 -B "$ports/source/calendar/run_model_tests.py"
apksigner verify --verbose --print-certs "$ports/apps/Calendar-QPR1-functional.apk"
```

The earlier standalone installation receipt references APK `c8a9d40dbfb3c975748e7c0520515316a5ef573414193e3128efa9ed400665e1`. The current image selects `72624139…`; its local-calendar port is a distinct, rebuildable candidate. Adoption requires publishing and selecting the exact port, establishing installed and retained user-data identity in the current Main, and running the local-calendar business and cleanup cases. This review performed zero installs, account operations or provider writes.
