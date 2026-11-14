# Selected QPR1 ART coherence and adoption boundary

## Current conclusion

The selected official CP3A.260905.010 / 16176746 ART must remain byte-for-byte intact. The current Native601 engine is an enabled CP2A engine/modified-ART pair and still requires private generation protocol `DLOOMGE1-PROCMET2`. It cannot currently satisfy that policy as a standalone bridge. No deployment, runtime, ABI or production-ready credit is granted by this audit.

The source-cone repair in private commit `c0522b7877485d786b58b67b02e8297e41d53c8c` addresses the actual r12 build failure. It preserves the paired build contract and does not resolve this cohort mismatch. Its four runtime/consumer Rust files were freshly read from that exact isolated recipe and match the earlier frozen audit byte-for-byte; see `latest-consumer-pins.json`.

This compact review should be read before the older `qpr1-audit/REVIEW.md`. That older document records an earlier channel outage. `qpr1-audit/FINAL-READONLY-ADDENDUM.md` supersedes its then-pending physical ELF observations, and the original raw evidence remains pinned by `qpr1-audit/FINAL-PINS.json`. This review adds no unobserved runtime result.

## Physical evidence that constrains the route

| Selected object | Bytes | SHA256 |
| --- | ---: | --- |
| Official raw `system.img` | 2294853632 | `dc781249bb4724b7a0777e5077321b84576db46f61abb4b9086b81077bfd0ab4` |
| Official ART CAPEX | 20357120 | `5d0e18b7e2ff241989323c1d0d1695c97921ba85b617ba12e5aa69775b7bd5c0` |
| Its embedded original APEX | 49065984 | `5ace9ff8a8ab73aa64b63901fe18782028d5c61c452a35b8ad07fb0b711247d0` |
| Stock `libnativebridge.so` | 51336 | `748db85ddb4c3284e6b3fe20417c2c58dee9a23d3da29c050abb92ffaa1a38ab` |
| Stock `libart.so` | 14884360 | `38849876d2101a7bac548d3438e3effff01e38f13f3b5740a2364b762fc229d3` |

The selected image has `/system/apex/com.android.art.capex`. Both inspected stock ELFs lack the private Droidloom generation markers and post-specialize symbol. The standard bridge loader's observed pre-zygote dispatch checks interface compatibility and invokes the standard callback; it is not evidence of a private post-specialize callback.

The real selected build properties identify CP3A / 16176746 and a `user/release-keys` system fingerprint, with `ro.dalvik.vm.native.bridge=0`. Bounded complete listings of its standard `/system/lib64` and `/system/lib` directories found no named ARM translation engine, only the lazy bridge loader. This does not assert absence from every image path. The inspected official emulator alternatives contain different build identities; neither is a qualified same-release replacement. Exact public CP3A source was not authenticated by the recorded searches; the audit does not claim that such a revision cannot exist.

## Existing guarantees and why the ordinary callback is insufficient

The frozen engine's `RequireReadyForNativeBridge()` runs before translation initialization. The current generation state machine prepares owned memory, closes a generation before a known fork transition, accepts an explicit post-specialize grant, and retires workers on unload, exec and exit paths. A changed TGID is explicitly insufficient proof of a private-memory fork; arbitrary `CLONE_VM` children cannot reset inherited ownership.

The authenticated CP2A sources show two separate gaps that modified ART currently closes. First, ART's single-thread check precedes the standard bridge pre-zygote callback, so a persistent raw worker cannot wait until that callback to retire. Second, the ordinary native-bridge initialize path is skipped in children of an already initialized app zygote. The private grant is deliberately placed before that early return. An atfork child handler executes before `SpecializeCommon` completes and therefore supplies no post-specialization credential or namespace guarantee by itself.

A request-scoped worker could remove the first obstruction only if every request retires its worker before returning. It must retain the current raw metadata ownership model, caller credential and namespace validation, guest FD separation, no accidental libc/TLS dependencies, bounded shutdown, clear-tid/reap guarantees and fail-closed handling of uncertain retirement. It does not by itself supply the missing child admission event. First use, a new PID, a marker string, a guessed stable credential snapshot or a generic thread callback must not become that event.

