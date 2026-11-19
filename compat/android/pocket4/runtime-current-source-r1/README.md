# Pocket4 current complete source packet

This packet reconstructs producer tree `ab772244ccef9bbce1ef90c5a92ff6d66e17f64c`
with **2,340 files / 43,947,940 bytes**. It preserves the complete source capsule,
all original targets and all ignored cases. The cumulative overlay is bounded by
the original 5 MiB expansion and 64 MiB decoder limits.

## Changes

The native successor handles original init's existing property-service threads.
It binds the actual notification ID, instruction pointer and six arguments to the
original thread PIDFD, the one-shot kernel ARM request, normal CONTINUE and the
real syscall exit. Original native errno and namespace observations remain
mandatory. The production seccomp filter refuses later NEW_LISTENER filters
while preserving native TSYNC, query and PR_SET_SECCOMP operations.

The ordinary control records real Linux behavior: a second live listener is
rejected with EBUSY; a later listenerless NOTIFY filter yields ENOSYS; replacement
after the original listener is closed is demonstrated separately. The producer's
original listener is retained, and the production rejection remains enforced.

The two actual intermediate failures are retained in their original receipts:
a Rust borrow conflict, then an incorrect new listener-control assumption.
The final source fixes the borrow only after its complete guard validation and
corrects the control to the real kernel behavior. No existing test was removed,
renamed or newly ignored.

## Exact verification scope

The affected complete supervisor harness actually passed **531 ordinary cases,
zero failures and 25 unchanged ignored cases**, with all original children
reaped. The source tree and complete file identities matched across execution.
This adds seven cases to the preceding 524-case supervisor catalog.

The full current runner requires **49 harnesses / 1,488 ordinary cases /
30 unchanged ignored cases**, nine separate recipe tests, 19 normal release
binaries, three compiled examples and 20 documentation targets. The current
full CI must pass on this exact packet; the local supervisor result is not a
substitute. Example mains and hardware-specific ignored branches are not
claimed executed by those gates.

The immediately preceding producer tree was
`fa0382574f4fc18f59b2b5dd67a30939167d8c3a`, with packet inventory
`d76e784431bad44dd69edc2eacf3744574dfddb63bf7f2b55e017b7c3f13a707`.
Its actual complete run
[44454070189](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/44454070189)
passed 1,481 ordinary cases and built 19 normal release binaries. That result
belongs to the preceding tree. All unchanged recipe targets and source repairs
remain in this successor.

## Reproduction

Use the FILES.sha256 digest pinned by the reviewed commit's workflow and source
guard. The inventory covers all thirteen other packet files. Run:

```text
python3 -I -B verify.py --inventory-sha256 <reviewed-inventory-sha256> --output <fresh-source-directory> --report <fresh-report.json>
python3 -I -B test_verifier.py
python3 -I -B test_runner.py
```

The unchanged preparation script and run_ci.py retain their normal locked build,
complete catalog, complete terminal, ordinary release, recipe and source
bookend checks. SOURCE-CAPSULE.tar.xz, EXPECTED-BINS.json, EXPECTED-TARGETS.json,
EXTRA-TARGETS.json, UPDATER-EXACT64.json, prepare_ci.sh and test_runner.py are
byte-for-byte unchanged from the preceding packet.

## Open acceptance gates

The new kernel ARM implementation still needs its complete kernel build and VM
qualification. The later default namespace, original apexd loop/AVB/dm-verity
activation, vendor image and real Android/application acceptance remain open.
The independent vendor R12 controller still targets the preceding tested source
and its actual normal release tools; this packet does not change its frozen
inputs. The three permitted app exclusions remain TextNow, TextFree and Uber.
**Android starts: 0. Production ready: false.**


## Cumulative overlay

95 paths; 615020 compressed bytes; SHA256 `228c7f5612394b2406c0a2e2f376a400ce2a4475fa27036e9ba4aaad344ac618`. Expanded bytes: 4628480; SHA256 `77cc23bf759b9cb08e23ed9d97da429b19d29bcedaae57313e583d836475f3fd`.
