# NORMAL03: strict framework build with an independent zero-swap budget

State: **SOURCE_ONLY / UNRUN**. Root alone dispatches this candidate. No Python or Soong execution, Android action, installation, branch update or PR update was performed by this author. Whole-app readiness is **0/45**.

NORMAL02 remains an actual failure: its fresh `SwapFree >= 2 GiB` condition failed before the builder was spawned. The inner function was called, but the normal builder was not. Its 40 pure cases, four real root/operator lifecycle cases, six outer retirement records and five root reports were independently read back. They do not turn the resource failure into success.

## Independent profile

| Setting | NORMAL02 | NORMAL03 |
|---|---:|---:|
| Owned RAM limit | 10 GiB | 10 GiB |
| Owned swap limit | 1 GiB | 0 |
| Required current owned swap before builder | inherited gate | 0 |
| Fresh MemAvailable minimum | 13 GiB | 15 GiB |
| Arithmetic free-RAM difference | 3 GiB | 5 GiB |
| Fresh global SwapFree minimum | 2 GiB | no owned-budget dependency; recorded only |
| CPU quota / jobs / nice | 200% / 1 / 10 | unchanged |
| Builder / request deadline | 6100 / 6400 s | unchanged |

The fixed Resource01 sample has MemAvailable 17,379,332,096 bytes and SwapFree 996,478,976 bytes. It is a later planning observation, never a substitute for NORMAL02's unavailable failing numerical sample or a future admission. The new gate must read fresh. Its 5 GiB difference is arithmetic headroom, not a physical reservation or proof of full-interval noninterference.

After validating the exact owned job, the controller sets only that job's MemorySwapMax to 0. It records four exact owned limit/current scalars and a bounded complete `/proc/meminfo` read in `resource-admission.json`, fsyncs and closes it, and prints its pin before applying the new capacity gate. Both owned swap limit and current must be 0. The normal terminal checks them again. Global swap is recorded but supplies none of this build's budget. Earlier lifecycle-control preamble is not retrospectively called zero-swap.

## Preserved boundaries and controls

The actual builder 468 ELF and 491-source map, both normal locks, fresh 214-to-224 project reconciliation, atomic publication, exact two targets, `Strict` / `ALLOW_MISSING_DEPENDENCIES=false`, projection restoration, original builder child cleanup, seven-role Main guard and all five Main limits are unchanged. The actual-tested capture core and root supervisor are byte exact; their four real controls run again on the new admission.

The stage runs 45 pure cases: 37 unchanged nonresource cases plus 8 zero-swap/admission-parser cases. This source author did not execute them. Reaching a normal command-completion record still leaves implementation-JAR bytecode and Android JNI object/header/link qualification pending.

## Risk and reproduction

Prior normal RAM peak was 7,947,964,416 bytes (7.402GiB), with 50,835,456 bytes swap. That attempt ended at a graph error. A successful full build may need more. The new zero-swap budget can make owned allocation failure more likely; no gate or OOM evidence is hidden. Lowering RAM to 8 GiB is not supported by that partial prior peak. The earlier 1 GiB Rust compile is a different workload.

`make_request.js` reproduces the exact staged 17 files, source packet and request from immutable text. `SOURCE_PINS.json`, six `from-normal02.patch` files and the full original failure/resource records identify the change. No original01/02 request is retried.
