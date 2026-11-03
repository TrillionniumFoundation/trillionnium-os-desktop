# Actual Root ABI reference and native execution

The strict-profile run executes the same real static ELF on Linux as Root and
on the retained ordinary Asterinas kernel. Both complete 27 checks; QEMU
returns raw status 33. The original run is retained separately before the
oracle was tightened to reject every trusted-profile marker. All source,
checker, serial and binary hashes are in [publication.json](publication.json).

This proves these concrete kernel ABI operations. It does not execute an
original durable writer or qualify CPU control, recovery or G2.

Native serial logs use gzip to preserve exact CRLF and terminal bytes.
Their decompressed SHA256 is unchanged; no whitespace was edited.
