# Independent review: official AAPT2 Calendar/Fcitx comparison

This review is local and read-only. It did not execute a test, tool, Main
operation or remote job, and did not modify the candidate. No blocking static
issue was found in the reviewed change.

Reviewed pins:

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `diagnose_calendar_and_fcitx.py` | 62,331 | `191692dda06eaaaa3fcbe024399985cf2ac6a547b567fd25967c96a1b31b09f6` |
| `owned_readonly_lifetime.py` | 16,925 | `a922596684aee084ae0aa07d0acaf1a4fa3b7088caf0e18b46b3fde5ca81a7ba` |
| `official_binding.py` | 11,338 | `fa9d5d05d0dcbd6495d470de936f373e659cf4015efb0a479616003e02f1c2be` |
| Worker diff against actual Debian r3 | 31,728 | `867403224551e324ebfbd4f39c18bbfd36abe223acdb943049bb6e6edb65358c` |
| Owned wrapper diff against actual Debian r3 | 3,455 | `f1a41b499a3face7029f06056975e56c06c37c04efb2a9c4f7cf338475b556b3` |

The full new official-binding module, changed worker paths, fixed eight-command
definitions, final receipt/FD path and wrapper gate were read. Independent AST
source extraction confirmed that `bind_tools`, `bind_static_dependencies`,
`recheck_static_aliases`, `recheck_tools`, `run_tool`, `parse_signature`,
`badging_manifest`, `xml_permissions`, `Store`, `read_bootstrap`,
`verify_actual_proof` and `all_apk_evidence_verified` are byte-identical to the
actual Debian r3 implementation. Apart from fixed CONFIG data, the owned-lifetime
wrapper changes only `worker_gate`, adding stricter official-comparison gates.

## Provenance and read-only layout

The new tool's source, candidate full stat/hash, actual two-line stdout and
authoritative terminal are separately pinned. `verify_official_host_proof`
requires the exact actual 34,091-byte artifact, its source-stage record,
successful normal version-child retirement, seven ELF records and the three
complete prior layout observations. It does not reclassify the older failed
Debian help result or claim dynamic-loader mappings from static evidence.

The existing official layout is rebound read-only. The actual seven child
directory paths and every full stat must match the prior host result. The
ancestor identities and root ownership/mode are rechecked. The output root has
a fresh explicit binding, not an invented claim that the prior host proof
recorded its full stat. The frozen `ControlledRunpathLayout` is used only for
`verify` and `close`; no creation or extraction method is called.

Its borrowed root descriptor belongs to the existing core pool; its eleven
owned anchor/child descriptors belong to the original layout class. Error
paths close the latter, while the caller's final pool retirement closes the
borrowed descriptor. No broad descriptor scan-close or allow-one-FD rule is
introduced.

The original nineteen-file Debian dependency graph remains bound. The exact
official seven-file graph is added under separate keys. The old `aapt2` binding
is retained as `legacy-aapt2`; it is not overwritten or dropped. All original
JDK/aapt/apksigner bindings, aliases and their rechecks remain intact.

## Fixed observations and result meaning

For each exact currently held Calendar and Fcitx APK, the only four commands
remain:

1. The original Java/apksigner signature verification.
2. Official AAPT2 `dump badging` on the held APK FD.
3. The original aapt `dump xmltree` for `AndroidManifest.xml`.
4. The original aapt `dump badging` as the legacy diagnostic comparison.

There are eight commands total. The six primary commands must succeed. The two
legacy commands must still produce complete joined observations, and their real
return codes are retained. No original nonzero diagnostic is rewritten as a
successful original audit. There is no signature/API override or APK editing.

The official layout is checked during initial binding, before and after every
command, and at final closure: eighteen complete layout observations, each with
five directories times six real ENOENT checks. There is a fresh five-second
minimum budget check after the immediate pre-spawn layout verification. The
original bounded child runner, lock, typed runtime guard, APK/data identity,
full byte/stat/path rechecks and normal owned-parent exit gates remain unchanged.

Official badging stderr must actually be empty for both APKs. A parser that
returns exit 0 while emitting resource corruption warnings cannot qualify the
comparison. Such metadata and warnings remain evidence, but
`comparison_complete` must be false. Even a complete clean comparison explicitly
keeps `resource_table_integrity_fully_proved=false` and production readiness
false. It establishes only these specific badging/manifest/signature observations.

The intermediate worker result file precedes final pool closure and cannot
serve as a standalone PASS. The final original stdout, outer strict worker gate,
held-pidfd normal child exit, whole-process FD identity restoration and durable
controller exit 0 are all required. This review establishes source compatibility;
it does not claim that the new Calendar comparison has actually run or passed.
