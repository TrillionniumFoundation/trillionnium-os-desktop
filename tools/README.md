# Tools

## Main workflows

| Tool | Purpose |
| --- | --- |
| `droidloom-package` | Build binaries and pacman packages in rootless Podman; test package lifecycle in a disposable container. See the [package guide](../packaging/arch/README.md). |
| `droidloom-update` | Rust source builder and transactional developer installer. Supplies the package builder's Android build and assembly implementation. See its [guide](droidloom-update/README.md). |
| `droidloom-source` | Materialize pinned sparse AOSP sources; a library dependency of the updater. |
| `droidloom-image` | Prepare the pinned Android base or the separate official CP3A GSI binary; a library dependency of the updater. |
| `droidloom-gapps` | Import a local LiteGapps archive, derive optional raw ext4 images and build a pacman data package. See [optional Google apps](../docs/BUILDING.md#optional-google-apps). |
| `droidloom-mesa` | Prepare pinned Mesa sources and patches; a library dependency of the updater. |

The package builder is the distribution entry point. The source updater is an
alternative developer installation; it cannot overwrite a pacman installation.
Do not assemble a preview from unrelated component builds.

### Official CP3A GSI binary input

The selected official-GSI route uses the unchanged CP3A.260905.010 / 16176746
system image and a separately built production vendor. Preparing that official
binary does not require claiming that the public CP2A source tree is CP3A.
The complete source-built four-partition route keeps its independent reviewed
source/ART/APEX coherence gate.

Download the original x86_64 archive linked by the
[official Android 17 QPR1 release page](https://developer.android.com/about/versions/17/qpr1/gsi-release-notes).
The reviewed archive is 1,237,475,685 bytes with SHA256
`81e37ae9e9280497c92fbda758b998a7dfab91ab9de000021622afa868a43b70`.
Then prepare it locally:

```sh
cargo run --locked -j 1 -p droidloom-image --release -- prepare-official-gsi \
  --archive "$OFFICIAL_GSI_ZIP" \
  --output "$NEW_GSI_DIRECTORY"
```

Both paths must be absolute and unaliased, the archive must have one hard link,
and the output must not exist. The command has a 180-second preparation bound,
reads the complete original archive before and after extraction, and checks each
member's exact expanded bytes and hash. Kernel-enforced atomic no-replace
publication preserves a concurrently created destination. No root privilege,
Android source checkout, external unpacker, image mount or device action is used.

The output contains the original `images/system.img` and original `build.prop`
and `vbmeta.img` under `provenance/`. The system image is raw ext4, 2,294,853,632
bytes, SHA256 `dc781249bb4724b7a0777e5077321b84576db46f61abb4b9086b81077bfd0ab4`.
Its embedded `/system/product`, `/system/system_ext`, and 38 APEX/CAPEX containers
remain inside that same unchanged image. The compiled
`android/manifest/official-gsi-x86_64.json` profile records their actual hashes and
the original init, framework and policy-interface inputs. Neither an edited
source-lock file nor an environment-selected build ID can choose different
input bytes.

`official-gsi-manifest.json` uses a distinct binary-input schema and cannot stand
in for a source-built product receipt or runtime admission. The reference vbmeta
is retained for provenance; this step does not verify its signing chain or install
it as a host boot policy. The GSI has no vendor contents or Droidloom components.
The separately built vendor still needs the strict normal user build, original
neverallow checks, actual VINTF and combined SELinux-policy compatibility against
this GSI, applicable linker and NativeBridge ABI checks, then fresh boot and app
acceptance. CP2A framework, ART or replacement system files receive no permission
to join this official binary cohort through the preparation command.

### Independent vendor for the official GSI

The separate vendor route consumes the complete unchanged GSI and 29 fixed
build references: 28 original x86_64 ELF libraries and its original framework
resource APK. ART and NNAPI are CAPEX in this release. The read-only preparer
checks the outer container, decompressed original APEX, ext4 payload and each
final file against the compiled `official-gsi-vendor-inputs.json` profile:

```sh
cargo run --locked --release -j 1 -p droidloom-image -- \
  prepare-official-vendor-inputs \
  --system-image "$OFFICIAL_GSI/images/system.img" \
  --output "$NEW_CP3A_REFERENCES"

cargo run --locked --release -j 1 -p droidloom-update -- \
  --source "$DROIDLOOM_SOURCE" --jobs 8 official-gsi-vendor-build \
  --work "$ADMITTED_WORK" --out "$FRESH_VENDOR_ATTEMPT" \
  --system-image "$OFFICIAL_GSI/images/system.img" \
  --references "$NEW_CP3A_REFERENCES"
```

The first command needs normal `debugfs` and `unzip` tools and no mount or
administrator privilege. It takes a fresh absolute output, preserves the input
image, bounds extraction to 180 seconds, and emits no runtime qualification.
The second runs as the admitted non-root builder under the ordinary package and
source locks. Its `aosp-source` must be absent or match the exact production651
materializer manifest and lock; an old partial source tree is not implicitly
accepted. The source release remains `cp2a`, variant `user`, with strict Soong
dependencies and `SELINUX_IGNORE_NEVERALLOWS=false`. The binary reference and
source provenance are recorded separately.

Phase `native` invokes the original Soong `ndk_translation_package` on explicit
host and ARM64 guest modules. Its actual distribution is checked for paths,
architectures, unique providers, versioned host imports against the original
CP3A references, and guest DT_NEEDED closure. Phase `vendor` builds
`vendorimage`, `secilc`, and `checkvintf` normally using that checked distribution.
Host translators retain normal prebuilt ELF checking. Original CP3A libraries
are non-installable link references; they never become vendor runtime providers.
ARM64 files are interpreter input data under
`/vendor/etc/droidloom/nativebridge/guest`, with the source guest loader and
guest linker projected to that location. Host engine and proxies install under
`/vendor/lib64/droidloom/nativebridge`. Vendor properties use the stock
`dalvik_config_prop` and vendor CPU ABI namespace; the engine's own option has
an explicit vendor property type. No binfmt registration service is packaged.

The two phases use distinct fresh outputs under the single attempt directory.
Admission must budget both outputs, the exact full651 source, pinned Mesa source
and host tools, Python dependencies, the 2.295 GB GSI and 51.6 MB link references.
The normal rootless builder supplies the tool packages from
`packaging/arch/Containerfile`, plus root-owned `readelf`, `debugfs` and `unzip`.
Cap compiler jobs at admitted capacity and leave at least two host CPUs free;
the command does not claim a resource admission or change cgroup limits.

The final receipt means only that both ordinary user builds returned success and
the final vendor retained the checked native binaries and properties. Production
still requires original-GSI plus vendor VINTF and combined policy checks, actual
kernel/config matching, the host linkerconfig generation with the single narrow
vendor bridge directory, NativeBridge callback ABI checks, and fresh Android/app
acceptance. CP3A's FCM 202604 matrix requires the 6.18 kernel family; a numerically
newer 7.0 kernel is not a match. Neither matrix/FCM nor the full source-build gates
are changed by this route.

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
| `droidloom-keystore-metadata` | Independent Rust host workspace for redacted cold-DB audits and new clone-only metadata experiments; see [Keystore metadata validation](../docs/BUILDING.md#offline-keystore-metadata-audit-and-clone-experiments). |
| `droidloom-inspect.rs` | Optional read-only diagnostics for the development workstation's u1000 cell; fixed `features`, `properties`, and `configuration` modes. |

The Rust updater and package workflow own x86_64 installation, init projection
and Mesa builds. New orchestration should be Rust; legacy scripts are not a
template for new tooling.

### Frozen Native source recipe

`droidloom-source`'s `frozen_pair_recipe` example prepares a detached patch from
the exact current 645-project Native lock. Supply an independently reviewed
append-only lock and an original superproject receipt, each with its separately
recorded SHA-256. The receipt contains `commit`, the original recursive Git tree
text in `gitlinks`, original `.gitmodules` text in `gitmodules`, and the two raw
text hashes in `gitlinks_sha256` and `gitmodules_sha256`. Deriving these texts
from the proposed lock does not provide independent upstream evidence.

```sh
cargo run --locked -j 1 -p droidloom-source --example frozen_pair_recipe -- \
  --repo "$SOURCE_REPO" \
  --frozen-manifest "$FROZEN_MANIFEST" \
  --expected-manifest-sha256 "$REVIEWED_MANIFEST_SHA256" \
  --superproject "$SUPERPROJECT_RECEIPT" \
  --expected-superproject-sha256 "$REVIEWED_SUPERPROJECT_SHA256" \
  --output "$NEW_OUTPUT_DIRECTORY"
```

Choose a new output directory outside the input repository. The command reads
local inputs and runs `/usr/bin/diff` on its own output files; it performs no
network fetch, materialization, build, installation or device operation. It
rejects an existing output directory and any source-template or input hash
drift. Its complete-plan check retains the current Native limit of 656 projects
and 336 sparse paths per project; a wider profile needs separate code review.

The patch updates the lock, the ordinary-pair producer and
`droidloom-source/src/native_pair.rs`. It preserves every historical validator
and adds an exact suffix check before validating the current645 predecessor.
The default Audio and Production source profiles retain their scopes. An
identical current lock produces an empty patch. Review the patch and perform
the normal materialization and build gates separately; `recipe.json` grants no
source-closure, native-artifact or runtime qualification.

Run the local generator regression tests with
`cargo test --locked -j 1 -p droidloom-source --example frozen_pair_recipe`.
Their synthetic receipts test behavior and are not upstream source evidence.

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
