# normal05 sealed source-r2 — independent final packet review

Reviewer: `app_history`. This is a local-only follow-up to `INDEPENDENT_REVIEW_app_history_r1.md`. No valid packet, device job, Main observer, build, installation, UI action, namespace entry, or Git write was performed by the reviewer.

## Conclusion

No blocking source/packet defect was found in the exact sealed source-r2 inspected below. The missing scope/transport conditions from the source-r1 review are now concretely filled. Dispatch remains coordinated by root, and the actual host resource admission, typed runtime/App checks and four owned-child lifecycle controls must succeed at execution time. Static review does not claim those actual controls passed.

## Exact artifacts

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| `source-r2/SOURCE_PINS.json` | 9939 | `97f3585bcaec3de7fd08dbf17a5f6482e5072e04adae34bb72f3ab9ac9c07c1d` |
| `source-r2/exact-request.json` | 906726 | `a14c1205fa732325c7da71f7fd7559132987c25463b6af0630dc5c5fbf7569c4` |
| `source-r2/exact-stdin.json` | 824918 | `20e061e7a28c9aca81ef5ae33fa8578caf9ee35b7eef6660e8d7675c2db2762d` |
| `source-r2/stage.py` | 7137 | `5723e4064379832141e068fb87b7a4460e594545ffc3d9a94f779df847b9ad83` |
| `source-r2/main_snapshot.py` | 24529 | `3c9c28efe41148a0e3812a9c96519ed7813c8e85f448bb7ba7596a608ac5adc3` |
| `seal_source_r2.py` | 11347 | `960c08f990ced5ac124266c897df31f0b5242058f8ebc352f11531fd10fae202` |

All manifest file rows matched the actual local bytes. The exact request's stdin is byte-for-byte equal to `exact-stdin.json`; its Python body equals `transport-boundary.py`. The boundary's wire byte count/digest and stage source digest match. Every one of the 21 embedded staged source members equals its on-disk file and the staged EXPECTED pin.

## Change review and real scope binding

An independent AST comparison, with only the specifically named assignments normalized, proved these source-r1 → source-r2 changes:

| File | Only changed assignments |
|---|---|
| `main_snapshot.py` | `APP_SCOPE_PIN`, `APP_SCOPE_PACKAGES` |
| `root_snapshot_supervisor.py` | `SNAPSHOT_SHA` |
| `fenced_build.py` | `ROOT_SUPERVISOR_SHA`, `SNAPSHOT_SHA` |
| `stage.py` | `EXPECTED` |
| `transport-boundary.py` | `WIRE_BYTES`, `WIRE_SHA256`, `STAGE_SHA256` |

`framework_build.py`, `capture_lifecycle.py` and `pure_controls.py` remain byte-identical to the reviewed source-r1. The original 10 GiB/zero-owned-swap/15 GiB fresh available-RAM admission and exact own-job resource modification are unchanged. Root/outer child-retirement logic is unchanged.

The final App scope is the actual post-Douyin 57,340-byte file, SHA-256 `489129d6e39a5aebc410ebcf74706279a99ff6751a15bd0a6b324ddd007e01a4`. The sealed snapshot's package constant and the manifest's package list both exactly equal all 46 keys in that actual scope. The sealer verifies the same runtime epoch, the original qualification's pinned initial scope bytes, and equality of the initial/final member sets. Its removed-member negative control occurs before sealing. No caller-selected subset is passed to the runtime App guard.

## Preserved launch envelope and pending runtime evidence

The exact request was compared with the saved normal04 launch envelope `70e19da34d7ef06c5f4d0eadd90291e07983ead1f074a3fc4a6a1ee8c84f2eb5`. Only the embedded body, stdin and unique idempotency key differ. Host, executable, argument prefix/suffix, 6400-second timeout, CPU quota 200, memory limit 10,737,418,240 bytes and nice value 10 are preserved.

The sealer was read in full. Its only reported local subprocess is a deliberately truncated-wire negative test, which rejects before stage execution. The saved 59 pure controls and four sealing checks are scoped to local validation; they are not the four real host capture-lifecycle controls scheduled inside the valid run.

At actual execution the fresh typedguard, complete App scope, fixed eight-role protection including composer, original Main limits, fresh host RAM gate, pre/post OOM fence and owned-child retirement must all pass. Failure or timeout must retain the actual receipt and must not be upgraded to a build or runtime PASS. The snapshot's existing 15-second observation budget remains intact.

No framework/App deployment is included. Runtime authorization and production-ready claims remain false. Original R1 UNKNOWN, all prior failures, the Main Bili Accept restriction, Meituan location restriction, and integrity constraints remain unchanged.
