# Original owner, live text thread and actual Notes process recovery

These are actual Linux-host component executions on 2026-10-24. The original
Root/issuer deployment, a real authenticated model session, the installed
Makepad product, native-kernel effects and physical devices remain separate
acceptance gates. Test authority and model fixtures are explicitly identified.

## Results

| Execution | Actual result | Original log |
| --- | --- | --- |
| AuthBus package | 29 passed, 0 skipped | [AuthBus](hepta-v2-step-1.log) |
| Explicit previous Notes original-store recovery | 2 passed; 374 outside the selected filter | [Memory](hepta-v2-step-2.log) |
| Agentd library | 336 passed, 32 skipped by the original configuration | [Agentd](hepta-v5-step-1.log) |
| Real Agentd/App Server text integration | 2 passed, 0 skipped; signed ingress and model responses are fixtures | [Text](hepta-v5-step-2.log) |
| Actual Notes App/Session/helper crash and original owner reopen | Explicit opt-in test passed; original source authority is a fixture | [Crash execution](notes-original-owner-crash-v2/test.log) |
| Rust 1.96 Session/App/helper build with the selected original dependency patches | Passed with the committed package constraints, including Tokio 1.53.3 | [Build](ui-v7-notes-step-1.log) |

The 32 skipped library cases are not passes. The selected opt-in Notes crash
case was subsequently invoked explicitly; its fixture authority does not become
production authority because the application processes are real.

## Source binding

An independent temporary Git index captured the actual Hepta working bytes
without changing the checkout's own index:

- Actual complete source tree: `bb84b4012922dc8b905cb2bc602c403dc699ac37`.
- Actual `codex-rs` subtree: `86c615d836d096e32ee96f2b1c20937bfa9ec2a0`.
- Published candidate: [Hepta 332d8b448758ad45e516a208d940f2358f888e32](https://github.com/TrillionniumFoundation/hepta-private-ci/commit/332d8b448758ad45e516a208d940f2358f888e32),
  complete tree `9d5a5c5603e86da23e6c8b6f7426e50ec160fac2`.
- Its `codex-rs` subtree is exactly the same as the executed subtree. The later
  difference is the native accessibility window traversal, outside this backend
  qualification. This record does not claim that later UI code ran here.

The backend directory retains its original checkout HEAD `6305d52b...` plus
the explicitly applied and hash-checked candidate patches. The working-tree
identity above, rather than that old HEAD, identifies the executed sources.
[source-and-evidence.json](source-and-evidence.json) records the actual capture
and hashes of every original log retained here.

The three companion binaries were built from the separately patched Desktop
integration directory. Their exact identities are in the actual application
receipt below. The final clean-checkout release-pair build and installed-product
acceptance are not replaced by this component execution.

## Actual effect, crash and retirement sequence

The [machine-readable receipt](notes-original-owner-crash-v2/qualification.json)
contains the independently returned application receipt, original source cuts,
application identities and both retirement responses. The test:

1. Dispatches one real Notes replacement through the original SQLite writer and
   original FinalUse route, with an explicitly test-only authority/issuer.
2. Loses the effect reply after the complete frame is written. The real app
   persists revision 1 and its pending receipt; the original writer retains
   `Indeterminate`.
3. Signals only the retained Notes child pidfd. The original Session observes
   and reaps that child before the old document lock can be opened.
4. Closes every original writer/store handle and reopens with the retained
   exact current cut. A new Session/App incarnation has an empty document and
   reports no previous receipt.
5. Attaches only the explicitly selected original operation/old target through
   a verified, sealed helper executable and private inherited channel. Its
   independent application readback moves the original writer to `Committed`.
6. Loses the first retirement reply after the helper has durably retired the
   receipt. After that same helper is killed and reaped, its replacement returns
   `already_released` for the exact original acknowledgement.

The assertions observe **one effect dispatch, one fixture issuer request and
two helper starts**. Recovery registers no old effects dispatcher, makes no
new grant request, leaves the current incarnation unchanged and never repeats
the old effect. Saved Chinese text is document-state evidence; it is not a
glyph, IME, pixel or physical-display qualification.

| Actual executable | SHA256 |
| --- | --- |
| `trill-session` | `5f5765f3be78d2dd165959f2c6dd2beff1f4b5e7e3445e3e71c2fa6301dda2e0` |
| `trill-app-window` | `fa701f706481f87118c7dacc93b6ea23fd88b8b44bcbdf11b2d68d526bf23aa0` |
| `trill-notes-recovery` | `ee15aec6baa331bd6cfe1bbe72b2ec752920df7cfe165ecf386cbb79f7bc3b16` |

## Retained failures and resulting repairs

- [Initial original SDK build](ui-v2-step-0.log): the fixed Script/Widget
  parser rejected newly introduced field syntax. The repair uses simple field
  type identifiers and ordinary methods; the original SDK is unchanged.
- [Initial dependency resolution](ui-v3-default-bins.log): a consuming Cargo
  workspace did not inherit Hepta's patched WebSocket crates. Both product
  roots now explicitly select the original patches.
- [Original keyring resolution](ui-v6-notes-step-0.log): the old exact Tokio
  constraint prevented the original zbus 6 encrypted-backend patch. The
  [resolved repair](ui-v7-notes-step-0.log) selects the original patched backend
  and the original Hepta lock's Tokio version.
- [Initial text run](hepta-v3-step-1.log): attaching a real, live zero-turn
  thread failed because its lazy rollout was not yet persisted. The repair
  goes through that same original Core thread/store, retains its thread/session
  identity and starts no model call merely to attach. The passing rerun is
  retained separately.
- [Recovery helper compilation](hepta-v2-step-3.log) and
  [crash-test compilation](hepta-v4-lib-step-0.log): method and assertion macro
  ambiguities were fixed explicitly. No runtime assertion was removed.

Further unresolved work includes actual deployment authority, human/session
authentication, orphaned or rejected text-reference recovery, initial history
projection, actual native input/accessibility and installed-product acceptance.
None is made successful by this evidence publication.
