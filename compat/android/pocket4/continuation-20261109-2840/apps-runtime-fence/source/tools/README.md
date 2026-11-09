# Tools

## Main workflows

| Tool | Purpose |
| --- | --- |
| `droidloom-package` | Build binaries and pacman packages in rootless Podman; test package lifecycle in a disposable container. See the [package guide](../packaging/arch/README.md). |
| `droidloom-update` | Rust source builder and transactional developer installer. Supplies the package builder's Android build and assembly implementation. See its [guide](droidloom-update/README.md). |
| `droidloom-source` | Materialize pinned sparse AOSP sources; a library dependency of the updater. |
| `droidloom-image` | Prepare the pinned Android base; a library dependency of the updater. |
| `droidloom-gapps` | Import a local LiteGapps archive, derive optional raw ext4 images and build a pacman data package. See [optional Google apps](../docs/BUILDING.md#optional-google-apps). |
| `droidloom-mesa` | Prepare pinned Mesa sources and patches; a library dependency of the updater. |

The package builder is the distribution entry point. The source updater is an
alternative developer installation; it cannot overwrite a pacman installation.
Do not assemble a preview from unrelated component builds.

## Application release evidence

The existing `droidloom-applications` binary also has a read-only evidence
completeness check. It does not connect to Android, change the XDG catalog,
install applications, or execute a test:

```text
droidloom-applications --release-check /absolute/release-manifest.json \
  --release-results /absolute/release-results.json \
  --expect-release-sha256 MANIFEST_SHA256 \
  --expect-main-sha256 CURRENT_MAIN_QUALIFICATION_SHA256 \
  --expect-app-count 42
```

Supply the manifest digest, current Main qualification receipt digest, and
complete selected application count from independently reviewed release inputs.
Do not derive the expected selection from whichever results happened to finish.
A 42-application manifest with 13 results reports the 29 missing applications.

Both JSON inputs use schema `1` and deny unknown fields. The manifest has
`schema`, `main`, and `apps`. The result has those same top-level fields:

- `main`: `main_sha256`, `boot_id`, `framework_epoch_sha256`, and
  `cohort_sha256`. Every application result repeats this exact binding.
- Manifest app: `identity` and `required_gates`.
- Result app: `identity`, `main`, and `gates`.
- `identity`: `package`, `android_user`, `uid`, `version_code`,
  `version_name`, `engine_mapping_sha256`, and `apks`. Each APK has
  `name` (a normalized APK role name), `bytes`,
  `sha256`, and `signer_sha256` (an array of certificate digests).
  All split APKs must have the same signer set.
- Result gate: `id`, `status` (`passed`, `failed`, `blocked`, or
  `unsupported`), `reason` (string or null), and `evidence`.
  Each evidence reference has absolute canonical `path`, `bytes`, and
  `sha256`.

The main APK is always labeled `base.apk`, even when its installed path is
`/system/priv-app/Settings/Settings.apk`. Derive that role from the installed
package's base code path; do not infer it from the source filename. Give splits
stable, unique names and apply the same normalization to manifest and results.
Retain the actual installed paths in the identity evidence. The checker compares
these declared roles; the runtime collector and reviewer establish their meaning.

Every selected application must declare `identity`, `lifecycle`, `stability`,
`data_permissions`, `release_scope`, and `ui_observation`, plus its complete
reviewed business gate list. Reuse the existing application gate definitions;
the checker does not invent business coverage. A passed gate requires nonempty
evidence with at least one nonempty receipt; an empty stderr log is allowed as
an additional reference. Other statuses require an explicit reason and remain incomplete.
Duplicate applications or gates, unexpected results, changed APK/signer/version/
UID, different Main bindings, missing gates, and damaged evidence fail the check.

The checker rereads regular files and verifies identity stability and SHA-256.
Input JSON is bounded to 8 MiB each, evidence to 64 MiB per reference and
256 MiB total per invocation. An evidence file larger than its declared size is
rejected before reading its payload, so an understated size cannot evade the
total read budget. Use the retained compact runtime receipts for
larger media artifacts; their semantic relationship to the media still requires
review. SHA-256 values are lowercase hex. The command writes its JSON report to
stdout and exits unsuccessfully for incomplete evidence or invalid input.

`evidence_complete=true` means complete declared coverage with matching bytes.
It is not a claim that the evidence is truthful, that Main is currently alive,
or that the applications are production ready. The checker always records
`tests_executed_by_checker=0`, `production_ready=false`, and
`runtime_qualified=false`. The runtime owner must obtain the fresh Main
receipt, execute the actual tests, review their meaning, and complete any
account, authorized test recipient, data migration, and release approval gates.
Source tests and prepared leaf entrypoints cannot be substituted for those
runtime results.

## Live application observations and browser entry

The same binary has two explicit live entrypoints. Both require an already
ready, authorized Droidloom cell and matching updated client/daemon binaries.
They never start Android, install or downgrade an APK, clear app data, sign in,
send a message, place an order, or approve a release.

```text
droidloom-applications --inspect-package org.mozilla.firefox --user 0
droidloom-applications --runtime-plan /absolute/runtime-plan.json \
  --expect-runtime-plan-sha256 INDEPENDENTLY_REVIEWED_PLAN_SHA256 \
  --expect-app-count 42
```

The inspection reads the actual Package Manager UID, version code and full
base/split path list, then rereads and hashes every installed APK with stable
file metadata. It repeats PM identity/path queries and binds observations to
the host boot UUID, the daemon-owned cell PID, and the live system_server
PID/start ticks. The main PM source path receives the logical `base.apk`
role even for system APKs whose physical basename differs. APK bytes are
limited to 1 GiB each and 4 GiB per installed set. Signatures are not executed
or invented by this observation: a separately reviewed official-source and
signature receipt must establish the expected complete APK byte set.

The daemon pins proc directories, PIDFDs, namespace FDs, root and cwd before
entry, verifies that the framework belongs to the held cell, and uses only
FD paths for nsenter. It clears the child environment and inherits only the
explicit entry FDs. Each invocation joins a new, exclusively owned cgroup v2
before exec; fixed commands have a 20-second deadline and 64 KiB per output
stream, within a 90-second observation. Nonblocking readers never wait for
pipe EOF. Success requires the invocation's cgroup to be empty and the direct
child reaped before the deadline. Failure allows up to two seconds to prove
retirement. An unresolved group retains its child/cgroup handles and blocks
further invocations. Missing writable cgroup v2 or cgroup.kill is a clear
precondition failure; the daemon does not fall back to numeric-PID entry or
process-group-only retirement. It never kills the cell's namespace init to
retire an application observation.

A runtime plan uses schema `1`, denies unknown fields, and contains:

- `android_user`, `execute_public_browser`, and the complete
  `applications` array.
- `main_qualification` and `gate_registry`: canonical regular-file
  references containing `path`, `bytes`, and `sha256`.
- `expected_epoch`: independently observed `boot_id`, `cell_host_pid`,
  `framework_host_pid`, and `framework_start_ticks`.
- Each application: `package` and `expected_input` (null when the reviewed
  current official delivery is absent). A present input has `version_code`,
  complete `apks` (`name`, `bytes`, `sha256`), and a pinned
  `source_receipt`.
- `browser_fixture`: null when execution is disabled; otherwise a reviewed
  `url` and `input_scope: "public_owned_https"`. Supply only a benign,
  public, operator-owned HTTPS fixture. No login, messaging, purchases, ride
  dispatch or booking is authorized by that scope string.

The gate registry uses the existing `pocket4-app-release-gates-v1` schema:
`common_gates`, profile `checks`, and package `app/kind/profile/prerequisites`.
All six common gates and every selected business contract must be present.
Firefox must resolve to the complete five-gate browser contract. All input
references are checked before any IPC. The Main receipt's bytes are pinned;
its semantic qualification is not parsed or asserted by this entrypoint, as
the report's `main_qualification_semantics_checked=false` states.

Before any package request, the runtime-plan entry performs one read-only
`ObserveRuntime` request and compares its actual physical epoch with the
independent plan pin. A missing, unready or incompatible daemon therefore
blocks every selected row after one preflight instead of repeating a full
socket deadline per application. A transport failure stops the remaining
selection without retrying the operation. A package-specific failure permits
continuing only after a fresh read-only runtime check confirms the same epoch
and owning lifecycle. An observed generation change is sticky: subsequent
apps are not called, and earlier partial observations become blocked while
their diagnostic evidence is retained. No later reply can reopen that run.

The report retains `runtime_preflight`, `observations_share_expected_epoch`,
and `runtime_failure`. These fields describe observation scheduling. They do
not issue a production HostAdmission token or validate a Main receipt. The
current daemon really owns `DevelopmentCell`, so its lifecycle observation is
explicitly `development`. This source has no production cell owner/borrow
adapter; production namespace preparation or a caller-supplied PID cannot
substitute for that missing lifecycle integration. The production/runtime
qualification flags remain false even when the epoch check succeeds.

Every selected row is retained. Missing runtime, installed package, expected
source delivery or matching current epoch produces `blocked`. Other registered
profiles currently produce `unsupported` after identity admission; their
separately qualified existing leaves remain separate. No arbitrary shell,
legacy leaf or account flow is auto-dispatched. Firefox resolves the reviewed
HTTPS URL through the actual implicit Android BROWSABLE/VIEW resolver and
requires it to select Firefox; it then executes the actual activity start and
checks returned activity status and unchanged installed identity. It does not
force an explicit component when another browser is selected.

That successful entry is only `partial_observation`. Rendered document/input/
images, media, navigation/reopen, recovery and all common gates remain pending.
The report always has `accepted_applications=0`, `accepted_gates=0`,
`production_ready=false`, `runtime_qualified=false`, and
`automatic_retry=false`; the runtime-plan command exits unsuccessfully because
whole-app acceptance is incomplete. Identity inspection may exit zero for its
observation and still cannot be consumed as an application PASS.

## Specialist helpers

These are not needed to install or build the x86_64 pacman preview. They remain
because the Rust package workflow does not replace their ARM64, diagnostic or
source-generation roles.

| Tool | Retained purpose |
| --- | --- |
| `droidloom-soong-core-smoke` | Focused Android builds, including ARM64 and individual framework components. |
| `droidloom-vendor-image-smoke` | Standalone vendor-image build, including ARM64. |
| `droidloom-navigation-services` | Services-JAR provenance used by focused Soong and ARM64 deployment scripts. |
| `droidloom-systemui-stubs` | Regenerate SystemUI Binder adapters when pinned AOSP interfaces change. The Rust builder checks these adapters. |
| `droidloom-dmabuf-probe` | GLES/DMA-BUF/explicit-sync diagnostic; does not validate a complete Android app. |
| `droidloom-translation-bench` | Repeat Digitalis host correctness tests, time seven guest workloads across three translation modes, and compare saved runs. See [translation benchmarking](../docs/BUILDING.md#translation-stress-and-performance-benchmarks). |
| `droidloom-inspect.rs` | Optional read-only diagnostics for the development workstation's u1000 cell; fixed `features`, `properties`, and `configuration` modes. |

The Rust updater and package workflow own x86_64 installation, init projection
and Mesa builds. New orchestration should be Rust; legacy scripts are not a
template for new tooling.

The workstation diagnostic helper can be built with
`rustc --edition 2024 -O tools/droidloom-inspect.rs -o /tmp/droidloom-inspect`.
Its optional administrator installation is `/usr/local/sbin/droidloom-inspect`,
owned by root with mode 0755. A sudoers rule may grant UID 1000's user the three
exact mode arguments above; validate it with `visudo -cf` before installation.
Use `sudo -n /usr/local/sbin/droidloom-inspect features` to inspect the live
feature list. The helper takes no PID, path, shell or extra command arguments,
selects init only from `/run/netns/droidloom-u1000`, pins its process resources,
clears the execution environment and bounds commands to 15 seconds.
It is deliberately workstation-specific and is not installed by the packages.
Remove `/etc/sudoers.d/droidloom-inspect` to revoke the local passwordless grant.

The package builder also provides `ship prepare`, `ship publish`, and
`runner setup|start|stop|status` for the [GitHub shipping workflow](../docs/BUILDING.md#shipping-with-github-actions).
