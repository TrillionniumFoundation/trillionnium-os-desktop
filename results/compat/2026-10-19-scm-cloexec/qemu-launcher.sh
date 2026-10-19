#!/bin/sh
set -eu
runtime=/workspace/scratch/3de9ecf4c563/continue-20261019/runtime/qemu-sysroot
export LD_LIBRARY_PATH="$runtime/usr/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export QEMU_MODULE_DIR="$runtime/usr/lib/x86_64-linux-gnu/qemu"
exec "$runtime/usr/bin/qemu-system-x86_64" -L "$runtime/usr/share/qemu" "$@"
