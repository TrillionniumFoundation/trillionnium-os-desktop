# normal06 SystemUI defaults — independent source review

## Decision and scope

No static blocking issue was found in the narrow two-default restoration in
candidate `9357aa8c0e0ab511278dcb24df57e5cb29f1570811019c501703fa387229c9e3`.
It restores complete, genuine declarations omitted by builder469's existing
projection. It is not evidence that normal06's complete Soong graph, compiled
framework artifacts, or any runtime behavior is ready.

The remaining ordinary dependency edges stay unresolved. No missing provider
may be replaced by an empty stub, no dependency check may be disabled, and no
consumer may be deleted to turn a missing-provider failure into success.

This review was local and read-only except for this independent report and its
evidence file. No SSH/Main operation, build, Rust test, Soong execution, source
deployment, or Git write was performed. The candidate owner's files were not
modified.

## Sources actually reviewed

All project-relative paths below are under
`/workspace/scratch/265e5bca485a/pocket4_eight_apps/`.

| Source | Bytes | SHA-256 / identity |
|---|---:|---|
| `framework_provider_repair/normal06/reference/builder469-AGENTS.md` | 4088 | `eac22deaa59d6906afe7eef3dfc9696fbacf20e71a90590608d744b096a8ff46` |
| `framework_provider_repair/normal06/reference/builder469-android.rs` | 287737 | `429b80b8fd9cd54c595e03f5551c906a398171732788636766db4eb1be42955f` |
| `framework_provider_repair/normal06/candidate/tools/droidloom-update/src/android.rs` | 289809 | `9357aa8c0e0ab511278dcb24df57e5cb29f1570811019c501703fa387229c9e3` |
| `framework_provider_repair/normal06/reference/SystemUI.Android.bp` | 49535 | `fa1aaf330d580d6cefb74dc0ef1b52fcebbdd9b6bced5497a3bd29f9fb3647a3` |
| `framework_provider_repair/normal05/source-r2/actual-provider-source-lock.json` | 96957 | `72848909e4931d712a3d59f344904ae8642b32c35a01cf520a51afce4c56b50d` |

The complete supplied builder AGENTS was read. Its Rust tooling, focused tests,
two-free-CPU policy, no implicit device action, and no build-output publication
instructions remain applicable. No AGENTS file exists in the local shared
workspace's ancestor paths checked for this review. The provided actual builder
AGENTS is therefore the relevant retrieved repository instruction source.

All 68 supplied SystemUI Blueprint files were independently checked against
their inventory's Git blob SHA-1 and byte count at upstream commit
`94b4c163b7dfe5ce3607f7bb8456f9573f7de57d`. The review did not infer current host
worktree contents from these upstream blobs.

## What the patch changes

The `android.rs` comparison has exactly three change hunks:

1. Add the two actual `java_defaults` names to the existing typed SystemUI
   projection selection.
2. Update that projected fixture's golden SHA from `f5e81cc5…` to `025d58f7…`.
3. Add the real-consumer/default-body regression test.

The three new consumer fixtures are byte-for-byte equal to complete same-commit
upstream files: `tests/Android.bp`, `pods/build/Android.bp`, and
`pods/util/policy/Android.bp`. They are fixture copies, not edits to upstream
consumers. The production source pin on the full SystemUI root remains intact.

An independent balanced-brace scanner reconstructed both projected byte
streams. It obtained the existing 1558-byte projection with SHA
`f5e81cc5342f8c2d50799c437df0e258e697b560e16052bbfa5cec9385523ce1`
and the candidate's 2017-byte projection with SHA
`025d58f766940a96ab6557b523456162201f393c9277abde86ad5030b52448cc`.
This is static byte verification, not execution of the Rust builder or Soong.

### Restored declarations are substantive

`systemui-non-platform-apis-defaults` retains its original
`static_libs: ["android.os.flags-aconfig-java"]`. The actual consumer is
`SystemUITests_defaults` in the supplied `tests/Android.bp`. The flags provider
is present in the same pinned `AconfigFlags.bp`, where it keeps the original
`android.os.flags-aconfig` declaration and
`framework-minus-apex-aconfig-java-defaults` dependency.

`SystemUI_compile_dagger` retains `dagger2-compiler`, all three upstream Dagger
annotation-processor flags, and public `defaults_visibility`. Its observed
consumers are `sysui_main`, `sysui_dagger`, and
`com.android.systemui.util.policy-impl`. No dependency, processor flag, or
visibility property was removed or synthesized.

The added regression test pins the complete real consumer fixture bytes and
requires the complete corresponding upstream default body to occur once in
the projection. It also checks the retained flags/compiler dependency. This is
a useful omission regression; it does not prove that Soong has resolved those
dependencies or built a consumer. The test has not been run in this review.

