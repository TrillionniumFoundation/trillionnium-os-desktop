# Finite browser action contract

This source implements a separate browser command and input-role contract, plus
an offline SELinux control-plane policy component. It closes the finite command
construction and role-separation source work without opening a production
Android action capability.

The current read worker retains its four read operations and its existing FD
protocol. The production controller still rejects OpenBrowser and Launch. This
crate has no process execution, filesystem access, runtime selection or authority
deserialization API.

## Command and input contract

The action input scope is `fixed_browser_action_v1`, separate from
`fixed_application_query_v1`. The only original executable role is
`/system/bin/cmd`. The specification checks the selected system digest, complete
cmd digest, bounded byte count and one of the two fixed 64-bit interpreter paths.
These are checks of declared metadata. A native provider must still open and
verify the actual original inputs, prepare a sealed private copy, and retain its
descriptor custody. Passing a declaration is never permission to execute it.

`BrowserPlan` contains one Android user and one immutable HTTPS target. `resolve()`
builds only the fixed Package Manager HTTPS resolver command. A bounded successful
resolver result must contain exactly one valid component owned by
`org.mozilla.firefox`. The resulting `Resolution` borrows the original plan.
Consuming it with `start()` keeps that same user and full URI, preserves VIEW and
BROWSABLE, and binds `start-activity -n` to the exact returned component. There is
no caller-supplied argv, executable, package, intent extra or component
constructor. Consuming one value prevents accidental replay through that
instance; it does not prove runtime uniqueness or replace a broker nonce.

`HttpsTarget` checks the lowercase HTTPS scheme, bounded ASCII bytes, DNS-label
or IP-literal authority syntax, bracketed IPv6 and a decimal u16 port. It is not a
complete URI parser. Valid authority syntax does not mean a destination is public
or approved: local addresses can have valid syntax. The actual owner must bind
the exact URI to its reviewed fixture before admitting any action.

Activity aliases and flattened component names are kept literally. This contract
does not add a requirement that a later Activity output name equal the resolver
name, and it does not claim rendered-page or application acceptance.

## Separate policy role

`policy/browser-action.cil` adds two concrete types:

- `droidloom_browser_action`, for the future fixed action worker;
- `droidloom_browser_action_exec`, for its future sealed private cmd copy.

The browser role receives only the Package Manager and Activity Manager service
handles needed by the two finite command shapes, their Binder callback/stdio
edges, and the original broker/manager observation and retirement relationships.
It has no automatic domain transition. The original broker must explicitly arm
the reviewed context, and the actual stopped executable and process labels must
be verified before continuation.

The existing query domain remains unable to find Activity Manager. An explicit
neverallow also prevents a future change from quietly expanding that authority.
The browser domain cannot acquire unrelated services, register/list services,
use the query executable role, write its own executable, administer policy or
namespaces, contact the host manager, or create network sockets. The browser
application's own network behavior is a separate app capability.

SELinux service permission does not inspect shell-command arguments. The finite
native adapter, exact executable role and actual runtime authority remain
necessary. This component deliberately does not invent the ELF/interpreter/
library access closure, a new worker transport or a sealed-runtime provider.

## Validation

Run the self-contained Rust controls with:

```sh
cargo fmt --all --check
cargo test --locked --offline -j 1 -- --test-threads=1
```

The frozen source passed rustfmt and all **9** host controls. They cover exact
user/URI/component binding, malformed and foreign resolver results, aliases,
literal argument handling, authority syntax and rejection of query-only or
incorrect runtime-role declarations.

### Repository CI and external policy qualification

Repository CI runs only this dependency-free crate and its nine Rust controls.
It does not run or receive credit for the policy qualification described below.

The policy was composed with the exact qualified R10 platform component using
its original AOSP secilc and libsepol, policy version 30, and strict neverallow
checks. No `-N` or permissive declaration was used. The original **211** binary
policy decisions remained identical field for field. The extended checker
passed **58** additional access/transition checks. Its original R10 arrays and
decision implementation are byte-identical after removing the new browser
function and its one call.

The unchanged R10 policy is an intentional negative baseline: it retains its
211 successful controls and reports the absent browser role. Two additional
negative compilations fail at this component's exact neverallows: granting
Activity Manager to the old query domain, and granting netd to the browser role.
These are offline policy operations only. No kernel policy was loaded.

That policy qualification used external, pinned R10 platform CIL inputs and
their original compiler/library. Those complete inputs are not contained in
this source packet. Reproducing it requires the exact baseline digests in the
manifest, the original strict compiler arguments and the retained qualification
records. Compiling a different local policy or observing passing repository CI
cannot substitute for that qualification or promote its runtime status.

`manifest.json` binds the source, compiler inputs and original verification
result. Private execution logs and build outputs are not part of the maintained
source packet. Host controls do not count as an Android start, a runtime pass,
or any of the 42 application acceptances.

## Native integration gates

Adoption must occur through the current owner and a fresh source-generation
check. The next native adapter must borrow the actual ReadyTreeWitness and held
framework observation, recheck the selected Firefox UID/user/APK set and epoch,
and carry the same original runtime binding throughout resolve and start.

The declared action role still needs its sealed runtime executable provider,
explicit role transfer, selected MAC contract, complete loader inputs, real
dual-LSM exec-stop observation and bounded owned-child/cgroup retirement. Keep
the read-worker protocol and query permissions unchanged. A source manifest or
saved inspection receipt cannot create these capabilities.

Only after those providers and gates are qualified may the production controller
enable the finite browser operation. A timeout or failed check after dispatch
must report an attempted/unconfirmed effect and must not automatically replay
the action. UI/content, lifecycle, permissions/data, stability and release-scope
acceptance remain separate requirements.
