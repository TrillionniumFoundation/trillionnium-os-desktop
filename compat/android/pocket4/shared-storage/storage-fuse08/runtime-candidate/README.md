# Offline fix against the exact installed services DEX

The candidate was built from the actual Main services JAR, preserving its
existing Wi-Fi/SystemServer changes. The only intended change is
StorageSessionController.onVolumeUnmount(ImmutableVolumeInfo): fetch the mapped
user connection under the controller lock, release that lock, and perform the
single removeSessionAndWait call. Binder identity and exception cleanup remain.

Actual build14 completed on 2026-11-05 at 09:07:37 UTC. The original and fresh
roundtrip disassemblies contain 7,582 classes and 53,839 methods. The semantic
comparison preserves class metadata, fields, method sets, branch targets and
per-instruction exception coverage; exactly the reviewed target method differs.
Debug/comments, implicit false annotation values and const-string jumbo width
are the narrow normalization rules. Nops and actual string content are retained.
This is bytecode comparison, not Android verifier or lifecycle qualification.

Only classes3.dex changes among the 65 ZIP payloads. Both other DEX members,
including the existing Wi-Fi/SystemServer fix, remain byte-identical. Candidate
DEX SHA-256: 8f74a77571feed8bc011bbaaa369f1cc8d75b793d6c3993d6f3b1cca49f912e3.

Alignment15 completed at 09:12:29 UTC, using the observed hash-pinned libzopfli
dependency in an isolated output directory. Original and candidate alignment
checks passed, and all 14 tool dependencies matched before/after. The final JAR
is 34,667,535 bytes, SHA-256
f1acb56e23cd9082a77ef686f2e840a736e7769dd8843830e53e56b1ac31566f.
The original JAR remains f33987e633e476f47ea043af3f7fb94907fd2431fa2b5b49df84cb586bce5c50.

Preparation13 had two retained failures: a request exceeded the transport's
64-KiB source limit before admission; then a shortened stage had an owned-parent
permission error before the Python builder entered. Neither produced a DEX.
Build14 used the same frozen builder after correcting traversal. Its first
alignment step reported a missing libzopfli; alignment15 resolved only that
dependency and did not repeat assembly. Original failed receipts remain private.

Read-only discovery16 bound the actual installed ART tools, 52 boot classpath
files, 28 system-server classpath files and 75 mapped ART artifacts. The tool
--help exits are usage results, not verifier failures. This snapshot has no ART
verifier or Android lifecycle result and is not deployed to Main. The separate
reference Java regression remains method-level evidence, not a complete AOSP build.

Selected original receipt hashes, exact source pins and actual job IDs appear
in public-metadata. This bundle excludes JAR/DEX binaries, complete environments,
process maps, captures, source-directory inventories and embedded stage payloads.
The fixed device/build source is an audit record; completed run paths are
create-only and must not be replayed.

## Later actual target verification

[ART22](public-metadata/ART_VERIFICATION22.md) has now verified the exact
StorageSessionController class with the installed ART tools and original-input
baseline. Candidate compiler and target dump both exited 0, and the exact class
status was Verified. ART20's observer failure remains failed; ART21 reconciled
its already-existing original output without recompiling it. The original and
candidate retain the same inferred boot-extension Wi-Fi checksum warning.
Neither the whole boot image nor live storage lifecycle is qualified, and the
candidate is still undeployed. The earlier discovery paragraph records its
historical checkpoint, not the current ART target status.

Run `python test_art_target22.py` for the eight packaged parser/command-boundary
controls. The actual target window and compiler argv are selected technical
fixtures; complete raw process maps, environments and cache names are omitted.
The executed fixed-device runners and exact source hashes are retained.
