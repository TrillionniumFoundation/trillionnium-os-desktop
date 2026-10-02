# Platform integration

This directory contains Linux source mechanisms and candidates for installed
services. `linux/adapters.py` provides descriptor-confined files, process and
endpoint custody, clocks/entropy and pure address policy. Its module README
describes those APIs and operational permissions.

`update_recovery.py` verifies externally rooted signed manifests and streams
complete candidate images into private leased inactive regular-file slots. Its
S11 contract describes durability, indeterminate publication, journal-bound
reconciliation and explicitly authorized rollback. It does not install a
bootloader, protected monotonic floor or physical A/B device adapter.

`durable_update_owner.py` composes that concrete verifier and both private
stores. It confirms complete durable staging intent before actual inactive
regular-file publication, binds results to the issuing owner and complete
history, and quarantines unfinished or unclean restart without replay. Its
`arm_first_boot` records source policy only and accepts no caller boot, health
or commit assertion. Installation still needs trusted roots/time/floor,
service wiring and actual boot/health/recovery adapters. The S11 directory-walk,
lease and publication cleanup correction is integrated with the wrapper's private
owner protocol and raw scan-record cleanup. Joint real close/reuse/GC and
constructor/return interruption regressions cover the reproduced paths; they do
not prove every C-return-to-bytecode window or close installed prerequisites.

`trusted_apps.py` verifies complete signed bundles offline and issues immutable
local asset responses for exact synthetic HTTPS origins. Its versioned bundle
contract records signature/index bytes, root and revocation policy, archive
bounds and restrictive headers. Actual engine interception remains separate
integration work.

`app_storage.py` binds admitted packages and data to private leased principal/origin
partitions. Its durable history preserves version floors, current trust-policy
pins and revocations, single-use operation identities and uninstall/data
tombstones. It refuses uncertain or interrupted owner histories without automatic
repair. Native storage binding, authenticated time/policy delivery, migrations,
authorized recovery and independently protected rollback detection remain open.

`taskflow.py` admits typed proposals and actual externally signed permits,
reserves task IDs durably and consumes grant identities before trusted adapter
dispatch. Original budgets, cancellation, human handoff and process ownership
are checked before effect admission. A real trusted approval surface and
installed final native effect checks still need integration.

`controlled_egress.py` performs actual approved DNS-over-TLS, exact TCP peer and
TLS identity checks, and bounded GET observations and redirects under one
deadline. Only its own sockets are covered. The explicit loopback qualification
client is rejected by the production constructor; default external egress stays
disabled. Browser resource interception and network namespace enforcement remain
installed obligations.

`manifests/platform-mechanisms.v1.json` registers public signatures and technical
contracts for six top-level candidates. `tools/validate_platform_mechanisms.py`
fixes each module's requirement and implementation/document/contract/test
mapping and detects unregistered modules and API drift without importing their
code. The durable owner has a separately reviewed fixed contract profile that
closes every nested object and pins every leaf, including null admission,
false activation/non-claims and its source status. `--refresh-api` updates AST
signatures only; it cannot refresh contract profiles or qualification. Source
inventory validation does not stand in for real executable regressions.

Candidates are tested without enabling product startup or external effects.
Compositor/portal, installed network namespace, audio and device adapters still
require implementation and their own native/image acceptance. Passing host
mechanism tests does not establish an installed product or release claim.
