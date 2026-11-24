# Pocket4 AppArmor socket peer labels

The maintained candidate retains the complete Ubuntu AppArmor 5.0.2 source
and distribution patch series. The additional patch makes aa_getpeercon_raw
query the original AppArmor socket peer hook through the per-call, read-only
P4_SO_PEERSEC_LSM ABI. It never changes shared socket or network namespace
provider state. The private option is defined by the retained shared kernel
patch in ../linux/patches/0002-readonly-socket-peer-lsm.patch.

Only ENOPROTOOPT permits fallback to the old SO_PEERSEC interface on kernels
without this option. Permission denials, malformed replies, and unsupported
peer providers fail closed. Both paths retain the original AppArmor context
parser. The public library ABI and SONAME remain unchanged.

Build the complete Ubuntu source with its original Debian rules after adding
this patch to the distribution quilt series and using candidate version
5.0.2-0ubuntu1~26.04.1+p4peer1. Use normal dpkg-buildpackage -F -us -uc -j1.
Keep the original source archives, normal source and binary package checksums,
raw build logs, maintained Git commit, and actual exported-ABI comparison.
The candidate library belongs only in a fresh, admitted qualification clone;
it does not alter the build host's installed libapparmor or dpkg records.

The kernel and library source changes alone do not qualify production. Query
correctness, simultaneous SELinux and AppArmor reads on the same socket, and
normal D-Bus startup require an actual boot of the matching complete kernel,
modules, and initrd batch with the original enforcing policy.
