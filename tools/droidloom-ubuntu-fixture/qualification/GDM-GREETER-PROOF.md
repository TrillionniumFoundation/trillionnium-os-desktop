# Fresh dynamic GDM greeter proof

This belongs only to `prepare-native`'s newly created, root-protected
qualification root. It changes no physical GDM configuration, package,
account, home, or service. It adds no runtime root observer or MAC grant.

## Normal session path

The selected Ubuntu GDM and gnome-session are 50.1-0ubuntu0.1. The normal
`gdm-launch-environment` PAM session includes `pam_systemd`; the original
`user@.service` runs the manager with `User=%i` and `PAMName=systemd-user`.
The original `gnome-session@gnome-login.target` drop-in requires
`gnome-session-basic-services.target` and `org.gnome.Shell@gdm.service`.
The original target and drop-in bytes are checked before mutation.

The fresh GDM configuration explicitly disables immediate automatic login,
enables stock timed login for alex after 20 seconds, and enables Wayland.
GDM manager.c's `set_up_session` therefore selects the normal dynamic greeter.
Its launch environment's `setup-complete` callback writes the environment;
timed login is handled after the greeter client connects. No test calls that
writer or manufactures its file in the actual guest.

Three regular files are added, all root:root 0444:

| Guest path | Purpose | Existing native label |
| --- | --- | --- |
| `/usr/libexec/droidloom-fixture-greeter-proof.py` | Fixed read-only verifier, interpreted by the original `/usr/bin/python3.14 -I -B` | `p4_linux_native_bin_t` |
| `/usr/lib/systemd/user/droidloom-fixture-greeter-proof.service` | Ordinary user oneshot, bound to the greeter target, no `User=` override | `p4_linux_runtime_lib_t` |
| `/usr/lib/systemd/user/gnome-session@gnome-login.target.d/50-droidloom-fixture-greeter-proof.conf` | Wants the proof only from the normal greeter target | `p4_linux_runtime_lib_t` |

`/etc/gdm3/custom.conf` is an existing fixture file whose bytes change; it is
not a fourth new file. The normal host-stage file count does not change.
All four paths receive final ext4 inode, label and body readback. A new
consumer intentionally rejects an old prepared native root without this
proof; regenerate a fresh native root with the matching tool.

## What the verifier proves

The executable has no path, UID, label or account arguments. It requires
real/effective/saved UID 60578..60705 and primary GID 121 (the selected
GDM_GROUPNAME=gdm public group, also checked through NSS), then resolves the actual
dynamic NSS account and its source-owned `gdm-greeter[-N]` home. Alex and root
cannot produce a passing record. It opens literal `/` and walks held
`O_PATH|O_DIRECTORY|O_NOFOLLOW` descriptors through `/run/gdm3/home`, the
allocated home, `.config`, and `environment.d`.

The process primary group and filesystem group are deliberately distinct.
The three private directories must be owned by that UID:65534 and mode 0700.
The fixed root-owned ancestors must not be group/other writable. The leaf
`gdm.conf` must be a single-link regular file, mode 0600, with the same owner
and 1..65536 bytes. A nonblocking no-follow open prevents FIFO/symlink hangs.
It validates unique environment keys and exact USER, LOGNAME, HOME and
GDM_SEAT_ID=seat0; it does not print the body. Full read, inode metadata,
path binding and parent identity are checked before returning the SHA256.
Only absence may retry, for at most eight seconds. A mismatch fails at once.
The normal user unit times out after twelve seconds and never restarts.

## Original journal acceptance

The existing ended-VM collector verifies and reads the original native
journals; no new journal API or root filesystem access in the running guest
is introduced. It also rereads the three exact proof source files and the
timed-login settings from the ended private disk.

The record must match journal-supplied `_UID`, `_GID`, `_PID`,
`_SYSTEMD_OWNER_UID`, `_SYSTEMD_UNIT=user@<uid>.service`,
`_SYSTEMD_USER_UNIT=droidloom-fixture-greeter-proof.service`,
`_SYSTEMD_INVOCATION_ID`, `_BOOT_ID`, `_EXE=/usr/bin/python3.14` and
`_TRANSPORT=stdout`. The payload's invocation field is only a cross-check.
There must be exactly one passing observation in one original boot.

The original user manager must additionally report a successful start job
for the same USER_UNIT and USER_INVOCATION_ID. The frozen Type=oneshot unit
contains no ignored command or condition; this job completes after the
actual process exits successfully. A failure, timeout, bad origin, missing
terminal, altered source or extra/malformed proof-unit record prevents
acceptance. systemd 259.9 `unit.c` selects USER_UNIT/USER_INVOCATION_ID for a
user manager; `job.c` emits the original JOB_TYPE/JOB_RESULT and message ID.
Matched upstream source commit: `63c0371fa71ae32ba02f05f90658bc40aaa19168`.

The result proves the dynamic environment writer's observed output. It
explicitly does not prove a visible greeter, successful graphics/input,
alex's desktop, Android applications, or production readiness.

## Targeted verification

`test_gdm_greeter_proof.py` needs root only to construct disposable private
trees and change child credentials. It starts no user unit and touches no
host GDM path. It covers actual UID/GID rejection, a successful dynamic-UID
read, symlinks, hard links, FIFO, ownership/mode, malformed fields, size and
a real file mutation during the read. An unprivileged run reports skips;
skips are not treated as successful credential tests.

Rust focused tests cover the journal trust and terminal gates. The ignored
`actual_greeter_proof_ext4_body_readback` test requires a new explicit
`DROIDLOOM_GDM_PROOF_IMAGE_WORK` directly under
`/var/lib/droidloom-qualification`; it creates its own small ext4 image and
checks real extraction plus deliberate image corruption and source-mode
rejection. Actual shared-kernel enforcing greeter execution remains a
separate qualification gate.
