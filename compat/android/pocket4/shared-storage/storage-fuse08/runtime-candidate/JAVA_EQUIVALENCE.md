# Runtime method candidate: reference Java equivalence

This candidate modifies only `StorageSessionController.onVolumeUnmount(ImmutableVolumeInfo)` in a disassembly of the captured, installed `services.jar`. It has not been installed or executed by Android. It is not a complete Java/AOSP source build.

## Exact input

- Installed JAR: `f33987e633e476f47ea043af3f7fb94907fd2431fa2b5b49df84cb586bce5c50`.
- Target member: `classes3.dex`, `bbbeed4aeb197113710fd084ebe7fc30d42c8ea0baf60c36e12fa62c238cd172`.
- Complete original controller disassembly: `e0ddf859ff6c243681256b2100baab7bbb4228b10e77ad65812b301fd9bd1523`.
- Complete candidate controller: `9c7070a802038cb1eaa4a18ebb3db12785aad1d7e96d37c50d5c62e92abe6e61`.
- The bytes before and after the target method in that class are unchanged. No additional method, field, class or dependency is introduced.

The actual disassembly confirms the defect directly. `onVolumeUnmount` calls `onVolumeRemove`, whose existing implementation calls `StorageUserConnection.removeSession`. It then calls `removeSessionAndWait`, which removes the same ID again and returns immediately if it finds no session. The actual `ActiveConnection.endSession` uses the existing `bindIfNotConnected=false`, ten-second wait path. This latter method remains unchanged.

## Java reference

The intended behavior is the one-method variant in `pinned-m600-candidate/frameworks/base/services/core/java/com/android/server/storage/StorageSessionController.java` (complete candidate SHA-256 `a1972cb6e5b84303069250bf8289455505a5c48c270acf666e1ed7effafdb8e0`). The reference file comes from frameworks/base commit `94b4c163b7dfe5ce3607f7bb8456f9573f7de57d`, with the narrow single-removal change. That source commit has not been established as the complete Java origin of the installed JAR.

```java
if (!shouldHandle(vol)) return;
String sessionId = vol.getId();
long token = Binder.clearCallingIdentity();
try {
    int userId = getConnectionUserIdForVolume(vol);
    StorageUserConnection connection;
    synchronized (mLock) {
        connection = mConnections.get(userId);
    }
    // Existing informational log remains here.
    if (connection != null) connection.removeSessionAndWait(sessionId);
} catch (ExternalStorageServiceException e) {
    // Existing error log remains here.
} finally {
    Binder.restoreCallingIdentity(token);
}
```

## Register and control-flow mapping

The candidate increases the register count from 9 to 11. Existing local registers `v0` through `v6` keep their original roles; the existing symbolic parameter registers `p0` and `p1` still identify `this` and `vol`. The two new local registers hold the connection user ID (`v7`) and monitor object (`v8`). All invoke operands still fit the non-range instruction form.

| Java operation / path | Candidate instructions and exception handling |
| --- | --- |
| Unsupported volume or reset in progress | Call the existing private `shouldHandle` before retrieving the session ID or clearing identity; return on false. The result briefly occupies `v0`, before the original log tag overwrites it. |
| Session ID and Binder identity | Retain the original `getId`, `clearCallingIdentity`, `v1` session ID and `v2/v3` long token instructions. |
| Clone/parent user mapping | Invoke the unchanged `getConnectionUserIdForVolume` after identity is cleared. Its result is stored in `v7`. |
| Connection lookup | Load `mLock` into `v8`, enter it, read `mConnections.get(v7)`, cast to the actual connection type, store in original register `v4`, and release `v8`. |
| Failure before the monitor is acquired | The range from `try_start_a` to `storage_before_lookup_end` reaches the original exception logger or catch-all identity restoration. It does not attempt to unlock a monitor whose acquisition failed. |
| Failure during the protected lookup | `storage_lookup_start` to `storage_lookup_end` routes to `storage_lookup_failed`; that handler releases `v8` and rethrows to the original outer exception / identity-restoration handlers. The normal path has already released `v8` before any log or session wait. |
| Null connection | Preserve the original null test and normal identity restoration. No session removal is attempted. |
| Present connection | Preserve the original informational log and single `removeSessionAndWait(sessionId)` invocation. There is no `onVolumeRemove` call and no separate `removeSession` call in this method. |
| End-session error | Preserve the original `ExternalStorageServiceException` log. The original error-log catch-all still restores identity even if logging throws. |
| Other exception | Preserve the original catch-all restoring `v2/v3` before propagating the exception. |

The existing `onVolumeRemove` method remains unchanged for callers that explicitly request the non-waiting removal operation. `StorageUserConnection`, its active connection and session types, MediaProvider behavior, duplicate-start behavior and the ten-second timeout are unchanged.

## Build and qualification boundary

The candidate must be assembled into the copied target DEX and disassembled again. Verification must compare every class and every method, permit the declared target method only, preserve class/field/method sets, and compare every other JAR member byte-for-byte. In particular, the existing Wi-Fi/SystemServer changes in `classes.dex` and all of `classes2.dex` must remain identical to the captured installed input.

Register/label offsets and equivalent `const-string` encodings may change during assembly. Such representation changes need an explicit semantic comparison; they do not authorize new non-target behavior. A completed assembly plus these comparisons qualifies an offline DEX candidate only. Android verifier/ART qualification, live unmount/end-session behavior, data persistence, Main continuity and deployment are separate later gates. The historical nine-case host Java method regression remains evidence for its documented source variant; it does not execute this generated DEX.
