# Audio430 original released API inputs

This capsule repairs the source selection behind two strict Soong failures:
`service-ondeviceintelligence.api.combined.system-server.latest` and
`service-ondeviceintelligence-removed.api.combined.system-server.latest`.

The normal build reached the real NeuralNetworks service consumer. The original
prebuilt API generator derives these module names from versioned API text files.
The source selection omitted the released system-server inputs while retaining
the consumer and generator.

## Exact source repair

The patch appends four explicit source paths within the existing
`prebuilts/sdk` project at commit
`0f07e8d60ab0aba46129e427101f96ba459a95c1`:

- `36/public/api/service-ondeviceintelligence.txt`
- `36/public/api/service-ondeviceintelligence-removed.txt`
- `36/system-server/api/service-ondeviceintelligence.txt`
- `36/system-server/api/service-ondeviceintelligence-removed.txt`

All four are original Git blob
`d802177e249b3f97128699222e65c35e57ba7540`, 25 bytes, with SHA256
`39824f8c9fee1582598de5aa8cfa9653e84fbd69bd8aeb92c4a78c861faad552`.
Their original body is a signature-format header. The fixtures preserve those
upstream bytes exactly.

The project count remains 430. Every existing project commit, purpose and
source path remains present. All 1,535 previously pinned original Blueprint
files remain unchanged. The source-lock hash changes from
`78cc10ee7459926ec151e6224e6341d1b33397801330499e5d7f1a13fadb997a` to
`45496b24c055fca9aa1f3fae7bd5c7c3c99cb46721150690645bf5d059159de2`.
The normal source validator requires the same SDK revision and all four paths.
The Audio driver checks their original bytes after normal source verification
and before applying a projection. Existing historical-lock rejection tests
reconstruct the prior exact locks before checking rejection.

No generator, consumer, module default, missing-dependency policy, full-build
target or runtime policy is changed.

## Source-role binding repair

The normal tool preparation also exposed a host relocation bug:
`{"path": local_role, **origin_reference}` let the provenance reference replace
the intended local path. `source_role_pin.py` extracts the small content-only
binding function used by the successful normal continuation. The caller retains
the original reference separately and passes only `bytes` and `sha256` to the
local role. Strict integer, digest, key-set and relative-path checks reject
ambiguous inputs.

The public helper uses a local `require` function in place of the controller's
identical check method. It grants no host, process, lock, source or build
authority.

## Verification

Run the portable controls from this directory:

```sh
python3 -B -m unittest -v test_source_role_pin
```

The seven controls reproduce the original mapping override, cover rejected
types and paths, and check all four upstream SHA256 and Git blob identities.
There are no platform-dependent skips.

The production patch also ran through the normal Rust source and Audio test
filters and both normal CLI builds. The sanitized qualification record states
the actual results and their limits. Portable controls do not substitute for
normal source reconciliation, a strict full build, whole APEX qualification or
guest audio runtime acceptance.

## Applying the repair

Apply the patch to the exact prior PASIT Audio430 recipe whose original file
hashes are listed in `source-origins.json`. Use the normal toolchain, then normal
`verify-lock`, `reconcile` and `verify-materialized` with the resulting source
lock. The production continuation verifies the unchanged 430 project identities,
all 1,535 Blueprint originals and the four API files before attempting another
strict full build. A later successful build still needs its own compiled-input,
APEX signature/content, deployment and runtime qualification.
