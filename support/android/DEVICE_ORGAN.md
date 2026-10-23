# Android device organ: development and technical contract

## Delivered scope

`device_organ.py` is a host adapter for the existing `pocket4` Digitalis/Droidloom
Android cell. Its executable implements two read operations: `qualify` reads
daemon/cell identity and `observe` reads one explicitly named application's
current window. A pure Python API prepares a semantic intent without executing
it. Every effect operation is rejected before the privileged helper is invoked.

The current device profile is Android 17 / SDK 37. It does not alter the existing
Android 15 AOSP/Cuttlefish lock, qualify APK workloads on the Rust kernel, or
establish physical handset support. The source profile is machine-readable in
[`device-organ-contract-v1.json`](../../compat/android/device-organ-contract-v1.json).

The source was developed against Desktop
`1f4a252c22adf3bc4e1de1ce655e42387070f503`; Hepta interface review used
`6d6097da843f5831dfaf9cee3530da512d072a15`. A downstream release must record its
actual repository commit/tree and adapter/transport hashes, rather than reusing
these development bases as the identity of a modified checkout.

| Component | Responsibility | Authority |
| --- | --- | --- |
| Original Runtime operator | Select `pocket4`, authorize the host process, retain job identity/output | Existing host authority; not proof of a new FinalUse device grant |
| `device_organ_transport.py` | Measure fixed tool files; one bounded process attempt | No shell, issuer, persistent ledger or retry loop |
| `device_organ.py` | Qualify identity, project observations, construct exact intent bytes | Observation and intent only |
| Original Digitalis helper | Discover the existing cell and perform its native operations | Existing privileged host receiver; unchanged by this slice |
| Original Hepta effect owner | Durable operation, FinalUse, dispatch and reconciliation | Required for future effects; `NOT_CONFIGURED` here |

This adapter performs host I/O and therefore cannot run inside
`TrustedReadOnlyOrganV1`. That handler must consume only a bounded observation
supplied by an owner outside the organ boundary. The default
[`hepta-os` observer](../../services/hepta-os/README.md) and Session do not enable
this adapter, discover devices or acquire device authority.

## Source pins and invocation

The reviewed helper is
`/usr/local/libexec/android-digitalis-observe-helper`, 34,048 bytes, SHA256
`8c9856a3791f0a208e59b00137547466c9f84d3a60d7a2cae700980de43f677b`.
The separately measured `/usr/bin/droidloomctl` was 1,687,600 bytes, SHA256
`aa1e415db5ddb865f600b0b201e5eea83715efab8d9c0db86902b568ec539376` on
2026-10-23. The adapter requires the latter pin explicitly from the trusted
operator; it does not learn a trusted pin from the same untrusted response it
is about to accept. A changed helper requires source review and an explicit
profile update.

Both files must be regular, executable, non-symlink files without group/world
write permission. The privileged helper must remain owned by root. Droidloom's
owner UID is a separate explicit pin: root by default, or the current original
operator UID. The actual 2026-10-23 deployment has Droidloom owned by UID 1000,
the original operator, and the helper owned by UID 0; both modes are 0755. Supply
`--droidloomctl-owner-uid 1000` for that measured deployment. A different user or
an invalid UID is rejected before invocation. The initial root-default probe
correctly rejected this user-owned Droidloom file without any transport attempt;
its failed receipt is retained. No ownership or permission change is required.
Both tools are measured before and after each call, and receipts record the
configured tool owners and the actual operator UID.
These measurements do not attest the interpreter, sudo policy, every library,
Android framework, or hardware. The host administrator remains trusted. The
`pocket4` target binding comes from the original Runtime job record, not from a
hostname or an identity claim made by this adapter.

From an isolated checkout or an exact two-file transfer on that selected host:

```sh
python3 support/android/device_organ.py \
  --droidloomctl-sha256 aa1e415db5ddb865f600b0b201e5eea83715efab8d9c0db86902b568ec539376 \
  --droidloomctl-owner-uid 1000 \
  qualify
```

This invokes `/usr/bin/droidloomctl status --json` once, then
`/usr/bin/sudo -n /usr/local/libexec/android-digitalis-observe-helper` once with
the exact stdin JSON `{"op":"status"}` followed by a newline. No UI dump,
launch, installation, click, input or device configuration occurs. The helper
uses its existing recorded cell and native namespaces; no ADB path is used or
enabled. A complete qualification checks matching daemon/helper host PID,
running/ready state, completed boot, release/SDK, stopped adbd, disabled TCP ADB,
and USB configurations without ADB.

`qualify` emits one JSON object and exits 0 only when all checks pass, 3 when
valid observations fail the profile, and 2 for a rejected or unresolved call.
Its receipt records both Python source hashes, the tool pins, identity/status
hashes and separate capability states. It explicitly reports zero device
mutation attempts and no UI observation. A successful status call is not an
execution qualification for `observe`, semantic actions or Chinese input.

An explicitly requested window observation uses:

```sh
python3 support/android/device_organ.py \
  --droidloomctl-sha256 aa1e415db5ddb865f600b0b201e5eea83715efab8d9c0db86902b568ec539376 \
  --droidloomctl-owner-uid 1000 \
  observe --package org.example.notes
```

Replace the example package only with the intended application's exact package.
Observation first qualifies identity, then permits only `display=0`,
`accessibility_mode=none`, and `with_png=false`. It reads the current screen/UI
through the original helper. It does not launch the app or change accessibility
mode. The projection contains hashes and window metadata, with private UI text
and PNG bytes omitted. The helper response is still private input; callers must
not log that raw response as ordinary telemetry.

## Bounded transport and unresolved results

