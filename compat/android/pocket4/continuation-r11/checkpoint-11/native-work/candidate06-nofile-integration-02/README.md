# Candidate06: exact NOFILE production-source integration

This revision derives a new immutable source candidate from candidate05. It does not modify candidate05, enable metadata generation, rebuild or deploy Main, start a factory, or run Android again.

The complete parent manifest is 367,777 bytes with SHA-256 `4e2f7f9ea09c6977afbe8d97c040fd2f1344772429f78fe0f16edc913dadc7ba`. The expected candidate06 manifest is 368,827 bytes with SHA-256 `3c780a398075f77d1f6b1c477c6ceaa35349de17b88e77896aa22820259c0376`. Both contain 948 files, including 925 engine files. Exactly three engine files change; the other 945 total files and 922 engine files remain byte-identical. Every unchanged ancestry entry is retained, and the three changed entries append one explicit source transition. The six signal-mask fixes remain intact.

| Engine file | Candidate05 | Candidate06 | Change |
| --- | --- | --- | --- |
| `kernel_api/proc_maps_raw_metadata_owner.cc` | `489264a8…` | `4400b1db…` | Exact descriptor-allocation EMFILE fallback and its private inherited FD table/stack lifecycle |
| `kernel_api/include/berberis/kernel_api/proc_maps_raw_metadata_owner.h` | `7e8ae5c6…` | `b3c0fed3…` | Comment describes both preallocated stacks; declarations unchanged |
| `kernel_api/include/berberis/kernel_api/proc_maps_provenance.h` | `79e871b7…` | `e21bc5db…` | Comment describes the exact inherited-table fallback; declarations unchanged |

The original attempt to bind only two files was rejected locally because the provenance header comment differed from the actual tested source. That failed assertion and the original two-file draft remain preserved. This revision includes the exact tested comment as the third change and proves that all 11 production source inputs used by the owned controls match candidate06 byte-for-byte.

## Actual evidence consumed

The owned host comparison passed with preimage 15 functional cases plus 11 exact EMFILE negatives and candidate 26 expected cases. Its raw receipt is pinned to `b0a03b1b95e3292131105dcb22fd59f4a767e63017197e29f4482036976a4ac2`.

The matching Android build receipt is `f3617407f8c624357f4bf9a9cc53e1e78a217b3c0b8bc9a51448c09569e2ea06`. Both actual APKs and final worker closures passed the matching ELF audit. The actual Android runtime coordinator receipt is 397,053 bytes with SHA-256 `fbc3ca4d6e861b50da8ee537c90908b5308249015a31220acdd2d09b00f42b13`. Its original assertions were reapplied locally to the full captured instrumentation results, with no Android execution or replacement harness: UID 10167 preimage reproduced 15 functional / 11 exact EMFILE cases; UID 10168 candidate met all 26 expected cases. Each arm retired 26 direct and 5 nested children and completed exact owned-package removal. Main and owned resource event deltas were zero in the actual cycle.

These results cover admitted ordinary-descriptor behavior in the owned Android application context. Initial NOFILE=0 authority establishment, first private-fork startup after NOFILE=0, and trusted virtual O_PATH reopening remain the declared red boundaries. Host-native lifecycle and ART generation qualification are not inferred from these probes. The default metadata-generation flag stays zero.

## Source-only composition

`compose.py` reuses the complete unchanged `source_contract` from the previously qualified Go6 streaming preparation source (`edf9f49f…`). It checks the original candidate05/925 source, six signal files, actual compiled builder450, R16 genealogy, and original matched gates before copying and again afterward. It also consumes the exact host/Android receipts, reapplies the unchanged Android assessment functions, and binds all 11 actual production source inputs.

It creates only `/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/overlay-reconstruction-10`, writes a new `candidate-06` file set, and records the new manifest and composition receipt. Existing roots are rejected. Copying reads unchanged inputs through bounded held regular descriptors and verifies their bytes and identity. The new source tree is checked for its exact complete inventory. No live AOSP source or projection journal is edited.

The request stages 10 exact UTF-8 inputs in a new owned source root and runs this composition under UID1000 with one CPU, 1 GiB, and a 300-second limit. Its stdin is below the controller's 1 MiB limit. It contains no compiler, Android, namespace, service, installation, or Main action. The fresh candidate06 Go5 streaming build profile must bind the actual composition receipt before source preparation and the later full cold build. Original candidate05 matched gates are retained as parent evidence and are not relabeled as a complete candidate06 execution.

`scope-draft.json` is the historical pre-receipt draft. `actual-Android-evidence-reassessment.json`, `LOCAL_BINDING_VALIDATION.json`, and the final request describe the completed local evidence binding. No source-composition execution has occurred at this freeze.
