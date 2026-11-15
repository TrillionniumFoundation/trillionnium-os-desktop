# Maintaining the source-only carrier

## Boundaries that must remain explicit

The published files derive from a frozen subset of the repaired base candidate, identified by its complete candidate-manifest SHA-256:

`0f176f3dff8c62f6d4dff893dcca047461de7804ff4d72165a0c73bfe5bfbe7c`

Of the 23 entries in `SOURCE-MANIFEST.json`, 22 match that base candidate byte-for-byte. `elf_closure.py` adds strict rejection of four unsupported loader directives; the manifest records the new bytes and retains the base provenance. The omitted historical storage/overlay entry points are not replaced with permissive substitutes. The retained `production_user_observation_legacy_j6.py` is a necessary import dependency for shared strict environment/variable validators used by both current jobs-2 observers; its presence does not select or authorize an old jobs-6 build. The published controller and importer retain `require_new_execution_binding()`, which always rejects execution before historical paths or source import work are used.

A future runnable generation needs actual completed source recovery, a new finite storage owner when required, newly sealed control/output/temporary paths, exact boot/unit/namespace identity, fresh resource and deadline admission, and a coherent frozen-tools record including current source/Git directory maps and retained engine/companion inputs. Review the complete resulting orchestration source as a new generation. Do not remove the gate to make CI or a production command pass, and do not reuse an expired or earlier admission.

Keep the original shared serial/work locks, PIDFD and executable witnesses, owned-child retirement, source restoration, strict user/cp2a build, dependency enforcement, neverallow checks, memory/disk/CPU limits and original finite stop/cleanup deadlines. Public unit tests do not grant permission to alter those controls.

## Producer and receipt changes

The verifier constants come from exact accepted producer source. A change to a producer commit, tree, tracked-file count, ELF hash, patch, input schema, provider, requested target or output identity requires review against the new actual producer source and its real qualification records. Update source pins and the specification together only after that review. Regenerating a manifest alone is not qualification.

`build_receipts.py` checks the actual live-observed input receipt F9/SHA again at completion, requires normal result input SHA binding and verifies restored source and concrete output files. Keep those checks independent of fixture construction. Do not add a synthetic success path for CI.

`elf_closure.py` verifies static file dependencies. Its `loader_resolution_qualified` and `tool_execution_qualified` flags remain false. Real host interpreter/library bindings, bounded preservation/delivery of runtime files, loader execution qualification and selected CP3A system-policy integration still require actual evidence. Unsupported inherited RPATH and the `DT_FILTER`, `DT_AUXILIARY`, `DT_AUDIT` and `DT_DEPAUDIT` load directives fail pending a reviewed resolver; they must not be silently accepted. Preserve all four actual-linker regressions when extending support.

Keep each path's first-read metadata bound to its exact F9/SHA reference through edge selection, queue processing and final revalidation. A new inode or different bytes cannot replace the tuple used for a SONAME decision. PT_DYNAMIC and its string table must each fit a unique complete file-backed PT_LOAD mapping, and the dynamic segment's declared offset must match that mapping. Preserve the actual-replacement and independent byte-layout regressions when changing this parser.

CP2A compilation does not authorize CP3A framework replacement, a build-ID/SPL relabel, production signing, device tests, whole-bulletin security acceptance or app/runtime readiness.

## Tests and CI

Use:

```sh
python3 -I -B compat/android/pocket4/current-full-build-carrier/tests/run_core.py
```

The public suite currently has 48 self-contained cases. The base private regression suite had 57 cases and has not been rerun for this revision. Keep these counts and scopes separate in PR descriptions. An actual compiler is required for the ELF cases, and the runner fails instead of skipping them when prerequisites are missing. Fixtures are temporary and are never production outputs.

The public source manifest is intentionally exact. For a later reviewed source revision, update the manifest with that revision and the recorded rationale. Review any test-count change explicitly. Do not import private RESULT/retirement records, source F9 maps, owner leases, raw machine logs, previous controller snapshots or compiled fixture binaries into this directory.

## Publication shape

Publish only this directory's two maintenance documents, `SOURCE-MANIFEST.json`, the 23 `src/` files and the two `tests/` files: 28 files total. The full private review archive, base snapshot, field evidence, private test reports and local publication-validation checkout are outside this directory and are not source deliverables.
