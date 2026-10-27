# Original Android receiver binding candidate

This source increment extends the existing Pocket4 helper and the existing
`local.pocket4.actions.v2/.ActionRunner`. It does not install a service, start an
Agentd, issue authority, retain an operation ledger, enable ADB, or register an
effect destination by default. The existing `device_organ.py` profile remains
read only and retains its deployed helper pin.

**Current local qualification:** source generation and host protocol/transport
tests pass. Android compilation, original signer equality, installation,
actual native observation, a real text effect and original-owner durable
reconciliation still require recorded execution. Host tests are not device
evidence. The original signing password and key were not read or copied.

## Source and compatibility

| Source | Purpose |
| --- | --- |
| `upstream/android_app.py` | Exact deployed 34,048-byte original helper, SHA256 `8c9856a3791f0a208e59b00137547466c9f84d3a60d7a2cae700980de43f677b` |
| `upstream/ActionRunner.java` | Exact deployed 21,421-byte runner source, SHA256 `bf3a577bfbb9b0f4b9c6035c0423e73f8fef0e1df34dd7dea2140efbe6308570` |
| `organ_extension.py` | Strict opt-in dispatcher compiled into the original helper file |
| `runner/OrganJson.java` | Exact canonical UTF-8 payload identity and bounded schema |
| `runner/OrganSnapshot.java` | Actual native window, cell/app incarnation, node and screenshot observations |
| `runner/OrganBinding.java` | Native preconditions, final deadline and independent readback |
| `build_receiver.py` | Pinned-preimage source generation, original SDK build and optional same-signer check |
| `qualify_receiver.py` | Explicit javac, APK signature and installed-source read-only qualification gates |

The generated ActionRunner changes six existing locations: a binding member,
binding parse, opt-in native find/readback, a pre-action check, result decoration,
and failure decoration. Legacy requests have no binding member and keep their
original paths. The original CLI bytes and entry remain unchanged. Duplicate
JSON fields/nonfinite numbers now reject at helper input; normal legacy JSON is
unaffected. The same original helper global lock still serializes requests.

No generated source imports a new host module: the reviewed extension is
embedded into the one original helper executable. The APK keeps its original
package, manifest, permissions, instrumentation target and signing identity.
The build does not generate a signing key and rejects a candidate whose signer
certificate differs from the verified original APK.

## Exact receiver protocol

### Development boundary: effects remain disabled

The helper rejects every `organ-set-text` with
`ORGAN_EFFECT_RECEIVER_NOT_QUALIFIED` before cell discovery or `ui(request)`.
No same-original-signer strict installed receiver is independently qualified in
this source profile. Caller fields, a claimed protocol, or a later successful
reply cannot supply that qualification. The original APK ignores the new
top-level `organ` field and could otherwise write before the helper rejects its
legacy reply. The reply check alone is too late to prevent that effect.

`organ-observe` and `organ-readback` retain their find-only paths. The deployed
read-only adapter, original signer and APK are unchanged. This guard does not
qualify P1 Android delivery or enable an effect lane. A future enablement needs
separate review of trusted installed-byte, original-signer and peer checks
before any native write; an unsigned candidate is insufficient.

Run the offline boundary regressions with
`python3 -m unittest tests.workloads.android.test_receiver_effect_boundary`.
All cell, transport and UI calls in these tests are synthetic doubles. They
cover old/unknown receivers, forged caller qualification, premature effect
submission and unchanged find-only observations/readback. The wire schema below
describes the candidate receiver; host write dispatch remains disabled.

The new operations are available only as explicit JSON on the existing helper.
They are not added to the legacy CLI or the read-only adapter's effect allowlist.

`organ-observe` accepts exactly `op`, `package`, and `resource_id`. The resource
must be a full exact ID in the requested package, such as
`com.android.settings:id/search_src_text` **only if actual native discovery
confirms that ID**. The receiver requires exactly one visible, enabled,
non-password editable node with native `ACTION_SET_TEXT`; no index, substring,
click ancestor, keyboard injection or accessibility-mode change is supported.

The instrumentation returns an observation containing:

- Cell identity from the real Android init: host boot UUID, init process start
  ticks, mount/PID/time namespace IDs. Numeric PIDs alone are insufficient.
