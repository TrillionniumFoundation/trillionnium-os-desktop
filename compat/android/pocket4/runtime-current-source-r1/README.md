# Complete current producer source and fresh CI

This packet reconstructs one complete producer tree containing the cumulative
Launch, MAC, task-control, selected-lock, Settings, Profiling, SMS and MMS work,
plus the boot-property, actual execution-state and source-recipe repairs below.
It contains ordinary source and reproducible host validation. It does not
contain an Android image, an APK collection or a production runtime acceptance.

## Exact current source

| Identity | Value |
| --- | --- |
| Committed source parent inside the baseline archive | `61a38baa745483fbfb757466a1cf352febc20552` |
| Parent Git tree | `db6249e80209abeda8000eeced6d045a1d57e0a2` |
| Previous complete source tree | `c386679ac5fdc96eeaa424477435cd3ac09ce764` |
| Current complete source tree | `ac099a3921615b7bec854dbe2272e3fa96fdf32c` |
| Current source files / bytes | 2,287 / 42,311,114 |
| Baseline archive members | 2,224: 2,222 source files, manifest and original commit body |
| Baseline archive SHA256 | `7ab244365184ef670c244b6a0ed75857c6f942897f3fc59c00e6375e76f51816` |
| Complete cumulative overlay | 115 path bodies / 564,452 compressed bytes |
| Overlay SHA256 | `c24b66f32ed9dbb4699d0f72d227868aa94cf8c6363b25f9940cc1c6c6502233` |
| Expanded overlay bytes | 4,433,920 |
| Expanded overlay SHA256 | `80a4b17c3473ba38f15144534c1e0226b2858a6c9cfd746be035ac3029ef0a11` |

The public wrapper commit is distinct from the source parent and reconstructed
producer tree. `verify.py` checks every parent body, mode, Git blob and tree,
then all 115 before/after rows and complete overlay bodies. The final tree
includes exactly 2,287 files. `source_commit` remains null because the
producer is represented by a verified cumulative overlay. The input manifest
awards no build or runtime credit. All 42 Rust files changed by the new runtime
and official-GSI increments passed the pinned Rust 1.93.0 formatter check.

`SOURCE-OVERLAY.tar.xz` stores canonical USTAR postimages and a complete manifest
without JSON base64 expansion. The verifier rejects extensions, aliases, links,
special members, unlisted bodies, nonzero padding, concatenated frames and
changed preimages or postimages. The original single-frame 5 MiB expansion and
64 MiB decoder-memory bounds remain unchanged. The external inventory and
source-integrity gate pin the compressed byte count and SHA256.

## Repairs

### Official CP3A binary inputs and independent vendor production

The image preparer holds and verifies the complete official CP3A.260905.010
archive and preserves its system, reference vbmeta and build properties byte
for byte. Its separate vendor-input preparer checks 29 actual original
references, including ART/NNAPI CAPEX layers, without using CP2A replacements.
Actual preparation succeeded for the official 1,237,475,685-byte archive and
all 29 references. These observations establish input identity only.

The new strict `official-gsi-vendor-build` command uses two fresh normal outputs:
an original Soong NativeBridge distribution followed by vendorimage, secilc and
checkvintf. It retains the exact full651 source lock, `user` variant, strict
Soong dependency checks and all neverallow checks. The checked translator and
ARM64 interpreter data are scoped to vendor. Stock CP3A system/ART/APEX bytes
are unchanged. Input provenance and source provenance remain distinct; no
source-equivalence label is manufactured. Both actual Android builds and
combined policy/VINTF acceptance remain required.

### Original-init execution inputs and retained activation ownership

The CP3A execution selection is bound to the exact original system and init.
Its fixed capability set is scoped to the owned subordinate user namespace,
with all six namespace owners, exact ID maps, the five capability masks,
NoNewPrivs and PDEATHSIG checked. It cannot select arbitrary masks or grant
initial-namespace administration. Actual `/dev` observation now inventories
all entries under the held executed root; fresh-device creation still uses
its original finite whitelist.

The activation path retains one runtime owner through its authenticated
listener, original linkerconfig broker and complete retirement. Separate
bounded writable `/apex` and `/linkerconfig` roots retain their exact labels,
noexec/nodev/nosuid flags and original inode/mount identities. The original
CP3A linkerconfig payload and the reproducibly built static trampoline have
complete code and metadata pins. Two independent trampoline builds matched;
that does not mean the original linkerconfig has executed.

The fixed query producer reads cmd, toybox, app_process64 and content.jar from
the same held official system. Original executable files retain their actual
0:2000 ownership, while the JAR remains 0:0 and nonexecutable. This repairs the
previous all-root-group rejection without changing original files. No query
or Android execution is claimed by input preparation. Actual APEX activation,
init namespace transitions, task-profile acceptance, same-epoch MAC decisions
and the final execution-contract type still require their genuine providers.