The CLI never accepts a shell fragment or arbitrary executable. Each call has a
55-second default deadline, at most 60 seconds, a 4 KiB request bound, and a
combined 1 MiB stdout/stderr bound. Qualification has two sequential calls;
observation has three. Bounds apply per call. JSON must be a complete UTF-8
object with no duplicate fields or non-finite values.

An invalid request or preflight pin failure occurs before submission. Timeout,
excess output, malformed response, helper failure, a changed tool after the
attempt, or a mismatched returned window is unresolved after submission. Such
failures preserve `transport_attempted=true`, `outcome_unknown=true` and
`automatic_retry=false`. The adapter kills its own transport process group when
possible; this is not proof that an Android operation was cancelled. It never
replays a call. This remains conservative even for the read-only profile.

No request counter, operation journal, signer, nonce namespace, background
worker or daemon is introduced. The original operator retains its existing job
receipt. If a future effect produces an unknown result, only the original
operation owner may reconcile it using the same operation/payload identity.
Neither a fresh operation ID nor a second grant is a recovery mechanism.

## Exact observation and intent binding

The projection retains the exact raw helper reply SHA256, a canonical native
snapshot SHA256, helper and observed identity hashes, frame/scope hashes,
capture time, screen/scope bounds, and the helper's context token. Its stable
window tuple is:

`package, activity, WindowManager window_token, display_id, window_bounds,
android_init_host_pid`.

The context token is recomputed from that tuple, scope bounds and screen size
with the original helper's canonical serialization. Accessibility window IDs
are connection-scoped and are not substituted for the WindowManager token.
Host PIDs are short-lived observations, not durable device incarnations. Capture
is explicitly non-atomic. These hashes neither authenticate an owner nor prove
freshness at a later effect boundary.

`prepare_semantic_intent(observation, operation_id, action, selector, value)`
accepts only `click` or `set-text`. It requires at least one exact `id`, `text`
or `desc` selector, restricts additional selector fields, and binds the package
to the observed window. Substring selection, positional `index`, cross-package
selection and unknown fields are rejected. `matching=exact_unique` is a future
receiver requirement; `selector_resolution=NOT_EXECUTED` makes clear that this
function has not resolved a native node.

The payload binds the original operation ID, all observation/source hashes,
the complete window tuple, screen/scope bounds, action, selector and value.
The digest covers exact canonical UTF-8 JSON bytes. Chinese characters and emoji
are preserved; text is limited to 4,096 UTF-8 bytes, and the complete intent to
16 KiB. It is a proposal with `authority=none`, not a signed envelope. There is no
CLI command to submit it. `commit-text` explicitly returns
`COMMIT_TEXT_NOT_CONFIGURED`.

## Remaining receiver and original-owner integration

The reviewed helper's `dispatch` semantic branch selects only `op`, `selector`,
`index`, `value`, `display`, `include_invisible`, `accessibility_mode`, and
`method` for its `ui` request. It does not forward the window token or snapshot
hashes to the final semantic receiver. Its visual branch has separate snapshot
checks, but those cannot qualify the semantic selector path. Consequently this
adapter rejects all effect operations before invoking the helper, even if an
intent contains the expected fields.

The next effect slice requires both of the following concrete integrations:

1. Extend and review the original semantic receiver so it accepts the exact
   window/snapshot binding, resolves exactly one native target in that window,
   and rejects drift immediately before action. Preserve UTF-8 readback and
   distinguish action submission, observed UI change and business success.
   Test ambiguous targets, stale tokens, switched windows, changed snapshots,
   lost replies and Chinese text on the real target. Update the helper pin only
   with its actual deployed bytes and receipt.
2. Connect that restricted receiver through the original Hepta operation owner.
   The reviewed `AgentdFinalUseGrantProvider::signed_grant(&FinalUseBinding)`
   returns an unconsumed original issuer grant; it is not an adapter-owned
   signer or a consumed provider effect. The existing writer must supply the
   exact subject, destination, request/scope/payload hashes, current source lease
   and recovery cut. Retain the original protected clock, external authority
   frontier, issuer keys, revocation distribution and any deployed independent
   approval roles. Define the Android operation/destination and durable device
   incarnation within those owners before effect dispatch. A Notes grant, Bao
   read grant or fleet allocation grant must not be relabeled as Android UI
   authority.

The existing inspected sources did not establish this Android-domain production
owner/provider assembly. All related fields remain `NOT_CONFIGURED`; the code
does not manufacture replacement credentials, a fixture issuer, or another
operation ledger. Read-only qualification can be delivered independently while
these effect gates remain explicit.

## Development and validation

Python 3.10 or newer and the standard library are sufficient. On Linux, from
the repository root:

```sh
python3 -m unittest discover -s tests/workloads/android -p test_device_organ.py -v
python3 -O -m unittest discover -s tests/workloads/android -p test_device_organ.py -v
python3 support/android/verify_source_integrity.py
```

The tests use clearly synthetic identities/UI data, plus real isolated child
processes for timeout, output bounds and UTF-8 transport. They cover the fixed
read allowlist, changed cell/window/context, strict JSON, hash pins, symlinks,
FIFO and writable-file rejection, exact Chinese intent bytes and pre-submit
effect refusal. They do not call the device or any production authority.
The existing A08 host workflow discovers this test module in normal and
optimized Python; the explicit source inventory prevents silent deletion.

A release must retain its actual source/tree, command, original Runtime target
and job identity, complete output/exit/timeout state and result hash. Report
source/unit qualification, actual read-only status, actual UI observation, real
effect execution, original production authority, physical handset support and
Android-on-Asterinas as distinct outcomes. This source change alone claims only
the implemented adapter and its testable boundaries.