The existing stager checks the candidate and base ART package before opening the base ART file for truncation. With the selected CAPEX-only layout, its lookup for the plain ART APEX fails closed before an ART replacement. Adding a replacement path for CAPEX, renaming the stock container, disabling the engine macro or relaxing mixed-pair checks would violate the retained-official-ART requirement. No such change was made.

## A distinct post-specialization boundary worth further study

Three additional original framework files were read and independently matched to Git blobs at CP2A `frameworks/base@94b4c163b7dfe5ce3607f7bb8456f9573f7de57d`; their full sources and exact pins are included here. They are **not authenticated CP3A implementation evidence**.

`ZygoteConnection` calls `WrapperInit.execApplication` in the child after `forkAndSpecialize` returns. That path execs the stock `app_process` and then enters `WrapperInit`. It is an actual source-level post-specialization execution boundary and could, in principle, preserve official ART bytes. It is not an available general production admission API:

- The explicit `invoke-with` policy rejects an ordinary non-root caller without the relevant debug flags. The source has a separate explicit allowance for root peers. That allowance does not authorize treating an existing system-server request as root or adding a privileged proxy.
- The `wrap.*` property path is separate and requires verification of actual selected-build property and SELinux policy. A comment about userdebug usage is not proof of the running policy. This audit neither sets properties nor changes debug, SELinux or capability policy.
- Exec discards the previous process's in-memory generation state. Calling the present private grant before exec would not authorize the fresh engine instance afterward.
- A viable new route would need a separately reviewed trusted launcher/admission producer, a one-use receipt bound to the actual owned child PIDFD, nonce, final credentials, namespaces, executable and launch generation, and an engine bootstrap consumer that validates it before translated execution. Its receipt descriptors must be retired before guest access. Caller-supplied JSON, a PID string, inherited state or a protocol marker cannot substitute for that producer.
- The route must prove ordinary children, app-zygote initialization, already initialized app-zygote children, repeated forks and failure cleanup under the selected stock binary. A route that covers only debuggable apps or only the first child cannot qualify all requested applications.

This is a conditional architecture lead, not an approved or implemented replacement. The selected QPR1 callback/zygote implementation, policy admission, fresh-process handoff, full worker lifecycle and real ABI/runtime behavior remain unverified. There is no small source patch justified by the present evidence that closes this entire blocker while retaining all current guarantees.

## Precise mainline adoption checklist

1. **Native601 source repair:** verify the three exact preimages, adopt the 9125-byte `original-flags-provider.patch` or the matching private commit, and retain the new lock SHA `74372a62836ec16c30a6f24c6e13725831f90e13f2bbc4c9f9f56c74895b163d`. Reconcile using the normal materializer under the foreground owner's existing shared locks. Reverify the 20 flags files plus the 8 original transitive-provider files. Start only the owner's one admitted strict full; a previous 35-test normal receipt is not a full-build receipt.
2. **C11 actual source rebinding:** the observed owner private Binder PASS used the original child, IPC and parent preimages. Apply the published deadline and mapped-ownership patches to the exact matching source generation, bind a new capsule to the combined postimages, then execute the owner's serialized real private control. Preserve the shared work deadline, independent cleanup allowance, no transaction resend, actual mapped UID/GID observations and full retirement checks. The old PASS and host smoke do not cover the new postimages.
3. **Stock ART route:** define a separate exact stock-input and admission contract. Preserve official system, ART CAPEX/original APEX, runtime APEX, framework, bionic and linker providers. Verify real candidate ELF dependencies and versions against those exact providers, and keep the existing paired validator intact so receipts cannot cross modes.
4. **Runtime qualification:** after production namespace/Main readiness, exercise actual ARM native loading and JNI paths, all relevant fork/admission cases, worker retirement and application business flows using the same frozen candidate and selected cohort. Until those observations exist, every runtime, ABI, final-app and production gate remains pending.

The current root coordinator owns CURRENT, foreground admission and publication. This audit did not modify owner sources, launch another full, mount a filesystem, start Android or repeat a private Binder control.
