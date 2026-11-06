# Independent review of the controlled AAPT2 RUNPATH layout

Reviewer: `app_history`. Scope: local source and already saved actual receipts;
no remote job, Main command, APK read, test execution or source edit was performed
by this reviewer. The frozen r3 source and its manifests were not changed.

## Conclusion

No blocking defect was found in the new `ControlledRunpathLayout`, the exact
candidate branch in `static_graph`, or their resource cleanup. The change is
limited to the observed official binary and its five exact RUNPATH expansions.
It does not add a general private-library search path or alter the system resolver.

The complete 61,830-byte assembled source was pinned to
`bdae0316cd5423f60a6d1884e2131ba446c3554ee696c3c543ebf3634e743a63`.
The 27,309-byte new worker body, full body diff, assembler and original reader
interfaces were read. All 14 rows in `SOURCE_REVIEW.json` matched their actual
local bytes and SHA-256. The embedded original reader and ELF parser matched
their 10,557/5b56807f… and 11,269/f829cd86… pins. The exact process packet's
stager and stdin matched the staged sources.

## Identity and search boundary

The root-controlled output is a fresh directory below `/var/lib`. The existing
`/`, `/var` and `/var/lib` ancestors must be root-owned and not group/world writable.
The new directory tree is mode 0700; the extracted tool is mode 0500. Every
component is opened without following symlinks. Initial parent metadata changes
caused by creating the new output are limited to non-identity fields; dev, inode,
owner and mode must remain identical. Subsequent original parent identity checks
include the observed link counts.

The candidate branch checks the exact tool bytes and SHA, exact interpreter,
absence of RPATH or other loader directives, the complete original six-entry
DT_NEEDED list, and the exact five-entry RUNPATH. The `$ORIGIN` expansions must
equal the five fixed directories in this new tree. Every directory's complete
stat, path identity and closed entry set are checked. All 30 direct SONAME
candidates must return actual ENOENT. Existing files, directories, regular
symlinks and dangling symlinks cannot be treated as absence.

The ordinary `search_paths`, `resolve_dependency`, `in_system_library_root`,
`BoundFile`, `EvidenceStore`, census and the other listed common definitions
were independently compared with r2 and are byte-identical. After proving the
private candidates absent, dependency resolution continues through the original
system-only resolver. No library is copied into the private RUNPATH, no binary
patch or LD environment override is introduced, and only the original bounded
runner's single `version` command is enabled.

## Lifecycle and receipt boundary

The layout is checked before system dependency resolution, immediately before
the version command and after its normal completion and the final file recheck.
Subdirectory stat values stay exact. The output root may change size/timestamps
only for the evidence files tracked by its existing `EvidenceStore`; its identity,
mode, owner and link count remain fixed. The new layout closes only its owned
directory descriptors and explicitly leaves the borrowed evidence-store FD for
the existing store's cleanup.

The original result file is written before the final whole-process FD census and
is therefore insufficient by itself. Acceptance still requires the complete
final stdout and the authoritative durable terminal, normal joined tool exit,
closed pipes, no errors and restoration of the original descriptor identities.

## Independently read actual host result

The saved actual job `1a1b257ba27-fc05-7da0` is durable and complete with exit 0,
no timeout/cancel/retry, 7,092 stdout bytes and zero stderr bytes. Its decoded
worker result is 34,091 bytes, SHA-256
`b827c080d7af767cab60fbd9a682eafd8dfe06d6f4375b23f62988212a4b908e`.
This review read that result and the original terminal locally.

The result records seven ELF files, three complete 5 × 6 ENOENT observations,
11 acquired and 11 closed owned directory descriptors, no errors and full
process descriptor identity restoration from three to three. The single owned
version child joined normally with exit 0 and closed pipes. The actual version
string is `Android Asset Packaging Tool (aapt) 2.20-16666295`; it was emitted on
the tool's stderr, while the controller job's stderr remained empty.

These facts qualify this specific host tool preparation. They do not establish
the dynamic loader's actual mappings, Calendar resource compatibility, any App
runtime result, or production readiness. A later read-only Calendar worker must
bind the actual installed tool bytes and directory identities again; it cannot
inherit a permanent permission to execute an arbitrary binary at the same path.
The original r2 safe rejection and failed b05 audit remain unchanged.