- Application main PID and process start ticks, obtained through the original
  UiAutomation shell capability. Multiple matching processes or inaccessible
  public process metadata reject this profile.
- The actual focused WindowManager token, package/activity, default display
  and native bounds. Accessibility connection IDs are not treated as tokens.
- The exact resource/class/bounds and prior text hash, plus a hash of that node
  record. Private text is not returned in this observation.
- A native screenshot RGB scope hash, with width/height prefix, and a monotonic
  observation time. This is explicitly a non-atomic observation.

`organ-set-text` and `organ-readback` accept exactly `op`, `payload_base64` and
`payload_sha256`. The decoded canonical UTF-8 payload is at most 16 KiB:

```json
{
  "schema_version": 1,
  "action": "set_text",
  "operation_id": "the-original-owner-operation-id",
  "destination_id": "pocket4.android:<scope-sha256>",
  "observation": { "...": "the complete exact native observation" },
  "value": "中文输入😀",
  "expires_elapsed_ms": 123456
}
```

This example is structural, not an executable payload. Canonical JSON uses
sorted keys, no insignificant whitespace, no ASCII escaping of UTF-8 text,
integer time values, no duplicate keys and no trailing newline. The destination
hash covers the canonical object with `application`, `generation`, `package`
and `resource_id` fields. The 79-byte ID fits the original Hepta StableId bound
and distinguishes editors within the same application incarnation. The action
expiry must be after observation and at most 30 seconds later. It cannot be
extended when a request is retried or reconciled. Text is at most 4,096 UTF-8
bytes and cannot contain NUL or invalid surrogate sequences.

The helper discovers the original production cell once. It opens and retains
the exact mount/PID/UTS/IPC namespace descriptors, verifies init start identity,
and invokes `nsenter` through those descriptors. It never rediscovers another
cell on a later phase. Android's and the host's time namespace must agree before
the host `CLOCK_BOOTTIME` deadline is compared to native `elapsedRealtime`.
Every step shares one 55-second helper budget.

Inside the original runner, the existing second full-tree resolution remains
in effect. Immediately before its existing `performAction`, the strict path
independently re-reads and compares generation, application incarnation,
WindowManager token, bounds, exact node/prior value and native scope hash. It
then checks the immutable action deadline. Any mismatch rejects before action;
there is no fallback selector or new request. This is the strongest available
public accessibility check, not an atomic transaction with the application.

The helper checks the actual runner's protocol, operation hash and generation
fields. It does not create successful receiver bindings on the runner's behalf.
The native reply distinguishes `action_submitted`, `postcondition_observed`,
`independent_readback_required`, `causal_receipt_persisted=false`, and
`business_success_verified=false`. A timeout or malformed reply stays unknown
and never triggers replay.

`organ-readback` executes a new native find/observation and never includes a
mutation value in its native request. It binds the same operation/payload,
generation, application and window. It returns an observed text hash and
`state_matches_requested_value`, with `terminal_outcome=unproven`. Matching UI
text is not proof that this operation caused it. A changed cell/application
incarnation rejects the old payload, even if a new app displays identical text.

## Original owner integration boundary

The matching [Hepta target development/technical contract](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/main/codex-rs/hepta-memory/PRODUCTION_ANDROID_TEXT.md)
maps the actual `ProductionAndroidTextTarget`, fixed helper input/output,
original `with_additional_target` bootstrap, focused Rust tests and unresolved
connector requirements. Use the exact Hepta source-profile commit for a build;
the link is navigation, not a deployed source pin.

The original ProductionDurableWriter must prepare the exact operation/payload,
obtain original authorization and FinalUse, dispatch once, and retain the same
operation for reconciliation. These source files do not supply that authority.
Independent readback can support immediate acknowledged execution, but cannot
resolve a lost response as Applied merely because the requested text is now
present. Without a retained original terminal receipt or an application-owned
causal receipt, a lost reply remains Indeterminate and is never replayed. There
is deliberately no replacement operation DB here.

The legacy read-only adapter stays disabled for effects until the original
owner adapter and actual deployed receiver pins are qualified together. A
standalone helper test is not a production FinalUse/owner acceptance test.

