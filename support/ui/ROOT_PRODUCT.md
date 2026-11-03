# Linux native Root product

This product composes the existing Hepta Root, Fleet supervisor, Agentd and Core
with the Rust Makepad Desktop. The original Session owns Notes and its two
private application channels. Packaging metadata does not grant an operation.
The original administrator and human checks still run after installation.

The external [recovery qualification tools](RECOVERY_QUALIFICATION.md) observe
the original App and can lose one selected reply body without modifying its
installed ELF. Their process fixtures do not replace genuine Root, human,
model, original-thread or durable owner-receipt acceptance.

## Source and package contract

Freeze one clean Desktop commit/tree and one clean Hepta commit/tree after
updating [the shared dependency contract](DEPENDENCIES.md). All three Desktop
manifests, every Hepta entry in the five ordinary Cargo locks and the declared
prepared UI lock, the native resource profile and its source-tool checkout must
select that same Hepta commit. The prepared Makepad SDK must pass
the complete original source verifier; a default SDK build cannot inherit its
input-method or accessibility evidence.

[build_text_product.py](build_text_product.py) produces the native Desktop
build receipt, final stripped ELF records, resources and original five-program
package. [build_root_product.py](build_root_product.py) consumes that actual
package and its build receipt. It checks both clean source trees, original
resolved Cargo source, immutable locks and compiler identities, then builds:

| Executable | Owner |
| --- | --- |
| `hepta-desktop-root` | Desktop's explicit Root composition binary |
| `codex-hepta-agentd` | Original Hepta Agentd and original Core owner |
| `hepta-authority-host` | Original Root diagnosis/authority entry |
| `codex-app-server` | Same-source Core used for unused thread seeding |

The builder accepts two explicit cache directories outside either checkout.
It does not accept a replacement owner dependency or rewrite a committed lock.
It records the actual distribution bytes after GNU `strip --strip-unneeded`.
`--jobs` selects 1–8 compiler jobs, defaults to one, and is retained in the
receipt. It changes build concurrency only.
Each product builder holds an exclusive advisory cache lease across all Cargo
commands and packaging, so another cooperating builder cannot replace its
final binaries between commands. Root builds reserve both caches in a fixed
order and refuse contention. Direct Cargo commands must leave those caches
alone until the builder finishes; Cargo's per-command lock alone is insufficient.

[product/root_bundle.py](product/root_bundle.py) packages both parts and verifies
their complete file sets. `desktop/` retains its original package manifest and
five binaries, resources, SDK notices and source profile. `bin/` contains the
four Root tools, and `libexec/native_human.py` contains the reviewed local-login
provider. Both build receipts and the Root manifest travel with the package.
The manifest binds the exact Desktop manifest and supplement hashes; a release
identifier includes a digest of its supplement. The unchanged size bounds are
128 MiB per file and 512 MiB per payload part. The complete compressed archive
also has a 512 MiB bound. These are two explicitly bounded parts, not permission
to put an unbounded extra executable into the existing Desktop package.

The explicit installer uses a Root-owned, canonical installation prefix, such
as `/opt/trill-product`. Every ancestor and every installed descendant must
remain in Root custody and reject shared writes. Files are copied into a
private staging directory and reverified before publishing an immutable
release. Existing releases must match their complete manifests. Installing or
switching a release does not start services, create a human identity or reset
an existing authority directory.

## Build, install and run the existing acceptance paths

Use an x86_64 Linux build host with Python 3.11+, Rust 1.96.0 and the native
dependencies in [RUN.md](RUN.md). The completed 942/de0 native UI CI retained
logs, metadata and hashes; it did not publish a distribution package. Choose
one clean final Desktop source and its selected clean original Hepta source,
then build the actual optimized package. Keep outputs and explicit Cargo
caches outside both checkouts. Each output directory below must be new, with
an existing parent; caches may be reused under the builders' exclusive leases.

For the selected callback-preedit product, first prepare the exact original
metadata and all-SDK override with [PREEDIT_TEXT_PROFILE.md](PREEDIT_TEXT_PROFILE.md).
Use its committed prepared lock instead of changing the original UI lock:

