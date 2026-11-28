# Stock native service capability boundary

This component closes a specific precondition: the selected SSH, GDM, network,
resolver and logind programs previously had no effective SELinux capability
permissions. It does not certify that those services have started. Socket,
filesystem, sandbox, PAM and user-data checks remain independently enforced.

The baseline is source commit 84d777db3e8dc8e1436e7a1025d39429fea0681b.
The original nine Android policy inputs and their neverallow assertions remain
unchanged. No unit CapabilityBoundingSet is copied wholesale.

## Actual selected programs and necessary calls

The selected public Ubuntu root's executable bytes were compared with the
installed public package executables before reading their package versions.
All nine compared executables matched. This is version/source attribution, not
a claim that an upstream tag includes every downstream Ubuntu patch.

| Service role | Selected package | Added capabilities | Actual source operation |
| --- | --- | --- | --- |
| sshd, including its exact sshd-session and sshd-auth entrypoints | openssh 1:10.2p1-2ubuntu3.8 | CHOWN, FOWNER, KILL, SETGID, SETUID, NET_BIND_SERVICE, SYS_CHROOT, AUDIT_WRITE | OpenSSH 10.2 privilege separation chroot; supplementary-group and uid/gid changes; PTY chown/chmod; login/session child signalling; direct sshd port 22; compiled Linux audit user records |
| gdm | gdm3 50.1-0ubuntu0.1 | CHOWN, FOWNER | gdm-launch-environment migration and gdm_ensure_dir chown followed by chmod, including a directory already owned by the greeter |
| gdm worker | same | KILL, SETGID, SETUID, SYS_TTY_CONFIG, AUDIT_WRITE | initgroups/setgid and authenticated child setuid; root worker killpg of its user session; VT_ACTIVATE and VT_WAITACTIVE |
| NetworkManager | 1.54.3-2ubuntu3.1 | NET_BIND_SERVICE, NET_ADMIN, NET_RAW | Default internal DHCP and raw network discovery; rtnetlink link/address/route configuration |
| wpa_supplicant | 2:2.11-0ubuntu5 | NET_ADMIN, NET_RAW | nl80211 configuration and PF_PACKET EAPOL; selected unit Group=netdev already matches its control socket group |
| systemd-resolved | 259.9-0ubuntu0.1 | NET_BIND_SERVICE, NET_RAW | DNS port 53 and SO_BINDTODEVICE/raw discovery; stock unit already runs as systemd-resolve |
| systemd-logind | systemd 259.9-0ubuntu0.1 | CHOWN, SYS_ADMIN, SYS_TTY_CONFIG | User VT ownership and kernel VT operations; DRM_SET_MASTER/DRM_DROP_MASTER for a newly opened or restored device descriptor |

In resolved.c the privilege-drop branch executes only when getuid() == 0.
The selected stock unit runs as systemd-resolve, so this component deliberately
does not grant SETPCAP even though the unit lists it in its bounding set.

The fixed shared-kernel source was read, rather than extrapolating from the
host kernel: drm_auth.c requires SYS_ADMIN for a descriptor without the same
prior master/tgid exception; vt_ioctl.c requires the controlling tty or
SYS_TTY_CONFIG; audit.c requires AUDIT_WRITE for userspace audit records.
Logind's SYS_ADMIN does not by itself grant any filesystem mount, namespace
creation, ptrace or arbitrary device access in this policy.

## Evidence source versions

Public source files were retained with URL, byte length and SHA-256 in the
private qualification work directory:

- OpenSSH portable tag V_10_2_P1: sshd-auth.c, uidswap.c, sshpty.c,
  sshd-session.c, session.c and audit-linux.c.
  https://github.com/openssh/openssh-portable/tree/V_10_2_P1
- GNOME GDM tag 50.1: daemon/gdm-launch-environment.c,
  daemon/gdm-session-worker.c and common/gdm-file-utils.c.
  Full tag archive SHA-256:
  95c333ece8415b67963a50de15216d4fef1a9eb3e81fbecbb9a8dfd6eb6426c0.
  https://github.com/GNOME/gdm/tree/50.1
- NetworkManager tag 1.54.3: nm-linux-platform.c and nm-dhcp-systemd.c.
  https://github.com/NetworkManager/NetworkManager/tree/1.54.3
- hostap tag hostap_2_11: nl80211 and l2_packet_linux.c.
  https://w1.fi/cgit/hostap/tree/?h=hostap_2_11
- Exact systemd 259.9 commit
  63c0371fa71ae32ba02f05f90658bc40aaa19168:
  resolved.c, logind-session.c and logind-session-device.c.
  https://github.com/systemd/systemd/tree/63c0371fa71ae32ba02f05f90658bc40aaa19168

The first capability commit used the upstream versions above. The subsequent
login-audit change obtained matching Ubuntu GDM, OpenSSH, PAM and audit source
packages through an isolated signed source index. No global apt configuration
was changed. Their downstream source calls confirm the selected login paths;
see ubuntu-native-login-audit.md.

## Enforced boundaries

Each of the seven roles has an explicit capability allowlist and a complement
neverallow. Every capability2, cap_userns and cap2_userns permission is denied.
Policy loading, enforcement changes and boolean management are denied. No
new relabel permission is added. The already-approved PAM tty relabel contract
is preserved exactly; other file-kind relabelling is denied.

