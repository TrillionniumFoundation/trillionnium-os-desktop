# Pocket4 shared Linux kernel

The normal Pocket4 kernel retains the selected Linux 6.18.64 source and
configuration. The current complete batch is
6.18.64-p4ctx6181-fusectl-aafs-peer-r1.

The retained predecessor already contains the AppArmor internal filesystem
genfs correction in 0001-selinux-apparmorfs-genfs.patch. That correction adds
apparmorfs to SELinux's existing SE_SBGENFS filesystem list without enabling
filesystem xattrs, SBLABEL, a new symlink capability, or relaxed assertions.

The current delta, 0002-readonly-socket-peer-lsm.patch, adds the private
P4_SO_PEERSEC_LSM option (0x50340001) to SOL_SOCKET when CONFIG_P4_LSM_CONTEXT
is enabled. Its fixed 32-byte versioned header selects SELinux or AppArmor for
that call. All original getsockopt permission checks and the selected original
peer hook remain in place. It does not mutate the socket, namespace, credentials,
or policy. Old SO_PEERSEC and the immutable Android network-namespace selection
keep their original behavior. Input version, reserved fields, provider, and
length are checked. ERANGE reports the original provider's required byte length
plus the header without copying context bytes.

source.lock.json binds the actual R101 predecessor and its previous source
lock, the new complete source comparison, unchanged configuration, original
compiler interfaces and toolchain pins, exact normal Kbuild arguments, and
resulting public artifacts. The comparison found exactly four changed files:
include/uapi/linux/p4_lsm_context.h, include/linux/security.h,
security/security.c, and net/core/sock.c. This is a delta against the retained
Pocket4 kernel, not an unmodified upstream tarball.

## Normal build and publication

Rebuild in a fresh output directory using the locked normal make bzImage
modules arguments, then run make INSTALL_MOD_PATH=<new-stage>
INSTALL_MOD_STRIP=1 modules_install. Keep two logical CPUs available and retain
actual command exits and raw logs. openssl.cnf preserves the public provider
configuration used by Kbuild. Each new batch generates a fresh private module
signing key. Keep that key only in private build output; never put it in Git,
a public archive, or a log.

This complete build and installation exited normally. All 6,797 installed
modules were individually verified with OpenSSL CMS against this batch's new
public certificate, and all vermagic strings exactly name the new release.
The manifest records all module bodies and the 15 generated module indexes.
The exported kernel, full module tree, indexes, and configuration are pinned
together. The public signing certificate is a separate pinned input; no private
key enters the export.

Generate the matching base initrd through the original Ubuntu mkinitramfs
workflow using this batch's complete module tree. A preceding release's initrd
is not a matching input. Compilation, signatures, and archive construction do
not qualify a physical boot or the complete Linux/Android service.

## Isolated peer-query mechanism check

tests/peer-runtime.c is an init program for a separate diskless mechanism VM;
it refuses normal host execution. It checks the exact new release and the
actual stacked LSM order, then uses the real normal-package libapparmor and
libselinux public peer APIs alongside both per-call provider selections and
unchanged SO_PEERSEC. Eight threads perform 50,000 actual calls against one
held connected socket. The error matrix includes invalid headers, unknown
providers, short buffers without body copying, null memory, and absent peers.

The fixed test-only tests/peer-deny.apparmor profile is compiled without
loading it on the host. Use the normal product compiler arguments
`apparmor_parser -Q -K --kernel-features
<board-policy/pocket4-6.18.64-apparmor.features> -o <new-output>
tests/peer-deny.apparmor`. The feature file must match the committed board
lock, not the build host running kernel. The material builder rejects the
parser user compression wrapper, unsupported kernel ABI, or forced complain
mode; the guest writes only the original raw stream to `.load`. The VM loads it only after the concurrent checks; a
real child enters it through the library's native AppArmor setter and proves
that the outer AppArmor getsockopt denial still applies to both provider IDs
and to old SO_PEERSEC.

tests/prepare-peer-mechanism.py packs the compiled init, the fixed profile,
the actual candidate library, and pinned public dependencies into a separate
small initrd. It neither installs a package nor boots a guest. Its receipt and
the runtime result explicitly mark production policy and production
qualification false. The strict production joint-policy and complete native
Linux/Android lifecycle remain separate required gates.
