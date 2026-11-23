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
python3 -I -B verify.py --previous-apk "$PREVIOUS_PROVIDER_APK" --current-apk "$CP3A_PROVIDER_APK"
python3 -I -B test_callers.py -v
```

The binary verifier completed against both Pocket4 originals with 7 prior hashes reproduced, 15 equivalent method bodies and both generations of URI route IDs checked. The caller tests import both Main models and execute their actual generated SQL on in-memory SQLite. They check unrelated rows, each ownership field changing after candidate selection and an event appearing before deletion.

This evidence qualifies the static provider implementation for the two reviewed inputs. Installed Calendar identity, capabilities of the CP3A client, current Main and provider identity, permission checks, the owned transaction, sync effects, post-delete readback and app acceptance still require device evidence. The existing standalone Calendar installation receipt describes the earlier installation.
