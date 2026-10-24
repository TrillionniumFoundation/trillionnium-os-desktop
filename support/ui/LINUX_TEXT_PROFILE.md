# Explicit Linux Makepad/text product

`build_text_product.py` builds one original source combination with
`trill-shell/hepta-native-makepad`, Rust 1.96.0, the original SDK
`337566c8b25d47f7e4fff6a202157b65bf183330` and its complete 54-file resource
bundle. Its reviewable inputs are in `linux-text-profile.json`. The first
device profile is x86_64 Linux with X11; native Asterinas and Android have
their own build and execution gates.

## Build and source identity

Use clean Desktop and original Hepta checkouts. Supply full commits and trees;
the Hepta commit must also be the one actually resolved by the committed UI
lock. The existing source verifier proves the original history owner's ancestry
and the Notes protocol goldens before building. The output's parent must exist,
and the output itself must be new and outside both repositories.

```sh
python3 -B support/ui/build_text_product.py \
  --desktop-commit FULL_DESKTOP_COMMIT --desktop-tree FULL_DESKTOP_TREE \
  --hepta-repo /absolute/original-hepta \
  --hepta-commit FULL_HEPTA_COMMIT --hepta-tree FULL_HEPTA_TREE \
  --output /absolute/new-linux-text-build --jobs 2
```

Release is the default. `--build-profile debug` is an explicit development
variant. `--offline` applies to Cargo and the original resource preparer;
`--liberation-source` may supply the exact existing font source archive, and
`--asset-cache` may read an existing original resource bundle by logical path. All
resource lengths and digests remain checked. This entry does not select the
independent clipboard SDK candidate or an arbitrary dependency override.

The command checks the actual resolved native features and one Hepta revision,
runs UI Rustfmt, the native UI workspace, native text host, observer, support
and host-contract Cargo tests, then builds all five real programs. It verifies
the unchanged source/locks after execution, prepares the original resources,
and calls the existing host archive helper and installer packager. A failed
step retains its logs and a failed receipt; it cannot produce a passing receipt.

`build-receipt.json` binds both source identities, the profile, lock digests,
resolved package features, commands and exit codes, compiler, built binary
hashes, resources and final package hash. The source profile remains
production-disabled. A build receipt is separate from owned-window,
installed-systemd, authenticated model and physical-device acceptance.

## Install the explicit renderer

The build writes a user-owned mode0600 `linux-text-config.json` with renderer
`makepad`, bundled resources, draft recovery and normal Notes storage. Copy
that file into a new private configuration directory and provide its absolute
path with the package installer's existing `--config` option. Existing
installations retain their chosen configuration during upgrades; review and
change `renderer` explicitly for those installations.

Use [PRODUCT](PRODUCT.md) for installation and interruption recovery and
[NATIVE_MAKEPAD](NATIVE_MAKEPAD.md) for the actual X11/IBus/AT-SPI test. Pass the
new `build-receipt.json` to that harness's `--build-receipt` option. The baseline
SDK's native `PasteText` remains unavailable; keyboard paste and real IME are
qualified by their respective input paths.

The config has no invented Root principal, writer or thread.
Actual Send uses the existing authenticated Root native launch documented in
[TEXT_SESSION](../../services/hepta-session-host/TEXT_SESSION.md). Installed
Root, original writer, human session, original App Server route and provider
must satisfy that owner contract. A package or resource check does not create
those deployment inputs.

## Development

```sh
python3 -B -m unittest discover -s support/ui -p 'test_text_product_profile.py' -v
```

These focused tests reject a default-egui metadata graph, a disconnected text
feature, mixed revisions, a substituted owner, duplicate original owners and
the separate patched SDK. The actual build command remains the executable
verification of compiler and package behavior.

