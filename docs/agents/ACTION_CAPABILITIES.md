# Desktop and Android action capabilities

This is the action contract for the existing interaction product. It covers the
Desktop host, original Hepta text/Objective/Notes paths and Pocket4 Android
adapters. Kernel syscalls, ordinary local widget clicks and model-proposed tool
names are not additional device actions.

The [source profile](ORGAN_RELEASE_PROFILE.md) selects the exact Desktop/Hepta
source pair for a build. The source links below are navigation, not deployment
pins. A source implementation, a mock test, an installed Runtime tool and a
production-qualified action are different facts. Production availability must
come from the live original owner and the exact installed target; this document
does not issue it.

The [repository source verifier](ORGAN_RELEASE_PROFILE.md#production-remains-disabled)
deliberately records `production.activation=disabled` and
`production.effects_authorized=false`. It has no enable flag. Consequently the
implemented effect paths below are not marked production-enabled by a source
verification receipt; their live original-owner qualification remains separate.

## 1. Implementation and deployment states

| Action or observation | Implemented entry | Current qualification boundary |
| --- | --- | --- |
| Local draft edits, room navigation and draft recovery | Original `ChatWorkspace` and product draft store | Local UI state only; restoring a draft restores no thread, signature or execution grant |
| Native chat text submission | `TextChatAdapter::request_send` → original Root signer → Agentd/AuthBus → same App Server thread | Real source path exists; requires the original registered UI, Root owner/session/profile and App Server route. A model/tool E2E belongs to that live deployment |
| Chat history, streaming, reconnect and delivery lookup | Original text worker and `ChatWorkspace` projection | Read/subscribe capabilities and original connection fence required; these observations are not device-effect receipts |
| Command/file approval and chat Stop | Original callback resolution / original queue or turn cancellation | Each uses its own capability and original request identity; ordinary text permission does not imply approval permission |
| Objective submit, retained history, run status and RunCancel | Optional trusted Session host | Original `objective.start` capability, issuer, live owner and retained sender required; generic drafts are not signed Objectives |
| Literal Notes replace (`notes.replace`, wire `replace_note`) | Literal Notes compiler, original production writer, private application channel | Concrete application backend exists. Requires exact current Notes target/revision, original admission and destination-specific FinalUse; application persistence alone does not prove original-writer terminal completion |
| Notes observe, state/previous-receipt reads and exact terminal retirement | Existing private recovery channel / original recovery helper | Retained original target and operation only; recovery cannot accept an effect or acquire the old effect capability |
| CPU delivery lookup (`QueryDelivery`) | Default-off `cpu-history` adapter | One read of an original retained delivery through a trusted transport; no UI budget-install action or device startup is supplied by this adapter |
| Android `qualify` (`status`) and bounded `observe` | Existing `AndroidDeviceAdapter` and pinned original helper | Executable host reads, with original operator/host binding and source checks. `qualified=true` is this read profile's result, not an effect grant |
| Android `click` / `set-text` semantic intent | Pure `prepare_semantic_intent` | Implemented non-authorizing payload construction only: `dispatch_status=NOT_CONFIGURED`, `selector_resolution=NOT_EXECUTED` |
| Android `organ-observe` / `organ-readback` | Strict receiver candidate, using the original helper/APK | Native source implementation exists; installed helper/APK/signer and original cell must be qualified separately. Not added to the read-only adapter allowlist |
| Android `organ-set-text` (`hepta.android.set-text.v1`) | Strict receiver plus original Hepta `ProductionAndroidTextTarget` and retained Runtime connector | Concrete source path exists. Requires the existing authenticated peer/runtime, original source verifier, qualified strict receiver and destination-specific FinalUse. Constructing the connector does not establish these inputs |
| Other Android legacy actions and generic desktop/mobile control | See section 4 | Not exposed as production organ capabilities by this source pair |

The original Android helper contains legacy effects; it is the organ adapter's
profile that is read only. The helper executable's name, presence on disk or
successful legacy CLI invocation must not be used to claim that the strict
original-owner path is deployed.

## 2. Desktop contracts

### Native text, approvals and cancellation

The [native text adapter](../../services/hepta-session-host/src/text.rs) accepts
the active original workspace's committed IME text, at most 8192 UTF-8 bytes.
It preserves text bytes and rejects active composition, stale room/epoch,
expired ownership and incomplete recovery/history. The original Root must have
registered the UI process and its pidfd; Linux UDS peer credentials and that
original registration select the owner. The renderer cannot choose a new
principal, thread, signing key or arbitrary RPC endpoint.

The original Agentd route fixes the agent, generation, App Server session,
thread and home. The signed payload and original client/delivery identity bind
the input. Reconnect resumes that same route and performs original lookup;
it must not sign again, resend an unknown input, create a replacement thread or
convert socket connectivity into `Authenticated`.

History, item/delta, tool and artifact observations retain original identities.
Attachments from another client use inert placeholders; paths, URLs and skill
references are not execution instructions. Tool output is not another effect
grant. The [approval adapter](../../services/hepta-session-host/src/text_approvals.rs)
supports the original command/file callbacks with separate approval permission.
Other credential, interactive input and tool-client callbacks remain with their
original client; this text lane does not fabricate a successful response.

Chat Stop requests the exact original queue/turn cancellation. Before a known
turn exists it uses the original retained queue identity; once a turn exists it
interrupts that exact turn after checking the current original route. A sent
cancellation request is not a cancellation receipt, rollback or proof that a
tool/device action never occurred. The [text contract](../../services/hepta-session-host/TEXT_SESSION.md)
specifies the separate admission, history and delivery barriers.

### Objective and Notes actions

The [trusted host](../../services/hepta-session-host/README.md) consumes an exact
original Objective opportunity once. Issuer/source registration, protected
clock, live verifier and independent durable checkpoint belong to the original
owner. `cancel_before_send` only consumes an unused local send opportunity.
After admission, RunCancel requires the original run and a freshly read original
revision; the UI cannot supply a stale revision to force cancellation.

The [literal Notes compiler](../../services/hepta-session-host/src/notes_intent.rs)
treats text as one document's literal UTF-8 content. It does not interpret it as
shell commands, a model instruction, networking or a request to select another
application. The original writer binds exact payload bytes, operation identity,
subject, policy generation, destination, scope and expected predecessor before
FinalUse. The [Notes protocol](../../ui/core/src/notes.rs) binds:

- A 32-hex Session instance, nonzero task ID and 32-hex application incarnation.
- The destination derived from that exact tuple and the document's CAS revision.
- At most 4096 text bytes, 8192 request bytes and one retained operation receipt.

The application checks the target and revision in the same serialized mutation
path. Local edits participate in the same revision domain. A stale external or
local edit does not silently become a write at a newer revision. A persistent
receipt is published after the document/receipt snapshot is synchronized; a
storage error fences further changes rather than proving that nothing happened.

For loss, crash or cancellation, recover only the same original operation and
incarnation. The [recovery helper](../../support/ui/NOTES_DURABILITY.md) opens the
private state under its exclusive incarnation lock, exposes observe/state/receipt
reads and exact `acknowledge_terminal`, and refuses even a byte-identical
`replace_note` request. A new Notes process gets a new incarnation and cannot
adopt an old effect capability by opening a saved file. Exact receipt retirement
requires the original operation, payload digest and receipt digest; it does not
authorize another write. Killing a child, unlinking its lock or replaying text
is not recovery.

### Platform limits

The trusted product composition currently uses Linux private UDS/datagram
channels, original UID/PID checks and pidfds. Renderer portability does not
provide equivalent owner bootstrap or OS automation on Windows, macOS or a
physical Android/iOS handset. The [default observer](../../services/hepta-os/README.md)
has no generic input injection, desktop app launch, arbitrary file mutation,
screen-control or device-discovery API. Its optional
[CPU delivery view](../../services/hepta-os/CPU_DELIVERY.md) reads one retained
original delivery; it cannot allocate a new delivery or dispatch a budget change.

## 3. Android action contracts

### Read-only profile and non-authorizing intents

The [host adapter](../../support/android/device_organ.py) targets the existing
Pocket4 Digitalis/Droidloom Android cell. The original Runtime/operator selects
the host; neither a hostname nor the helper's self-report proves that binding.
The original helper must remain a pinned root-owned executable. Droidloom has
its own exact hash and explicitly permitted owner pin. Existing sudo/nsenter
and Android instrumentation capabilities are deployment inputs; the adapter
does not acquire them, enable ADB or change accessibility settings.

`qualify` performs fixed daemon status and helper status reads. `observe` adds
one explicitly named application's default-display observation, with
`accessibility_mode=none` and `with_png=false`. Its projection includes window
and screenshot/scope hashes without private UI text. It is a non-atomic
observation; numeric PIDs alone are explicitly not durable incarnation identity.
Every phase shares one deadline, and a post-submission timeout or malformed reply
remains unknown. Cleanup of a transport process is not proof of device cancellation.

`prepare_semantic_intent` accepts exact integer schema version 1, the reviewed
observation profile, exact-unique selector constraints and the full window/hash
binding. The only proposals are `click` and `set-text`; `commit-text` is explicitly
unconfigured. It performs no selector resolution, device I/O or grant issuance.
The read-only profile rejects all other helper entrypoints before source
measurement or privileged invocation, including the strict receiver operations.

This intent's `android_semantic_intent` / `set-text` format is not the strict
receiver's canonical `AndroidSetTextV1` / `set_text` operation. A caller must not
rename fields, substitute a fresh observation or silently promote the proposal
into an authorized request. The original owner prepares and authorizes the exact
strict operation separately.

### Strict observation, text effect and independent readback

The [strict receiver](../../support/android/receiver/README.md) extends the original
helper and `local.pocket4.actions.v2/.ActionRunner`. Its only effect is setting
one exact editor's text with native `ACTION_SET_TEXT`. The target must be a unique,
visible, enabled, non-password editable node supporting that native action.
Only an exact full resource ID in the expected package is allowed; no index,
substring, click ancestor, focus fallback, keyboard injection or accessibility
mode change is introduced.

`organ-observe` reads that target. `organ-set-text` and `organ-readback` consume
the same exact canonical payload and hash. Their target contract binds:

- Host boot UUID, Android init start ticks, mount/PID/time namespace identities.
- Application main PID, process start ticks and exact package.
- Real focused WindowManager token, activity, default display and bounds.
- Exact resource/class/bounds, prior text hash, node hash and native scope hash.
- Original operation/destination, canonical UTF-8 payload, at most 4096 text
  bytes, and an immutable deadline at most 30 seconds after observation.

The helper holds the original cell namespace descriptors; it does not discover
another cell between phases. Before the native effect, the receiver re-observes
cell/app/window/node/predecessor/scope and checks the deadline. This is not an
atomic transaction with the Android application. Changing cell, application,
window or target refuses the old operation instead of retargeting it.

The matching original Hepta sources are `codex-rs/hepta-memory/PRODUCTION_ANDROID_TEXT.md`
and `src/production_android*.rs` in the source-profile-selected Hepta checkout.
`ProductionAndroidTextTarget` uses destination-specific original FinalUse.
`OriginalRuntimeAndroidTextDevice` retains the original authenticated MCP peer,
live runtime and source verifier; it invokes the fixed helper once, with no
replacement client, credential discovery, automatic retry or reconnect. A job
ID is transport correlation, not a terminal operation receipt.

Immediate completion needs the exact native apply acknowledgement followed by
a distinct read-only `organ-readback` invocation with the same operation/payload
and target. Merely matching current text is not causal evidence. Lost reply,
timeout, cancellation or source revocation closes the effect lane and does not
permit a second attempt, a new operation ID, a renewed deadline or a fallback
legacy command. Readback may still report the same target's current state;
without a retained original causal receipt the original outcome remains
Indeterminate. An original source terminal receipt, if present, remains owned
by the original writer. This adapter does not add a replacement receipt ledger.

## 4. Legacy and unsupported actions

The pinned [legacy helper source](../../support/android/receiver/upstream/android_app.py)
and [original ActionRunner](../../support/android/receiver/upstream/ActionRunner.java)
contain the entries below. They stay under their pre-existing operator contract
and are not production organ actions in this profile. A backend being callable
under shell/operator authority is insufficient to add a new FinalUse destination.

| Legacy or proposed action | Existing mechanism | Organ status and missing contract |
| --- | --- | --- |
| `click`, `type-text`, legacy `set-text` | UiAutomation accessibility / focus-based paths; click may choose an ancestor | Read-only intent permits only a proposal for click/set-text. No strict original-owner click/type-text contract; use only the separately bound strict set-text path when qualified |
| `scroll-forward`, `scroll-backward` | Native accessibility scroll actions | Rejected by organ profile; no bound original operation, postcondition and recovery contract |
| `tap`, `swipe` | Existing shell coordinate input | Rejected; no new coordinate fallback or universal gesture action |
| `home`, `back`, `enter` | Existing keyevent injection | Rejected; no organ key action, implicit commit or confirmation |
| `visual-click`, `snapshot-tap` | Existing visual/window/snapshot helper paths | Rejected; visual helper preconditions alone do not supply original FinalUse or durable outcome recovery |
| `launch` | Existing package launcher resolution and `am start` | Rejected; no production organ application-launch grant or process-incarnation recovery contract |
| `dump`, `find`, `screenshot`, `apps`, `visual-find` | Existing helper observation/listing APIs | Not allowlisted in the bounded read-only organ profile; these may expose broader/private data than `observe` |
| `commit-text`, arbitrary shell, install/uninstall, permission changes | No selected production organ backend/contract | Unsupported; neither chat text nor a new connector creates these capabilities |
| Generic Windows/macOS desktop control, physical handset control, iOS control | No qualified product owner/transport in this source pair | Unsupported as a production product claim; sharing a Rust renderer does not close the platform boundary |

## 5. Validation and open gates

The host regression below performs no live device actions. It verifies exact
schema types, fixed read entrypoints, rejection of legacy and strict operations
at the read-only boundary, one-attempt behavior and bounded host child cleanup:

```sh
python3 -B -m unittest tests.workloads.android.test_device_organ
```

The [receiver regressions](../../tests/workloads/android/test_bound_receiver.py)
exercise canonical bytes, exact resource selection, immutable deadlines,
generation changes, independent readback and refusal of synthesized success.
The Notes and native text documents link their original-owner and application
tests. Host fixtures do not establish any of the production gates below.

| Gate | Required evidence before enabling the action |
| --- | --- |
| Original Desktop owner | Actual registered Root/UI lifetime, original principal/session/profile, original same-thread App Server, exact capabilities and trusted package source |
| Original Notes writer | Original issuer/checkpoint/current authority, exact target/revision, FinalUse entry, persisted application receipt and original durable terminal acknowledgement; unknown/revoke/restart cases retain identity |
| Original Android session | Retained authenticated Runtime peer and live runtime actually injected into the original owner; live verifier of original host/tool/helper/Droidloom/APK/signer/cell bindings |
| Strict Android receiver | Compiled candidate, original signer equality, installed-source qualification and actual native observation for the selected harmless exact editor; old helper/APK presence is not this evidence |
| Android effect and recovery | One original authorized Chinese-text operation, distinct readback and original durable status; stale window/cell/app, expiry, cancellation, revocation, lost reply and restart must produce no late or repeated effect |
| Additional actions/platforms | A real bounded backend plus action-specific permission, target identity, postcondition and cancellation/recovery contract, then original-owner qualification. No alias to a legacy command and no synthetic universal action |

Update this matrix, the owning adapter contract and meaningful boundary tests
whenever an action is added, removed or changes identity/permission semantics.
Record deployment evidence with the actual source profile and installed hashes.
Do not change a source-only status to production based on compilation, mock
passes, matching UI text, a Runtime job ACK or an unrelated action's success.
