# S07 exact-pin Servo retained-node action boundary

## Status and historical provenance

The original package was extracted on `codex/s07-servo-retained-node-closure-v1`
from historical S06 commit `f0e947e5e7267a3fcdd0a7d5437c0ae00c09ebfe`,
tree `b0b0304d70b209e26a08ed8a9d7e26f8a25cba02`, whose sole parent is
`648b204618328c2f9b9271ed6eb6db8aea7d8987`. The original fifteen-file extraction
and all eight ordered patch parts remain fixed. BrowserActor, daemon, platform,
image, update, hardware, signing, publication, and release code was not imported
from the rejected older carrier.

`carrier_base_commit` and `carrier_branch` identify that historical extraction;
they do not assert that every later qualification candidate descends from it.
The official commit exists, but the published Round4 `772837c6` candidate is
not its descendant. Its S07 job failed before qualification when the historical
object was absent locally; fetching the object alone does not make the old
ancestry assertion true. That failed run remains evidence of failure.

The closed `contracts/s07-qualification-lineage.v1.json` separately binds this
historical commit, tree, and single parent to the official repository URL, and
requires each current checkout to match the external event SHA. The prospective
job also requires the actual two-parent merge to contain the current live base
and head in that order. No future head SHA or tree is embedded in its own source.
The verifier reads actual Git commit bytes and emits only
`PASS_GIT_METADATA_AND_SOURCE_CONTRACT_ONLY`; it cannot prove S06 or Servo
execution, installation, or production activation.

Both jobs fetch the fixed historical object from the explicit official URL,
check the closed lineage contract, run the current S06 source and contract tests,
run the actual public-export inventory/absence guard, and execute the actor's
compile-fail documentation tests with Rust 1.93.0. Private imports and restricted
`pub(crate)` declarations are allowed. The scanner removes Rust comments and
literals before identifying `pub use` and `pub type`, preserves identifier
boundaries and aliases, and refuses public wildcard exports or its bounded-read
errors. This lexical gate does not expand macros or replace compiler API checks.
Historical metadata success never substitutes for these current-source gates
or the original actual-PIN patch and runtime qualification.

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
both pull-request and push workflow filters. The lineage verifier, closed
contract, current S06 sources, export scanner and their regression tests are
additional explicit qualification inputs in both filters.

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
