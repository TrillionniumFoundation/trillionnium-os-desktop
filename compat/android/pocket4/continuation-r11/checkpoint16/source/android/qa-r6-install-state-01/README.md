# Exact R6 installation and state — first attempt

This frozen source derives the original R5 install03 worker and coordinator. The
new R6 package uses a fresh source root, flow and two nonces. It requires both
installed and retained uninstalled package records to be absent across users.
Installation uses the original explicit `-R -t --user 0 --pkg` command, with no
grants, replacement fallback or retry. Other owned helpers remain unchanged.

The complete actual R6 build and stage receipts, 32,912-byte APK and signer are
externally pinned in INPUTS.json and in the worker. The original frozen R6
adapter validates all ten source files, seven tool pins, eleven joined build
commands, exact self-instrumentation manifest, APK and signer before any Android
command. Root separately reconciles the authoritative original build job. The
installation and state request have not run; the installed UID is unknown.

After installation, the original R6 Session verifies the actual installed base
APK and new UID, runs only state with UiAutomation disconnected, rechecks the
installed identity and verifies the single all-users package record. No R6
reveal or other UI input is requested by this package installation transaction.

The R5-specific no-action install02 prerequisite is removed because R6 is a
new package's first attempt. Its original failure and review stay unchanged;
no old helper qualification is inherited. The same-inode five-second EX|NB lock
admission, post-lock Main recheck, R4 held namespace/root transport and original
worker/coordinator finally blocks remain unchanged. Failed or unknown installs
are retained for exact reconciliation. Cleanup removes only the held-inode
owned temporary APK and directory, with no recursive deletion.

The helper is retained after actual identity/state qualification for a separate
reviewed UI request. Pause, seek, audio, commercial data, account state and
engine deployment are outside this request. Whole-app readiness stays false.
Root owns eventual one-time execution and exact retained receipt collection.