## Strict target strategy remains unchanged

The actual `builder469-native_role_ingress.rs` fixes `TARGETS` to
`framework-minus-apex` and `libandroid_runtime`.
`build_native_role_ingress()` calls the optional-role path with `Strict` and
`typed_ingress=true`. That path rejects a different target set, a non-Strict
mode, or an ART-flavor combination before materializing/projecting source.

For this route, `configure_soong_dependencies()` explicitly sets
`ALLOW_MISSING_DEPENDENCIES=false`; `target_closure_soong_patches(Strict)` is
empty. The native leaf/NativeBridge switches that enable missing-dependency
tracking and scoped discovery do not match these two targets. The
native-bridge-only Aconfig trimming branch also does not match them.

The unchanged fixed source lock selects the complete `frameworks/base/packages`
subtree, in addition to the earlier explicit SystemUI root Blueprint. The
builder's unconditional `SOONG_EXCLUDED_TEST_FIXTURES` contains aapt2 integration
tests, framework core/media/service test subtrees, the named Trusty test
subtrees, and Binder SDK tests. It contains no SystemUI path. The candidate
neither adds a SystemUI exclusion nor changes the 225-project lock or its
commits. Its retained-module checks also remain unchanged.

The initial review had no actual normal05 module-path list. The subsequent
actual-graph read described below confirms all 68 SystemUI Blueprint paths were
in discovery, including every one of the 14 static reference consumers. This
does not identify each ordinary dependency’s active variants or prove target
reachability. The pinned Soong ordinary-missing-dependency implementation has
not been examined here. No edge is therefore exempted by the two-target list.

## Remaining closure work

The static audit has **14 total omitted references**, not 14 ordinary ones:
four `defaults` references to the two restored names, plus ten ordinary
`libs`/`static_libs` references to four other omitted root providers.

| Still-omitted provider | Ordinary references | Observed consumers |
|---|---:|---|
| `SystemUI-tests` | 1 | `SystemUITests_defaults` |
| `SystemUI-application` | 1 | `SystemUI_test_fixtures` |
| `kosmos` | 2 | `SystemUI_test_fixtures`, `sysui_testlib` |
| `SystemUI-res` | 6 | Common Compose API, headline preview, notification-rules UI, QS API, statusbar chips API/testlib |

The current candidate intentionally leaves those ten references intact and
marks their graph qualification pending. Static occurrence of the two restored
names does not resolve this table. Equally, the two-target CLI must not be used
as a reason to declare these dependencies unnecessary.

The next evidence should come from the unchanged strict route: retain the
actual loaded module-path/effective-projection evidence and its precise
dependency diagnostics, and verify the affected consumers and providers in
that graph. If an active edge resolves to an omitted provider, restore the
genuine same-commit provider and its required transitive closure under an
explicit reviewed revision. Do not add empty definitions, suppress the error,
remove the consumer, or switch to a permissive build mode.

The source patch is suitable for the next separately reviewed host compile and
focused regression gate. Completion still requires the actual strict Soong
result and full artifact evidence. This review supplies no runtime activation,
UI/install authority, production readiness, or cleanup eligibility.

## Actual normal05 discovery addendum

The three actual normal05 files were subsequently retrieved by the source
owner through a separate read-only window, with fixed file versions and
per-chunk/full hashes. This reviewer read the local exact originals and checked:

- `Android.bp.list` has 6,472 entries; all 68 SystemUI Blueprint files occur.
- All 14 reference consumers’ Blueprint paths occur in that list.
- The actual ingress records Strict mode, the original two targets, the original
  root projection `f5e81cc5…`, and `transitive_build_closure_qualified=false`.
- The actual source manifest retains 225 projects, eight links and lock
  `72848909e4931d712a3d59f344904ae8642b32c35a01cf520a51afce4c56b50d`.
- Runtime authorization remains false.

This closes the discovery-list uncertainty; it does not close the ten ordinary
variant/dependency edges. `actual-graph-evidence.json` records exact source pins
and the consumer-by-consumer list check. No Rust or Soong execution was added.

## Evidence preservation note

The original 8,610-byte report was read back with SHA256
`e8088b7ba32651048e94bed1e9a3b00d9445d4f286f9bd65ba3229e2daf3afe0`
and used for this revision. Its original 5,337-byte temporary independent
projection-evidence JSON was observed earlier but later disappeared from the
transient directory. This revision does not recreate it under that old hash.
The source, fixture, projection and diff checks above are the actual completed
first review; the new actual-graph evidence is independently recorded here.
The candidate owner’s source and tests remain unchanged.
