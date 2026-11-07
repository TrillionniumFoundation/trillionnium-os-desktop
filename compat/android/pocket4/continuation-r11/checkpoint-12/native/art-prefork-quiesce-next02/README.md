# ART pre-fork owner quiescence, next02

This independent source revision corrects the order of the existing native bridge callback in `Runtime::PreZygoteFork`. It does not alter candidate06, paired-generation-v2-next01, an installed library, or an existing build attempt. Neither this source nor its lifecycle control has been compiled or executed at freeze time.

## Observed defect and correction

The held current AOSP `runtime.cc` has a complete `Runtime::PreZygoteFork` which calls the bridge after `WaitUntilSingleThreaded`. That wait reads the real kernel thread count, repeats up to 2000 times, and then emits a fatal error. ART's ThreadList does not account for the private raw owner thread. A live owner therefore prevents reaching the callback that would stop it. This is a source-supported enabled-path defect; it is not an observed failure of the currently disabled candidate06.

For an explicitly enabled `DROIDLOOM_NATIVE_GENERATION_RUNTIME` build, next02 calls the same hook after JIT pre-fork work and before either ThreadList or kernel single-thread waiting. It leaves the legacy guest log close and generation `BeforeFork` in their existing order inside libnativebridge. A failure to quiesce remains fatal. It makes no metadata call after quiescing and does not introduce lazy owner startup. The branch for an absent or zero macro keeps the original late call after heap pre-fork work. Each branch calls the hook once.

The first-fork class-linker and heap operations are otherwise unchanged. This patch does not prove that every transitive implementation of those operations is generation-safe. That requires a real ART build and lifecycle execution.

This corrects the prior libnativebridge comment and next01 timing assumption that its pre-fork callback already runs before ART waits. The frozen prior sources and their unverified statements are retained. The implementation in this revision makes that ordering true only for the explicit enabled flavor.

## Build macro coverage

The observed `art/runtime/Android.bp` lists both `runtime.cc` and `native_bridge_art_interface.cc` in `libart-runtime_common_defaults.srcs`. `libart-runtime_defaults` inherits it, the `libart-runtime` static archive consumes that defaults module, and `libart` links that archive using `whole_static_libs`. A macro on the final `libart` module would not establish how the two archive translation units were compiled.

The separate `build-only-enabled-flavor.patch` puts the runtime macro on `libart-runtime_common_defaults` and the same value on `libnativebridge-defaults`, whose library compiles both `native_bridge.cc` and `droidloom_generation.cc`. This patch is explicit opt-in build data. It is not part of the default runtime source delta and is not applied to candidate06. The source relationship alone is not proof of actual compiler command lines or final linked behavior. The full TU gate must inspect the actual generated compile commands for each of the four translation units and the resulting archive/shared-library inputs. Markers do not establish call order.

## Four bounded lifecycle controls, prepared but not executed

The control extracts the exact complete old/new `Runtime::PreZygoteFork`, unchanged `WaitUntilSingleThreaded`, the exact libnativebridge pre-fork function, and ART's one-call wrapper from pinned sources. It supplies explicit peripheral ART class fixtures. Its live worker is a real pthread deliberately absent from the fixture ThreadList; it is not represented as a new production raw-owner qualification. The wait still performs the actual own-process kernel stat read. No Android process, arbitrary process, service, or namespace is touched.

| Arm | Required result |
| --- | --- |
| Old function, enabled flag, live unregistered worker | The real 2000-try wait reaches fatal before any bridge callback. |
| New function, enabled flag, live worker | Guest log callback, quiesce and join precede the first kernel-wait read; function returns. |
| New function, flag zero, no owner | Original late callback order after kernel wait and heap pre-fork remains. |
| New function, enabled flag, quiesce refuses | The existing bridge failure remains fatal before any kernel-wait read. |

The parent captures only owned process output, enforces a per-case deadline, reaps each child, verifies frozen source and compiled control ELF identity, and records its invocation cgroup limits, peaks and OOM deltas. Fatal exits are expected negative results, not discarded errors. The request is compile plus these four controls only, with CPU 1 and a 1 GiB maximum. A source fixture PASS will not be described as a complete ART translation-unit build or installed runtime PASS.

## Remaining gates

- The four held AOSP source observations do not bind installed ART binaries or the old compiled450 builder.
- The existing updater exposes engine build and pair-record operations, not a complete enabled ART projection/build entry. A new explicit normal projection route must use the ordinary journal and locks, fixed ART targets, fresh output and complete source inputs. There is no honest executable full-TU request yet; the required gate is recorded in `FULL_TU_GATE.json`.
- An app zygote intentionally retains SETUID/SETGID/SETPCAP and must execute guest preload code. The raw owner still requires nonroot zero capabilities. This revision neither weakens that gate nor resolves the child-zygote preload contract.
- Java post-specialize callback wiring, actual owner generation across the complete ART fork lifecycle, host-native credential/root/mount transitions, final native thread exit, signed APEX pairing, and app acceptance remain separate requirements.