The normal compiler reads the linked binary with the pinned libsepol and
checks every one of the 82 capability bits for all seven service roles and
the three protected broker/public-client/user-session roles. Those protected
roles retain their actual base vector, including the broker's pre-existing
namespace entry requirements. There is no fabricated all-zero broker baseline.

The first independent comparison of baseline and candidate covered all 390
process contexts, 63,960 bit decisions total, and exactly 24 additions in these
seven global capability sets. The later login-audit component adds only
AUDIT_WRITE for the GDM worker and the independently owned service executor;
its combined comparison requires exactly 26 additions in eight roles. The
normal GDM filesystem-credential repair subsequently adds only SETUID/SETGID
to the GDM manager: exactly 28 additions in eight roles, no removals and no
change to namespace capability bits. The normal compiler additionally preserves the
original 2,010 Android effective-access comparisons, 190 exact ioctl decisions
and original host-control checks.

## Explicit remaining functional blockers

Passing this capability gate is not a service or desktop acceptance receipt.

1. GDM 50.1 creates dyn_uid-owned 0700 .config/environment.d, then its root
   process attempts g_file_replace for gdm.conf without changing credentials.
   The original Android DAC_OVERRIDE assertion remains intact. A normal
   source-package fix is now maintained in packaging/ubuntu/gdm: it uses a
   verified thread-local fsuid/fsgid scope through atomic file close/rename.
   The normal Debian build and three real root/cap-minimal regressions pass.
   Actual GDM dynamic-greeter startup under the final shared kernel/policy is
   still required; autologin alone cannot prove that path.
2. The selected OpenSSH helper binaries import the Linux audit functions.
   The separate fixed login-audit component now closes its binary policy
   prerequisites. Real login under the final enforcing policy is still pending.
3. Default executor sandboxing, native storage and session IPC are independent
   components. No physical service was started or restarted by this change.

Qualification receipts and the rerunnable complete AV-delta script are under
/home/qq/work/p4-native-service-capabilities-516eec-r1. A final merged policy
must rerun the normal compiler gates and the appropriate integration checks.

## Normal startup boundaries

The normal R3 boot reached the original PID 1, journald and udev before
namespace and executable denials prevented later service acceptance. Its
first `tmp.mount` executor could not inspect the selected `/usr/bin/mount`
inode, and the calibration exporter could not inspect `/var/lib/droidloom`.
The source-owned fixes preserve the original programs, units and enforcing
shared-kernel policy. Their binary proofs are prerequisites for another
complete boot, not runtime acceptance receipts.

The original `tmp.mount` invokes the immutable mount ELF with tmpfs, `/tmp`
and its existing options. The executor now enters a separate
`p4_linux_tmp_mount_t` role for that ELF. Only this role can mount a tmpfs over
the native temporary-directory type; the original `fs_use_trans tmpfs` rule
and a source-specific directory transition label the new root. Its complete
binary vectors prohibit block-device access, filesystem remount/unmount,
inode relabelling, arbitrary executable entry and file mutation. The existing
root-remount role retains its complete previous authority. This component
does not qualify the separate loop/squashfs mounts used by snap packages.

The calibration exporter gains only `getattr` and `search` on the selected
public image parent type and read-only loader-cache mapping. Parent-directory
enumeration, file bodies with that parent type, symlinks and mutation remain
denied. The verifier checks raw attribute-expanded rules, complete permission
vectors and category pairs. It binds the actual selection and early-release
consumer source bytes before compilation.

The original systemd executor's `log_open()` uses an unbound native journal
datagram socket. It gains exactly create/connect/write/getopt/setopt on that
socket, write on the fixed native journal socket inode, and sendto to journald.
The executor and `src/basic/log.c` source hashes are checked against the normal
source admission. Independent whole-class checks continue to reject listener,
receive and unrelated-peer permissions. The journal stream restart-state
subtree has its own types and exact AppArmor names, as described in
`ubuntu-native-journal-storage.md`. A single additional journalctl TCGETS2
regular-file probe has a precise audit suppression; the operation is still
denied and the original policy commitments remain unchanged.

The normal credential namespace setup can relabel a newly created tmpfs root
to the fixed credentials-root type. Its source relabel permission remains
limited to tmpfs, and an existing credentials root cannot be relabelled away.
For `ProtectKernelLogs`, FINISH labels the original 1:11 devtmpfs kmsg inode
after entering the early role. The 0600 diagnostic backing remains available
to early diagnostics; it no longer covers the original `/dev/kmsg`. This
avoids carrying a device descriptor across the SELinux exec transition or
adding another mount. The early role receives only metadata and the target
label permission. The kmsg type gains only its required devtmpfs association;
no log-body operation or generic-device mount permission is added.

The timesync manager's source calls `sd_network_monitor_new()` before it can
start. When networkd has not created its state directories, that library
watches `/run/systemd` itself. The observed failing `inotify_add_watch` needs
directory read in addition to the existing watch/search/getattr permissions.
The isolated timesync role receives this one directory bit, the normal
read-only machine identity and the journal sendto operation. It remains
outside the broad native-process and SELinux-query groups. Proc/device-body,
NET_ADMIN, terminal ioctl and fallback-probe denials confer no new rights.