### Boot property reads survive legitimate concurrent updates

The prior reader could reject a torn `sys.boot_completed` snapshot before
checking whether Bionic was still publishing its value or trie node. Two
real-file regressions fail against that original algorithm. The updated
reader makes at most three observations under the caller's original deadline,
checks allocation headers and file custody, and re-reads the small property
leaf between explicit serial observations. A changed or dirty value remains
non-ready; a stable malformed property remains rejected. No property is
written and no boot deadline is extended.

The fixed implementation passes ten focused cases, including actual file
interleavings, a concurrent writer, bounded retries, malformed values and
changed custody. Publication ordering was checked against the locked
[Bionic source](https://android.googlesource.com/platform/bionic/+/06356e41c5ed7b12220b24c05ba4fdb873b126a7/libc/system_properties/system_properties.cpp).
Seven of these cases are new ordinary supervisor catalog entries.

### Observe the original init's actual kernel execution state

`PreparedExecution::observe_init` now retains the five capability masks,
NoNewPrivs and seccomp mode read from the original init witness's held proc
directory. Fixed `openat("status")` reads require procfs, a bounded complete
status, the original leader PID, two equal observations and the original
witness's generation, PIDFD, namespace and executable revalidation. The
opaque observation remains on the same thread and is rechecked by
`ObservedExecution`.

Six new cases cover a real ordinary child, a wrong PID, a reaped child,
forged filesystem input, malformed fields and the existing NNP/seccomp
boundary. Observing a capability mask does not approve an Android capability
profile. `AndroidUnqualified`, the uninhabited final-contract type and
`ExecutionAdmission::acquire` remain unqualified until their actual providers
are complete. No new execution, namespace or permission mechanism is added.

### Repair the current frozen-source recipe

`frozen_pair_recipe` now reads the actual current645 lock and Native profile
location. It preserves the complete earlier validation chain and adds only an
exact append-only layer for reviewed project and sparse-path suffixes. The
complete Native plan retains its existing 656-project and 336-sparse-path
bounds. A current645 input produces no source delta.

Nine example regressions pass. A local behavior check also ran the real CLI
with explicitly synthetic source receipts, applied its 646-project plus one
sparse-suffix patch to an independent copy, and compiled and ran one Native
profile and three existing pair-source controls. Those synthetic inputs
prove generator behavior only; they are not original upstream receipts,
source-closure evidence or an Android build. The recipe still emits a detached
patch and never activates it or changes its input repository.

## Exact fresh CI scope

The runner reconstructs this source into a new directory and uses a fresh
Cargo target. Metadata and exact catalogs define 28 workspace packages,
49 ordinary harnesses, 1,385 listed cases and 19 normal release binaries.
The current increment adds 37 ordinary names: 18 supervisor, 9 image,
6 runtime-inputs and 4 updater cases. These names were read from the actual
newly compiled harnesses. Every old case and all thirty ignored names remain
present. Catalog listing is separate from execution. Historical tests, binaries and component runs receive
no fresh credit.

| Execution group | Required result | Bound |
| --- | --- | --- |
| Explicit updater cases | 64 ordinary cases | 60 seconds per exact name |
| Remaining updater catalog | 431 ordinary cases; 1 ignored | 300 seconds |
| Other 48 harnesses | 860 ordinary cases; 29 ignored | 300 seconds per harness |
| Normal release builds | 19 fresh binaries | 900 seconds per package batch |
| Workspace examples | 3 fresh binaries, mains never executed | 900 seconds |
| Frozen recipe example harness | 9 exact ordinary cases; no ignored cases | 300-second compilation, 60-second execution |
| Documentation targets | 20 actual library targets, 0 doc cases | 180 seconds per target |

The catalog total is **1,355 ordinary cases and 30 ignored cases**. The nine
recipe example cases are recorded separately. Each of the three normal
example binaries and the separate recipe test ELF is joined to its actual
source metadata and compilation interval. The recipe's exact and ignored
catalogs are read from that ELF; its complete identity is checked before and
after execution. The CPU placement and notification-service example mains
are never run. Zero-case rustdoc output must still contain a complete
successful terminal; twenty target commands do not create twenty test cases.

Every command uses the original runner's owned PIDFD, descendant retirement,
complete streams and cleanup checks. Cargo uses one job and tests use one
thread. The two-CPU affinity leaves at least two logical CPUs reserved. The
whole runner retains its **5,400-second deadline**, including final source
and artifact checks. Missing process-observation support or an incomplete
child retirement fails the job. The exact source bookend must still match.

The thirteen previous verifier controls are retained, with two new strict
USTAR framing controls for fifteen total. The runner keeps all nine
original controls and adds two for ordinary example/test-ELF locations and
Cargo hardlink aliases, for eleven total. The alias control covers both
plain and hyphenated target names: Cargo preserves the public binary name
and uses the underscore-normalized crate name for its hashed hardlink. The
original inode, full identity, exact parent and complete link count remain
required. These host controls are separate
from the Rust counts. On a host without `/proc/self/task/*/children`, the four
original actual-child controls fail; that host cannot qualify this full job.
They are not skipped or replaced with simulated success.

The final report records example binaries, the nine example tests and twenty
documentation commands separately; doc test cases remain zero. It keeps
`full_workspace_qualified`, `runtime_qualified`, `production_ready`, Android
build/start counts and inferred positive hardware branches false or zero.
The thirty ignored tests and hardware-specific positive branches remain
outside this ordinary host result.

## Source and runtime boundaries

The earlier SMS/MMS, MAC and selected-lock corrections remain in the complete
source. Their old component evidence remains bound to its original source
and run. The normal Android producer still requires its strict user build,
unchanged original dependency and neverallow checks, original APEX/linker
inputs and actual image/runtime acceptance. CP2A sources are not relabeled as CP3A. The official-GSI route preserves the
original binary system and separately qualifies its vendor; it does not need
a fabricated full CP3A source-equivalence record. Original libvintf and the
202604 matrix require the 6.18 kernel family. A 7.0 kernel is not a match.

The user's current application scope is the separate
[39-app release scope](../current-app-acceptance/RELEASE_SCOPE.md): TextNow,
TextFree and Uber Rider are explicit unverified exclusions. This packet gives
no app freshness, APK signing, installed-version, Play eligibility or business
acceptance credit. Old 42-app records retain their original meaning.

The [R36 storage-owner source packet](../storage-r36-owner-source-r1/README.md)
is an independent ordinary source correction. Its actual owner/CAS ROOT slot
remains unresolved; passing either CI component cannot admit storage, Full-B
or an Android deployment or authorize deletion of a working generation.

## Host preparation and reproduction

Use a disposable Ubuntu 24.04 amd64 host with Python 3, the pinned Rust 1.93.0
toolchain and at least four allowed CPUs. The host must provide Linux PIDFD,
`/proc/self/task/*/children`, Unix sockets/SCM_RIGHTS, private D-Bus, SysV
fakeroot and ordinary execute-enabled temporary storage with working links,
permissions and nanosecond timestamps. Do not set `RUST_MIN_STACK`.

The unchanged `prepare_ci.sh` installs recorded host development/test
packages and builds the pinned Debian-published EROFS 1.9.4 source in a new
private prefix. Its source archive is 273,489 bytes with SHA256
`7d135aa2550326a5acf20f53c518aea5a8900015ce50700044e40f818c31dd80`.
The preparation retains its 1,800-second deadline, original process cleanup,
LZ4HC/xattr feature checks and tool identities. It does not build or install
Android. Ordinary ext4/EROFS fixtures remain private synthetic images, not
production image acceptance.

Obtain `CURRENT_SOURCE_INVENTORY_SHA256` from the workflow at the exact
reviewed public commit. This external pin authenticates the complete
`FILES.sha256`, including `EXTRA-TARGETS.json`.

```bash
set -euo pipefail
capsule="$PWD/compat/android/pocket4/runtime-current-source-r1"
: "${CURRENT_SOURCE_INVENTORY_SHA256:?use the exact reviewed workflow pin}"
: "${RUNNER_TEMP:?use an absolute private temporary directory}"
printf '%s  %s\n' "$CURRENT_SOURCE_INVENTORY_SHA256" "$capsule/FILES.sha256" | sha256sum --check --status
(cd "$capsule" && sha256sum --quiet -c FILES.sha256)
python3 -I -B "$capsule/test_verifier.py"
python3 -I -B "$capsule/test_runner.py"
python3 -I -B "$capsule/verify.py" \
  --inventory-sha256 "$CURRENT_SOURCE_INVENTORY_SHA256" \
  --output "$RUNNER_TEMP/current-producer" \
  --report "$RUNNER_TEMP/current-source-replay.json"
bash "$capsule/prepare_ci.sh" --work "$RUNNER_TEMP/current-dependencies"
python3 -I -B "$capsule/run_ci.py" \
  --inventory-sha256 "$CURRENT_SOURCE_INVENTORY_SHA256" \
  --producer "$RUNNER_TEMP/current-producer" \
  --work "$RUNNER_TEMP/current-ordinary" \
  --report "$RUNNER_TEMP/current-ci.json" \
  --erofs-prefix "$RUNNER_TEMP/current-dependencies/erofs"
```

All destination paths must be new. The runner removes ambient compiler,
Cargo/profile, pkg-config, preload, library and test-branch overrides. It
records a locked dependency fetch before using locked offline builds.
The workflow preserves complete reports and command streams on failure and
only preserves the nineteen normal release binaries after overall success.
Cargo caches, target directories, operator journals and APKs are excluded.
A passing component cannot override a failed command, expired deadline,
changed source or unretired child.
