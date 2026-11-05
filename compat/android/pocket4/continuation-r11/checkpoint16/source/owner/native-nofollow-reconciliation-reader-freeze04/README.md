# Fixed NOFOLLOW ACK reconciliation, revision 04

This is a single-target copy of the actual-used revision03 metadata reader. It reads only the fixed worker jobs parent as UID1000, matches the complete stored execution tuple, and then validates exact stdin length and SHA256. It cannot verify the original idempotency key from metadata and cannot derive a runtime outcome. A zero match is only NOT_FOUND_AT_OBSERVATION.

The original NOFOLLOW request is pinned to 157007 bytes / 407b5a345263ecdf8a8b6e7582edf4484fa898053cfe930abc23c3498ca3cd8e. Its stdin is 138246 bytes / 80ae75307eb4043f28857a67d5b5989933260c610a588c63c18298d9b4a5e799. Owner14 is excluded because its original job ID is already known.

All original read/FD/identity/matching/cleanup functions remain byte-identical except the inert result scope label in main (TWO to ONE). The TARGETS literal and top docstring are the other source changes. The 131072-byte limit is for request.json metadata; stdin uses the fixed exact target sizes, so 138246 bytes fits the existing code without a limit change. All stdin bytes still count against the original 32MiB total. The 4096-entry, 10-second checked scan, eight matches and 64KiB output limits remain unchanged; the outer reader keeps CPU1 /128MiB /30s.

Eighteen actual local controls passed, including a 138246-byte owned file, zero-body wrong-size rejection, wrong-hash rejection, aggregate budget, unchanged metadata cap, and an owned three-entry scan that reads only the exact target stdin. Tests redirect only the imported module to an owned temporary tree and local test UID; the frozen production source remains UID1000 and the fixed worker path. No reader main, Hepta, runtime, namespace or original job was executed by the author.
