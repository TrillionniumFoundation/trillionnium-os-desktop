# Producer05 actual build input closure

The 31 input files in source/ match the exact byte sizes and SHA256 values recorded both before and after the successful producer05 host build. That original build receipt is 1623811c108a7cac8af3460d828c063ed9e7064519d2d4e41d70bce4ab25e64c (34,073 bytes), with 122 supervisor tests, 23 relay tests and seven ordinary IPC controls recorded as passing.

Ten exact inputs were already present locally. The remaining 21 were retrieved from only the fixed candidate paths in that receipt, using nine bounded read-only batches including the initial two-file permission/schema check. Each remote response digest was independently recomputed from its UTF-8 bytes, then every local member was rechecked against the original build receipt. This is independent per-file matching to a historical build receipt, not an atomic remote tree snapshot.

All 31 inputs total 726,924 bytes. source-manifest.json is the exact source inventory; verification.json records each file's local or remote origin and remote version where applicable. The 16 distinct previous local variants were preserved separately before remote retrieval. preserved-prior-variants.json lists their identities without republishing their old source bodies. No prior source or frozen evidence was overwritten.

These are the complete 31 explicitly recorded build inputs, not a claim that the whole Cargo workspace or every transitive build dependency is present here. No compilation or executable was run during this collection. The successful native ip/unshare prefix control still used a C stand-in; actual RustOwner/CellSpec runtime, Android init constructor, real init enrollment and production deployment remain unqualified.
