# Configured identity authority and persistent reservations

This patch implements a prerequisite for the production namespace broker. The
new `identity-inspect` command validates configured identity authority and
explicitly withholds namespace mapping and production authority. The existing
daemon still uses its development backend. This patch does not install a host
runtime, change accounts, allocate subordinate grants or start Android.

## Behavior

A dedicated non-login service account must have a unique UID and private primary
GID. Other accounts cannot share that GID. Explicit group members and duplicate
service-group names are rejected. Root and reserved sentinel owner identities
are rejected in both configured authority and existing reservation records.
The selected account and group are cross-checked through NSS.

Configured subordinate UID and GID grants must exactly match the requested
intervals, contain at least 100,000 IDs, exclude local host identities, and avoid
other grants. Authority files are bounded, root-owned, non-writable and
single-link. Trusted directory descriptors prevent alias substitution. The
actual file identities and full hashes are rechecked before reservation writes.
A JSON summary cannot construct authority. Complete effective NSS enumeration
and reconciliation of live namespace ownership remain separate requirements.

The root-owned durable reservation binds the cell, principal, ranges, Android
cohort and metadata identities of its data images. Image bodies are not read.
An exclusive process lease prevents concurrent use. Ending the lease preserves
the reservation. Changed bindings, overlapping records, interrupted records,
unexpected files and unsafe links require explicit reconciliation. There is no
automatic expiry, reclaim or reassignment during an Android upgrade.

## Exact source and actual verification

Apply `production-identity-reservation.patch` to Droidloom base
`fcb5afd7347b13f32c96daa073a63a048e95ecb2`. The latest source was committed
normally as `b4dc3b49ce29e706efca0ba5a7c775864d9b54b8`, tree
`9e4bdba177ba081789f45a97163a8f113b5c712b`. The six source-file identities
and exact patch are recorded in `validation.json` and `FILES.json`.
The isolated source worktree is clean. No upstream main branch was pushed.

Normal offline Cargo on Linux passed all 19 focused identity tests and built
the supervisor in the debug profile. Tests exercise real private filesystem
fixtures for missing and overlapping grants, short ranges, authority changes,
shared groups, reserved owner sentinels, persistent reservations, concurrent
leases, interrupted records and unsafe registry links. Tests excluded by the
focused filter are recorded separately; they are not counted as passed.
The source commit and reverse patch check used 13 normal Git commands.

The exact latest binary was then copied to a single-link, root-owned sealed
file and executed on Pocket4 as UID/GID 1000 through an inherited descriptor.
It rejected the current specification because the dedicated service account is
absent. Its actual pidfd exited. The reservation registry remained absent, the
four public account/grant inputs were unchanged, and original data-image
metadata was unchanged. This is a negative admission check. It does not qualify
a production namespace or an Android boot.

This public capsule was freshly assembled from the durable original source and
execution receipts after the local collaboration workspace disconnected. The
unpublished local capsule's manifest is not represented as recovered. No source
or runtime qualification was inferred from that workspace failure.

## Remaining integration

The mapping broker must reconcile effective NSS identities and namespace
ownership, retain the child through pidfd/proc/namespace descriptors, and write
and read back complete UID and GID maps while preserving Android's use of
`setgroups`. Privileged block/APEX mounts, data ownership translation, derived
IPC peer identities, seccomp and daemon integration remain required.
All runtime and production-ready claims in this capsule remain false.