```sh
python3 -B support/ui/build_text_product.py --profile preedit-callbacks \
  --desktop-commit FULL_DESKTOP_COMMIT --desktop-tree FULL_DESKTOP_TREE \
  --hepta-repo /absolute/frozen-hepta \
  --hepta-commit FULL_HEPTA_COMMIT --hepta-tree FULL_HEPTA_TREE \
  --sdk-original-metadata /absolute/inputs/original-native-metadata.json \
  --sdk-cargo-config /absolute/inputs/preedit-overrides.toml \
  --committed-preedit-lock --build-profile release --jobs 2 \
  --target-dir /absolute/caches/ui \
  --output /absolute/new-ui-build

mkdir /absolute/new-ui-extract
tar --no-same-owner -xzf /absolute/new-ui-build/trillionnium-desktop-linux-text.tar.gz \
  -C /absolute/new-ui-extract
python3 -B support/ui/build_root_product.py \
  --desktop-package /absolute/new-ui-extract/trillionnium-desktop \
  --desktop-build /absolute/new-ui-build --hepta-repo /absolute/frozen-hepta \
  --hepta-target /absolute/caches/hepta-runtime \
  --root-target /absolute/caches/desktop-root \
  --build-profile release --jobs 1 --output /absolute/new-root-build
python3 -B support/ui/product/root_bundle.py pack \
  --desktop-package /absolute/new-ui-extract/trillionnium-desktop \
  --root-build /absolute/new-root-build \
  --output /absolute/new-product.tar.gz
```

Supply `--offline`, the verified `--asset-cache` and `--liberation-source` to the
UI builder when using a fully prepared offline host; offline is not a fallback
for missing sources. `--sdk-helper-repo` is unnecessary when it is the same
selected Hepta checkout. If the Root/runtime release exceeds an unchanged
size bound, a new explicit `--build-profile product-linux` Root build may be
measured; it has its own receipt and cannot inherit the failed package result.

Verify the outer archive SHA256 against the independently retained build
output before extraction on the target host. Then use the included original
installer, retaining its returned `installed` path and release ID:

```sh
mkdir /absolute/new-product-extract
tar --no-same-owner -xzf /absolute/new-product.tar.gz \
  -C /absolute/new-product-extract
python3 -B /absolute/new-product-extract/trillionnium-desktop-root/root_bundle.py \
  verify /absolute/new-product-extract/trillionnium-desktop-root
sudo -n python3 -B /absolute/new-product-extract/trillionnium-desktop-root/root_bundle.py \
  install /absolute/new-product-extract/trillionnium-desktop-root \
  --prefix /opt/trill-product
```

The target needs an actual active local graphical logind session for the
explicit non-Root UID/GID, its real display/DBus/private `XDG_RUNTIME_DIR`, and
the finite `qwen38-flash-next-uc` Responses provider at
`http://127.0.0.1:18083/v1`, ready before the bounded launch episode. Root must
be able to create the actual protected bind mount; UID0 in a container that
denies mounting does not meet that prerequisite. No real model credentials are
copied into a fixture or generated by these commands. A new physical `/var/lib/trill/NAME` prefix
must be available; the initializer creates it and refuses an existing one.
Do not pre-create that state prefix or reuse a failed initialization.

