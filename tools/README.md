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
| `droidloom-ubuntu-fixture` | Independent Rust public-root capture, initialization, and bounded boot tool; see [Real Ubuntu qualification material](#real-ubuntu-qualification-material). |
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

## Real Ubuntu qualification material

`tools/droidloom-ubuntu-fixture` is an independent Rust workspace. It captures
reviewed public files from an installed Ubuntu root and creates a new private
qualification root. The capture/materialize/verify commands do not boot guests
or generate private state. Separate explicit commands initialize and boot a
disposable native root for real qualification. The production Cargo workspace
and lock are unchanged.

Build and run its focused synthetic tests with:

```sh
cargo test --offline --locked -j 1 --manifest-path tools/droidloom-ubuntu-fixture/Cargo.toml
cargo build --release --offline --locked -j 1 --manifest-path tools/droidloom-ubuntu-fixture/Cargo.toml
```

The real commands require existing administrator rights so they can read the
selected native kernel and preserve original ownership, capabilities and ACLs.
No privilege helper or sudoers entry is installed. Output and receipt parents
must already be new, root-owned mode 0700 directories. Every artifact and the
destination root is create-only; a failed partial attempt is not resumed or
silently removed.

Prepare a `droidloom.ubuntu-public-selection.v1` JSON object with `source_root`,
`audit_sha256`, `target_kernel_release`, `entries`, and explicit
`unresolved_requirements`. Each entry has an absolute in-root `path`,
`component`, and `origin`. Components are `native`, `public_config`,
`generated_public_cache`, and `snap_archive`; the last three require the exact
`expected_sha256` (`readlink` target bytes for a symlink). `expected_size` is
optional. A package/file availability audit is not itself a copy allowlist:
review public configuration paths before selecting them.

Native inputs are confined to public `/usr` files and usrmerge links. The
configuration allowlist is maintained in `src/paths.rs`. Real homes, account
databases, SSH host private keys, private TLS, NetworkManager connection keys,
Bluetooth/SSSD/Snap authentication state and Android data are rejected.
Ancestor directories carry metadata only. They cannot be used as regular-file
inputs. Every source component is opened relative to a pinned directory FD
with no symlink following; sources must be root-owned and not writable by
group or other. The manifest binds source device/inode, mode, UID/GID, link
count, size, mtime/ctime, content hash and selected privilege attributes.

The optional `kernel` object supplies `release`, `image_path`, `image_sha256`,
`config_path`, `config_sha256`, `module_manifest_path`, and
`module_manifest_sha256`. It accepts the original
`p4-normal-kernel-installed-module-manifest-v1` producer roster, checks every
module/index hash and size, and compares its entire regular-file set plus the
pinned config against the installed selected-release tree. Build/source links
are omitted without following them. A separate module output is mandatory
when this input is supplied. Native selection cannot smuggle in another
kernel's module tree. Module content identity does not assert cryptographic
signature verification; the independent signing receipt remains separate.

```sh
sudo -n /absolute/path/droidloom-ubuntu-fixture capture \
  --selection /private/work/SELECTION.json \
  --selection-sha256 "$P4_REVIEWED_SELECTION_SHA256" \
  --output /private/work/MANIFEST.json \
  --module-output /private/work/TARGET-MODULES.json
sudo -n /absolute/path/droidloom-ubuntu-fixture materialize \
  --manifest /private/work/MANIFEST.json \
  --manifest-sha256 "$P4_CAPTURED_MANIFEST_SHA256" \
  --destination /private/work/root \
  --receipt /private/work/MATERIALIZED.json
sudo -n /absolute/path/droidloom-ubuntu-fixture verify \
  --manifest /private/work/MANIFEST.json \
  --manifest-sha256 "$P4_CAPTURED_MANIFEST_SHA256" \
  --destination /private/work/root \
  --receipt /private/work/VERIFIED.json
```

JSON is hashed and decoded from the same bounded buffer. Source identity is
checked before and after regular-file reads. Copying refuses content growth
past the reviewed size, preserves hardlinks, and reads back every destination
file, symlink, mode, owner, capability and ACL. Verification also rejects
unexpected paths. Standalone verification checks the declared in-root hardlink
relationships; it does not prove that an existing inode has no additional
hardlinks outside the verified root. Materialization creates its hardlinks
inside the new private root only. SELinux labels are intentionally not inherited
from the source host; the target joined policy must supply and validate its own
labels.

`materialization_complete=true` means the selected public bytes and metadata
were copied and read back. All receipts retain `guest_qualified=false` and
explicit requirements for real distribution account/machine-id/hostkey/cache
generation, fixture network configuration, Snap state/assertion import, native
AppArmor generation, SELinux roles and PAM contexts, cold service/login
execution, and selected-kernel device qualification. No missing sensitive
configuration is replaced by a successful placeholder. Numeric service UID/GID
metadata must agree with the later fresh fixture account mapping.

Keep manifests, public root trees, module/Snap payloads and logs outside Git.
Only source and this maintained invocation guide belong to the repository.

### Native initialization and shared-kernel boot

The explicit `prepare-native`, `prepare-boot`, and `boot` commands continue
from the public material above. Their JSON configurations are read from one
bounded SHA-256-checked buffer. A `FilePin` contains an absolute `path`,
`bytes`, and `sha256`. All work is restricted to a new child directory of
`/var/lib/droidloom-qualification`; the enclosing work remains root-owned
0700 even when the filesystem that will become guest `/` has mode 0755.

`prepare-native` accepts schema `droidloom.ubuntu-native-boot-plan.v1`,
`work_directory`, the pinned `fixture_manifest`, the independently verified
`fixture_root`, and `native` inputs defined in `src/boot_native.rs`. It first
verifies the public root, makes an independent copy, and verifies that copy.
Public passwd/group inputs preserve the reviewed numeric service identities.
The ordinary Ubuntu sysusers, firstboot, tmpfiles, ssh-keygen, and systemctl
programs then initialize fresh accounts, locked passwords, machine identity,
host keys, and unit links. They operate on the separate root. Host passwords,
private keys, home contents, connection credentials, and Snap authentication
state are not imported. Fresh fixture autologin, DHCP, root-filesystem UUID,
and optional SSH keys are explicit configuration changes in the receipt.
The public Snap archives and original read-only mount units are material only;
registration and generated profiles still require real runtime acceptance.

`prepare-native` can also accept an optional `public_packages: FilePin`. This
selects schema `droidloom.ubuntu-public-packages.v1`: `packages` contain the
original package name, version, architecture, pinned `.deb` archive and pinned
intake `provenance`; `dependency_audit` binds the complete selected package set;
`retained_originals` is an explicit, narrowly checked list. This layer is applied
after the complete public clone is verified and before native initialization.
It supplements missing public package content without claiming the fixture's
dpkg database has been installed or updated.

The ordinary `dpkg-deb` reader inspects the exact copied archive's metadata and
emits its data tar. The Rust reader accepts the reviewed GNU/POSIX ordinary
members and package-local hardlinks, checks every header, bound, termination,
path and permission, and rejects extensions, devices, traversal and private
state. It does not extract a tar namespace or run maintainer scripts. Package
bytes and paths must match their retained acquisition receipts; this is a
binding to the earlier APT intake, not a fresh signature-verification claim.
Original public configuration is limited to the existing allowlist and the
explicit stock initramfs/Plymouth/braille/microcode/kernel-hook paths in
`src/boot_packages.rs`. The three public package state directories are created
empty; no live state is copied. Target kernel modules remain a separate input.

Every existing member must match before new content is written. The one
reviewed exception retains the original `fuse3` `fusermount3` installation's
04755 mode while the same-byte archive member is 0755. It requires the original
manifest's exact hash, size, UID/GID, mode and single-link identity plus the
specific package digest; it is neither a general permission override nor a
change to the host. Newly introduced hardlinks retain their actual shared
inode and exact group size. All members are read back, again after native
initialization and before boot preparation. The pinned
`public-packages/SUPPLEMENT-VERIFIED.json` reports the new, matched and retained
members, the original package inputs and the still-unqualified state. Missing
dependencies or conflicting files fail; a fresh root and its diagnostics remain
available for review.

`prepare-boot` accepts schema `droidloom.full-ubuntu-boot-plan.v1` and the
pinned native receipt, normal host manifest/archive, kernel, ordinary base
initrd, `initrd_tools`, Android release inputs, label tools, and a 64–96 GiB sparse root-image
bound. The normal ustar export is checked against its exact member set,
content hashes, ownership, modes, and protected empty calibration directory.
The four Android images, runtime declaration, and device bank must identify
one normally published cohort. Data is either fresh ext4 or a further
independent copy of the explicitly admitted working-data receipt; the original
user-data paths are rejected. Calibration and a supplied normal five-file MAC
release are mutually exclusive.

For a normal kernel-first v2 runtime, `android.query_inputs` is required. It
maps exactly `cmd-original`, `toybox-original`,
`contacts-app-process64-original`, `contacts-content-jar-original`, and `toolbox-original` to
the five published `FilePin` inputs. The fixture shares the production
`production_query_input_profile.rs` and original-init identity constants.
It parses the original runtime bytes with duplicate/unknown-field rejection,
binds schema, cohort, complete CP3A system and original init, and checks all
five role declarations and external pins before importing query bytes. A v1
runtime accepts neither query declarations nor query input pins.

The new copies are root:root, single-link, mode 0555 for the four executables
and 0444 for the JAR, with no file capability or POSIX ACL. Their final guest
paths are `/var/lib/droidloom/runtime-cohorts/<runtime-sha256>/images/<fixed-name>`.
After the ordinary Linux setfiles traversal, the fixture applies and reads
back the original stock role labels: system_file, toolbox_exec, zygote_exec,
system_file and toolbox_exec. The actual generated ext4 is then read independently for
every complete file, inode type/mode/owner/size/link count and label. Its xattr
inventory must contain exactly that original SELinux label. This proves the
sealed input copies survived root-image construction; it does not prove query
execution, Android readiness or application acceptance.

A new shared-kernel candidate can supply `replacement_kernel`: a complete,
separately captured/materialized target-module fixture, the normal module
manifest, the matching image, and its matching ordinary initrd. Only the old
module tree inside this disposable native root is retired to its private work
directory. The live host kernel, modules, and boot configuration are untouched.

`initrd_tools` identifies the reviewed `initramfs-tools-core` package with
`package_name`, `package_version`, and a pinned public `hook_functions` file.
That exact support file is added only to the new qualification root, or reused
when the public package layer already supplies exactly the pinned bytes,
root ownership, 0644 mode and single-link identity. The
ordinary exported initramfs hook runs in a read-only namespace rooted at the
complete fixture, so dynamic dependencies are resolved from its actual libraries.
Construction sets the normal umask 022 explicitly. The same distribution
`copy_exec` function also copies the selected `libselinux.so.1` and its real
dependencies, since the project hook's own ELFs do not necessarily link it.
Every copied regular dependency and resolved alias is compared against the
fixture. The finished initrd follows the kernel's documented concatenated-newc
format. The actual final file is read again through one held descriptor: its
base prefix and appended compressed member must match their producer hashes,
alignment must contain only zero bytes, and no trailing data is accepted.
The stock unpacker then extracts that actual final member, since some
distribution versions silently stop after the first compressed member in a
concatenated image. Every member, file/alias byte sequence, mode and owner is
read back. The base's four usrmerge aliases must match the fixture, and the
layer must preserve existing directory permissions without ambiguous hardlink
or file-type collisions. Actual target-kernel unpacking remains a separate
runtime gate. The format is specified at
https://docs.kernel.org/driver-api/early-userspace/buffer-format.html.
A base that already schedules Droidloom custody is refused
to avoid invoking that entry twice. A material test with an older kernel/initrd
does not establish compatibility with a newer kernel candidate.

An explicit `libselinux_candidate` can select the narrow native exec-attribute
candidate for the reviewed `libselinux1` 3.9-4build1 original. Its fields are
the pinned `declaration`, `package`, `source_commit`, `source_dsc`,
`source_debian_archive`, and `source_orig_archive`. The current candidate is
3.9-4build1+p4lsmexec1 on amd64. Admission checks actual Debian metadata, the
source `.dsc` archive pair, the exact quilt patch against its maintained Git
receipt, normal build/API evidence for the stripped package member, and an
independent comparison of all 247 exported ELF symbols/version nodes, SONAME,
and dependency names. Only the regular
`usr/lib/x86_64-linux-gnu/libselinux.so.1` member is selected from the data tar;
the tar namespace and maintainer scripts are never installed. The original
library must match the public fixture manifest and its known bytes. It is
preserved separately before an atomic replacement in this fresh root. The
usrmerge lookup and final inode/hash are read back. The fixture's dpkg status
is unchanged and the receipt calls this a candidate overlay. A physical
installation still requires the normal package path and independent runtime
qualification. The original host and public fixture remain unchanged.

The ordinary exported initramfs hook constructs the custody layer. The
distribution's setfiles and matchpathcon tools apply the selected file-context
rules; a separately pinned matching producer libsepol handles policy
capabilities that an older distribution library cannot decode. No policy
capability is removed. Missing labels fail admission. Root-image creation
checks critical SELinux labels and every nonempty native capability/ACL attribute
through independent debugfs reads. Critical inodes and all selected privileged
mode or ownership objects also receive actual type, mode, UID/GID and applicable
file-size comparisons. A fixture-only journald configuration preserves the
actual native service journal without replacing the original journal service.

`boot` accepts schema `droidloom.full-ubuntu-run-plan.v1`, the pinned
`prepared` receipt, a short `run_name`, `cpus`, `memory_mib`,
`duration_seconds`, `network`, and optional `ssh_port`. It makes a distinct
working disk from the prepared image, preserves two logical CPUs, and bounds
the guest lifetime and log size. The shared kernel boots with SELinux enforcing
and AppArmor selected. SSH forwarding, when requested, binds only to loopback
on ports 50000–59999, with a known-host entry derived from the fresh fixture's
actual public host key. Original account keys are not consulted.

Every owned subprocess is placed in its own process group. Error returns stop
and reap the owned child; QEMU's ordinary power-down request retains a 45-second
grace period before a forced stop. QMP input has line, event-count and whole-call
time limits. `RUN-ENDED.json` uses `droidloom.full-ubuntu-run-ended.v1` and
includes the preserved source image pin/identity plus a complete pin for the
independent working disk. `RUN-FAILED.json` instead records the cleanup outcome
and retained paths, without inventing a complete working-disk pin after an I/O
failure. Neither receipt declares runtime acceptance.

```sh
sudo -n /absolute/path/droidloom-ubuntu-fixture prepare-native \
  --config /private/inputs/NATIVE-PLAN.json \
  --config-sha256 "$P4_NATIVE_PLAN_SHA256"
sudo -n /absolute/path/droidloom-ubuntu-fixture prepare-boot \
  --config /private/inputs/BOOT-PLAN.json \
  --config-sha256 "$P4_BOOT_PLAN_SHA256"
sudo -n /absolute/path/droidloom-ubuntu-fixture boot \
  --config /private/inputs/RUN-PLAN.json \
  --config-sha256 "$P4_RUN_PLAN_SHA256"
```

Preparation, successful process execution, a QEMU exit, and generated receipts
do not qualify the product. These commands retain `guest_qualified=false`
and `production_ready=false`. Evaluate the original persistent journal,
normal PID 1 service completion, MAC object/epoch checks, graphical session,
Android lifecycle, real working-data compatibility, and application gates
independently. Failed private attempts and their original diagnostics remain
available for diagnosis; the commands do not clean up the host or activate its
production services.

### Selected public APK material in a fresh normal guest

The optional `prepare-boot` field `public_apks: FilePin` selects a
`droidloom.public-apk-import.v1` object with three pinned inputs: `execution`
(the original `p4-selected39-execution-v3`), `selection` (the current
`p4-selected39-static-launch-inputs-v1`) and `source_receipt` (the complete
SDK37 material/signature handoff). Each pin contains `path`, `bytes` and
`sha256`. This field is accepted only for a normal guest with
`android.persistent_data=null` and `android.calibrate=false`.

The importer joins the complete 39-package roster and 65 original APKs across
all three records. Versions, signer sets, original paths, SDK37 verification,
one base plus the complete unique split set, per-session limits and the exact
three exemptions must agree. The source paths are the explicitly selected
public `.apk` files below `/home/alex/work`; no private Android data is read.
The retained signature receipt is source evidence, not a new signature or
runtime verification performed by this importer.

After normal host/Android import and before `label_root`, every original APK
is copied with held-descriptor identity checks, full hashing and independent
destination readback. The create-only destination is
`/var/lib/droidloom-public-apks/u1000/<sha256>.apk`. The normal public root
remains root:root 0755; `u1000` is 1000:1000 0700 and all payloads are
1000:1000 0400 with exactly one target hardlink. Existing public source
hardlinks are preserved without edits; every source's complete F9, including
its original link count, must agree before and after the whole copy and is
retained in the receipt. Symlinks, privilege attributes, foreign owners,
group/other writes, partial split sets and pre-existing destinations are
rejected. A failed import stops preparation and leaves no successful boot
receipt. It is not resumed or silently accepted as a partial selection.

The same directory contains byte-identical `selected39-execution.json`,
`selected39-source-selection.json` and `selected39-signature-receipt.json`.
The import object may also include `gate_registry`, a `FilePin` for the complete
original `pocket4-app-release-gates-v1` contract including its Firefox extension:
27,878 bytes, SHA-256
`0b21f963898308b082f3808dd48165c1397badd1fa8a753c3a766e135b3cb3c8`.
When present, the typed registry must retain all 46 original package entries,
all six common gates, every profile and the full selected-39 coverage. A changed
or weaker contract is rejected. Its original bytes become
`/var/lib/droidloom-public-apks/u1000/app-release-gates.json` through exactly the
same create-only copy, identity, ownership, label and readback checks. The
complete imported set is then 69 files; the original three-input form remains
exactly 68 files.

With that registry, `PUBLIC-APKS-STAGED.json.runtime_preparation_inputs` exposes
the actual guest `selection`, `source_receipt` and `gate_registry` pins and every
selected application's required gate IDs. These are only static prerequisites.
It contains no `main_qualification`, `expected_epoch` or preparation intent.
After the owned Android runtime exists, the ordinary UID-1000 user session can
create new flat, pinned evidence/intent files in the same public input directory;
the installed public client has read-only access under the existing policy.
Bind the actual Main evidence, daemon-observed physical epoch and selected
specification before `droidloom-applications --prepare-runtime-plan`. The later
live evidence is not part of the initial image's 68/69-file import receipt.

`PUBLIC-APKS-STAGED.json` records every source pin, destination and the existing
`droidloomctl --json install`/`install-multiple` argument vectors, with original
account signer blockers preserved. None of those commands runs during
preparation. Before later installation, bind the owned Main/runtime epoch and
inspect the current package; after any actual install, inspect the full
installed version/APK set. Uncertain commits require inspection before retry.

The normal label pass must produce exactly the public-root, UID directory and
public-input SELinux types. Root-image generation reads back every payload's
label, UID/GID, read-only mode and size through the existing ext4 checks, then
dumps and hashes all 65 APKs and the three or four declared provenance files
from the actual ext4 image. `ROOT-IMAGE.json.public_apk_readback` records those
complete byte comparisons. Staging and image construction retain zero installed apps,
`guest_qualified=false` and `production_ready=false`; the ordinary Android
installation and application acceptance contracts remain required.

### Normal material smoke checks without a guest

`verify-host-import` accepts schema `droidloom.normal-host-import-smoke.v1`,
a new `work_directory`, `host_manifest`, and `host_archive`. It exercises the
same strict USTAR importer in a small empty private root and reads back every
file and the protected empty StateDirectory. It does not run imported programs.

`verify-boot-materials` accepts schema `droidloom.boot-material-smoke-plan.v1`,
a new `work_directory`, `fixture_manifest`, `fixture_root`, `host_manifest`,
`host_archive`, `base_initrd`, `initrd_tools`, and `libselinux_candidate`.
It verifies and independently copies the complete public root, then exercises
the same importer, real candidate-package overlay and ordinary initrd builder.
Its explicit construction-only layout adds the four normal usrmerge aliases
and empty `/dev`, `/proc`, `/sys`, `/run` directories. It does not generate
accounts, copy Android userdata, produce a bootable root disk or start a VM.
All source files, modules and the original public root remain untouched. Its
`MATERIALS-VERIFIED.json` is only evidence for these material operations.

```sh
sudo -n /absolute/path/droidloom-ubuntu-fixture verify-host-import \
  --config /private/inputs/HOST-IMPORT.json \
  --config-sha256 "$P4_HOST_IMPORT_SHA256"
sudo -n /absolute/path/droidloom-ubuntu-fixture verify-boot-materials \
  --config /private/inputs/MATERIALS.json \
  --config-sha256 "$P4_MATERIALS_SHA256"
```

### Original-host working qualification and return

The working qualification consumes the actual returned first-once history,
the retained independent working data copy, and a newly admitted normal host
release. It preserves the selected shared kernel and both original Android
images. Its material plan is `droidloom.working-qualification-material-plan.v1`;
the normal source, full guest evidence, original-copy origin, current public
application materials, and source program are independently checked. An edited
receipt cannot recreate a live owner or make an old source cohort current.

These commands have different effects:

| Command | Effect |
| --- | --- |
| `prepare-working-qualification` | Admit materials and create private working boot/runtime sources. |
| `verify-working-publication` | Install the actual normal packages, publish runtime and boot files, exercise the data/selection/label transactions, and reverse them. It does not arm GRUB or reboot. |
| `run-working-qualification` | Perform one real working boot attempt, including automatic original-kernel recovery, a single one-shot GRUB arm, actual thaw, and one normal PID1 reboot request. |
| `recover-working-qualification` | Acquire a new original-kernel owner and finish the actual inverse after a working attempt. It does not recreate the previous owner from JSON. |

The first three are separate create-only attempts; do not run preparation and
then replay publication/run against the same already consumed workspace. Use
the newly selected normal producer and the actual complete material-plan SHA.
The physical run executes as root in the admitted
`droidloom-working-cold@<candidate-id>.service`, with the exact executable,
subcommand, `--config` path, and `--config-sha256` arguments. Its executable and
input must be protected absolute paths below
`/var/lib/droidloom-qualification`. A direct shell invocation, another service
name, a changed namespace, or a replacement program is rejected by the live
owner factory.

The real run publishes a separately owned recovery unit and its wanted link.
The unit selects the original kernel, calls the same normal producer's fixed
`recover-working-qualification` command, has a finite start budget, and runs
before the graphical and Android owners. Its two files are independent of the
twelve candidate runtime files and their seventeen-member directory/file
publication bound. Publication never replaces an existing recovery unit. Its
initial held transaction is retired after complete publication; subsequent
inverse operations freshly open the exact source-owned inode generations and
current parents.

The run keeps its actual cold owner and all four original/working image open
file descriptions through publication. It adopts a real GRUB observation even
when the command reports an error after taking effect. Unknown outcomes permit
read-only reconciliation, not another arm. Before requesting reboot it requires
the independent thaw report, the exact released groups, and retirement of the
held reaper pidfd. After release it never uses the earlier full-root snapshot
for inverse operations. The reboot command is issued once; later normal PID1
state/job reads distinguish an actual pending shutdown from a settled idle
manager. A request acknowledgement alone is not shutdown or qualification.

Fresh recovery first settles its current owned one-shot GRUB field, observes
actual boot retirement, and reacquires the four image locks and full original
image hashes. It restores complete original labels under a new finite freezer,
then restores boot files, the original data/metadata directory arrangement,
and runtime files. After actual thaw it runs the source-bound native and public
package inverses. A native package replacement of the named `systemd` binary
is accepted only through a completed normal command and a separate proof of
the still-running PID1 inode, body, pidfd, namespaces, and exact original named
package member. It then retires the owned recovery files and restores the
normal masks/writer requests.

The returned runtime evidence directories and their captured records stay at
their actual names while retirement readers hold them. The completion report
lists those retained paths explicitly; it does not claim they were deleted.
`WORKING-RETURN-COMPLETED.json` points to the actual return report. Both keep
`production_ready=false` and `application_business_accepted=false`: normal
package installation, a clean boot, a restoration test, or an acknowledged
reboot cannot substitute for the selected applications' actual acceptance
gates. Final activation and removal of retained evidence and obsolete cohorts
follow the same-candidate production acceptance.

### Independent EMPTY official Meituan diagnostic

The normal `prepare-native` / `prepare-complete-native` and `prepare-boot`
pipeline also has an explicitly separate diagnostic input. In the Android
inputs, set `persistent_data` to `null`, `calibrate` to `false`, and supply
`empty_meituan_diagnostic.official_apk` as the actual admitted original APK
`FilePin`. The only accepted APK is 64,632,545 bytes with SHA-256
`66e5d03668d4bcd34457539fe92c1284c1f4493e4d31cdfacb250d7b71fc9733`.
The producer copies those complete bytes to
`/var/lib/droidloom-qualification/empty-meituan-diagnostic/official.apk`
inside the separate root, as root:root mode 0400 with one link.

This branch accepts no data-image source. It creates new exclusive 8 GiB data
and 128 MiB metadata files, runs the reviewed normal `mke2fs` through held
descriptors, observes its actual child exit and pidfd retirement, and checks
both complete initial bodies. The fixed tool, formatting parameters, UUIDs and
reproduced full-image hashes live in `empty_meituan_contract.rs`. The runtime
independently repeats both full readonly comparisons before its first writable
open, loop or mount. It then retains a non-deserializable `FreshDiagnosticPair`
alongside the actual backing descriptors and lease. Neither a missing
`original_copy` field, a matching UUID, nor a saved diagnostic receipt creates
this capability. A changed initial image is rejected before mutable admission.

The Android fields belong to `prepare-boot`'s `BootPlan.android`; they do not
belong to the earlier native-root plan. Set `calibrate=false` only with the
same candidate's actual normal five-file `mac_release`, as required by normal
release admission. An unfinished host-stage or MAC release has no substitute
hash. Prepare a new native work root from the immutable complete manifest;
do not reuse another run's mutable native root or Android data pair.

The normal fixture CLI can derive each configuration without running it:
`plan-empty-meituan --config INPUTS --config-sha256 SHA --phase PHASE`.
The closed phases are `native`, `boot`, `run`, `collect`, and `verify`. Its
`droidloom.empty-meituan-input-plan.v1` input contains actual `FilePin` values
for `native_reference`, `boot_reference`, `collect_reference`,
`android_reopened`, and the executing `normal_producer`. `output_directory`
must be an existing root:root 0700 direct child of
`/var/lib/droidloom-qualification`; `native_work_directory` is a separate,
previously unused child. The old reference plans supply only their normal
public materials and tool selections. They supply no previous data pair.

`release` may be `null` during native planning. For boot planning it must
contain the new actual `host_manifest`, `host_archive`, `official_apk`, and
`mac_release` map with exactly `contract.json`, `manager-label.json`,
`policy.bin`, `policy-export.bin`, and `derivation.json`. The Android reopen
record must retain the exact whole bytes of all thirteen relocated normal
members. No placeholder hash, calibration policy, or earlier host stage is
substituted. The planner holds and checks the actual public source files and
writes each output with create-only semantics. Subsequent phases require the
previous normal producer's actual output and its exact input pin. A failed
generation keeps its existing files; planning does not overwrite or resume it.

Each output prints the actual new plan pin and the fixed normal command to
execute: `prepare-complete-native`, `prepare-boot`, `boot`, `collect-boot`, or
`verify-owned-guest`. It also prints `stage_seconds` and a bounded
`controller_budget`. The current source derives 8,700 seconds total: 300 for
admission, 1,800 each for native and boot preparation, 2,640 for boot (including
the complete observation and shutdown windows), 1,200 for collection, 900 for
verification, and 60 for retirement bookkeeping. An outer controller must
start one monotonic deadline before admission and bound every command by both
its stage allowance and the time remaining on that same deadline. It must
not reuse the earlier 3,000-second calibration controller or renew the total
between phases. An error or unknown mutator result stops forward execution;
collection may proceed only if a real normally ended guest is available.
Planning and printed budgets do not themselves start a guest, establish
process retirement, or grant runtime, business, or production acceptance.

After the normal shared-kernel Main is ready, the ordinary installed
`droidloom-empty-meituan-diagnostic.service` runs the exact no-argument
`/usr/bin/droidloomctl empty-meituan-diagnostic` entry. It is not automatically
enabled in the general host package. Only the explicit EMPTY preparation uses
normal `systemctl --root ... add-wants graphical.target` for this fixed unit,
then reads back that exact link and unchanged unit. The ordinary graphical
kernel command line and user-session setup remain in use. The source-pinned
host stage, enforcing policy and AppArmor package
must include this exact unit, its cgroup and fixed input path. Its actor and
accepted socket peer require the actual installed ELF, root credentials,
fixed invocation and unit, PIDFD, and both enforcing preparation roles. The
existing working-copy preparation peer is unchanged.

The observer dependency establishes its original Binder observer, not complete
Android readiness. The diagnostic obtains actual full Main custody from the
same authenticated peer. It repeats only the precise normal boot-incomplete
read response; a different error, expiry, changed peer or quarantine stops it.
The original 720-second entry deadline starts before actor validation. Startup
reserves a final 500 seconds for normal payload creation, whole-byte copying,
PM, launch and retirement checks. No failed installation is repeated.

The client reuses the normal empty payload birth protocol. The creator really
retires before its returned inode is filled from the held official APK, checked
in full and sealed. The receiver independently requires its actual positive
EMPTY owner, observes the complete user-zero package table and all-user
retained package absence, consumes one nonrenewable installation claim, and
runs the normal create-only PackageInstaller transaction. It performs no
replacement, uninstall, clear, downgrade, re-signing, credential import or
automatic retry. It compares the complete package table afterward, checks the
actual installed base APK bytes and current UID, and uses the same authenticated
normal control instance for one ordinary launch with Main bookends.

The diagnostic guest needs its own run duration. The normal producer derives
1,560 seconds from the published manager/factory/launcher/observer startup
limits (30/60/240/255), the diagnostic runtime/stop limits (780/30), and native
startup/report allowances (120/45). It rejects a shorter EMPTY run before
starting QEMU. After the single QMP power-down request it allows 480 seconds:
the six normal unit stop limits plus 40 seconds for final journal shutdown.
These are bounded observation allowances. The client keeps its original
720-second deadline, and success still requires actual ordinary shutdown and
real QEMU retirement. Other guest modes retain their original shutdown budget.

Complete phase results and failures go to the ordinary unit journal as fixed
small frames with one whole-report SHA-256. The normal ended-guest collector
requires verified journals, normal shutdown, the unchanged source unit and
installed executable, and one trusted root unit/boot/PID/invocation before
reassembling `EMPTY-MEITUAN-REPORT.json`. This remains a comparison document;
it creates no live owner or acceptance capability. Missing or mixed frames
stay an explicit collection failure. A normal
launch observation leaves `production_ready`, `original_data_migration` and
`business_acceptance` false. This diagnostic neither accesses the protected
old app's CE/DE/external data or keystore nor claims that official login restores
those local files. User-data recovery and application business acceptance have
their own actual evidence requirements. A used or failed EMPTY generation is
retained for inspection; it cannot be relabeled as a fresh retry.

### Fixed public helper release inputs

The normal helper materializer reads ten immutable APK and public certificate files
from `/var/lib/droidloom-public-build-inputs/prebuilt-helpers/20261128-r2`.
The fixed child directories are `saf`, `features`, `ihg`, `rotation`, and `video`;
each contains only `helper.apk` and `signer.der`. Directories are root-owned
and mode `0755`; each file is root-owned, single-link, and mode `0444`.
The compiled source member table requires the complete original bytes and signer
for every file. The installed forty-member helper tree is unchanged. These
release inputs and all private signing material stay outside the source repository.
