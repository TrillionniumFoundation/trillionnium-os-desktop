# Candidate07 complete engine build profile

This profile keeps the qualified builder450 ELF, its compiled source manifest, the separate Go5 runtime data manifest, normal projection journal and lock recovery, and all complete engine targets. Candidate07 adds the narrowly scoped host UAPI include fix to candidate06. The actual five-TU receipt and the actual new source-composition receipt are checked before source preparation and again by the build contract.

The candidate inventory is 949 files, including 926 engine files. The six signal fixes and the preceding NOFILE source changes remain present. The earlier NOFILE runtime proof is retained for its exact earlier artifacts; it is not relabeled as a runtime result for the new header delta.

The new root is `full-build-combined07-go5-streaming-01`. Its working source, Android output, attempt, and fence directories must be fresh. Candidate06, both of its fences, its failed compiler output, and all earlier profiles remain untouched. No failed output is reused to qualify the new candidate.

## Unchanged resource and acceptance requirements

- 10 GiB owned memory maximum and 1 GiB owned swap maximum.
- A fresh reading of at least 13 GiB MemAvailable and 2 GiB SwapFree before compilation.
- Two allowed CPUs, jobs=1, and the existing complete builder timeout.
- The same exact read-only Main snapshot source and pre/post identity, limit, and OOM checks.
- The same owned cleanup and artifact/source closure checks. Nonzero resource counters are recorded; they are not described as zero or as proof of no interference.
- The same full native engine and test targets, warning flags, normal builder recovery, and default-disabled feature marker.

The actual candidate06 build reached host compilation without an OOM kill and then failed on the old sysroot header. That supports fixing the compiler input rather than deleting a target. It does not guarantee that this new complete build will succeed or fit in the budget.

`bind_composition.py` accepts only the complete actual candidate07 source-composition report and its explicit SHA. It creates a new local bound profile by replacing one composition hash and deriving the dependent controller/fence pins. `make_requests.py` then produces the exact preparation request. A full build request remains unavailable until the new actual preparation and copied runtime builder manifest have been read and verified. Neither program submits requests.

The final complete host suite, Android signal cases, enabled ART/engine pairing, and app acceptance remain separate gates. This profile builds the default-disabled engine; it neither builds paired ART nor enables or deploys the metadata owner.
