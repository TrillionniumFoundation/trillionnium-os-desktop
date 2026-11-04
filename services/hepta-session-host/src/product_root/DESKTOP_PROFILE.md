# Original Notes and Calculator Root profile

## Status and exact scope

This is the source integration checkpoint for the explicit
`notes_calculator_v1` successor. It is separate from the frozen Desktop
`fd8d56c52b971c2d5d0e6430f296803b43ef60a3` / Hepta
`a39a0871d9601ffccb5e0d95d8f39d54b3a63360` product pair.

The App/Session parent is Desktop
`c2c369836e87e9cf27b4dc9aa8b7446e85efdf90`
(tree `56f2672a7eeca971870e616762b0a730bec2d32b`).
Its preceding `5a8684cc4591a4163c162f198b4121ca4cfc6ebc` tree has actual
Rust 1.96 core and default App/Session component receipts. Those receipts do
not validate this later Root integration, a native Calculator window, or an
original owner/model/effect closed loop.

The actual original-owner API reviewed for this checkpoint is Hepta
`c1f336cf50cc6c3bcf47da059e767273499506f0`
(tree `7191691322d070f97b885487eeb59c5936546b18`). Its Root source is saved,
but the joint Agentd CLI, final shared dependency pin/locks, Cargo checks and
joint runtime acceptance are not complete at this checkpoint. The current
Cargo manifests still select the frozen a39 dependency. This source checkpoint
must not be installed or described as a buildable, qualified new pair until
the explicit pending steps below are completed.

## Selection and compatibility

| Entry | Input schema | Required profile | Thread and targets |
| --- | --- | --- | --- |
| `initialize` | `trill.original-desktop-root.initialize.v1` | Absent | Existing three-tool Notes contract |
| `initialize-desktop` | `trill.original-desktop-root.initialize.v2` | `notes_calculator_v1` | New six-tool original Core thread; real Notes task 1 and Calculator task 2 |
| `recover` | Existing v1 Notes input | Absent | Existing exact Notes recovery protocol |

The v2 input has the same physical file custody, actual UID/GID, installed
programs, source files, private geometry, display inputs, lease bounds and
fresh-prefix requirements described in [README](README.md). It additionally
requires `"profile": "notes_calculator_v1"`. A different schema/profile
combination is refused before product creation. Each fresh CLI entry checks
its selected profile. The old recovery entry refuses v2; it cannot change an
old thread catalog or convert an old Notes receipt into a Calculator receipt.

The new preference schema is `trill.original-desktop-preferences.v1`; its
locale/model/provider fields and finite provider selection remain explicit.
The new prompt schema is `trill.original-desktop-prompts.v1`, with the same
nonempty, bounded `developer_instructions` field. Their actual bytes are
frozen in the original bindings. The old Notes schemas are accepted only by
the old entry.

The new seed is produced by the original `seed_original_desktop_thread` and
uses `ORIGINAL_DESKTOP_THREAD_EXECUTION_CONFIG` and
`ORIGINAL_DESKTOP_THREAD_ENVIRONMENTS_CONFIG`. The original metadata receipt
has its own model-tuple domain, catalog and execution profile. The adapter
retains a typed Notes/Desktop enum in memory. It never deserializes these
structurally similar receipts through an untagged enum.

## Original ownership and startup

The wire, identity, arithmetic and causal receipt contract is
[CALCULATOR_PROTOCOL](../../../../ui/core/CALCULATOR_PROTOCOL.md). The sequence
is one bounded Session/Root episode:

1. Root starts its actual non-Root Session with
   `--desktop-root-bootstrap-stdin` on the original unnamed datagram pair,
   with SO_PASSCRED enabled before spawn. Session stages both actual Apps.
2. Root peeks the one `desktop_targets_reserved` metadata packet and checks
   the held pidfd, real credentials, actual process birth, strict canonical
   target types and the joint profile. The metadata contains no grant or
   transferred application descriptors.
3. Root provisions four exact policies in the same original issuer:
   Objective, the new original Text route, the actual Notes target and the
   actual Calculator target. Existing original writer registration and its
   durable outbox/ledger remain the sole authority path. Notes uses the
   original Notes FinalUse consumer; Calculator uses the original Device
   FinalUse consumer.
4. The same original `PreparedHostAuthoritySession` consumes the reservation
   through `with_desktop_startup_from_session_before(profile, bootstrap,
   session_pidfd, deployment, end)`. It rechecks the real owner and Session,
   admits both targets against the existing exact policies and seals the
   distinct deployment. This is not a Desktop-created permit.
5. Agentd recovers its one protected original writer, activates the exact
   reservation and receives Notes two-FD offer/ACK followed by Calculator
   two-FD offer/ACK. Original host installation completes only after both
   successful exchanges. Partial startup does not claim rollback of a
   published effect.
