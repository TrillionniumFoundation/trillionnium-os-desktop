"""Bounded Linux-only subprocess runner for disposable GPU laboratory tests.

The caller owns GPU identity/isolation admission. This module only contains
host-process resource limits; it does NOT prove GPU DMA quiescence on failure.
"""
import os
import resource
import signal
import subprocess
import tempfile

MAX_OUTPUT_BYTES = 65536


class OutputLimitExceeded(RuntimeError):
    pass


def _limit_file_bytes():
    # Child only; parent process file limits remain unchanged.
    resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_OUTPUT_BYTES, MAX_OUTPUT_BYTES))


def run_bounded(argv, *, capture_output, text, timeout, check=False):
    if not capture_output or not text or check:
        raise ValueError("bounded CUDA runner requires text capture and check=False")
    if not isinstance(timeout, (int, float)) or not 0 < timeout <= 120:
        raise ValueError("invalid bounded timeout")
    with tempfile.TemporaryFile(mode="w+b") as stdout, tempfile.TemporaryFile(mode="w+b") as stderr:
        process = subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            start_new_session=True,
            preexec_fn=_limit_file_bytes,
        )
        try:
            result_code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            # Only the newly created *child* process group; never the parent
            # machine's GPU driver or host services. Killing a process group
            # is NOT proof that its GPU commands or DMA have stopped.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
            raise
        out_size = os.fstat(stdout.fileno()).st_size
        err_size = os.fstat(stderr.fileno()).st_size
        if out_size >= MAX_OUTPUT_BYTES or err_size >= MAX_OUTPUT_BYTES:
            raise OutputLimitExceeded("CUDA child output exceeded 64 KiB cap; GPU effect unknown")
        stdout.seek(0)
        stderr.seek(0)
        return subprocess.CompletedProcess(
            argv,
            result_code,
            stdout.read().decode("utf-8", "replace"),
            stderr.read().decode("utf-8", "replace"),
        )