## Generate and compile without changing the live receiver

Run from a clean isolated checkout. The output directory must not exist:

```sh
python3 support/android/receiver/build_receiver.py --output /tmp/android-organ-review
python3 -m unittest tests.workloads.android.test_bound_receiver tests.workloads.android.test_device_organ
python3 -O -m unittest tests.workloads.android.test_bound_receiver tests.workloads.android.test_device_organ
```

The actual Android build uses the original SDK 35 jar, build-tools 35.0.1,
original manifest/resources, and original APK. `--compile` first verifies their hashes
and the original APK signature, then compiles all four Java files, dexes, packs
and aligns an unsigned candidate. If the original XML manifest is unavailable,
use the explicit verified-binary-resource mode below. It preserves the exact
original binary manifest; it does not reconstruct or pretend to recover XML.

Java compilation alone does not need the original manifest or signing material:

```sh
python3 support/android/receiver/qualify_receiver.py java \
  --output /tmp/android-organ-javac-only --sdk /opt/android-sdk
```

This writes `javac-record.json` with the measured original SDK jar and generated
class hashes. It does not claim that an APK is signed, installed or functional.

```sh
python3 support/android/receiver/build_receiver.py \
  --output /tmp/android-organ-original-build \
  --compile --sdk /opt/android-sdk \
  --manifest /absolute/path/to/the/original/AndroidManifest.xml \
  --original-apk /opt/pocket4-android-controls/actions-v2.apk
```

When the original source XML is absent, reuse the exact authenticated APK's
binary manifest and resources:

```sh
python3 support/android/receiver/build_receiver.py \
  --output /tmp/android-organ-original-resources-build \
  --compile --sdk /opt/android-sdk --reuse-original-resources \
  --original-apk /opt/pocket4-android-controls/actions-v2.apk
```

This mode verifies the fixed original APK hash and its actual original signer
before compiling. It retains every non-signature resource byte, replaces only
`classes.dex`, removes the old `META-INF` v1 signature entries, and rewrites the
ZIP so the old APK Signing Block cannot survive. It verifies resource hashes
again, runs the original `zipalign`, and requires the unsigned artifact to fail
APK signature verification. `aligned.apk` is deliberately **unsigned** and is
not deployable as an update. Only the original signing material can make the
same-package candidate installable; no fallback signing key is generated.

The exact 20,847-byte original APK was inspected locally on 2026-10-24. Its
binary manifest is 1,528 bytes with SHA256
`8ee050bbc4bc9938ebcfbb1bf1d6cea3414de9e868ca9b141dfa0dd27e921494`.
The archive contains `classes.dex`, that binary manifest, three v1 signature
entries and an APK Signing Block. Its public v1 certificate fingerprint is
`7c36bafbdb2789384aeae9dabf69cca6b468f6c1a2d75952ab315288b77ff7f7`.
Certificate extraction is metadata inspection; actual APK signature validation
remains an explicit `apksigner verify` build gate. A local resource-preservation
check used the original dex unchanged and is not a strict-receiver build or
Android execution claim.

Optional signing uses only the already-authorized original keystore and its
existing password environment variable:

```sh
python3 support/android/receiver/build_receiver.py \
  --output /tmp/android-organ-original-signed-build \
  --compile --sdk /opt/android-sdk \
  --manifest /absolute/path/to/the/original/AndroidManifest.xml \
  --original-keystore /absolute/path/to/the/original/control-v2.p12 \
  --password-env POCKET4_LOCAL_BUILD_PASSWORD
```

The recorded original build paths are below. They identify original provenance;
their presence on Pocket4 has not yet been verified:

`/home/qian-qi/Documents/Codex/2026-10-07/referenced-chatgpt-conversation-this-is-an/work/wechat-control/implementation/runner/AndroidManifest.xml`

`/home/qian-qi/Documents/Codex/2026-10-07/referenced-chatgpt-conversation-this-is-an/work/wechat-control/implementation/runner/build/control-v2.p12`

Only signer SHA256 fingerprints, source/artifact hashes and build scope are
written to the build record. No installation command is present in the builder.

The signed artifact can be checked separately without installing it:

