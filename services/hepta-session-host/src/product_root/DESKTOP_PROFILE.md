# Original Notes and Calculator Root profile

## Status and exact scope

This page describes the explicit `notes_calculator_v1` source successor.
The selected original owner is authoritative in the
[shared source contract](../../../../support/ui/HEPTA_SHARED_PRESENTER.json);
[DEPENDENCIES](../../../../support/ui/DEPENDENCIES.md) records the matching
Cargo entry points, locks and verification procedure. The published source
pair is [Desktop f5](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/commit/f5fbc7e1a533e5bec588575ab56312a3203f6d8c)
and [Hepta 14](https://github.com/TrillionniumFoundation/hepta-private-ci/commit/14e2d89b3367232ec5dbe6187f09feed0f2b68d3).
The original joint Agentd CLI and sealed deployment loader are included.

The [actual source checkpoint](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/d27ae5dede3ebd91614b40fa6a9b47f5425f955e/results/integration/2026-11-03-organ-followup/joint-desktop-canonical14-source-20261104/README.md)
records Rust/Cargo 1.96 generation of the three consuming locks, preservation
of the other three locks, all 39 dependency declarations and six fresh
locked/offline metadata graphs. Original source/cache checks passed. The normal and optimized dependency
regressions each passed 41 cases. The published full
tree equals the clean local source-check tree; canonical checkout was then
verified clean. These checks establish source and dependency selection, not
a new joint product build, installation, GUI effect or recovery result.

The [original owner's execution ledger](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/14e2d89b3367232ec5dbe6187f09feed0f2b68d3/codex-rs/hepta-agentd/DESKTOP_ORGAN_CANDIDATE.md#executed-evidence-and-remaining-gates)
retains the actual 26a four-package failures, the exact 47 custody repair and
the separate 857d/92a seed component. Earlier App/Session evidence belongs to
Desktop 5a and its c2 successor. Neither those results nor the previously
installed fd/a39 Notes baseline qualify this later joint Root integration.
Fresh builds and the real original human/Core/Notes/Calculator sequence must
record their own exact source pair and artifacts.

The earlier API review used Hepta
`c1f336cf50cc6c3bcf47da059e767273499506f0`
(tree `7191691322d070f97b885487eeb59c5936546b18`). Its then-pending CLI and
a39 dependency selection are historical checkpoint limitations; they are
not the current source selection. The active contract above now binds the
reviewed joint implementation and generated locks.

This remains a finite original-owner session with the existing maximum
300,000 ms lifetime. Continuous reauthorization and epoch continuation are
not implemented. The joint profile has no qualified restart/recovery path;
the old Notes-only recovery entry cannot be used for it.

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

The CLI and shared pin/lock prerequisites are now in the selected source.
Run the original checks on that exact clean pair and retain their actual
results; the following commands are instructions, not passed-run claims:

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

Remaining product and verification gates:

- Build and test the selected pair's original owner, Objective, production
  Agentd binary and Desktop Root entry using the original features and locks.
  Preserve the full 26a red results and the narrower 47 repair from the owner
  ledger; a selected pass cannot replace a complete package result.
- Keep the cross-implementation raw Calculator Applied/readback/ACK fixture
  and original typed terminal/retirement checks in component validation.
  Their existing fixture results do not establish an installed Root grant
  or a real application effect.
- Run a fresh isolated native original-owner session with the explicit new
  thread/profile, actual Notes and Calculator Apps, original human/Core
  callback, checked effect, independent readback and causal receipt.
- Exercise same-turn cross-target refusal and Unknown observation without
  retry. Confirm actual Session lifetime closes idle Apps. Retain partial
  startup and failure receipts without inventing successful effects.
- Bind each build, installation and run to its own source pair, package,
  binary and resource identities. Preserve the previous installed fd/a39
  baseline and its failures. Joint recovery and continuous authority renewal
  remain separate unimplemented or unqualified conditions.
