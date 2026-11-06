# Successor QA candidate over the existing R5/R9 path

## Status

This directory is a locally prepared source candidate. It has not generated a
real successor package, run the Pocket4 Java build, installed a helper, launched
an App, entered an Android namespace, clicked a control, granted a permission,
or restarted the cell. It does not contain a new runtime PASS. The old Bili
launch remains unknown; task 873 is never adopted, removed or reconciled by
this code.

The parent has separately completed an actual **read-only recovery preflight**:
job `1a1b0802b05-fc05-70f1`, durable exit 0, 46 targets (45 launchers plus the
existing actions package), 823 observation FDs and 48 lease FDs closed, no
errors or Android mutations. This is predecessor preflight evidence. The
successor qualification and new QA evidence still have to be produced.

The actual m579 CLI source is now retained in
`../recovery/reference/actual-m579-droidloomctl.rs`: 20,413 bytes, SHA256
`19a9e75d0deb0836fb9d125850600004a4a15be1b1ce8519fb8ca40e2165708d`.
The live CLI actually parsed `--cell --json --help` during that preflight.
The source also has install-multiple functionality absent from live ordinary
help, so source/ELF equivalence is **not** assumed. This candidate uses existing
single-package native launch, original held Android commands, and public
UiAutomation operations already present in the observed path.

## Files and evidence boundaries

| Entry | Purpose |
|---|---|
| `generate_successor_sources.py` | Requires a real successor guard and App observation, then writes new per-package R5 and R9 source closures |
| `stage_helper_source.py` | Copies the exact helper source closure into a new root-owned, group-1000-readable immutable source directory for the unprivileged build |
| `templates/source_contract.py.in` | Independent runtime and App scope validation, exact source closure, original namespace-helper qualification |
| `templates/flow_methods.py.in` | New typed R5 flow initialization and guards, retaining the original task claim, once-only operation and command journal implementation |
| `templates/main_binding_class.py.in` | Binds the actual new init and zygote identities, held root/namespaces, paired classpaths, exact target UID/data directories |
| `templates/install_owned_helper.py.in` | Fresh helper absence check, one non-replacing test-package install, exact installed bytes/UID and independent no-automation state check |
| `templates/run_case.py.in` | At most eight declared R9 sequences, with independent fresh inspection/restoration and an exact postcondition before each further decision |
| `test_successor_qa.py` | Local negative controls and compatibility of generated source with the observed 45 package names/UIDs; no Android calls |
| `GENERATOR_PINS.json` | External pin of all executable generator inputs and original source dependencies |
| `source-origins.json` | Original commit, file paths and byte digests |

The original R5 references remain byte-identical. The old held namespace-entry
binary is still separately verified against its actual R4 qualification. Its
qualification covers owned namespace entry, not whole-process-tree cleanup.
The new APK is a different helper with a fresh package name and fresh signing
key; it instruments itself. It does not instrument or alter a commercial App's
signature, security checks or manifest.

## Runtime identity and App versions

The source generator accepts only
`pocket4-successor-qa-build-input-v1`, produced by the existing recovery utility
`observe_successor_scope.py`. It imports the explicitly pinned successor guard,
calls `current_guard()`, checks the real typed baseline and qualification, and
rejects the old `734fab42...` framework epoch. It validates the selected App and
`local.pocket4.actions.v2` through `check_app_scope()` before and after generation.

Each generated helper embeds the framework epoch, full runtime digest, baseline
and qualification digests, App scope digest, actual target UID, target package,
an explicit public text value, and a closed operation list. Its helper package
is derived from the complete new binding and an explicit generation nonce. A
helper compiled for one App version cannot accept a request for another App
scope on the same runtime. A legal signed App upgrade therefore creates a new
versioned App observation and source binding without changing the runtime guard.

There is no inferred UID floor for target Apps: the observed Settings package
uses UID 1000. The helper itself must have a new ordinary App UID, distinct from
the target and excluded historical helper UIDs. CE/DE directory metadata is
checked only where actually present; the underlying App guard also preserves
the observation of an absent directory. Legitimate creation or replacement of
a bound directory requires a fresh App observation; it is not silently accepted.

The generator reads an externally pinned native launcher catalog as the source
of the exact requested component. It does not claim to refresh the resolver or
to prove that an older catalog is the complete current list. A fresh catalog
after updates/restart is preferred. Native launch must still return an actual
successful receipt and satisfy the original task scope checks.

