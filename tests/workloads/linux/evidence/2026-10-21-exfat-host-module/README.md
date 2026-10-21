# Running-kernel ExFAT prerequisite

The original main `22a3284a14069f79c784e6bf33bb3c6035b9765f` A06 run
`39590054181`, job `119188464418`, failed before the Linux reference produced
any case observations. The preserved stderr reports `mount(..., "exfat", ...)`
returning errno 19 (`ENODEV`). The runner used `6.17.0-1022-azure`; the frozen
probe, loop binding and disk-image hashes stayed valid and cleanup completed.
The later guest and frozen-negative-control stages were skipped by this failure.

The workflow now tries the real kernel module first. On refusal it installs
only the Ubuntu extra-module package matching the currently running kernel ABI,
then requires successful module loading and an exact ExFAT registration in
`/proc/filesystems`. It preserves the running kernel, module filename/vermagic,
initial refusal and package-install output in the existing always-upload step.
`exfatprogs` and the original approved formatter-version rule are unchanged.
No userspace filesystem substitute or weakened observer result is accepted.

The Ubuntu package for the failed runner's exact ABI was downloaded without
installation, matched to the SHA-256 in Ubuntu's official HTTPS package index,
and inspected: it contains `lib/modules/6.17.0-1022-azure/kernel/fs/exfat/exfat.ko.zst`.
See `receipt.json` for package and module hashes, raw-artifact provenance and
local YAML/Bash checks. This is package-content evidence, not a local module-load
or mount result. The existing complete native CI remains required on the new head.

`python3 verify.py` validates the saved raw bytes and their original input chain.
The full 184 MB artifact and 51 MB package are deliberately not committed.
