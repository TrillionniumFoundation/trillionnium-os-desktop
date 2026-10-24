# Live read-only transition policy

Dynamic changes to either the mount or filesystem RDONLY state return
`EOPNOTSUPP`. The decision runs under the mount topology write lock before any
filesystem callback, sync or flag mutation. This preserves the old state even
when the request also contains NOEXEC, NOSUID or NODEV. Remounts that preserve
RDONLY still work. Initial read-only mounts remain supported and are covered by
[the 57-case readonly probe](../readonly/README.md).

This is a fail-closed compatibility restriction, **not an implementation of live
writable-to-read-only conversion**. An existing writable mount stays writable
when conversion is rejected; callers must handle the error. Full conversion
requires superblock-wide writer and mapping lifetimes, coordination of all
metadata/atime writers, alias and namespace handling, dirty-page flush ordering,
and an atomic state publication/recovery contract.

The 37-case native guest probe tests tmpfs and ext2 with existing writable shared
mappings, read mappings retaining MAY_WRITE, dirty mapped pages, bind aliases
and a child with a cloned mount namespace. For each rejected request it compares
all mountinfo flags, mapped bytes and the original descriptor/mprotect behavior.
For ext2 it also hashes the complete 32 MiB raw guest disk immediately before and
after each rejected call while dirty pages are retained; the call must not flush
or mutate the disk. Later intentional probe writes and guest shutdown may change
the image, so an end-of-run disk hash is recorded but is not an unchanged-disk
assertion for this workload. The readonly probe separately enforces whole-image
identity for the initially readonly filesystem.

```sh
python3 tests/workloads/linux/remount/run_guest.py \
  --kernel /absolute/path/to/fresh/kernel.elf \
  --initramfs /absolute/path/to/build/initramfs.cpio.gz \
  --output /absolute/path/to/new/evidence-directory
```

No host mounts, host block devices or networking are used. The probe requires a
disposable-guest marker. The runner records commands, source/artifact hashes,
serial output and a strict complete-result check; `--expect-failure` is only for
a completed negative control, not a way to accept a crash or setup failure.

Validation status: the final 37-case version completed on the preceding freshly
built read-only-syscall-fix kernel (`3bc14def2c40b0aabd7dc427745dd8dd7f85005bd3f113a54b11b981827af6af`)
with 20 failures, confirming false-success and changed mount flags/write policy.
The final 57-case initial-readonly/policy probe also completed on that kernel,
with eight failures. Patched-kernel compilation and positive native results
remain pending integration validation.