## Reproducible sequence after a real successor exists

1. Wait until the separately authorized App installs and other workers settle.
   Take a new coordinated drain and pre-restart App scope. The earlier Beike
   3066010 APK scope is stale: Beike has actually reached 3067100/3.06.71 while
   retaining UID 10143 and its data directories. Other pending upgrades must
   also be reflected in the new actual scope. Do not use the old snapshot.
2. The root operator uses the separately reviewed native cell recovery and
   real successor qualifier. Require actual old pidfd deaths, the real native
   receipt, three double observations spanning 10–90 seconds, and successful
   publication/readback of the new guard. This directory does not restart.
3. Run `observe_successor_scope.py` against that new guard. Its selected package
   set must include the target and `local.pocket4.actions.v2`. Supply the actual
   parent App scope and any exact signed-install evidence. That reader does
   not invent an install receipt or qualify its policy; the install evidence
   must be reviewed separately.
4. Make a closed request below using actual byte pins, actual package/component,
   a fresh nonce, and the reviewed public text/operations. Run the generator as
   root with `--request`, `--request-sha256`, and
   `--generator-manifest-sha256`. It has no process-spawn or Android entry API.
5. Require `generation-result.json` to report `ok:true`. It names exact new
   recorder/helper manifests and `build-plan.json`. Run the plan's `stage_argv`
   and preserve its actual terminal receipt. Staging creates only new source
   directories/files; it changes no existing file permissions.
6. Execute the plan's `build_argv_after_exact_source_staging` **as UID 1000**.
   The original pinned JDK/SDK31/D8/aapt/zipalign/apksigner pipeline, one CPU,
   256 MiB Java heap, once-claim and 230-second build bound are retained. The
   helper declares no permissions, activities, services, receivers or providers;
   it is a test-only self-instrumentation APK. Require real
   `BUILT_STATIC_VERIFIED_ANDROID_UNRUN`, exact new source/tool/readback evidence,
   signature output, APK digest and signer digest. No build result from the old
   helper is accepted. Do not treat the local parser tests as a Java build.
7. Initialize a **new** R5 flow with the generated `recorder.py init`, actual
   successor baseline path/hash, exact source manifest hash, package/component,
   and a fresh `/home/alex/work/pocket4-successor-qa-flow-<32hex>` directory.
   Run its `admission` operation as a distinct once-only step. This uses the
   original qualified held namespace entry and one real package UID command.
   It also checks the actual new zygote's environment and complete paired
   classpaths; missing environment keys fail closed without invented defaults.
8. Use the generated `install_owned_helper.py --install-once` with exact
   `--source-manifest-sha256`, `--build-receipt`, `--build-receipt-sha256`,
   `--apk-sha256`, `--signer-certificate-sha256`, `--recorder-root`,
   `--flow-dir`, a fresh `--step`, and a fresh `--state-nonce`. It requires
   absence including retained records for every Android user, then executes
   exactly `cmd package install -R -t --user 0 --pkg <fresh helper> <owned APK>`
   through R5's held transport. `-R` forbids replacing a package. There is no
   option retry, `-g`, permission operation, target App install, UI connection,
   launch or automatic uninstall. Require exact installed-byte/UID checks and
   a successful no-UiAutomation `state` result. The transfer APK is retained.
9. Use the same generated recorder's `launch` step for one actual native App
   launch. A matching successful native receipt and a unique current task are
   mandatory. The original guard still refuses a pre-existing target task.
   If Android restores a target task during restart, observe it and establish
   a legitimate ownership path; this candidate cannot claim or remove it by ID.
10. Run the generated `qa_adapter.py` first with a `state` or `inspect` plan.
    It requires the actual installed helper UID, exact build/APK/signer pins,
    source manifest and fresh native launch scope. Then use `run_case.py` only
    with an exact reviewed case. Every mutating sequence performs fresh node
    selection and the original 10-second inspection freshness check; every
    next decision requires a separate read-only inspection, exact unique
    untruncated postcondition, accessibility state restoration and unchanged
    task/runtime/App binding. Whole-App success remains separate evidence.
11. Use the original recorder's cleanup only for its own successfully claimed
    new task with `cleanup_allowed:true`. Unknown native launches never gain a
    cleanup scope from this pipeline. Retain source, build, helper and App
    artifacts until the relevant production acceptance is real.

Generation request shape:

