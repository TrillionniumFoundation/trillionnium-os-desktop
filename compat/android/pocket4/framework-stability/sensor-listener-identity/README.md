# Sensor client registration uses Binder identity

## Fix and current status

The candidate fixes duplicate registration and missed unregistration when two C++ interface wrappers refer to the same Binder. Both hashing and equality in `SensorService::mBinderStateRecipients` now use `IInterface::asBinder`. The map still retains the original listener object. Registration, unregistration, death cleanup, destructor behavior, locking, rollback and return values retain their original method bodies.

The original implementation reproduces four contract failures in the host regression. The candidate passes all 17 cases. An independently executed replay of the portable runner also passes. **A complete Android library build, ABI comparison, deployment and device lifetime qualification remain pending.** This source result grants no whole-App production readiness.

Apply [binder-identity.patch](binder-identity.patch) from the root of the pinned `frameworks/native` checkout. The original header hash is recorded in [SOURCE_MANIFEST.json](SOURCE_MANIFEST.json) and [evidence-summary.json](evidence-summary.json). Do not apply it to an unmatched source revision.

## Why the identity matters

A remote interface conversion may create a fresh C++ proxy wrapper for an existing canonical `IBinder`. The previous hasher used `listener.get()`; the default equality predicate compared those wrapper pointers too. Repeated registrations could therefore add independent recipients for one Binder, while unregistration through a newly converted wrapper could miss the original entry.

Each retained recipient owns its listener. A retained interface proxy also holds references to the canonical Binder. The corrected hash and equality treat aliases of the same Binder as one registration, while keeping distinct Binder objects separate even when their caller PID is the same.

The existing mutex covers the duplicate check, notification registration and insertion. Normal removal extracts the exact original recipient under that mutex and unlinks it after releasing the mutex. The patch preserves these boundaries. It also preserves the behavior of an old unregistration overlapping a new registration: the old callback is removed without removing the new recipient.

## Installed-code diagnosis

The old framework aborted at 04:42:33 UTC on 2026-11-06. Its native trace reported the `incWeak` safety assertion with a previous weak count of 1,048,576 while registering a SensorService client. This is a reference-limit assertion, not evidence of integer wraparound or that many registrations.

Read-only capture of the three relevant mapped libraries established the same Build IDs as the old tombstone. The capture checked actual mapped backing files, two complete hashes and unchanged framework identity. No process memory was read or library executed.

Saved-file disassembly then established two distinct facts:

- The installed SensorService hashes and compares the raw interface-wrapper pointer and retains a new listener/recipient on a miss. The identity defect is present in the installed code.
- The fatal Binder call occurs while copying a temporary weak reference to the current `BpBinder` for an already-known frozen-state callback. Its normal path contains the matching releases. It precedes callback-vector insertion and is distinct from the initial driver-notification registration.

These observations establish a concrete accumulation path compatible with the crash. They do not identify the initiating App, count historical registrations, or prove that every old reference came from this one map. The patch does not raise or bypass the reference guard. Raw tombstones, process memory, full maps and private binary snapshots are not included here.

## Reproduce the host regression

On a POSIX host with Python 3 and a C++20 compiler:

```sh
python3 tests/run_saved_regression.py --compiler g++ --output /tmp/sensor-listener-regression-new
```

The output directory must not exist. The runner validates the five test-input hashes, compiles both unchanged saved translation units, runs them, checks all expected summaries and rechecks the inputs. The original must reproduce exactly four expected defects with zero unexpected failures; the candidate must satisfy all 17 contracts.

| Scenario | Original | Candidate |
|---|---:|---:|
| 64 new wrappers for one Binder: retained entries/callbacks | 64 | 1 |
| Same case: test Binder strong references | 65 | 2 |
| 16 concurrent registrations for one Binder: successes | 16 | 1 |
| Same case: duplicate responses | 0 | 15 |
| Unregister through a new wrapper for the same Binder | Misses entry | Removes original recipient |

Other cases cover the same wrapper, distinct Binders sharing a PID, null/disabled-feature inputs, failed death links, frozen-callback failure rollback, later registration after a failure, lock release before normal unregistration, duplicate removal, death/destructor cleanup, dead-remote handling and overlapping old removal/new registration.

This regression compiles the complete original four lifecycle method bodies and the actual original/candidate map declarations, with unmodified AOSP `StrongPointer.h`, `LightRefBase.h` and allocator definitions. Binder transport, fixed IPC caller identity, logging, unrelated policy members, `IInterface`, and the recipient layout are explicit test substitutes. The measured strong count belongs to this adapter; it is not a kernel Binder weak-count measurement or a full Android SensorService compilation.

## Source and release boundaries

Fifteen selected cached files were byte-equal to their Git HEAD blobs:

- `frameworks/native`: `ae266dcb706d083868578cfedce381ef44488a07`
- `system/core`: `545d2487e38192a2ce25040897ced877cf6b4f53`
- Java/JNI sensor-manager files in `frameworks/base`: `94b4c163b7dfe5ce3607f7bb8456f9573f7de57d`

This does not establish an entirely clean checkout or that these exact revisions produced every installed library byte. The next gate is a paired original/candidate Android build with exported-symbol, dependency, SONAME, load alignment and object-layout comparison, followed by isolated runtime validation and controlled deployment.

AOSP source fragments and utility headers retain their upstream Apache-2.0 terms; the upstream utility [NOTICE](NOTICE) is included. See the [continuation checkpoint](../../continuation-r11/checkpoint-14/README.md) for the fixed 45-App status.
