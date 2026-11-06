# Exact actual microG private parser budget

This is an independent local adapter for the successful microG correction and private readback. It does not change the original parser, its eight core functions, the old capture failure, the permission ledger, any device state, or any other file's 256 KiB input limit.

The sole expanded input is the exact PM body captured by job `1a1b2d790f2-fc05-7ffb` and completely read back by job `1a1b2ea0995-fc05-8030`: 1,478,016 bytes, SHA-256 `738586aac7aef5aafee12cc238bb0f70be69ba218d8b512b25fe168559dfab8d`. Both its full remote pin dictionary and its exact local private pathname must match before `private_input_limit` returns 2 MiB. Every other dictionary or path returns 256 KiB, including microG AppOps.

The single changed line in `read_private` replaces its constant 256 KiB bound with this selector. Its original outside-repository requirement, nofollow open, bounded read, exact size/SHA, complete nine-field held/path stat recheck and finally close are otherwise unchanged. `need`, `sha`, `unknown`, `lines`, `section`, `parse_package`, `parse_appops` and `derive` remain byte-identical.

The new closed `main` accepts no target/path arguments. Before reading any private body it verifies the frozen independent full-joint correction, exact UID 10118/versionCode 252432034, both actual stream pins, the exact completed private-readback receipt, the authoritative durable successful terminal and actual start's source/argv/key binding. These public artifacts are frozen in `INPUT_CLOSURE.json`. It uses only the expected private files under `p4_private_ui/fixed45-permissions-compressed-readback-r2/batch-02/` and creates a new public `actual/PERMISSIONS.derived.json` with `O_EXCL` after interpretation and final FD equality.

One real local file-budget control passed: a self-created 256 KiB nonservice file is accepted, 256 KiB + 1 is rejected, the exact microG metadata selector alone chooses 2 MiB, other path/hash/size combinations do not, and all eight original parsing definitions are byte-identical. The test reads no actual service body and creates no device request. Positive interpretation of the actual 1,478,016-byte file remains pending root review of this source.

After that review, the local invocation is simply:

```text
python3 -B interpret_microg_exact.py
```

No shell, Android, ADB, grant, install, UI, namespace or Main query is executed. No raw PM/AppOps text or usage timestamp is published. Unknown text stays UNKNOWN, AppOps modes are not treated as permission grants, unprefixed AppOps scope stays unknown, roles remain unqueried, and no operation or production-readiness result is inferred.
