"""Bound A05's untrusted host compiler logs and one disposable guest ELF.

Host-only evidence protection: a successful compile is not a QEMU boot or an
Asterinas ioctl result. Child limits never change the parent's rlimits.
"""
import os
from pathlib import Path
import resource
import signal
import stat
import subprocess

MAX_COMPILER_FILE_BYTES = 16 * 1024 * 1024


def _limit_child_files():
    soft, hard = resource.getrlimit(resource.RLIMIT_FSIZE)
    cap = MAX_COMPILER_FILE_BYTES
    if soft != resource.RLIM_INFINITY:
        cap = min(cap, soft)
    if hard != resource.RLIM_INFINITY:
        cap = min(cap, hard)
    resource.setrlimit(resource.RLIMIT_FSIZE, (cap, cap))


def _read_bounded_regular(path):
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NONBLOCK | os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError as exc:
        raise ValueError("compiler did not produce a guest ELF") from exc
    with os.fdopen(descriptor, "rb") as source:
        before = os.fstat(source.fileno())
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or before.st_size == 0 or before.st_size > MAX_COMPILER_FILE_BYTES):
            raise ValueError("compiler ELF is not a bounded isolated regular file")
        payload = source.read(MAX_COMPILER_FILE_BYTES + 1)
        after = os.fstat(source.fileno())
        if (len(payload) != before.st_size or len(payload) > MAX_COMPILER_FILE_BYTES
                or (before.st_dev, before.st_ino, before.st_mtime_ns,
                    before.st_ctime_ns) != (after.st_dev, after.st_ino,
                                           after.st_mtime_ns, after.st_ctime_ns)):
            raise ValueError("compiler ELF changed during bounded read")
    return payload


def compile_guest_probe(argv, guest_elf, log_path, timeout=60):
    """Compile without unbounded capture_output/ELF read; return checked bytes.

    Timeout/failure cannot certify a kernel, prove that all descendants are
    reaped, or authorize copying a partial image into the QEMU initramfs.
    """
    if not isinstance(argv, (list, tuple)) or not argv or any(
        not isinstance(arg, str) or "\0" in arg for arg in argv
    ):
        raise ValueError("compiler argv must consist of nonempty argument strings")
    if not 0 < timeout <= 60:
        raise ValueError("compiler timeout must be in (0,60]")
    guest_elf = Path(guest_elf)
    log_path = Path(log_path)
    # The parent owns the single, new capture file. Do not buffer compiler
    # stdout/stderr in Python RAM or reopen that pathname after a write.
    with log_path.open("xb") as capture:
        proc = subprocess.Popen(
            list(argv), stdin=subprocess.DEVNULL, stdout=capture,
            stderr=subprocess.STDOUT, start_new_session=True,
            preexec_fn=_limit_child_files, close_fds=True,
        )
        try:
            exit_code = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                raise RuntimeError("compiler process not reaped after deadline") from exc
            raise TimeoutError("compiler exceeded the disposable host deadline") from exc
        if exit_code != 0:
            raise ValueError(f"compiler failed with exit status {exit_code}")
    return _read_bounded_regular(guest_elf)
