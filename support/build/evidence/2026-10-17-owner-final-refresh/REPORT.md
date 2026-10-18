# Final owner readback — bounded historical snapshot

This phase preserves the complete original **39-file /357,755-byte** scratch final-owner-readback. The original SHA256SUMS remains byte-identical, SHA256 `3416ac3789de0a29bed99483d89dc91dff4d4c7d45447e2878eedfddf04d3e8f`. All38 files in that inner checksum closure and the original checksum file are retained in raw-readback.tar.gz. No original raw field, document, report, timestamp or checksum was updated.

The remote observation window is **2026-10-17 01:52:52.607–01:53:47.412 UTC**. Requests.json inside the archive is explicitly a posthoc literal transcription of the18 actual read-only tool names/arguments, using the original captured per-request start/end fields. The connector returned normalized structured data; this is not raw HTTP transport capture. Captured old docs, upstream-lock and frozen phase reports remain historical source bytes. Source-bindings.json does not invent a Git commit for them or claim the final repository still equals them.

At that window A01 PR22 head was d879a9d2 and its host-evidence run38992415807/job117277478013 was queued with null conclusion. A05 PR87/25cbffe6, A06 PR18/57b23ede and A04 PR8/da4107f8 remained open Draft. Issue63 was open with0 comments. Both limited A07 title/head queries returned zero; this is not proof that an external owner or every possible branch is absent. Associated A05 host-contracts success and A06 G0 failure remain host CI metadata. Empty status/run arrays are never interpreted as acceptance.

**Temporal boundary:** the original reports correctly said the final cross-path pair and snapshot full22 lacked completed frozen evidence at that time. Root later reported an actual pair exit0 at01:56 and the final22/22 matrix, with their separate later evidence. This package neither reexecutes nor validates those newer runs. Its old pending statements must not be used as the current final aggregate. Root's consolidated report uses the later pair/matrix receipts. AF_UNIX/KVM/cross-host/immutable-environment and A05/A06/A04/A07 owner boundaries likewise retain their precise source/time scopes, not a blanket claim that all blockers closed.

The archive uses sorted regular USTAR members, mode0644, uid/gid0, empty owner names and mtime0; gzip uses mtime0 and an empty filename. This normalizes container metadata without changing any member payload. It is below2MiB. Members.json binds every original path/size/SHA256; archive.json binds the compressed storage and unchanged original checksum manifest. No executable tool or native payload is installed or run by this wrapper.

Offline verification from the repository root:

```sh
python3 -I support/build/evidence/2026-10-17-owner-final-refresh/verify.py
python3 -I -O support/build/evidence/2026-10-17-owner-final-refresh/verify.py
```

The verifier uses explicit checks, not Python assert. It verifies the full outer checksum inventory, compressed archive/member identities, the exact39-file/38-entry original closure, all18 requests and original timings,15 local document/frozen-report bindings and the bounded PR/issue/A07/CI observations. It performs no extraction, network request, compiler, tool installation, owner test or VM. Later root outcomes are contextual statements outside its acceptance scope.
