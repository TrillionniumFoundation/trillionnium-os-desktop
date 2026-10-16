#!/bin/sh
# Linux-host-only contract smoke; no QEMU or HOS2 driver is claimed.
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
scratch=$(mktemp -d)
trap 'rm -rf -- "$scratch"' EXIT HUP INT TERM
cc -std=c11 -O2 -Wall -Wextra -Werror -pedantic \
   "$here/hos2_queryabi_probe.c" -o "$scratch/probe"
"$scratch/probe" --selftest
set +e
"$scratch/probe" --device /dev/null --ioctl-cmd 0x123456 >"$scratch/refusal.log" 2>&1
result=$?
set -e
if [ "$result" -ne 77 ]; then
    cat "$scratch/refusal.log" >&2
    echo "Expected unsupported ioctl exit 77, got $result" >&2
    exit 1
fi
echo "PASS real Linux /dev/null ioctl rejected; Asterinas ioctl remains untested"
