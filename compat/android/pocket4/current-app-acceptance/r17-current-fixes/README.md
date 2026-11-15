# Bind Firefox resolution and validate the browser URL authority

This packet supplies four coherent source replacements for native commit
`6b4ff636e42f6e016f40e9941b09adfd1553c852`, tree
`0357f56f3f54303216535bd75d3e7e91749e5fdd` (2,120 tracked files). The final
bytes passed focused tests and compilation in that complete native source tree.
It is a compatibility source packet. It does not supply the complete native
checkout, a running Android system, or production readiness.

## Changes and resulting behavior

### Preserve the actual resolved Firefox component

The native base already has a typed browser operation, fixed Query/Browser
domains, owned child processes and retirement, and the browser business workflow.
Its start parser nevertheless accepted only an implicit command. That allowed
a second default-handler resolution after the resolver returned, and rejected
the explicit `-n` command emitted by the earlier Firefox probe repair.

The probe now puts the actual unique Firefox resolver component in the fixed
`/system/bin/cmd activity start-activity -W --user … -n …` command. The operation
parser accepts only that finite explicit shape. The business binding stores the
resolver component from actual stdout only after successful child exit, complete
retirement and the existing deadline check. Parsing must succeed before the
binding advances to `Resolved`. The start must match the stored user, URL and
component. Failed resolution, substitution, the old implicit start, out-of-order
commands and replay remain rejected.

The component sent through `-n` keeps the exact resolver spelling. Flattened
component names and Android activity aliases remain supported: a successful
reported activity may normalize to another class within the same Firefox
package. The returned activity need not have the same spelling as a requested
alias. An input command or serialized record cannot manufacture a completed
resolver observation or issue a native execution authority.

### Reject malformed HTTPS authorities without changing authorization

The existing URL validator accepted malformed authority strings, including an
unclosed IPv6 literal and a nonnumeric port. The added structural checks require
a nonempty host, complete and valid bracketed IPv6 literals, and an optional port
whose nonempty value consists of decimal digits and fits in `u16`. Brackets in
ordinary host names, trailing data after an IPv6 literal, empty hosts, malformed
ports and out-of-range ports are rejected.

The original HTTPS scheme, ASCII, 4,096-byte, control/whitespace, credential and
authority character restrictions are retained. Empty ports, port 0, port 65535
and leading zeroes remain accepted within the original total length limit.
Accepted URL bytes pass unchanged to both resolve and explicit start. The
validator adds no DNS resolution, host allowlist, public-address claim, fixture
approval, or network permission. A syntactically accepted loopback address is
not an approved public fixture. The existing restricted ASCII host syntax is
preserved rather than replaced with a general URL parser.

The applications crate imports this same supervisor validator. Its runtime-plan
and nested leaf-route tests are included in the final verification.

### Describe the observed operation accurately

The applications runtime-plan success reason now says that an implicit HTTPS
resolution and a bound explicit activity invocation were observed. This is one
string replacement. Its `partial_observation` status, zero accepted applications,
false acceptance flags and pending rendering, media, return/reopen, recovery and
common release gates remain unchanged.

The four-file patch preserves the actual Ready/framework checks, complete
before/after package UID, version and APK identities, absolute workflow deadline,
read role, operation domains and child custody/retirement semantics. It does not
change the worker FD protocol, executable labels, host admission, MAC policy,
cgroup budget or execution admission, and adds no dependency.

## Exact source packet

| Packet file | Destination in the complete native tree |
| --- | --- |
| `application_probe.rs` | `runtime/droidloom-supervisor/src/application_probe.rs` |
| `production_application_operation.rs` | `runtime/droidloom-supervisor/src/production_application_operation.rs` |
| `production_application_business.rs` | `runtime/droidloom-supervisor/src/production_application_business.rs` |
| `runtime_plan.rs` | `runtime/droidloom-applications/src/runtime_plan.rs` |

`BASE.json` records all four original byte counts and SHA-256 values, the exact
native commit/tree and the full tracked-membership digest. `CANDIDATE.json`
records the final source hashes and unified `source.patch` hash. The patch starts
from the original four files in that native base and includes both the component
binding repair and the URL repair; an earlier component patch is not a separate
prerequisite. All other 2,116 native source files remain unchanged. The patch was
checked and applied to exact originals, reproducing all four final files byte
for byte.

This packet has no dependency on the separate browser-provider packet or the
superseded second-worker experiment. It uses the browser pipeline already in
the specified native base.

The complete native base is not supplied here. A commit lookup for that exact
native commit returned HTTP 404 in the publication repository and authentication
context used for the check. That observation does not establish whether the
commit exists elsewhere. PR303's public base `2f35479…` is a different tree; this
packet does not claim that base can build or accept the native patch. An owner
must provide or publish the complete corresponding native generation before a
public native CI job can reproduce this verification. No stub native CI gate is
provided, and the packet must not be overlaid onto an unrelated production tree.

## Actual native verification and preserved failures

Verification used actual `rustc 1.93.0 (254b59607 2026-01-19)` and
`cargo 1.93.0 (083ac5135 2025-12-15)`, with locked offline dependencies, isolated
writable source/cache/target copies, one cargo job and one test thread. The task
was limited to one CPU and 2 GiB of memory. Original native files and prior
source/cache/target inputs were read only and were verified unchanged afterward.

