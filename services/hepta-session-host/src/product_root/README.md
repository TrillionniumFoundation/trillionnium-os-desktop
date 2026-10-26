# Original Linux product Root entry

This module is the finite first-deployment entry for the original Hepta Notes
product. It is built by the `product-root` feature of `hepta-session-host` as
`hepta-desktop-root`. It does not replace the existing open-only authority
launcher. A new short `/var/lib/trill/<name>` prefix is required; an existing or
partial prefix is an error and is never treated as a recovery bootstrap.

## Operator input

Fresh creation uses `initialize --config <absolute-file>`. Exact existing-state
recovery uses the separately specified [RECOVERY](RECOVERY.md) command; no
existing prefix is accepted by initialize. The input must be a
Root0600, single-link regular file under a Root0700 directory. Its ancestors,
installed programs, provider script and public source inputs must be physical,
Root-owned, and reject shared writes. Executable paths must resolve directly to
the installed ELF, including the Python interpreter; `/usr/bin/python3.12` is an
example on a matching installation, while a symlink is refused.

The JSON schema is `trill.original-desktop-root.initialize.v1`, with no unknown
fields:

| Field | Meaning |
| --- | --- |
| `prefix` | New direct child of `/var/lib/trill`; 1–12 lowercase letters/digits/hyphens |
| `uid`, `gid` | Explicit actual non-Root owner for Agentd, Session and native UI |
| `programs` | Absolute paths: `agentd`, `app_server`, `authority_host`, `session`, `shell`, `app_window`, `python`, `human_provider` |
| `sources` | Actual Root-owned files: `runtime_body`, `preferences`, `prompt_registry`, `sdk`, `source_freeze` |
| `makepad_resources` | Installed canonical Root-owned Makepad resource directory |
| `environment` | Bounded original display inputs described below |
| `locale` | `zh-CN` or `en-US`, equal to the consumed preference document |
| `lifetime_ms` | Original issuer maximum, 120000–300000; writer and human remain within the actual lease |
| `grant_lifetime_ms` | Explicit nonzero Notes maximum, at most 30000 and no greater than lifetime |

The expected package layout is configurable through those absolute paths.
Session must be installed beside its original `trill-app-window`; the entry
refuses a different sibling. It never discovers an older Codex on PATH.
`runtime_body` must hash to the actual installed Agentd ELF. The SDK and source
freeze files are real package inputs, not caller-supplied digest strings.

The only accepted display environment keys are `DISPLAY`, `WAYLAND_DISPLAY`,
`XDG_RUNTIME_DIR`, `DBUS_SESSION_BUS_ADDRESS`, `XAUTHORITY`, `XMODIFIERS`, `LANG`,
and `LC_ALL`. When supplied, `XMODIFIERS` must equal the original IBus selector
`@im=ibus`. The actual private owner runtime directory and an explicit display
are required. Initialize refuses an existing `trillionnium-ui/session.sock`. Recovery proves
original Session retirement and leaves stale handling to original Session
startup locking; it never overwrites a live endpoint. The entry
creates private owner home/state directories and supplies the installed
Makepad resources and explicit draft recovery setting. Inherited provider
environment values are cleared before any runtime threads exist.

The public preference document is exactly:

```json
{
  "schema": "trill.original-notes-preferences.v1",
  "locale": "zh-CN",
  "model": "qwen38-flash-next-uc",
  "model_provider": "hepta_local"
}
```

The public prompt document contains only `schema` equal to
`trill.original-notes-prompts.v1` and `developer_instructions`, a nonempty UTF-8
string of at most 512 bytes without NUL. It is actually supplied through the
original ThreadStart API. The product's finite public provider is
`http://127.0.0.1:18083/v1`, Responses, without OpenAI authentication. Preferences
must name that exact profile. There is no model or provider fallback.

The newly created Core home also receives the original finite Notes execution
configuration and an `environments.toml` that disables both the default and
local execution environments. Shell, general agent, browser, computer, plugin,
MCP and other Core tool sources are disabled. The three original Notes dynamic
tools retain their existing Root authority path. The schema-2 seed records the
exact configuration bytes and execution profile in its model tuple. Original
Start and Resume must report Never/read-only permissions, and the effective
Core config is independently observed. Old schema-1 seeds and changed config
files are refused; no migration creates a replacement thread automatically.

## Development and module ownership

| Module | Responsibility |
| --- | --- |
| `config`, `fs` | Bounded explicit inputs and physical file custody |
| `geometry`, `geometry_existing` | Disjoint fresh creation and exact existing bind/source/UID custody |
| `recovery`, `recovery_authority`, `recovery_sockets` | One same-boot original owner handoff, actual lease window and stale-only Root rendezvous retirement |
| `process`, `supervisor` | Held real children, one original driver spawn and original stop/reap |
| `seed` | Actual original Core Start/Resume, observed model/catalog receipt and graceful seed shutdown |
| `packet`, `session` | Same-Root anonymous pair, actual Session and credential-checked metadata peek |
| `authority` | Actual original Root initialization, leases, writer proof and frozen source bindings |
| `replay` | Original evidence-store empty frontier, checkpoint and actual public issuer trust |
| `human` | Trusted provider child, exact receipt/hash and one actual held login-leader FD |
| `mod` | Retained original Root composition and final native launch |

