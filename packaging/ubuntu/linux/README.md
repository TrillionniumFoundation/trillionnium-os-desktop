# Pocket4 shared Linux kernel

The normal Pocket4 kernel retains the selected Linux 6.18.64 source and configuration.
The added patch makes AppArmor's internal filesystem use SELinux genfs labels by
adding apparmorfs to the existing SE_SBGENFS filesystem list. It does not enable
filesystem xattrs, SBLABEL, a new symlink policy capability, or relaxed policy
assertions. The counter files can therefore receive their selected AppArmor
load-generation types.

source.lock.json binds the actual retained source, complete source comparison,
unchanged configuration, upstream compiler interfaces, normal Kbuild arguments,
toolchain package pins, and resulting public artifacts. The full comparison has
91,182 regular files, 6,050 directories, and 85 symlinks; only
security/selinux/hooks.c differs by this one line. This patch applies to the
retained Pocket4 kernel, which already contains the approved shared-kernel work.
The complete source tree is not an unmodified upstream tarball.

Rebuild in a fresh output directory with the locked normal make bzImage modules
arguments, then make INSTALL_MOD_PATH=<new-stage> INSTALL_MOD_STRIP=1
modules_install. Keep two logical CPUs available and retain all command exits
and raw logs. openssl.cnf preserves the public provider configuration used for
the build. Each new candidate generates its own private Kbuild module-signing
key; retain that key only in the private build output and never put it in Git,
an export archive, or a log.

The completed candidate's 6,797 installed modules were each cryptographically
verified against its new public certificate, and every module's vermagic
matches 6.18.64-p4ctx6181-fusectl-aafs-r1. The normal module manifest also records
the 15 generated module indexes. The installed config is a separate input.
Only public kernel, modules, indexes, configuration, and public certificate may
enter the isolated material stage.

Generate a matching base initrd through the original Ubuntu mkinitramfs
workflow using the candidate's complete module tree. The previous release's
initrd is not a matching input. Compilation and module verification do not
qualify a physical boot or the complete Linux/Android service; those remain
separate enforcing-kernel and native-service checks before activation.
