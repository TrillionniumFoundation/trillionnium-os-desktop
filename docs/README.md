# Droidloom documentation

- [Install Droidloom and APKs](INSTALL.md): package installation, first start and app management.
- [Build packages](BUILDING.md): prerequisites, Rust builder and package checks.
- [Known issues](KNOWN_ISSUES.md): preview limitations and workarounds.

- [Architecture](architecture.md): Android cell, graphics path and source boundaries.
- [Desktop integration](desktop-integration.md): windows, clipboard, notifications and diagnostics.
- Integration proposals: [audio](audio-integration-proposal.md) and [SMS](sms-integration-proposal.md).
- [Security requirements](threat-model-v1.md): trust boundaries and isolation limitations.

## Integration contracts

- [Runtime layout](contracts/runtime-layout-v1.md): namespaces, mounts and lifecycle.
- [Private Binder](contracts/binderfs-v1.md): cell-local Binder devices.
- [Text input](contracts/text-input-v1.md): Android IME and Denial keyboard dismissal.
- [Navigation insets](contracts/navigation-insets.md): app geometry and host system bars.
- [Frame timeline](contracts/frame-timeline-v1.md): optional Denial protocol contract.

The private Android-to-host wire protocol is documented in [protocol/](../protocol/README.md).
Build and installation internals live with their code in
[tools/](../tools/README.md), [packaging/](../packaging/README.md) and
[android/](../android/README.md).

## Pocket4 native application leaf adoption

The native dispatcher compiles the complete selected thirteen-source catalog.
A root-owned detached release pairs that catalog with the final installed
`/usr/bin/droidloom-applications` artifact. This avoids embedding a CLI hash in
Python source whose own hash contributes to the same CLI. Source preparation,
CI compilation, release adoption and actual Android acceptance remain distinct.

After the full current CI run and normal installation have both been verified,
the deployment owner prepares a root-owned, content-addressed adoption intent
under `/etc/droidloom/native-application-leaves/adoption-intents/`. The intent
pins the complete original CURRENT raw bytes and F9, the actual installed CLI,
the compiled selector, and the complete CI report with its GitHub commit/run.
The publisher is invoked explicitly with `--adopt-native-leaf-release` and
`--expect-native-adoption-sha256`; these options conflict with all Android and
catalog operations. No package is installed by this command.

The root deployment layout must already contain `catalogs`, `current-preimages`
and `releases`, each with a root-owned `.layout` file containing exactly
`pocket4-native-application-leaf-layout-v1` followed by one newline. Root parents
must be ordinary, non-writable by group/other, and contain no symlinks. The
publisher retains both original owner locks exclusively, saves the actual full
preimage, publishes content-addressed records and changes only the
`native_application_leaf_release` CURRENT field using a fresh whole-file CAS.
It retains the original owner, fixed expiry and every false qualification flag.
The running CLI's actual `/proc/self/exe` OFD must equal the installed artifact.
No later CURRENT edit silently inherits this adoption: a new independent root
adoption is required, without recompiling an unchanged source catalog.

Gallery's four original finite cases use two 340-second image observations,
the unchanged 600-second business/120-second cleanup limits, and a fixed
1530-second outer bound. Calendar reminder keeps its 690-second outer bound.
Other prepared leaves retain the existing maximum of 1200 seconds. Neither
new wrapper accepts an arbitrary host entry, source path or resource profile.

The final invoking controller must place the native CLI inside its actual
bounded outer job before either resource-sensitive route runs. Gallery requires
that parent's local `cpu.max` to be numeric and at most two CPUs, `memory.max`
exactly 2147483648, `memory.swap.max` zero and `pids.max` 64. Calendar reminder
requires at most half a CPU and `memory.max` exactly 536870912, with the same
zero-swap/64-PID bounds. Both require zero OOM events and real CPU 20 availability.
The new child remains nested inside that exact job, is create-only, uses CPU 20
and no core dumps, and is completely drained/reaped by the original ownership
primitive. Its held real ancestor controls prove the effective hierarchy limit
when cgroup v2 does not expose local child memory controls; `max` is never
relabelled as a numeric limit. No shared controller or ancestor is modified.