Prepare the administrator's Root0600 configuration under a Root0700 directory
using the exact [input schema and public preferences/prompts](../../services/hepta-session-host/src/product_root/README.md#operator-input).
Use the physical `/opt/trill-product/releases/RELEASE_ID` path returned by the
installer, not the `current` symlink. Its existing files supply these inputs:

| Configuration input | Actual installed source |
| --- | --- |
| `programs.agentd`, `app_server`, `authority_host` | Corresponding `bin/` ELF in that release |
| `programs.session`, `shell`, `app_window` | Corresponding `desktop/bin/` ELF; the recovery helper remains its installed sibling |
| `programs.human_provider` | `libexec/native_human.py` |
| `programs.python` | Actual canonical system Python ELF, for example `/usr/bin/python3.12`, not an interpreter symlink |
| `sources.runtime_body` | The same installed `bin/codex-hepta-agentd` ELF |
| `sources.sdk` | `desktop/resources/NATIVE-SDK-SOURCE.json` for the selected preedit package |
| `sources.source_freeze` | `desktop/source-profile.json` |
| `makepad_resources` | The physical `desktop/resources` directory |

The administrator supplies the actual UID/GID, local display environment,
new state prefix, the schema-checked preference/prompt documents and finite
lifetimes. Principal, thread, PID, grant, signature and authority state are
not configuration inputs. Start the original entry in the foreground:

```sh
sudo -n /opt/trill-product/releases/RELEASE_ID/bin/hepta-desktop-root \
  initialize --config /absolute/root-private/initialize.json
```

Keep its original logs and generated evidence. In another administrator
terminal, the existing read-only command observes the same live instance:

```sh
sudo -n /opt/trill-product/releases/RELEASE_ID/bin/hepta-desktop-root \
  admin --instance-file /var/lib/trill/NAME/admin/root-admin-instance.json observe
```

The real local user then submits one explicit Notes edit in the launched
original chat. Preserve the actual thread/turn/tool call, original operation
and target incarnation, predecessor and resulting revision, original writer
result, and independently read current document text. Use the existing
`hepta_notes_state` and `hepta_notes_status` tools to reconcile that same
operation; a second edit or a replacement call ID is not a recovery step.
An answer saying “saved”, a window, or a successful `observe` is insufficient.

The existing [packaged-window gate](PREEDIT_TEXT_PROFILE.md#required-actual-packaged-window-gate)
checks the exact stripped Shell/resources with owned X11/IBus/AT-SPI;
[`smoke_installed.py`](product/smoke_installed.py) and
[PRODUCT.md](PRODUCT.md#verification-boundary) exercise installation, two
distinct releases, restart, upgrade/rollback and retained user data through a
real user systemd manager. Run those with their explicit package/build pins;
neither creates the physical-human/model authority required above. After a
successful real operation, the existing [partial-reply recovery](RECOVERY_QUALIFICATION.md)
and [precise grant-revocation](NOTES_ISSUER_GATE.md) tools cover their separately
specified fault boundaries. Retain each actual result, including Unknown or
unexecuted outcomes, under the same installed source/binary identities.

## Runtime composition

The Root entry is a separate `product-root` binary in `hepta-session-host`.
The existing library continues to forbid unsafe code. Its explicit first
deployment is for a new dedicated private state prefix; existing or partial
authority state must not fall back to fresh initialization.

The original Fleet registry and supervisor spawn the actual unprivileged
Agentd. Retained process handles, pidfds, process birth, UID/GID and capability
checks bind the original incarnation. The Root composition creates the
anonymous startup pairs in the same process that serves Root; a helper cannot
impersonate their original creator. A one-use supervisor driver cannot reuse
the same inherited descriptors after an uncertain spawn. The original
supervisor continues to poll health and own process cleanup.

Before the bounded Notes startup episode, the same-source Core creates one
unused original thread with the exact Notes tool catalog. No prompt or model
turn is submitted during seeding. The final owner must resume and verify the
original thread, Core session, catalog, metadata bytes and configured model
tuple. A retained seed receipt alone is insufficient.

The actual Session reserves its Notes document. Root obtains the exact target
and nonce from the kernel-credential-bound reservation; it does not invent a
target for bootstrap policy. Reservation observation and later original
consumption share one cumulative startup deadline. The two application
descriptors stay in Session until the original Agentd recovery and activation
checks complete.

The physical human provider is described in [NATIVE_HUMAN.md](NATIVE_HUMAN.md).
It checks the actual local logind session and passes its retained leader pidfd
to its actual Root parent. Root independently checks that login and binds the
same human, original UI process and live route. A profile file, user-written
session name, model response or generic signed text cannot establish that
provenance. Leader-exit detection does not claim instant notification of every
logind state transition.

The prepared Root object launches the final `trill-shell --renderer makepad`
and serves the original authority lanes. It does not reopen the exclusive
clock/issuer through a second service. Human text is retained together with its
human binding in the existing issuer transaction, then delivered through the
original AuthBus to the original Core turn. Notes tools require the admitted
AuthBus delivery, original Core reconciliation and current Root human proof.
The model cannot authorize itself by directly starting another turn.

The first eligible Notes call in that original turn uses its original durable
writer identity. Before preparing and before signing, the original checks read
the current human proof again. A later call cannot turn a lost reply into a
second effect. The Notes application commits the actual document and returns
the original receipt; status/readback uses the same run, call and document
identity. Document format and migration rules are in
[NOTES_DURABILITY.md](NOTES_DURABILITY.md).

## Same live Root administration

The explicit Root launcher retains an opaque administrative capability from its
same prepared service. Its private `root-admin.sock` and write-once instance
descriptor are described in [the administrative development/technical entry](../../services/hepta-session-host/src/product_root/ADMIN.md).
The finite `hepta-desktop-root admin --instance-file <Root0600 descriptor>`
client connects only to that already-live original Root, with actual peer
credentials, boot/birth, retained process handle and episode nonce checks. It
cannot initialize or reopen an issuer, clock, service, owner or lease.

`observe` reads the original physical Current and writer lease/frontiers.
`observe-grant` selects the bounded volatile observation of an actual original
Notes issue result and can export its same signed bytes into a new Root0600
file. `revoke-grant` verifies that original artifact against the same current
issuer, fixed Notes policy and complete existing effect lease, then performs
the original effect and exact-head grant revocation CAS. Only the original
authenticated observation/consumer synchronization can confirm both protected
consumer frontiers. Pending/Unknown and partial first-store results are explicit;
no unsigned administrative reply updates consumer authority and no mutation
is automatically retried. `observe-grant-state --signed-grant-file <same file>`
reads the original independent lease/revocation/head after a lost reply. An
expired artifact identifies an observation only and cannot authorize mutation.
`revoke-writer` is separately named and never substitutes for precise revoke.

The original 30-second bootstrap, at most 180-second writer and original
120–300-second issuer windows remain in force. Administrative exchanges add no
time: a single cumulative deadline is capped at one second and the original
transport timeout; precise revoke is also clamped to its original grant expiry.
Root/owner/UI/human termination or expiry invalidates the capability. Recreating
a descriptor or retaining artifact bytes cannot revive an old instance.

The selected Hepta crate's `ROOT_ADMIN.md` contains the original-object and
source-closure constraints and scoped tests. Desktop's [ADMIN.md](../../services/hepta-session-host/src/product_root/ADMIN.md)
contains actual CLI syntax and local component checks. These are development
entries, not an assertion that actual Root/GUI/model revocation has run. Product
qualification must distinguish a not-yet-spent original grant refused specifically
as Revoked after authenticated synchronization from an already-spent replay,
expiry, transport failure or process exit.

## Recovery and acceptance

Root retains a bounded, immutable SQLite image independently of Agentd before
publishing its corresponding original `Current`. Recovery reads the actual
protected `Current`, requires original retirement and lease fences, verifies
that independent image, installs under the original store lock, and performs
the original adoption CAS. The old database and WAL remain preserved. Dirty or
unrecognized state cannot be promoted to `Current`. Interrupted UID handoff is
reconciled against the retained original image; it does not capture the
possibly changed live database or repeat adoption.

| Evidence | What it establishes |
| --- | --- |
| Clean-source builds and package verification | The recorded source combination produced these exact package bytes |
| Controlled Root recovery tests | Original guards, real process descriptors and storage recovery in the recorded test environment |
| Installed-package product operation | Actual Root, physical human, original thread and real model completed the recorded Notes operation |
| Installed-ELF input/accessibility checks | Only the actually exercised Chinese/preedit, undo/redo, navigation, reader, focus and scale cases |

Neither the package schema nor a successful compilation claims the last two
rows. Preserve the installed package hash, process identities, original thread
and tool item, Root observation, exact document before/after identity and
readback when qualifying the product. Unknown outcomes remain fenced until
their original result is reconciled. Android original-signer qualification and
Asterinas native guest/driver qualification require their own source-bound
execution evidence.

The product builders use the selected optimized release profile for both native
UI tests and distribution binaries. The unoptimized 2026-10-26 runtime attempt
produced an actual 338,058,032-byte stripped Agentd and 304,151,824-byte stripped
App Server, both above the original 128 MiB per-file limit. That attempt is not
an installable product; stripping cannot remove already stripped code. The
release build must pass the unchanged file and bundle size guards. Root and
native UI build receipts retain their actual profile and compiler identities.