Changes must preserve the original authority owners and closed caller inventory.
Do not add a second effect ledger, transcript, request-ID table, clock, key
constructor, grant fallback, dynamic catalog repair, or lifecycle JSON writer.
An uncertain spawn consumes the one-spawn wrapper. Restart cannot reuse inherited
FD numbers. Additional startup/recovery modes need their own explicit contract.

## Technical sequence

1. Validate custody and create a separate Root:peer runtime parent mode02710
   for all five original Root lanes and the native human text lane; the per-Agent
   control parent remains its original Root02750 after handoff. Create the new
   dedicated geometry and actual bind
   identity. Use original `FleetRegistry::initialize/register`; no serialized
   lifecycle transition is written by this module.
2. In the same genuinely new Core home, consume the public preferences/prompts,
   start the installed same-source AppServer ELF, and call original ThreadStart
   with the fixed Notes catalog. Immediate Resume materializes SessionMeta.
   Stop and reap that seed owner and remove only its verified temporary aliases.
   This phase sends no user input or model turn and precedes the Session budget.
3. Compute the real empty AuthBus replay frontier with the original evidence
   store, initialize generation one with that digest, write the independent
   owner checkpoint, and await the original pool close.
4. Create the Notes pair in this Root process and enable SO_PASSCRED before
   spawning the actual non-Root Session. Peek only the metadata reservation.
   Exact kernel PID/UID/GID, actual held birth, nonce, target, truncation flags,
   unknown/duplicate fields and zero rights are checked. The original packet
   stays queued and SO_PASSCRED remains enabled.
5. Delegate one spawn to original Supervisor/UnixProcessDriver. Its retained
   Child is pinned before any PID can recycle. Read actual dropped credentials
   and birth. The original Supervisor remains ticking and owns health, leases,
   stopping and reaping, with its original time limits.
6. Initialize the original protected Root issuer and register the actual new
   writer through the original lease/issuer factories. Key bytes come from that
   initializer. The three finite policies use original Objective/text scope
   functions and the actual Reserved Notes target.
7. Prepare fresh cognitive state with physical material through the original
   Root factory, then its bounded filesystem handoff. The same retained Root
   instance consumes the original reservation and seals the inherited read-only
   deployment. Peek, registration, consume and handoff share one cumulative
   30-second episode; expiry cannot rearm it.
8. Capture the actual local logind session using the installed Root provider
   child. Verify its kernel credentials, exact public receipt/profile hash and
   one held login leader. The original Root independently verifies and retains
   that same physical login before launching the actual Makepad shell.
   This model product explicitly selects the Shell's original-thread Notes
   presentation. It hides the separate literal Objective buttons; saved-result
   queries belong to the original chat tools, not a new Session target.
9. The same prepared Root first completes native child registration and binds
   all five real authority listeners with the original custody checks. Only
   its successful ready callback sends the held bootstrap once to Agentd,
   using the remaining cumulative deadline. The listeners are already open
   when Agentd performs its original single bounded connect; no retry or
   synthetic readiness file substitutes for the actual bind. A partial bind
   never invokes the callback. A callback error closes only this invocation's
   retained socket guards and does not retry a possibly delivered handoff.
   Serve through that same prepared Root,
   without reopening exclusive issuer or clock owners.
   The sealed model mode includes the mandatory typed seed.
   Agentd resumes on its actual tool connection and compares original thread,
   session, model, provider, catalog and metadata before accepting callbacks.
   Root-authenticated human ingress, original writer and exact operation
   receipts remain required for any Notes effect.

The canonical model tuple digest is supplied by
`NotesThreadSeedReceipt::model_tuple_digest`; literal mode keeps its existing
no-model identity. Saving a seed receipt alone is not a final Resume proof.

## Failures, cleanup and evidence limits

Every error leaves the prefix and administrative evidence in place. A rerun
never overwrites it or reinitializes authority. A lost Start reply does not
create a replacement thread. A failed/uncertain spawn never grants a second
inheritance attempt. Original children are stopped and reaped only through
their held handles and original Supervisor. No numeric PID loaded from a file
is adopted or signalled. The dedicated bind is normally unmounted only after
owned resources close; a busy mount remains visible and is never force/lazily
detached. Product data is never recursively deleted by this entry.

A Session or native Notes app may have local drafts. Existing user sessions,
services, model transport and displays are not stopped. The entry refuses an
existing Session socket; it does not use Root privileges to remove arbitrary
nodes in a user's runtime directory. Explicit cleanup must inspect this
invocation's retained evidence and act as the owning user for stale user IPC.

`actual-artifacts.json`, the original seed, writer proof, registration,
provider receipt and `actual-composition.json` describe observed inputs.
They are not grants or a production-ready certificate. Bootstrap sends no
model turn. Acceptance still requires the real installed final package, Root,
human input, real model and original-thread operation/result receipts.
SQLite pool shutdown is not a Root crash or a power-loss test.

## Verification

The packet and inheritance tests use real Unix kernel credentials and FD
lifetimes. They qualify transport rejection/cleanup only, never Root, logind,
model, signing, or product deployment. Original-owner tests remain in Hepta
and run through its `just test` workflow. The final product entry needs a
same-source package/typecheck and actual installed acceptance after source
freeze; no fixture or zero-selected test result satisfies it.

Human capture uses the actual remaining writer lease, and the returned profile
expiry must not exceed that original writer expiry. The provider and Hepta
native launcher independently repeat the same cap; no field renews authority.
