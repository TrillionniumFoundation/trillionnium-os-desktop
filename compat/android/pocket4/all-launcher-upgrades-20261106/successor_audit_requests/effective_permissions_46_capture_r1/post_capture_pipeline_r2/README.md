# Actual-only readback and literal interpretation for corrected capture revision 2

This is a local follow-on interface to `../bound-candidate-r2`. It does not submit a job, create a capture claim, query Main, change a permission, or supply any future job/log/grant value. It preserves the rejected unsubmitted r1 pipeline and the old45 capture STOP.

The selected capture plan is SHA `ae7570780e890f0855b2dc98ff4b5b387e52048deef4dcb9f33e2983e1735e58`, the serial gate is 30,205 bytes / SHA `2dbf56bace4ccca9e668d47cefda885fb5f1cbbfe8fe8a4018ff33dabd57bcbe`. All49 scope and actual46 component checks remain in that gate.

## 1. Prepare from an actual successful batch

```sh
python3 -B -I prepare_completed_readback.py --batch N
```

N is1–14. The program revalidates the entire actual capture/source chain and requires that batch to be in the serial gate's successful completed list. No request is generated for an unobserved, failed or unknown batch. It obtains the real service log paths, lengths and hashes from that exact batch. It calls the unchanged proven `render_reader` from `effective_permissions_batch_readback_r2/prepare_compressed_readback.py`; its five original per-file functions are unchanged.

The program creates a new `readbacks/batch-NN` folder once, containing the exact reader, request, source diff and `READBACK_PLAN.json`. Root reviews and dispatches the existing process request once; this local program does not dispatch it. The new host reader has no Main namespace entry or action lock and only opens the fixed already captured private logs. Its ordinary limits remain256KiB per file, with only the exact actual batch02 microG PM file allowed2MiB; total body size remains2MiB, compressed stdout1MiB. A larger combined capture is rejected, not truncated.

The source preparation writer retains the original local write/readback behavior; this does not claim an additional directory power-loss durability proof. Device log reads retain original file/path stat and hash rechecks and the original process FD count check.

## 2. Preserve and decode the actual private result

Save actual start metadata as `readbacks/batch-NN/actual-public/start.original.txt` and the complete durable terminal as `terminal.original.json`. Store the full compressed stdout outside the repository at:

```text
/workspace/scratch/265e5bca485a/p4_private_ui/fixed46-permissions-compressed-readback-r2/batch-NN/stdout.original.jsonl
```

Then use the actual reviewed plan SHA:

```sh
python3 -B -I decode_completed_readback.py --batch N --plan-sha256 ACTUAL_PLAN_SHA
```

The decoder requires exact source/request/start plus complete durable success. It verifies the entire compressed envelope and every decoded body before writing any decoded output. Seven original helper definitions are unchanged. Only local destinations and the1–14 range differ from the proven decoder. Private original stdout, decoded result and individual logs remain outside Git; `READBACK_RECEIPT.derived.json` contains only pins and observed resource metadata.

## 3. Interpret literal service rows

```sh
python3 -B -I interpret_completed_readback.py --batch N --plan-sha256 ACTUAL_PLAN_SHA
```

This independently checks the capture chain, selected identities, actual reader source/start/terminal/receipt, and complete private envelope. It reads private files by the actual matching pins, then imports unchanged original `need`, `sha`, `unknown`, `lines`, `section`, `parse_package`, `parse_appops`, and `derive`. The exact-path-and-pin2MiB exception is set only for the new actual microG PM file; the old capture's identity does not qualify a new file.

The parser retains exact whitespace, selects only the unique matching package/appId and User0 block, preserves missing/duplicate/unknown grammar as UNKNOWN, and does not infer shared-UID membership or unprefixed AppOps scope. A PM true/false row is an observation, not proof of successful operation or user denial. Modes are not grants. Role holders, network behavior, UI behavior, permission denial recovery and production readiness remain untested.

Safe `PERMISSIONS.PACKAGE.derived.json` files and an `INTERPRETATION_RECEIPT.derived.json` are written O_EXCL under the corresponding `actual-public` directory. Raw bodies and usage timestamps are never emitted. Existing capture results and UNKNOWN/FAILED records are not changed.

## Current state

At preparation, no new46 capture or private readback existed. Local controls confirmed batches01 and14 were refused before any reader directory was created; decoder helper inheritance and exact original parser source pins were verified. The control's process FD count remained4→4. These are local source/boundary checks, not device permission evidence. `PIPELINE_DIFF.patch` shows only r2 capture pins/locations and new private destination/key changes relative to the preserved unsubmitted r1 pipeline. There are zero new permission results, zero remote jobs and zero production-ready claims.