6. The existing original logind human capability and Text route launch the
   native conversation. Model arguments still have no authority. The new
   original Objective profile `organ.desktop.thread-tool.v1` compiles either
   finite action; both targets share the original durable one-effect-per-turn
   fence. Unknown outcomes permit observation/readback only.

The joint Agentd arguments are `--root-production-profile desktop`,
`--desktop-production-handoff-fd`, `--desktop-thread-deployment-fd` and
`--desktop-session-pidfd`. Original Root handoff, control, App Server,
UID/GID, lifetime, AuthBus and Objective arguments retain their meaning.
The joint path creates no legacy Notes UI listener and supplies no legacy
Notes handoff/UI/listener arguments.

The native Shell retains `--notes-ui original-thread`. Despite its historical
name, this option only hides and rejects the old literal Notes controls; the
actual chat uses the original Text adapter and selected Core route. It does
not choose target identity, a tool catalog or a grant. Calculator is never
registered as Notes.

## Frozen data and files

The original Root profile schema is
`hepta.root.desktop_launch_profile.v1`, with profile
`notes_calculator_v1`, grant lifetime, original
`original_desktop_thread_tool_v1` interaction, original route/seed and exactly
these ten binding fields:

| Binding | Source |
| --- | --- |
| `principal_scope` | Explicit `organ.desktop.notes_calculator` |
| `principal_scope_digest` | Distinct versioned scope domain, actual agent and original signer |
| `issuer_id` | Same actual original Root signer |
| `policy_generation` | Explicit original policy generation |
| `locale` | Validated preference/Root locale |
| `runtime_body_digest` | Actual installed original Agentd input |
| `preference_state_digest` | Actual new profile preference file |
| `model_tuple_digest` | Original Desktop seed's validated observed tuple |
| `prompt_registry_digest` | Actual new profile prompt file |
| `artifact_set_digest` | Actual package artifact set |

The profile rejects unknown fields and has no previous-recovery object.
Its on-disk profile is `desktop-startup.json`; the Objective profile is
`desktop-thread-profile.json`. The composition receipt uses
`trill.original-desktop-root.composition.v2`, an explicit profile and both
actual target identities. It states that model/effect acceptance still
requires actual original runtime receipts.

Old v1 Notes profile, Objective filename, seed shape and composition fields
retain their old meanings. Historical evidence remains in place.

## Development and verification

| File | New responsibility |
| --- | --- |
| `config.rs` | Exact schema/profile selection and refusal of joint Notes recovery |
| `seed.rs` | Explicit typed original seed and new finite configuration |
| `session.rs`, `session_profile_tests.rs` | Joint wire-to-original-type boundary; same real Session custody |
| `authority.rs` | Same original issuer with both exact App policies and new Objective profile |
| `mod.rs` | Explicit Agentd FD routing, original prepared factory, separate composition receipt |
| `../bin/hepta-desktop-root.rs` | Distinct `initialize-desktop` action |

After the owner CLI and one exact shared new Hepta pin/lock graph exist, run:

```sh
cargo test --manifest-path services/hepta-session-host/Cargo.toml \
  --locked --features product-root --bin hepta-desktop-root
cargo clippy --manifest-path services/hepta-session-host/Cargo.toml \
  --locked --features product-root --all-targets -- -D warnings
cargo test --manifest-path ui/Cargo.toml --locked -p trill-ui-core
cargo test --manifest-path ui/Cargo.toml --locked \
  -p trill-app-window -p trill-session
python3 -I -B support/docs/check_modules.py
```

The new Root tests are ordinary schema, profile and identity-boundary cases.
They do not start an issuer, model or real application. Existing real-owned
process and App/Session tests retain their separate scopes. Rustfmt can check
syntax without resolving dependencies; it is not a Rust type check.

Pending before a new pair can be selected:

- Complete and review the original Agentd CLI/loader against the actual
  sealed joint deployment and held Session pidfd.
- Pin every relevant Desktop workspace to one reviewed new original Hepta
  commit, regenerate the original lock graph and pass meaningful original
  owner, Objective and Root contract tests.
- Verify the original writer's raw Calculator Applied/readback/ACK fixture
  across implementations and retain its durable terminal/retirement proof.
- Run a fresh isolated native original-owner session with the explicit new
  thread/profile, actual Notes and Calculator Apps, original human/Core
  callback, checked effect, independent readback and causal receipt.
- Exercise same-turn cross-target refusal and Unknown observation without
  retry. Confirm actual Session lifetime closes idle Apps. Retain partial
  startup and failure receipts without inventing successful effects.
- Review the resulting new exact pair before any deployment or change to
  the frozen product. Joint recovery remains unsupported until separately
  implemented and verified.
