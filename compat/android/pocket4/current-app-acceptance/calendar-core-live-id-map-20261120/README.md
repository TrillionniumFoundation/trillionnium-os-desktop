# Calendar core live UID/GID mapping successor

The selected Contacts/Calendar source group still compared Android guest UID
values with host `fstat` ownership. `system_session.TargetReads.open_root`
passes the original held Main file descriptor through without entering the
guest user namespace. With the observed subordinate range beginning at
100000, Calendar 10061, provider 10017 and native helper 10125 do not equal
their host owners.

This successor reuses the exact 5776-byte mapping helper reviewed and published
in PR324. It reads the actual held Main `ns/user`, `uid_map`, `gid_map`, and
root identity, with before/after guards and complete FD retirement. It does
not derive authority from `cell.json`.

Only three of 35 source files change: `app_common.py` receives the same helper;
`calendar_identity.identity` compares both actual mapped owners; and
`calendar_base.counts` compares its original UID condition with the mapped
provider UID. The database inode/device/mode/link/owner bookends, SQL text,
physical empty-state checks, permission checks, fixtures, budgets and cleanup
are retained. The database's original GID fingerprint remains preserved; no
new assumption that its GID equals the package UID is introduced.

`adapt_sources.py` reproduces the source, preparation, full 13-entry selector,
compiled catalog candidate and 42-route map over the PR324 proposal. Only
selection index 0 changes. Every other selected source remains byte-identical.

This is source work. CURRENT, the active CI input, releases, APKs and Android
userdata are not changed. Native adoption and actual shifted Android business
execution remain pending; neither source inspection nor host model controls
constitute an app acceptance pass.
