# Fixed native login audit transport

The selected Ubuntu OpenSSH 10.2, PAM 1.7.0 and audit 4.1.2 sources were obtained
through a private, signed Ubuntu deb-src index, with no host source-list change.
The matching source package versions are openssh 1:10.2p1-2ubuntu3.8,
pam 1.7.0-5ubuntu3.2 and audit 1:4.1.2-1ubuntu0.1.

OpenSSH audit-linux.c treats an audit_open failure other than unsupported
kernel auditing as a failed login. Linux-PAM libpam/pam_audit.c similarly
returns PAM_SYSTEM_ERR. The selected libpam.so.0.85.1 contains audit_open,
audit_close and audit_log_acct_message dynamic imports; SHA-256
fe942230acb13b5b645ecb41cfff350004a8b69f18877e1e924e643be21eee64.
These calls are real login prerequisites, rather than permissions inferred
from the services' capability bounding sets.

## Exact actors and messages

| Actor | Source-owned message IDs |
| --- | --- |
| p4_linux_sshd_t | PAM's 1100, 1101, 1103, 1104, 1105, 1106, 1108, 1109, 1110; OpenSSH USER_LOGIN 1112; pam_selinux USER_ROLE_CHANGE 2300 |
| p4_linux_gdm_worker_t | Same nine PAM messages; pam_selinux USER_ROLE_CHANGE 2300 |
| p4_linux_service_executor_t | Same nine PAM lifecycle messages for the stock PAMName=systemd-user execution path |

Each actor receives only AUDIT_WRITE. The existing SSH capability contract
already includes it; this component adds it to the GDM worker and service
executor. AUDIT_CONTROL and AUDIT_READ remain denied. No other executor
capability contract is changed.

The selected shared-kernel binary policy actually enables netlink_xperm.
The target 6.18 security/selinux/nlmsgtab.c and hooks.c therefore use the
nlmsg base permission plus the exact 16-bit message number. Merely granting
the older nlmsg_relay permission would not work.

The socket is created by its actor and is allowed only create/read/write/nlmsg.
libaudit's actual audit_open creates an unbound NETLINK_AUDIT socket;
__audit_send sends to kernel port 0 with no multicast groups and reads the
matching ACK using poll and recvfrom. Explicit bind/connect/options,
multicast subscription and other socket permissions are denied.
The message set excludes AUDIT_GET, AUDIT_SET, rule mutations, rule reads,
daemon replacement and other audit control messages. pam_loginuid's
require_auditd option is not enabled by this component.

## Binary verification

The normal nine-input strict producer includes this CIL and the source-owned
verify_native_login_audit.py gate. It reads the resulting binary using the
pinned libsepol, checks all 27 socket permission bits for three login actors
and three protected application roles, verifies AUDIT_WRITE without CONTROL
or READ, and reads all effective extended message grants back from the binary.
Their union must equal the exact message set above. Complement neverallowx
rules make any additional message number a strict compilation error.

The full u16 set equality is an exhaustive boundary check derived from the
actual binary; it is not a claim that 196,608 separate runtime sends occurred.
No audit messages, credential operations or real login attempts were sent
during this offline policy validation.

The normal strict compile also reproduces the original Android binary and
retains all original assertions and the Android/host-control readbacks.
Actual SSH, GDM and executor PAM startup under the final enforcing policy
remains a required integration check.
