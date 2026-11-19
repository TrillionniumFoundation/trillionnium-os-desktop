# Official Gallery DEX source identity

The current GSI already contains the official Gallery APK. The remaining
problem was its relationship to the old modified candidate and the source
inputs of the old ART verifier. This packet closes the official DEX class-set
and selected-method source identity questions. It does not qualify ART,
installation, rotation, editing, MediaProvider cleanup, or application business
behavior.

## Actual result

On 2026-11-19 at 11:20:53 UTC, an ordinary `qq` process on `ai395` read the
retained 7,390,425-byte official Gallery APK and its complete 326,611-byte
SDK37 source receipt. Their full SHA256 and nine-field file identity were
unchanged before and after. The retained receipt binds the APK to inode 3477
at `/system/product/app/Gallery2/Gallery2.apk` in the complete CP3A GSI with
SHA256 `dc781249bb4724b7a0777e5077321b84576db46f61abb4b9086b81077bfd0ab4`.
The new worker did not reread that full GSI body or rerun the SDK.

The official APK is `com.android.gallery3d`, version 1.1.40030/code 40030,
SHA256 `835fe119745324276457b4434fc39f25b633e752c822d2fc9be40eb4b2d45439`.
Its single `classes.dex` is 1,857,660 bytes, DEX version 039, SHA256
`725ac7153e9ab4a9742672c238fc140bda311e6c940daf9e1d10a2b26c33e829`.

The worker verified the DEX's own complete Adler32 and content SHA1, bounded
its tables, decoded every defined-class descriptor, and rejected duplicates.
It observed **2,144 unique defined classes**. The canonical descriptor list is
119,880 bytes, SHA256
`48784ff0a225c9319f685c86b44772d2240809a857686965aab3cdbe8b0d265e`.
Those bytes exactly match the class-name list pinned by the old verifier.
This permits reuse of the same class-name expectation, not the old ART result.

The following two definitions were located in the official DEX:

| Declaring class and method | Method ID | Instruction bytes | Instruction-array SHA256 |
| --- | ---: | ---: | --- |
| `ExifInterface.rewriteExif(String, Collection): boolean` | 7979 | 224 | `785b2b337c991f1321c757b7960f67335e579711dba35d03f6aad4ffcbf92992` |
| `MenuExecutor$MediaOperation.run(ThreadPool$JobContext): Void` | 11276 | 240 | `6df2bff8180c365d92ecc0d14dce97bd25d64876a1cd1b53dff1b2723b201f47` |

These hashes cover only the exact instruction arrays. Additional recorded
hashes cover each code header plus its instruction array. Neither kind includes
exception handlers, debug information, or annotations, and neither proves
behavior. The entire official DEX SHA continues to bind all its bytes.

Five actual in-memory mutations were rejected: truncated DEX, bad Adler32,
bad content SHA1, a class table outside the fixed-table region, and duplicate
class definition. The latter two controls repair the header checksums so the
structural checks must reject them independently.

## Resource and failure evidence

The successful unit was limited to CPU 31, 192 MiB memory, zero swap, 16 tasks,
and 60 seconds. The worker additionally limited address space to 128 MiB and
CPU time to 30 seconds. Systemd recorded 115 ms runtime, 87 ms CPU, and 46.6 M
peak memory. The worker spawned no child processes, made no Android or SDK
calls, and wrote no APK or DEX copies. Only bounded JSON source metadata was
written.

The first invocation refused its actual CPU-affinity check before creating its
work directory or opening the APK. The same worker bytes then ran with explicit
`taskset -c 31` inside a separate bounded unit. The refusal and proof of an
absent work directory are retained under `history`; they are not counted as a
successful source run. Both original units were subsequently not-found and
their cgroups absent.

## Replay and remaining work

```sh
python3 -I -B compat/android/pocket4/current-app-acceptance/gallery-official-dex-source-20261119/verify_gallery_source.py
```

The consumer checks all exact packet hashes, the original Gallery source
receipt, the historical verifier's literal name-list and DEX pins, and the
current four-provider cohort. It reads the historical Python as syntax only;
it never imports a runtime entry. It checks that the current MediaProvider APK
is source-qualified while its actual UID and cleanup semantics remain pending.
The replay performs no APK/DEX body read, SDK command, or Android action.

The old runtime candidate is a different APK (`6677d382…`) containing a different
DEX (`6a994fab…`). Its old ART result and two modified-method repair claims do
not transfer. The old installer requires one `pm install`, and the rotation
case requires that install receipt; those entries remain retired. Required
future work is fresh official-DEX ART verification against the actual current
framework closure, image-installed custody with actual Main/UID, reviewed
official rotation/edit behavior, and current MediaProvider owned-fixture
cleanup. Every runtime, business, and production flag remains false.

The parser's table layout follows the [AOSP DEX format](https://source.android.com/docs/core/runtime/dex-format).
It is a source inventory parser, not a complete DEX semantic verifier.
