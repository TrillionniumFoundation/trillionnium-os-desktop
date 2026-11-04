# Original four-package Hepta execution at 26a46e3f

Actual source: `26a46e3fe763b53e1f0362793701f112383a72fa`, tree
`2175f198948308c3a2f9d61f8282bc179669e798`. All four original package commands
used Rust 1.96.0 and the existing `just test` / nextest configuration, with
`--locked --offline --test-threads 1`. Each command records the same clean
source before and after execution. No retry count, deadline or original
assertion was relaxed.

| Original package | Passed | Failed | Skipped | Command exit |
| --- | ---: | ---: | ---: | ---: |
| codex-hepta-objective | 66 | 0 | 2 | 0 |
| codex-hepta-memory | 399 | 1 | 13 | 100 |
| codex-hepta-agentd | 546 | 1 | 60 | 100 |
| codex-app-server | 1,315 | 16 | 2 | 100 |

All passes occurred on their first attempt. The original failures retained
both attempts under the existing automatic retry policy; there were no flaky
passes. Agentd reports one slow passing case. Skipped and nested fixture
processes are not added to these distinct top-level pass counts.

The original [pipeline result](pipeline/result.json) is failed after all four
steps completed. Its [authoritative process status](pipeline/process-status.json)
records job `1a1a397dd99-96a-7709`, exit 1, complete output and no outer timeout
or cancellation. The command series took 3,320.695 seconds. This completed
failed execution remains failed after later fixes or additional prerequisites.

## Findings retained from the original logs

The Memory federation truncation case observes zero completed peers where
sixteen are required. Its two-second product budget and all assertions remain
unchanged. The log does not identify one unique stage or peer cause. The three
new Notes/Calculator shared-turn writer/fence cases passed on their first
attempt. See [Memory result](memory/result.json) and [full log](memory/stderr.log).

The Agentd custody case reaches its final lock-acquisition assertion before
the physical file lock becomes available. A separate test-only successor
observes that actual release within the original one-second deadline; it has
its own validation record. It does not change this execution into a full
package pass. See [Agentd result](agentd/result.json), [full log](agentd/stderr.log)
and [root review](root-review/agentd-log-review-26a.json).

App Server has fourteen failures with a missing cross-package fixture binary
in their actual output: four code-mode-host-related cases, four requiring the
original `codex` executable, and six requiring `test_stdio_server`. Two of the
four code-mode cases fail downstream assertions after explicit host ENOENT;
they are not classified solely from the assertion text. Correctly building
and binding those original executables requires its own later selected
execution. No production parser change or relaxed test is implied.

The other two App Server failures concern the original owned command tree
remaining observable after disconnect, and a cold-resumed worker's parent
ThreadId mismatch. They remain distinct from missing binary prerequisites.
The new three parent signal tests and two original drain tests passed in this
full package. See [App Server result](appserver/result.json), [full original
log](appserver/stderr.log), [failure navigation](root-review/appserver-failure-index.json),
[root log review](root-review/appserver-log-review-26a.json) and the bounded
[static command-child review](root-review/command-child-static-review.json).

## Original bytes and qualification

[The source index](source-index.json) binds each archived file to its bytes,
SHA256 and source. Original file responses and immutable native SDK payloads
are retained in `transport/`. The complete 404,859-byte App Server stderr was
rebuilt from seven contiguous chunks of the same file version; every retained
native payload page and both levels of SHA256 were independently checked.
Its zero-byte stdout is recorded by the original completed command receipt;
this archive does not claim a separate stdout read.

This directory proves the recorded original package executions and preserves
their failures. It does not qualify the later canonical publication commit,
the mixed-source seed component, an installed joint Desktop product, user
admission, an actual model turn, application effect/readback, durable terminal,
restart reconciliation, native G2 or Android device execution.