```json
{
  "schema": "pocket4-successor-qa-source-request-v1",
  "qa_build_input": {"path": "ACTUAL_ABSOLUTE_INPUT_PATH", "bytes": 0, "sha256": "ACTUAL_SHA256"},
  "launcher_catalog": {"path": "ACTUAL_ABSOLUTE_CATALOG_PATH", "bytes": 0, "sha256": "ACTUAL_SHA256"},
  "package": "ACTUAL_LAUNCHER_PACKAGE",
  "component": "ACTUAL_PACKAGE/ACTUAL_ACTIVITY",
  "generation_nonce": "ACTUAL_32_HEX_NONCE",
  "public_text": "审阅过的公开测试文本",
  "allowed_operations": ["state", "inspect"],
  "output_root": "/home/alex/work/pocket4-successor-qa-source-ACTUAL_32_HEX_NONCE"
}
```

The placeholders deliberately fail validation. Add `click` and `set_text` only
for the concrete reviewed test scope; the user has authorized App repair, so
this is source binding/review, not a new user permission request. Player-specific
operations remain Bili-only. Main Bili acceptance/consent controls are rejected;
the historical Accept authorization remains confined to the independent cell
`p4-bili-m30-cell-20261010`. No active location permission is granted to Meituan.
Chinese input uses the existing UiAutomation `ACTION_SET_TEXT` path with the
exact compiled public text, observed resource ID, editable non-password node
and value readback. There is no ADB dependency or substitute automation stack.

## Failure and recovery

| Failure | Preserved state and next legitimate action |
|---|---|
| Input, source, process, namespace, classpath, APK or directory mismatch before an action | Stop; preserve the rejected result; obtain new real evidence or repair the actual mismatch. Never edit a PID/epoch/expected hash to admit it. |
| Source generation or staging partial write | Preserve its exclusive new directory. Do not retry into it. A separately reviewed new nonce/directory can be used after diagnosing the failure. |
| Java build fails or times out | Original builder joins its own child/group and retains output and failed receipt. No Android action occurred. Review outputs; create a new build/source identity for a new attempt. |
| Helper absence check fails | Do not replace or reinstall. Read and pin the existing record and determine its owner; no automatic uninstall. |
| Install command fails, hangs or loses its receipt | Retain candidate/stage/build and any possibly installed helper. `action_attempted`/`outcome_unknown` prevent automatic replay. Observe exact package UID/paths/APK through the same still-valid binding before deciding. |
| Namespace-entry command or UI helper hangs | Retain original command journal and unknown result. The existing held runner owns its direct child only; do not infer whole Android worker death from a joined host process. The helper retains its existing 12-second self watchdog and restore logic, but actual termination and restoration still require evidence. |
| Helper acknowledges click/text but postcondition or restoration fails | Stop the case. Preserve original unknown action. No next declared action, no consent fallback and no cached inspection reuse. |
| Framework/native generation changes | Existing guards reject every old flow. Drain actual workers and qualify an explicit real successor through the separate recovery path. Do not borrow old task ownership, old PASS, or a fake launch scope. |
| Native launch returns ownership error or lacks a receipt | Preserve unknown state and current tasks; no task-ID cleanup or replay. This is the same boundary that protects original Bili task 873. |

`qa_adapter.py` and `run_case.py` keep business action outcomes unknown. A
completed UI sequence is evidence of its scoped observations, not a claim of
network correctness, login success, long-term stability, restart recovery or
production readiness. The 136 per-App cases in the separate test catalog still
need actual execution and evidence; this source candidate does not mark any
of them passed.

## Local verification scope

The controls exercise the generated production parser, source adaptation,
symlink/length rejection and fresh nonce/postcondition checks. They cover the
observed 45 package names, including a system UID, without using invented
runtime identities for generation or activation. They also run the original
32 wire/idle controls against the new parser and 16 scope controls against the
new runtime/App digest fields. There is no local JDK/Android SDK in this scratch
environment; actual Java compilation and Android tests remain pending on
Pocket4's pinned existing toolchain.

Original source provenance is CP20 commit
`df9465b6a899fbbd9f8e40294f14185f70880c4f` in
`TrillionniumFoundation/trillionnium-os-desktop`, particularly
`host-r5-source/android-current-host-r5-source-01/source` and
`app_bili_current_build01-source_tree/android-current-baseline-four-helpers-01/bili/source`.
The retained original standalone install and Bili navigation sources explain
the once-install/state and post-inspection continuation patterns. They are
reference evidence, not inherited qualification for this candidate.
