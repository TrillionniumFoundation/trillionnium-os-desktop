# Private generation V2 pairing source revision

This is a new source delta based on the actual candidate06 source map and the
actual compiled450 updater source map. It does not modify either frozen parent,
the running cold build, its resource gates, or Main. The 925 engine file hashes
are identical to candidate06. Exactly one of the 948 overlay files changes:
the two ART_RUNTIME marker literals now identify `DLOOMGE1-PROCMET2`, matching
the existing engine, bridge, and two protocol headers.

The updater is a separate expected 451-file source revision: three existing
files change and one module is added; the other 447 files retain their compiled450
source bytes and modes. These are derived maps, not receipts of a remote source
composition, Rust compilation, ART build, or Android run.

## Concrete code changes

- `platform/art/runtime/native_bridge_art_interface.cc`: repair the stale
  PROCMET1 marker in both enabled and disabled modes. The function bodies and
  feature conditionals are unchanged.
- `tools/droidloom-update/src/native_generation.rs`: port the previously
  published pairing module, require PROCMET2, and add a create-only production
  record generator. Existing verifier/staging bodies and nine original tests
  are retained except for the protocol constant. Five focused tests are added.
- `main.rs`: wire the module and add `native-generation-pair --product PATH`.
  This command reads the already built engine and ART APEX, extracts both
  nested ELF components, checks all three enabled role markers, and creates an
  exact hash record. It never sets an enable flag, compiles, installs, activates,
  or starts a service. A separate CLI parsing test covers its argument boundary.
- `native_bridge.rs`: call `stage_product` inside the existing image-derivation
  transaction after copying the engine. A provided pair replaces the whole APEX
  only after checking the actual components and equality of its payload key to
  the base APEX key; the new APEX and record enter the existing image inventory.
- `bundle.rs`: invoke `verify_bundle` on the actual staged image. The existing
  `verify` action and ordinary build/seal flow already call `bundle::verify`.

The generator derives hashes from actual bytes. It rejects old or mixed role
markers, and a contract supplied for disabled or unmarked components is refused.
Publication uses a temporary file in the explicit product directory and
`persist_noclobber`; any existing record, including a symlink, remains intact.
Staging and bundle verification re-read the component bytes rather than trusting
the product record alone. Unmarked legacy components remain accepted only when
all three generation modes are disabled and no enabled contract is supplied.

## Source-bound lifecycle call chain

The following current references were independently matched to candidate06's
948-file map. They are included under `references/current`.

| Source entry | Observed call | Meaning and remaining limit |
| --- | --- | --- |
| `art/libnativebridge/native_bridge.cc` load path | `Prepare(handle)` after bridge compatibility and before initialization | Resolves the private engine entry and requests stack preparation; does not start an app worker here. |
| `PreZygoteForkNativeBridge` | Legacy `preZygoteFork()` first, then `BeforeFork()` | Guest log cleanup precedes quiescing the owner, before ART's later thread wait. The broader caller timing still requires the current ART caller sources. |
| `art/runtime/native_bridge_art_interface.cc::InitializeNativeBridge` | `DroidloomNativeBridgePostSpecializeV1()` before the already-initialized early return | This is the explicit grant site, including the app-zygote early-return path. Its comment is not proof of every caller's specialization order. |
| `art/libnativebridge/droidloom_generation.cc` | `AfterSpecialize()` builds protocol2 requests and marks a changed TGID as a private child | Actual private-fork, credential and child-zygote authority must be established by the ART caller chain, not inferred from TGID inequality alone. |
| `engine/kernel_api/proc_maps_generation.cc` | `Dispatch` checks ABI/size/protocol before operations | The existing protocol2 machine words already reject protocol1 requests. The source revision does not relax these checks. |
| Bridge initialize/unload | `RequireReady` before guest initialize; `BeforeUnload` before `dlclose` | Failure remains closed. No lazy `Attach` or `ExecuteGuest` startup is introduced. |
| Guest clone/exec/syscall adapters | Explicit generation entry points | Existing private-fork, exec failure and guest transition handling is retained; it does not cover every host-native transition. |

The public private-call declaration has C linkage in `native_bridge.h`, and its
name is present in `libnativebridge.map.txt`; both exact references are included.
The two actual protocol headers contain ABI1 with PROCMET2 machine words.

The separately prepared four-file reader requests the current `runtime.cc`,
`dalvik_system_ZygoteHooks.cc`, `com_android_internal_os_Zygote.cpp`, and runtime
`Android.bp`. At this freeze those observations have not been supplied. Even a
successful source read will not by itself bind those files to installed ART.

## Verification status and next required gates

`LOCAL_SOURCE_CHECKS.json` records only exact source/hash comparisons and
`git apply --check` against the exact preimages. This local environment has no
Rust toolchain. None of this revision's Rust tests, CLI, ART translation units,
or Android lifecycle paths has been executed. No historical R8 fixture PASS is
carried forward as a new result.

The matching updater compile must use the new complete 451-file map, pinned
Rust 1.93 and its verified offline/locked dependency closure. It must run the
existing seven builder gates, all fourteen `native_generation` tests, and the
new CLI test. The added controls cover each old protocol role in both modes,
self-consistent wrong-generation hashes, an old contract protocol, refusal to
generate for legacy/disabled components, and create-only exact record output.

This revision intentionally does not claim that pairing alone enables the
feature. The following concrete platform work remains required before enabling:

1. Bind and validate the actual post-specialize caller sequence, including
   ordinary apps, app-zygote preload, and subsequent app-zygote children. The
   existing `kChildZygote` bit is not propagated or acted on by the current path.
2. Add the explicit normal builder projection and common feature selection for
   the engine, `libart`, and `libnativebridge`, then build and inspect all three
   actual components and the complete ART APEX. Current flag0 engine builds do
   not build or project this platform delta.
3. Qualify actual APEX container/payload signatures and normal package activation.
   Comparing `apex_pubkey` bytes and component hashes is not signature verification;
   the owned image fixtures are not signed production ART artifacts.
4. Close the remaining host-native credential/root/mount transitions and final
   host-native thread exit lifetime. Guest syscall checks and source sampling
   do not establish those broader lifecycle guarantees.
5. Run actual enabled engine/ART/factory lifecycle and application controls.
   The unrelated scoped host and Android NOFILE controls remain separately bound.

Both generation macros remain default-disabled. This source revision provides
no deployment authorization and no whole-app production qualification.