A correctly rejecting unbounded invocation is only a precondition test. The
production launcher/controller must also be exercised in its final resource
layout, followed by real Main, business, cleanup and source bookends, before
these runtime blockers can be called closed. Source/CI success and detached
adoption confer no whole-application or production-ready status.

## Preparing the selected application runtime plan

The static `p4-selected39-static-launch-inputs-v1` source document is not an
executable runtime plan. `droidloom-applications --prepare-runtime-plan` binds
that reviewed document to the current daemon's complete PM identities and
enabled MAIN/LAUNCHER catalog. The operation only queries metadata. It does not
install, launch, close, retry or change Android applications or user data.

The deployment owner supplies a separately reviewed JSON intent with `schema:
1` and all of the following fields. File pins have exactly `path`, `bytes` and
`sha256`, using bounded canonical absolute files and their actual SHA-256.

| Intent field | Required input |
| --- | --- |
| `selection` | Pin of the complete current static launch-input document. |
| `source_receipt` | Pin of the admitted byte-identical copy of that document's signature/material receipt. Its path may differ from the original work directory; its size and digest must match every selected app's receipt. |
| `main_qualification` | Pin of the current independently established Main receipt. Preparation checks bytes, not the receipt's qualification semantics. |
| `expected_epoch` | Actual `boot_id`, `cell_host_pid`, `framework_host_pid`, and `framework_start_ticks` for that Main. Source artifacts cannot supply these observations. |
| `gate_registry` | Pin of the complete `pocket4-app-release-gates-v1` registry, including each selected app and all six common gates. |
| `specification` | Pin of the currently admitted cell specification. |
| `android_user` | Explicit Android user for these observations and subsequent operations. |

Stage reviewed receipts through the normal admitted release-input path. Work
directory paths in the static document do not authorize reads from the public
client's domain. Each package's entire installed version/APK byte set must match
the selected source. The prepared plan uses actual normalized PM filenames;
downloaded split filenames are never guessed. The preferred manifest component
must be present exactly once in the current enabled catalog. If that preferred
alias is disabled, preparation accepts only one unambiguous enabled alternative
from the reviewed candidate set.

```sh
droidloom-applications --prepare-runtime-plan "$intent" \
  --expect-preparation-sha256 "$intent_sha256" --expect-app-count 39 \
  > preparation-report.json
```

Exit status zero means only that all 39 launch bindings were prepared. Any
blocked binding causes a nonzero status while preserving every selected row,
its source version, source file identities, actual PM observation if available,
failure reason, business/common assertion text, and external prerequisites.
Review the complete report, including unresolved source freshness and signer
or data-migration facts. A newer installed package cannot erase those facts.

The report's `runtime_plan` object is the existing schema-3 execution input.
Extract it to a new ordinary file, review it, and independently pin the exact
file that will execute:

```sh
jq '.runtime_plan' preparation-report.json > runtime-plan.json
sha256sum runtime-plan.json
droidloom-applications --runtime-plan "$runtime_plan_absolute_path" \
  --expect-runtime-plan-sha256 "$runtime_plan_sha256" --expect-app-count 39
```

Keep the preparation report with the exact executed plan and its runtime
report. A failed binding is retained inside the plan and cannot turn into a
launch just because the runtime later changes; resolve it and prepare a new
reviewed plan. Successful rows use only the existing launch-only route, which
rechecks Main, PM/APKs, current launcher, source/specification pins and actual
owned task binding. It does not prove rendering, close/reopen or business gates.

Runtime reports retain the expected source input, requested route, actual
inspection/launch/leaf observations, required assertion text and failure reason
for each selected app. Only assertions explicitly verified by an original
finite leaf receive evidence credit: the current Settings terminal contract
verifies `settings.pages` and `settings.roundtrip`, while `settings.permissions`
and all common gates remain pending. Other existing finite cases remain scoped
observations; in particular IHG's London input/readback is not hotel availability
or business success. Whole-app counts require every registered assertion to
pass. Metadata, installation and launch counts cannot increase that total.
