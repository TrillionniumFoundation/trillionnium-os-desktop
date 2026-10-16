#!/bin/sh
# SPDX-License-Identifier: MPL-2.0

# Fail before the success marker if any required boot check fails. The host
# verifier must additionally require QEMU's successful debug-exit status (33).
set -eu
export PATH=/bin:/sbin

echo "TRILLIONNIUM_A01_INIT_BEGIN"
mount -t sysfs none /sys
mount -t proc none /proc
mount -t cgroup2 none /sys/fs/cgroup
mount -t configfs none /sys/kernel/config

if ! grep -q '^[^ ]* /dev devtmpfs ' /proc/mounts; then
    mount -t devtmpfs devtmpfs /dev
fi
mkdir -p /dev/pts /dev/shm
mount -t tmpfs tmpfs /dev/shm
chmod 1777 /dev/shm
mount -t devpts devpts /dev/pts
chmod 0666 /dev/pts/ptmx
ln -s pts/ptmx /dev/ptmx

echo "TRILLIONNIUM_A01_PROC_VERSION_BEGIN"
cat /proc/version
echo "TRILLIONNIUM_A01_PROC_VERSION_END"
uname -a
test "$(uname -m)" = x86_64

cpu_count=$(grep -c '^processor[[:space:]]*:' /proc/cpuinfo)
test "$cpu_count" -eq 1
echo "TRILLIONNIUM_A01_CPU_COUNT=$cpu_count"

# Preserve and execute the actual fixed upstream smoke test. Its plain marker
# alone is insufficient: the checks above and the host exit checks also apply.
/bin/sh /test/boot_hello.sh
echo "TRILLIONNIUM_A01_BOOT_OK"
exec /bin/poweroff -f
