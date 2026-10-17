#!/bin/sh
# Linux-host-only contract smoke; no QEMU or HOS2 driver is claimed.
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
scratch=$(mktemp -d)
trap 'rm -rf -- "$scratch"' EXIT HUP INT TERM
cc -std=c11 -O2 -Wall -Wextra -Werror -pedantic \
   "$here/hos2_queryabi_probe.c" -o "$scratch/probe"
"$scratch/probe" --selftest
# Compile the *same* C guest verifier into a pure Linux host negative oracle.
# Fail closed if either mandatory native guest source or the test disappears.
test -f "$here/queryabi_guest.c" && test ! -L "$here/queryabi_guest.c"
test -f "$here/queryabi_reply_contract.c" && test ! -L "$here/queryabi_reply_contract.c"
cc -std=c11 -O2 -Wall -Wextra -Werror -pedantic \
   "$here/queryabi_reply_contract.c" -o "$scratch/reply-contract"
"$scratch/reply-contract"
# Run native guest archive-injection and pin checks on a CPU-only host:
# these tests do not spawn QEMU or touch a device.
test -f "$here/run_queryabi_guest.py" && test ! -L "$here/run_queryabi_guest.py"
test -f "$here/test_queryabi_guest_runner.py" && test ! -L "$here/test_queryabi_guest_runner.py"
python3 -I -m unittest discover -s "$here" -p 'test_queryabi_guest_runner.py' -v
python3 -I -O -m unittest discover -s "$here" -p 'test_queryabi_guest_runner.py' -v
set +e
"$scratch/probe" --device /dev/null --ioctl-cmd 0x123456 >"$scratch/refusal.log" 2>&1
result=$?
set -e
if [ "$result" -ne 77 ] || ! grep -Fqx 'HOS2_IOCTL_ENOTTY' "$scratch/refusal.log"; then
    cat "$scratch/refusal.log" >&2
    echo "Expected actual ENOTTY marker and exit 77, got $result" >&2
    exit 1
fi
# A second, intentionally faulting ioctl is still an unsupported probe, but
# must NEVER be misclassified as the correct ENOTTY refusal above.
cc -std=c11 -O2 -Wall -Wextra -Werror -pedantic -fPIC -shared \
   "$here/fake-ioctl-efault.c" -o "$scratch/fake-efault.so"
set +e
LD_PRELOAD="$scratch/fake-efault.so" \
  "$scratch/probe" --device /dev/null --ioctl-cmd 0x123456 >"$scratch/efault.log" 2>&1
fault_result=$?
set -e
if [ "$fault_result" -ne 77 ] || grep -Fqx 'HOS2_IOCTL_ENOTTY' "$scratch/efault.log" ||
   ! grep -Fq 'HOS2_IOCTL_OTHER_ERROR' "$scratch/efault.log"; then
    cat "$scratch/efault.log" >&2
    echo "Injected EFAULT was misclassified as ENOTTY" >&2
    exit 1
fi
echo "PASS Linux /dev/null ENOTTY vs injected EFAULT differentiated (host only)"
echo "PASS real Linux /dev/null ioctl rejected; Asterinas ioctl remains untested"
