# Inspect paired image format and existing extraction capabilities

CellSpec::validate explicitly rejects a relay policy combined with the legacy lmkd.rc override. The earlier RC-read README's proposal to retain that override is therefore inapplicable. That frozen proposal is preserved; no production validation is changed. The old RC read establishes the existing init import/start relations only. The underlying image RC remains OPEN.

This fixed request opens only the first 4096 bytes of the manifest-pinned system image and executes only --help for the two fixed fsck.erofs locations, or -V for the fixed debugfs location, after root ownership, safe modes, native ELF, no file capabilities, held digest and before/after identity checks. Missing tools are reported. It does not extract or mount the image, does not write files, and does not claim the complete image hash has been verified.

Upstream erofs-utils documents --path for selecting one inode; this is only a prospective option until actual installed help confirms it. Reference: https://kernel.googlesource.com/pub/scm/linux/kernel/git/xiang/erofs-utils/+/1ca8aff02c99d111b59bdc8f458b500d08374d16/man/fsck.erofs.1 . No host version or flag is inferred from that source.

If the installed tool supports the exact one-file operation, the next separately reviewed request will first verify the whole immutable image digest, extract only /system/etc/init/lmkd.rc into a new owned path as an unprivileged process, retain its exact bytes, and revalidate the source identity/digest. No loop device, mount, namespace, Main root or new Android service is needed for this option. This inspection is NOT that extraction request.

The original request budget remains CPU1/128MiB/nice10/30s. It has not been submitted. Any unknown transport result is reconciled under the same fixed key.