```sh
python3 support/android/receiver/qualify_receiver.py apk \
  --sdk /opt/android-sdk \
  --candidate-apk /tmp/android-organ-original-signed-build/actions-v2.apk
```

Both `apk` and `installed` first capture the original and candidate APK through
one held file descriptor each. Inputs must be single-link regular files of
1 byte to 4 MiB; symlinks, directories, FIFOs, oversized files, and changes in
identity, size, timestamps or metadata during the bounded read are rejected.
The original fixed hash, signer verification, candidate manifest inspection,
and reported hashes all describe these same captured bytes. `apksigner` and
`aapt` read mode-0600 copies in one private temporary directory, which is
removed on success or failure. Neither inspector reopens a caller's APK path.

`apk_input_binding` records each source path observed at capture, its device
and inode, timestamps, byte length and snapshot SHA256. The original paths may
subsequently be replaced; this record does not assert their later contents.
It also does not prove that the candidate DEX came from a particular reviewed
build, that a strict receiver is installed, or that any native effect is
qualified. Installed-package identity remains a separate read below. The
existing unconditional `organ-set-text` rejection is unchanged.

The focused host regressions use actual temporary files and path replacements
with synthetic signature/Android metadata inspectors:

```sh
python3 -B -m unittest tests.workloads.android.test_receiver_qualification \
  tests.workloads.android.test_receiver_effect_boundary -v
python3 -B -O -m unittest tests.workloads.android.test_receiver_qualification \
  tests.workloads.android.test_receiver_effect_boundary -v
```

They verify snapshot binding, mid-read changes, nonregular/aliased/size-invalid
inputs, signature failures and the unchanged pre-dispatch effect guard. They
do not execute Android tooling, sign an APK, install a package or use ADB.

After an independently coordinated original-package update, installed-source
verification uses the existing original root inspection capability. This
inspector never invokes sudo or changes permissions to acquire that capability;
an unavailable capability is an explicit failure. It verifies the deployed
helper/source pin and the original Droidloom pin, takes the original helper's
lock, pins the original cell namespace descriptors, reads the unique installed
package path and APK bytes, and verifies their hash and original signer.
No application is launched, stopped or changed, and no UI observation is made.

```sh
python3 support/android/receiver/qualify_receiver.py installed \
  --sdk /opt/android-sdk \
  --candidate-apk /tmp/android-organ-original-signed-build/actions-v2.apk \
  --expected-helper-sha256 95731ff1a5e72b5f31a0625b157ea8ff2da1b8c718c0efb5055778cc458d1c9f \
  --droidloomctl-sha256 aa1e415db5ddb865f600b0b201e5eea83715efab8d9c0db86902b568ec539376 \
  --droidloomctl-owner-uid 1000
```

The helper hash above is the generated strict candidate at Desktop `5b22e16`,
not the old deployed read-only helper. A different candidate requires its own
reviewed hash. The inspector reports only a point-in-time source match. It does
not establish the original operator's external host binding or replace any
existing peer/signature checks, FinalUse or production-owner acceptance.

## Review, runtime acceptance and rollback

Coordinate with the existing Android app work before any replacement. Record
the actual currently installed package version/signature, original helper hash,
and original APK hash. Preserve those exact bytes with root-owned permissions.
The source candidate does not assume that an old delivery manifest is a current
installed-package measurement.

After original-signer equality is proven, the original package may be updated
in place through the existing production cell control route. Never uninstall
it to bypass a signature conflict, reset application data, restart the whole
cell, open the Android desktop, or enable ADB. Replace the single helper
atomically only after its reviewed hash is recorded. The legacy CLI stays in
place; changes to the separate read-only adapter pin require their own review.

Use one explicitly selected harmless Settings search field or an owned test
application. Confirm its actual native resource ID. Record the native observe,
original-operation request, native effect reply, a separate readback invocation
and the original owner's durable status. Exercise stale window, node hash,
scope hash, expired request, duplicate request after lost reply, package restart
and cell generation change. Tests must confirm no late or repeated effect.

If receiver qualification fails, restore the exact original helper atomically
and restore the same-signer original APK through the same in-place package
route. Do not force a version/signature downgrade or uninstall to make rollback
work. A failed rollback remains an explicit blocker for the original operator.
No app data or device settings are part of this change.
