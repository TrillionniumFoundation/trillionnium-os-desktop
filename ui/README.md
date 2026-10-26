# Linux host UI workspace

This workspace has five real packages. It is developed on a Linux host
compositor; it is not an Asterinas compositor or a phone hardware port.

| Package entry | State and authority owner | Technical and development contracts |
| --- | --- | --- |
| [core](core/README.md) | Bounded public/private types and atomic Notes document store | [Session IPC](../support/ui/SESSION_IPC.md), [Notes persistence](../support/ui/NOTES_PERSISTENCE.md) |
| [session](session/README.md) | Child lifetime, generations, fair public IPC and explicit private bootstrap | [IPC deadlines and lifecycle](../support/ui/SESSION_IPC.md), [trusted startup](../support/ui/NOTES_ORGAN.md) |
| [broker](broker/README.md) | Default-deny renderer boundary; separate private Notes/X11 destinations | [integration contracts](../support/ui/INTEGRATION_CONTRACTS.md), [X11](../support/ui/DESKTOP_X11.md) |
| [app-window](app-window/README.md) | GUI-thread Notes text/revision, document commits and exact application receipts | [persistence and recovery](../support/ui/NOTES_PERSISTENCE.md) |
| [shell](shell/README.md) | Rendering, local drafts, context and safe observation projections | [workspace model](../support/ui/CHAT_WORKSPACE.md), [signed-request inbox](../support/ui/OBJECTIVE_INBOX.md) |

Session handles an entire input frame within 500 ms; it does not renew the
deadline for each byte. The public interface does not export private effect
descriptors or mint a grant. Notes commits document text, revision and a pending
application receipt together before Applied. Timeout remains unknown, requiring
independent recovery rather than effect replay. Original Hepta owns its separate
authorization, SQLite operation journal, Current publication and receipt retirement.

From the repository root, with the dependencies in the [host runbook](../support/ui/RUN.md):

```sh
cargo +1.88.0 build --manifest-path ui/Cargo.toml --workspace --bins --locked -j 2
cargo +1.88.0 test --manifest-path ui/Cargo.toml --workspace --locked -j 2
```

The runbook names the full host gate, isolated compositor tests and separate
original-owner tests. Individual package unit tests do not establish GUI,
production authority or native kernel qualification. When `CARGO_TARGET_DIR` is
set, use its actual `debug` directory for binary-consuming tests.

The [2026-10-26 documentation supplement](../docs/agents/MODULE_DOCUMENTATION_2026_10_26.md)
separates the `d3ae4b9a` kernel reception from the `85425721`/`fef6a641` host and
isolated GUI receipts. These are source-bound results, not passes for every later
documentation or integration commit. This shared manual complements the five
package entries; it does not claim two independent complete manuals per crate.
