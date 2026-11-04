# Pocket4 native-bridge repairs: R15 and R16

Status: **built, host-tested and qualified on owned private native probes; R16 is activated in Main; publisher application qualification remains open**. Neither candidate is marked production ready.

This bundle preserves two focused Teto/Android native-bridge fixes and all their public source preconditions. It also preserves the separate DroidLoom builder source required to produce the recorded Android engines. No shared library, executable, APK, signing material, private device data or raw app crash capture is included.

## Fixes and direct regression evidence

**R15 — SIGALRM disposition.** `ClaimHostFaultSignals` previously changed a default process-wide SIGALRM disposition to ignore. That could suppress ordinary alarm termination and discard a blocked pending alarm. The repair removes that override while keeping the actual host-fault signal setup. Eight real fork/signal cases cover the default disposition, an armed timer, a pending blocked alarm, existing handlers and sender/cause data, explicit ignore, the process signal mask and unrelated signals.

The predecessor failed the three default/timer/pending cases while passing five controls. The candidate passed all eight cases and 30 existing signal/PSTATE controls.

**R16 — file offsets in guest maps.** When a host VMA is split at guest execute boundaries, a file-backed chunk's offset must advance by its start address delta. The repair updates that offset while preserving anonymous mappings, the unsplit fast path, permissions, device/inode fields and paths. The real memfd regression covers ordinary offsets, offsets above 4 GiB, an unsplit mapping and an anonymous mapping.

The predecessor failed both split-file cases and passed the two controls. The candidate passed all four cases and 38 signal/PSTATE controls. An earlier test-fixture initialization failure is retained as failed evidence, not counted as a pass.

The full frozen host suites were also run:

| Revision | Registered | Executed | Failed | Disabled | Skipped |
| --- | ---: | ---: | ---: | ---: | ---: |
| R15 | 3,789 | 3,787 | 0 | 2 | 3 |
| R16 | 3,793 | 3,791 | 0 | 2 | 3 |

Executed counts include cases reported skipped; registered counts include disabled cases. These totals do not mean every registered test passed. [Focused results](evidence/focused-regressions.json) and [full-suite results](evidence/full-host-suites.json) preserve exact scope, source/artifact bindings and omitted cases.

## Public source reconstruction

The translator starts at `denialwm/teto` commit `917021cf3ecd077eb1581146a79d2265011755b8`. Apply the three patches in order:

1. Complete inherited R14 precondition — 906 raw source files, commit `1f961de88621af76b0d9e8c1f3c8ad7f7ca4c965`.
2. R15 alarm repair — 907 files, commit `a2cbf8072a580fb1949924e3dda858a6ba6ed984`.
3. R16 maps repair — 908 files, commit `a9496d886a85752ba407b76509952c06cd79ddb8`.

Exact manifests for every stage are included. The six final files changed by R15/R16 are preserved under `source/`.

The builder starts separately at public DroidLoom commit `75c5acf086f25fb8d2a31d159a57cdb4e75f85de`. Its complete public precondition changes 31 paths and reconstructs **389 public files**. It does not assume that the intermediate local commit `7a9e8bbe...` is publicly available. Private historical provenance metadata is excluded. The recorded local builder snapshot is `500dd3af851aaadb95537b68129b8bd889504951`.

Use repositories containing the pinned upstream commits:

```sh
python3 tools/verify_source_series.py \
  --teto-repository /path/to/teto \
  --builder-repository /path/to/droidloom
```

The verifier exports those immutable commits to temporary directories, applies the complete patch chains, and checks every raw source hash and the final delivered files. It does not modify the input repositories or the Android runtime. Python 3.12 or newer and Git are required.

## Raw source and effective compiler inputs

The raw source snapshots and the compiler-effective sources are distinct. The frozen build receipts match all 907/908 raw snapshot files to their respective manifests. The builder then applies existing controlled compatibility projections.