| Observation | Actual result |
| --- | --- |
| Original native operation plus the identical two component regression tests | Successful compilation, 0 passed, 2 assertion failures, 0 ignored, exit 101 |
| Previous `154c1c43…` probe plus the identical two URL authority regression tests | Successful compilation, all 28 malformed inputs observed accepted, 0 passed, 2 assertion failures, 0 ignored, exit 101 |
| Final four-source `production_application::` tests | 25 passed, 0 failed, 0 ignored |
| Final four-source `control::application_probe::` tests | 16 passed, 0 failed, 0 ignored |
| Final four-source `runtime_plan::` tests | 14 passed, 0 failed, 0 ignored |
| Final all-targets check of both actual crates | Exit 0 |
| Final rustfmt check of the four sources | Exit 0 |
| Complete source membership before and after final compilation | Same 2,120 files; exactly the four listed overlays |

The final total is **55 unique passing tests**, counted once. The applications
`runtime_plan::` filter includes seven tests in its own module and seven in its
nested `leaf_routes` module. The probe group includes the previous ten tests,
the two malformed-authority regression groups and four positive/control tests.
The original component failures demonstrated rejection of a valid explicit
resolved start and acceptance of the unsafe old implicit shape. The URL
regressions observed the old validator's actual acceptance before asserting.
Neither baseline result was a compile error.

An earlier URL qualification attempt ended with exit 1 because its orchestration
expected seven runtime-plan tests and observed fourteen passing tests. That
attempt stopped before the all-targets check. Its original failed result and
logs remain preserved and are not classified as a successful qualification or
a source regression. After that task retired, the final four-source stage ran
all 55 tests, rustfmt and the two-crate all-targets check under a new task
identity. It completed with exit 0 and complete durable logs. The earlier failed
stage's originals and proof archive were verified unchanged. No previous
35-test, provider or superseded-worker count is added to the final total.

All ten recorded final task process generations were subsequently observed
absent; its actual recorded cgroup was absent, and the exact unit was not found
in both system and user scopes. These observations concern the source validation
task, not Android child retirement qualification.

The focused tests include existing host process, FD, PIDFD, IPC and retirement
checks. Finite `AndroidProbe` fixtures exercise the browser parser/binding and
unchanged URL bytes; they do not construct a production Ready, start Android,
contact a website or manufacture an execution-admission witness.

## Reproduce with the complete corresponding native source

Verify the native commit, tree, membership and original four file hashes against
`BASE.json`. In an isolated copy, check and apply `source.patch`, then verify all
four replacements against `CANDIDATE.json`. Do not apply only the probe or mix
files from different generations. Use the complete native lockfile and available
offline dependencies with isolated writable `CARGO_HOME` and `CARGO_TARGET_DIR`.

```sh
rustfmt --edition 2024 --config skip_children=true --check runtime/droidloom-supervisor/src/application_probe.rs runtime/droidloom-supervisor/src/production_application_operation.rs runtime/droidloom-supervisor/src/production_application_business.rs runtime/droidloom-applications/src/runtime_plan.rs
cargo test --locked --offline -j 1 -p droidloom-supervisor --lib production_application:: -- --test-threads=1
cargo test --locked --offline -j 1 -p droidloom-supervisor --lib control::application_probe:: -- --test-threads=1
cargo test --locked --offline -j 1 -p droidloom-applications --lib runtime_plan:: -- --test-threads=1
cargo check --locked --offline -j 1 -p droidloom-supervisor -p droidloom-applications --all-targets
```

For the component negative baseline, use the exact unmodified native base and
append only the final `#[cfg(test)] mod r17_component_regressions` block from the
packet's operation file to the original operation file. Leave its original probe
and business implementation intact. The filter `r17_component_regressions::`
must produce the two expected assertion failures after compiling successfully.

For the URL negative baseline, use the preceding complete component-fixed
cohort with the exact 20,971-byte probe SHA-256
`154c1c43d22768e221400d41191c44a9aff2be2bbb4c6018e96f1bedb9109e20`.
Append only the final `#[cfg(test)] mod r17_url_authority_regressions` block from
the packet's probe. The filter `r17_url_authority_regressions::` must produce the
two expected assertion failures and report all 28 previously accepted malformed
inputs. Keep these tests identical when comparing baseline and final inputs.
The final source packet does not include a second copy of that previous probe.

## Remaining production conditions

The base's normal execution admission still returns `Unqualified`. This packet
does not construct or qualify a production Ready. Adoption requires a fresh
complete native generation and real validation of the held runtime, Ready and
framework observations, sealed executables and dynamic dependency closure,
same-generation dual-LSM execution, actual command results and child retirement.
Approved URI/fixture authority and actual browser business acceptance remain
separate requirements. URL structure validation does not issue that approval.

The existing external-HTTPS business gate requires an owned caller's implicit
ACTION_VIEW dispatch without an explicit component, a visible document and Back
behavior. This component-bound diagnostic flow does not satisfy that gate. Its
partial observation and pending gates remain explicit.

No Android or VM action was performed for this qualification. The packet makes
no application runtime acceptance, all-app coverage, latest-version or
production-ready claim. Private raw evidence, compiled policy, caches, targets
and binaries are excluded from this publication packet.
