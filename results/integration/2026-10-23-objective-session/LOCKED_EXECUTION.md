# Original locked packages and final owner-start gate

## Scope and exact source

Initial published source is Desktop `940313d876481c6effc14ad783444e9e7b9d275a`,
tree `2e94a12b8500ddca1d775712f0ffa7fbe86046d8`. The source verification receipt
compares 75 locally materialized source/document/lock files to their exact Git
blob identities. Only eight dependency test files were absent; neither tested
package compiles those dependency test targets.

The final source adds the mandatory original-owner `mark_send_started` call,
one real-UDS regression, and its contract documentation. `send-start-green.json`
records all final source SHA-256 values before and after execution. Source and
both original Cargo lockfiles stayed unchanged during each recorded run. No
substitute package manifest, rewritten workspace or dependency replacement was
used. The package manifests, feature switches and target scope are in each raw
command record.

## Actual executions

| Source/toolchain | Original package command scope | Actual result |
| --- | --- | --- |
| Published 940313, Rust 1.95.0 | Session all targets, `objective-submission`, original lock | 63 passed, 0 failed/ignored/filtered |
| Published 940313, Rust 1.95.0 | Transport all targets, `objective-history`, original lock | 52 passed, 0 failed/ignored/filtered |
| Published 940313, Rust 1.88.0 | Same Session scope, locked/offline | 63 passed, 0 failed/ignored/filtered |
| Published 940313, Rust 1.88.0 | Same transport scope, locked/offline | 52 passed, 0 failed/ignored/filtered |
| Published 940313, Rust 1.88.0 | Both original packages, all targets/features above, Clippy `-D warnings` | Both exit 0 |
| Old call order + new owner-start regression, Rust 1.88.0 | Exact one new test | Expected exit 101: `owner start must precede transport`; 0 passed, 1 failed, 10 filtered |
| Final owner-start gate, Rust 1.88.0 | Session all targets, `objective-submission`, locked/offline | 64 passed, 0 failed/ignored/filtered, including 11 actual UDS adapter tests |
| Same final source, Rust 1.88.0 | Session all targets, `objective-submission`, Clippy `-D warnings` | Exit 0 |

The source fix consumes the adapter permission first, then calls the original
owner's mandatory local-ticket/live-authority gate, and only then calls the
one-shot transport. Owner refusal opens no socket, cannot grant a second send,
and cannot become a pre-send cancellation after permission consumption. The
negative receipt is an actual executed counterfactual, not a static assertion.
Transport source is unchanged by this final three-file correction; its locked
52-test and Clippy results above bind the same final transport bytes.

Rust 1.88.0 compiler commit is
`6b00bc3880198600130e1cf62b8f8a93494488cc`. Compiler, Cargo and clippy-driver
binary SHA-256, exact argv, UTC start times, durations, exit codes and raw output
are retained in the JSON receipts. The toolchain binaries worked directly;
this does not assert that the rustup installer final proxy-setup command exited
successfully. Network access recovery allowed original dependency acquisition,
after which the Rust 1.88 executions used `--locked --offline`.

## Practical limits and remaining gates

These are real original-package executions on Linux. The UDS fixtures use a
test-only owner and scripted original responses; no fixture signature or local
in-memory test owner is production authentication or durable-owner evidence.
The tests do not qualify the full A10 GUI/Wayland workflow, original production
writer/checkpoint/issuer composition, actual chat-to-model/device effects,
original run cancellation, Makepad rendering, accessibility or mobile devices.
Required GitHub checks and original-owner end-to-end qualification remain
separate. No default Send command was enabled.

The original failed offline attempts remain in `local-execution.json` and the
historical README sections. Later actual success does not turn those failed
commands into passes.
