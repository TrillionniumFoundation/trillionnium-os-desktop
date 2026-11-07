# IHG: current artifact and launcher metadata only

This is a target-only derivative of the frozen 12306 five-command reader. The
exact historical launcher-matrix row names `com.ihg.apps.android` and version
50023219 at the original November 4 observation. That row has no UID field.
The current UID, version, APK count/layout and launcher component are all read
from the actual fixed package; none is guessed or inherited from another App.
The current UID must also equal the pinned activation package mapping. Historical
version equality is reported separately, not substituted for current evidence.

The command list is unchanged: package metadata, package paths, the unique current
MAIN/LAUNCHER component, package paths, and package metadata. One to sixteen APKs
must share the exact current package install directory and include exactly one
base APK. Every APK is held read-only, bounded and stream-hashed; final held/named
identities and current package metadata/paths must match again. Existing 256 MiB
per-file, 512 MiB total and 45-second hash bounds remain. Original Main before/after
fences, pinned held namespace/root entry, independent primary/secondary error
recording, five-second same-inode action-lock admission and descriptor cleanup
remain unchanged. No existing business Flow or legacy helper is instantiated.

The request creates only its own new source/evidence root. It performs no App
launch, instrumentation, helper installation, UI input, permissions/settings
change, screenshot, audio, package-wide inventory or private journal read. It
does not independently qualify IHG signing provenance or whole-App behavior.
Root reviews and dispatches the exact request once; partial failures are retained
and never retried with a new key. Legacy TICKET12306 diagnostic/module labels are
retained so the only method-level change is the result's human scope label.

This source preparation uses AST comparisons, complete payload hashes and the
real default PLAN path. Existing 12306 parser/transport controls are not rerun or
relabeled as IHG device tests. No Main or Android operation was performed here.
