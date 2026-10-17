"""Bounded nonblocking Linux subprocess capture for disposable GPU labs.

Only stdout/stderr capture is limited: unlike RLIMIT_FSIZE this does NOT
restrict NVRTC/CUDA compiler caches or other guest process file writes.
Process-group termination is not proof of physical GPU DMA quiescence.
"""
import os
import selectors
import signal
import subprocess
import time

MAX_OUTPUT_BYTES = 65536


class OutputLimitExceeded(RuntimeError):
    pass


REAP_TIMEOUT_SECONDS = 2


def terminate_child_group(process, *, reap_timeout=REAP_TIMEOUT_SECONDS):
    """Best-effort bounded local child cleanup, never a GPU DMA quiescence proof.

    A GPU-stalled process may be uninterruptible even to SIGKILL. Never let
    process.wait() without a timeout turn a bounded CUDA run into a hang.
    """
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=reap_timeout)
    except subprocess.TimeoutExpired:
        return False
    return True


def run_bounded(argv, *, capture_output, text, timeout, check=False):
    if not capture_output or not text or check:
        raise ValueError("bounded CUDA runner requires text capture and check=False")
    if not isinstance(timeout, (int, float)) or not 0 < timeout <= 120:
        raise ValueError("invalid bounded timeout")
    process = subprocess.Popen(
        argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, start_new_session=True,
    )
    outputs = {"stdout": [], "stderr": []}
    used = {"stdout": 0, "stderr": 0}
    deadline = time.monotonic() + timeout
    try:
        with selectors.DefaultSelector() as selector:
            for label, pipe in (("stdout", process.stdout), ("stderr", process.stderr)):
                os.set_blocking(pipe.fileno(), False)
                selector.register(pipe, selectors.EVENT_READ, label)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(argv, timeout)
                ready = selector.select(remaining)
                if not ready:
                    raise subprocess.TimeoutExpired(argv, timeout)
                for key, _ in ready:
                    try:
                        chunk = os.read(key.fileobj.fileno(), 8192)
                    except BlockingIOError:
                        continue
                    if not chunk:
                        selector.unregister(key.fileobj)
                        key.fileobj.close()
                        continue
                    label = key.data
                    used[label] += len(chunk)
                    if used[label] >= MAX_OUTPUT_BYTES:
                        raise OutputLimitExceeded(
                            "CUDA child stdout/stderr exceeded 64 KiB cap; GPU effect unknown"
                        )
                    outputs[label].append(chunk)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired(argv, timeout)
        result_code = process.wait(timeout=remaining)
    except BaseException:
        # Bounded reap: an uninterruptible GPU-stalled child must not hang
        # the test supervisor forever. Unreaped child and GPU DMA remain
        # unknown effects requiring independent A01/A05 quarantine.
        terminate_child_group(process)
        raise
    finally:
        if process.stdout and not process.stdout.closed:
            process.stdout.close()
        if process.stderr and not process.stderr.closed:
            process.stderr.close()
    return subprocess.CompletedProcess(
        argv, result_code,
        b"".join(outputs["stdout"]).decode("utf-8", "replace"),
        b"".join(outputs["stderr"]).decode("utf-8", "replace"),
    )
