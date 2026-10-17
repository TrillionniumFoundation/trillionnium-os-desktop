"""Immutable Linux FD inputs for a disposable, checksum-pinned QEMU guest.

The verifier supplies bytes *already* read and checked against independent
SHA256 pins. Never reopen the caller-supplied pathname in the QEMU process.
No kernel, block device, cgroup, BIOS firmware or GPU is modified here.
"""
import fcntl
import hashlib
import os
import sys


_INPUT_NAMES = frozenset(("kernel", "bios", "initramfs"))
_REQUIRED_SEALS = (fcntl.F_SEAL_SEAL | fcntl.F_SEAL_SHRINK |
                   fcntl.F_SEAL_GROW | fcntl.F_SEAL_WRITE)


def sealed_input(name, payload):
    """Return an immutable memfd holding the exact checked snapshot bytes.

    The caller owns the FD, must pass it to QEMU in ``pass_fds``, and must
    close it in ``finally``. QEMU sees ``/proc/self/fd/N`` rather than the
    original user-writable pathname. Fail closed if sealing is unsupported.
    """
    if (not sys.platform.startswith("linux") or
            not callable(getattr(os, "memfd_create", None)) or
            not hasattr(os, "MFD_ALLOW_SEALING") or
            not hasattr(fcntl, "F_ADD_SEALS") or
            not hasattr(fcntl, "F_GET_SEALS")):
        raise ValueError("Linux sealable memfd snapshots are required")
    if name not in _INPUT_NAMES:
        raise ValueError("unknown QEMU snapshot identity")
    if not isinstance(payload, bytes) or not payload:
        raise ValueError("QEMU snapshot must contain nonempty verified bytes")
    fd = os.memfd_create("a05-queryabi-" + name,
                         flags=os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
    try:
        data = memoryview(payload)
        written = 0
        while written < len(data):
            n = os.write(fd, data[written:])
            if n <= 0:
                raise OSError("failed to write the complete QEMU snapshot")
            written += n
        fcntl.fcntl(fd, fcntl.F_ADD_SEALS, _REQUIRED_SEALS)
        if fcntl.fcntl(fd, fcntl.F_GET_SEALS) != _REQUIRED_SEALS:
            raise OSError("QEMU input is not fully immutable")
        if os.fstat(fd).st_size != len(payload):
            raise OSError("QEMU input snapshot size changed")
        actual = os.pread(fd, len(payload), 0)
        if hashlib.sha256(actual).digest() != hashlib.sha256(payload).digest():
            raise OSError("QEMU input snapshot hash changed")
        return fd
    except BaseException:
        os.close(fd)
        raise
