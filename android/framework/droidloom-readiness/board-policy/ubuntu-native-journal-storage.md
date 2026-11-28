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

The reviewed upstream revision is
[systemd 63c0371fa71ae32ba02f05f90658bc40aaa19168](https://github.com/systemd/systemd/tree/63c0371fa71ae32ba02f05f90658bc40aaa19168).
The matching [journal-vacuum.c](https://github.com/systemd/systemd/blob/63c0371fa71ae32ba02f05f90658bc40aaa19168/src/libsystemd/sd-journal/journal-vacuum.c)
is 11421 bytes with SHA256
c038f8b0a500f7726e1993f79c2036f5282acded604abb88c6c6bde9012a1e2f.
Its normal directory walk rejects nonregular and unknown files, preserves
active journals, and unlinks recognized archived/isolated files according
to the configured retention, size and count limits (including empty archives).

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

## Standard-output stream restart state

The normal R3 guest reached journald but its attached AppArmor profile rejected
creation of `/run/systemd/journal/streams`. The original `stdout_stream_save()`
uses the socket's device and inode as the decimal filename, writes a private
temporary file, and atomically renames it into place. On restart, journald reads
these records to restore its held output streams and unlinks retired records.
Omitting this state breaks the daemon's ordinary restart contract.

The reviewed systemd 259.9 `src/journal/journald-stream.c` is 33929 bytes with
SHA256 `193b68c448ba6a686020ed736702608454b9f2ce50ad004095503577aec64863`.
The matching `src/basic/tmpfile-util.c` is 12703 bytes with SHA256
`a88d08443488a816367a3df2e1022b19a72bd8796377b9fe856174aeb5ceee74`.
`fopen_temporary_at()` uses `O_RDWR|O_CREAT|O_EXCL`, mode 0600, and the filename
`.#<device>:<inode><16 lowercase hex digits>` before rename.

Two separate native types now cover only that runtime directory and its regular
state files. Journald alone can read or change file contents and the file
lifecycle. It cannot remove or relabel the directory, execute a state file,
create links, or write another runtime subtree. Existing metadata observers keep
only their prior directory `getattr/search` view. The AppArmor intersection and
class-aware file-context matcher restrict names to one through twenty decimal
digits per identifier, with the exact hexadecimal temporary suffix. Existing
denials on process environment, memory, mappings and command lines remain.

The normal linker checks every concrete process role against complete file,
directory and symlink permission vectors, checks both automatic transitions,
and runs positive and negative pathname/inode-kind matches through libselinux.
The new type family is explicitly removed only when comparing the immutable R13
original-authority projection. That comparison still uses its original fixed
commitments. This static proof does not mark a real guest restart qualified.
