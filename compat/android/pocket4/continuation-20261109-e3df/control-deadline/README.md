# Lifecycle request deadline source capsule

The lifecycle socket receiver now uses one absolute two-second deadline for the
first-byte/SCM_RIGHTS receive and every subsequent body read. A client cannot
extend the budget by sending another byte before each per-syscall timeout.
The 64 KiB request cap, peer credentials, progress envelope, descriptor identity,
close-on-exec behavior and install-only descriptor policy remain checked.

## Exact source and dependency closure

The public preimage is the latest Settings control source from
commit 75492962a9b9afdd6b9f28fec979b9c40419ec0b and
continuation-20261109-2840/apps-settings-page/source. The deadline helper,
receive function and six tests were transplanted as one minimal delta; all
other Settings control bytes remain unchanged.

The independent Cargo workspace contains the complete, unmodified manifests
and source of droidloom-supervisor and its three internal dependencies from that
same commit, except for control.rs. SOURCE_BINDING.json records every original
Git blob and SHA256, preimage, postimage, patch, toolchain and external lock tuple.
Only workspace member paths were adapted. The pruned Cargo.lock retains all
51 external name/version/source/checksum tuples from the original lock in
provenance/original-workspace-Cargo.lock. This builds the real control.rs and
its actual APK/SCM helper, not an extracted or mirrored receiver implementation.

## CI command

Run on Linux with a target directory outside this capsule:

    CARGO_TARGET_DIR=/tmp/pocket4-control-deadline-target cargo +1.93.0 test --locked -j 1 --manifest-path compat/android/pocket4/continuation-20261109-e3df/control-deadline/Cargo.toml -p droidloom-supervisor --lib control::request_deadline_tests -- --test-threads=1

The six exact test names and their native result hashes are in QUALIFICATION.json.
Native execution with Rust 1.93.0 reported 6 passed, 0 failed and 0 ignored.
A separate complete control:: run reported 110 passed, 0 failed and 3 ignored:
two pre-existing explicit root/cgroup tests were not selected, and one ignored
private process entry is invoked by its parent fixture.

The original production-base reproduction and qualification are recorded
separately: two regressions failed before the fix, then the full control group
reported 66 passed, 0 failed and 1 ignored. Its preimage differs from the public
Settings source, so its patch is provenance only and must not replace the
published Settings control file.

## Scope

This is source qualification. No image, APK or service was installed or started.
Android runtime qualification and application acceptance are unchanged and
remain false here. Local raw journals and compilation targets are intentionally
excluded from the capsule.
