# Native journal storage and rotation

This is a shared-kernel native service correction. The nine admitted Android
CIL inputs and their assertions are unchanged; secilc runs without -N.

## Observed mismatch

The original native policy admitted only the named system.journal creation
and explicitly rejected rename/unlink of the persistent database. That covered
initial writes and FlushToVar, but not the original daemon's production lifecycle:

- systemd 259.9 journald-manager.c, manager_find_user_journal(), creates
  user-<decimal UID>.journal when it splits persistent journals by user.
- journal-file.c, journal_file_archive(), renames the existing inode to
  <name>@<32 hex sequence ID>-<16 hex sequence>-<16 hex realtime>.journal.
- journal_file_dispose() isolates an unusable file as
  <name>@<16 hex realtime>-<16 hex random>.journal~.
- manager_do_vacuum() calls the normal journal_directory_vacuum() implementation
  for the selected store and configured file-count, size and retention limits.

Reviewed original source bytes:
journald-manager.c: 101185 bytes, SHA256
0cb89330fef46f7e043658459c5028258aeb27bc689f5f3fc001fda622f6bbf1.
journal-file.c: 174091 bytes, SHA256
3608596a276974248862638d5a2e5be318e5c17a01b399e426b9ea149975013b.

## Contract

Journald alone obtains a regular-file default transition within the already
typed persistent machine directory. The original named system.journal
transitions remain. Its automatically attached AppArmor profile restricts
active, archived and isolated filenames, with one to ten decimal UID digits,
exact 32-digit machine IDs and exact hexadecimal rotation fields. The profile
does not admit arbitrary files beneath the journal tree.

Journald can rename and unlink database files for normal rotation and retention.
It cannot remove, rename or relabel the persistent machine directory or the
persistent store itself. This explicitly replaces the earlier native
no-rotation assertion; it does not disable an assertion check to make a build
pass. Other native roles cannot mutate either persistent or volatile database
bodies. Android policy protections, mount restrictions and executable-file
restrictions remain intact.

The existing journalctl flush role remains unable to open/read/map either
database class. A separately reviewed maintenance reader can receive read-only
access without inheriting daemon write permissions.

The normal compiler verifies the actual linked binary's complete writer file
and machine-directory permission vectors, all Android and native process
roles' write decisions, and the exact automatic file transitions. File-context
entries preserve these labels for the daemon's normal persistent filenames.

Successful compilation is not runtime qualification. Actual user journal
creation, normal rotation/retention and same-boot authenticated collection are
still required in the enforcing guest and deployment.
