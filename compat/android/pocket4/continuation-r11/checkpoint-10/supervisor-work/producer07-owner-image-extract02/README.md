# Original system-image LMKD RC: single-file extraction request

This is a new create-only ordinary-user read/extraction attempt. The actual inspector receipt is included verbatim. No prior attempts or frozen producer sources are edited. The legacy lmkd.rc override remains forbidden when pressure_relay is present; the extracted original bytes are only a proposed preimage until separately reviewed.

The exact image is root-owned 0444 and the exact native fsck.erofs is root-owned 0755 with no file capabilities, pinned to the actual inspector identities and SHA-256. Both remain held read-only and are hashed in full before and after the single child. Named paths must still name those held identities. The source image is never mounted or opened writable.

The only extractor selection is /system/etc/init/lmkd.rc. --path and --extract were confirmed by the actual tool help. No whole-image fallback, extra device, overwrite, force, checksum bypass or xattr restoration is allowed. The held output directory is newly created at /home/alex/pocket4-owner07-original-lmkd-rc-read-02 with mode 0700. Existing roots fail; they are never reused or removed. The command inherits exactly the held executable, image, and output-directory descriptors beyond its redirected standard streams.

The request runs python3 -I -B as the ordinary host user, CPU 1 / 512 MiB / nice 10 / 90 seconds. The extractor has a 10-second wait bound, 64 KiB file-size limit, no core output and a cleared environment; timeout cleanup kills and reaps only that Popen child. The controller's full-image hashing deadline is 75 seconds. These are request limits, not a claim of measured resource qualification; no cgroup settings are written by the controller.

claim.json, tool.stdout, tool.stderr, original-lmkd.rc, and result.json are the only success members. The final record includes exact UTF-8 RC bytes, hashes, input pre/post verification, child return code/reap, first error, and secondary cleanup/verification errors. No automatic retries or deletion follow failures. Parent must reconcile the same idempotency key after a transport timeout. The complete result is also stdout, so root-private transport assumptions are unnecessary.

Actual extraction is NOT_SUBMITTED at this freeze. Local validation covers AST/request/encoding and exclusive owned temporary-file behavior only. It does not execute fsck.erofs, read the remote image, or qualify Rust Owner, init constructor, pressure monitoring, Android or any App. The request success field reports extraction integrity only; qualification and semantic_rc_admission remain false.

Primary upstream reference consulted for option/output semantics: https://kernel.googlesource.com/pub/scm/linux/kernel/git/xiang/erofs-utils/+/1ca8aff02c99d111b59bdc8f458b500d08374d16/fsck/main.c . This is not a source-provenance claim for the installed ELF; the actual held ELF hash/help are authoritative for this request.

## Revision 02 and preserved first failure

Parent executed revision 01 exactly once as job 1a1a9668676-fc05-34f0. It failed closed before mkdir or any image/tool opening: /home/alex/work is mode 0775 and the existing no-group/world-write parent gate rejected it. No extraction root or child was created. The original source and request remain frozen. The durable original failure stdout is held by the parent; this note does not replace its authoritative receipt.

A separate parent-owned read observed /home/alex mode 0750, uid/gid 1000, dev 66306 inode 31326210, below root-owned 0755 / and /home. This revision selects a fresh direct child under that safe parent. Only the output-root literal and attempt-kind literal change in source; the request gets its new stable key. No preexisting permissions change, no writable-parent exception, and no image/tool/FD/hash/cleanup gate changes. Source/request binding was rechecked locally; the earlier owned-tempfile check is historical validation of the unchanged functions, not a new remote result.