For both revisions, **22 translator files** differ between the raw and effective layers: 21 `Android.bp` files and `interpreter/arm64/interpreter.h`. The new signal implementation, maps implementation and their tests are not rewritten by that projection. Both complete effective input manifests and the raw-to-effective differences are published under `manifests/`. The [build-input binding check](evidence/build-input-binding.json) independently matches the effective manifests in the frozen source and input receipts, rehashes both engine and host-test artifacts, and matches the full-suite binary identity. The Android engine and host suite share the recorded effective source graph; their target ABIs and compiler flags are not claimed identical. The complete builder patch contains the transformation code; no projection is concealed as an unchanged raw file.

The one production-header projection removes only the unused two-line `need_write` declaration from `LoadStoreExclusive`. The frozen builder applies an exact string replacement in `tools/droidloom-update/src/native_bridge.rs`; its comment identifies the obsolete flag left after the transition to fault-recoverable atomic builtins. The raw header SHA-256 is `6a07de1c3b9b0b4be2dc521829734ec2fed82a3764247b0a4b73afc93464a174`; independently applying that exact replacement yields `c2dbb95f386e5d542c62031123b85926e6661cf3a31dca9090e353713ef78d87`, matching both frozen effective manifests. [The exact diff](projection/interpreter-unused-flag.patch) is included as an audit aid. It is applied by the builder during the projection stage, not as a fourth raw source-series patch. Atomic load/CAS and fault-recovery operations are unchanged by this removal.

The AOSP lock pins 214 projects. Compiler revision `clang-r584948b`, its project commit and compiler entry hash are recorded in [dependencies.lock.json](dependencies.lock.json). The native build uses an existing frozen `libandroid.so` link reference, SHA-256 `ce601e9536fb971a53bcdf17acd0bf25ee0ac54b1c4e03f83904514667bfb25e`. Its provider ELF dependency check is disabled by the inherited engine-only build path, and installed-runtime compatibility was not established by that build-time check. Later owned-runtime qualification is documented separately; it does not prove every provider/application combination. This limitation remains explicit.

## Recorded builds and limits

The actual Android engine hashes are:

- R15: `a770eda38e27d072f10568b7dee164a429f9eb05261667f7cb3c6f1c10e0d535`.
- R16: `c8b9bae4466d4f66525fdef6bcec140b29612581efeb6ceb621f96e17277d26d`.

R16 reused the verified output cache while preserving the separate frozen R15 source and artifacts. The engine and complete host-test binaries were rebuilt. This was an engine-only build, not a full Android runtime rebuild.

With the exact reconstructed builder and a separately prepared, verified AOSP workspace, the recorded command shape is:

```sh
DROIDLOOM_NATIVE_BRIDGE_SOURCE=/absolute/path/to/frozen-teto-source \
  /absolute/path/to/droidloom-update \
  --source /absolute/path/to/frozen-builder --jobs 2 \
  native-engine-build --work /absolute/path/to/prepared-aosp-work \
  --tests --out /absolute/path/to/engine-out
```

The prepared workspace, frozen baseline link reference, full host environment and earlier focused-test provider preparation are not distributed. Their available pins and missing-input boundaries are enumerated. Public source reconstruction is verified separately from a clean independent Android binary rebuild, which is not claimed.

The candidates retain the observed ELF dynamic contract: seven needed libraries, the same SONAME, 1,114 exported symbols and 245 undefined symbols. That comparison is necessary evidence, not runtime acceptance. The final isolated three-arm owned-native contract passed and R16 was subsequently activated in Main. [Qualification sources and evidence](qualification/README.md) preserve expected negative controls, lifecycle attribution, cleanup and sampling limits. Fresh real App business flows remain a separate gate.

## Licenses

The translator and its per-file notices retain **Apache-2.0**, with the original LICENSE and NOTICE. The separate DroidLoom builder retains **GPL-3.0-or-later**, with its notice, complete GPL text and third-party scope under `builder/`.
