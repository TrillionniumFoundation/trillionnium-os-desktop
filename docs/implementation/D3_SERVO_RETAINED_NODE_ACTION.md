# S07 exact-pin Servo retained-node action boundary

## Status and immutable parent

This document describes the bounded S07 source and real-test-harness candidate
on `codex/s07-servo-retained-node-closure-v1`, based on exact S06 commit
`f0e947e5e7267a3fcdd0a7d5437c0ae00c09ebfe`. Only the 15 S07-specific files from the rejected older candidate
were extracted; no BrowserActor, daemon, platform, image, update, hardware,
signing, publication, or release source was imported from frozen PR #73 or old
PR #102.

The source manifest stores the immutable S06 parent and actual carrier branch.
The S07 head cannot safely contain its own SHA without a self-referential commit;
therefore the exact head and tree are asserted at runtime and recorded in the
workflow evidence artifact and live pull request. Any parent restack changes the
static parent field and fails the package tests until deliberately updated.

## Servo target and claim ceiling

The package targets Servo commit `670ae8a70801b162e186f81cbb5bdd2d59c39108` exactly. A green exact-head job proves
complete patch application and the retained-node corpus on the explicitly
recorded post-format Servo patch digest and staged tree. A green prospective
merge job proves the live two-parent PR merge retains and applies the complete
base plus hardening package with the declared changed paths. Neither job proves
installed product wiring, unrestricted navigation, target hardware, HSM custody,
publication, or release.

## Security property

At the pinned Servo revision the non-root AccessKit action path stops at
`TODO(#4344)`. The reviewed patch routes the exact retained `TreeId + NodeId`
back to the current active document and dispatches at most one untrusted Click
only when that same retained node advertises Click and remains connected,
enabled, visible, element-backed, and layout-finalized. Coordinate targeting,
JavaScript, WebDriver, selectors, text search, DOM-order lookup, and a separated
resolve-then-act phase remain forbidden.

## Route

1. `HeadedWindow` handles root-tree chrome locally and routes a non-root tree
   only when exactly one current WebView owns it.
2. WebView and Constellation retain the original typed AccessKit request and
   callback, bind it to the active top-level pipeline, and reject stale or
   ambiguous ownership.
3. Script refreshes retained accessibility/layout state and resolves the node
   inside one script-thread task, preventing page-script interleaving at the
   final lookup/action boundary.
4. The exact node must advertise Click and pass document, connection, element,
   enabled, visibility, and finalized-bounds checks.
5. One typed terminal callback reports dispatch or a closed failure class. A
   dropped receiver cannot cause duplicate dispatch.

## Immutable package and transitive qualification sources

The manifest binds eight ordered patch parts, every part digest, aggregate base
and hardening digests, the allowed Servo path set, source invariants and claim
ceiling. The production dispatcher is only a router, but its default path also
depends on `_qualify_servo_exact_pin_v3_impl.py` and
`qualify_servo_exact_pin.py`; all four transitive CLI sources are included in
both pull-request and push workflow filters.

The verifier rejects duplicate/escaping paths, digest or changed-path drift,
missing retained-node tokens, and forbidden coordinate/JavaScript/WebDriver/
selector/text-search additions.

## Exact tested Servo bytes

The exact-head job applies both patch stages, captures the pre-format result,
formats only patch-owned Rust files, stages the resulting Servo tree, writes the
full-index tested patch, and records its SHA-256 and Git tree. The behavior suite
then runs without source mutation. After the tests, the workflow regenerates the
staged patch, compares it byte-for-byte, rechecks the Git tree, and verifies the
recorded digest before marking evidence complete.

The prospective-merge job also applies both stages—not merely a base application
plus hardening dry run—compares the complete final changed-path set to the
allowlist, checks whitespace on the actual Servo worktree, stages the tree, and
publishes a merge evidence artifact containing live base/head/merge identities,
tested patch digest and tested Servo tree.

## Behavior matrix

The real Servo harness covers a valid retained button click, exactly-once
callback/dispatch, unadvertised Click, unsupported action/data, replaced node,
stale or inactive tree, disabled/hidden/non-element targets, missing finalized
bounds, dropped callback receiver, and the pinned accessibility mapping
regression. Each command must execute exactly one named test and produce one
passing terminal result.

## Remaining integration

A later successor must introduce a distinct concrete Servo product adapter and
prove the complete attested AgentPort → BrowserActor → Servo → durable receipt →
response path. Installed-image, hardware endurance, independent builders,
offline/HSM signing, protected publication and release claims remain outside S07.
