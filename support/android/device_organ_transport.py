"""Bounded local process transport for the explicitly selected Android helpers.

This module performs host I/O. It is not a TrustedReadOnlyOrganV1 handler, a
grant provider, an effect owner, a command shell, or a persistent operation log.
"""

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import selectors
import signal
import stat
import subprocess
import time


MAX_REPLY_BYTES = 1024 * 1024
MAX_REQUEST_BYTES = 4096


class AdapterError(Exception):
    """Finite, non-sensitive failure with conservative submission semantics."""

    def __init__(self, code, *, attempted=False, outcome_unknown=False):
        super().__init__(code)
        self.code = code
        self.attempted = attempted
        self.outcome_unknown = outcome_unknown

    def receipt(self):
        return {
            "ok": False,
            "error": self.code,
            "transport_attempted": self.attempted,
            "outcome_unknown": self.outcome_unknown,
            "automatic_retry": False,
            "production_authority": False,
            "device_effect_verified": False,
        }


def _object_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def _reject_constant(_value):
    raise ValueError("nonfinite JSON")


def parse_object(data):
    if not isinstance(data, bytes) or len(data) > MAX_REPLY_BYTES:
        raise AdapterError("REPLY_TOO_LARGE")
    try:
        value = json.loads(
            data.decode("utf-8", "strict"),
            object_pairs_hook=_object_pairs,
            parse_constant=_reject_constant,
        )
    except (UnicodeError, ValueError, RecursionError):
        raise AdapterError("INVALID_JSON_REPLY") from None
    if not isinstance(value, dict):
        raise AdapterError("OBJECT_REPLY_REQUIRED")
    return value


def canonical_bytes(value):
    try:
        return json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8", "strict")
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise AdapterError("INVALID_UTF8_JSON") from None


@dataclass(frozen=True)
class PinnedTool:
    path: str
    sha256: str
    owner_uid: int = 0

    def measure(self):
        """Check the selected file, not an executable found through PATH.

        Hashes before and after an invocation are source measurements; they are
        not hardware attestation or proof of every transitive dependency.
        """
        if not isinstance(self.sha256, str) or len(self.sha256) != 64:
            raise AdapterError("INVALID_TOOL_PIN")
        if any(c not in "0123456789abcdef" for c in self.sha256):
            raise AdapterError("INVALID_TOOL_PIN")
        if not Path(self.path).is_absolute():
            raise AdapterError("ABSOLUTE_TOOL_PATH_REQUIRED")
        try:
            fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
            with os.fdopen(fd, "rb") as stream:
                before = os.fstat(stream.fileno())
                if (not stat.S_ISREG(before.st_mode) or before.st_uid != self.owner_uid
                        or before.st_mode & 0o022 or not before.st_mode & 0o111
                        or before.st_size > 64 * 1024 * 1024):
                    raise AdapterError("UNTRUSTED_TOOL_FILE")
                digest = hashlib.sha256()
                count = 0
                while chunk := stream.read(65536):
                    count += len(chunk)
                    if count > 64 * 1024 * 1024:
                        raise AdapterError("UNTRUSTED_TOOL_FILE")
                    digest.update(chunk)
                after = os.fstat(stream.fileno())
        except OSError:
            raise AdapterError("TOOL_UNAVAILABLE") from None
        identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        if identity(before) != identity(after) or digest.hexdigest() != self.sha256:
            raise AdapterError("TOOL_PIN_MISMATCH")
        return {"path": self.path, "sha256": self.sha256, "bytes": before.st_size}


@dataclass(frozen=True)
class ProcessReply:
    returncode: int
    stdout: bytes
    stderr: bytes


def run_bounded(argv, stdin, timeout_seconds):
    """Make one attempt; timeout never schedules another process or effect."""
    if (not isinstance(stdin, bytes) or len(stdin) > MAX_REQUEST_BYTES
            or type(timeout_seconds) not in (int, float) or not 0 < timeout_seconds <= 60):
        raise AdapterError("INVALID_PROCESS_BOUND")
    try:
        process = subprocess.Popen(
            argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, start_new_session=True,
            env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C.UTF-8"},
        )
    except OSError:
        raise AdapterError("HELPER_START_FAILED") from None
    deadline = time.monotonic() + timeout_seconds
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    completed = False
    try:
        process.stdin.write(stdin)
        process.stdin.close()
        with selectors.DefaultSelector() as ready:
            for name in buffers:
                stream = getattr(process, name)
                os.set_blocking(stream.fileno(), False)
                ready.register(stream, selectors.EVENT_READ, name)
            while ready.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise AdapterError("TIMEOUT", attempted=True, outcome_unknown=True)
                for key, _ in ready.select(remaining):
                    chunk = os.read(key.fileobj.fileno(), 65536)
                    if not chunk:
                        ready.unregister(key.fileobj)
                        continue
                    buffers[key.data].extend(chunk)
                    if sum(map(len, buffers.values())) > MAX_REPLY_BYTES:
                        raise AdapterError("REPLY_TOO_LARGE", attempted=True, outcome_unknown=True)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AdapterError("TIMEOUT", attempted=True, outcome_unknown=True)
        returncode = process.wait(timeout=remaining)
        completed = True
        return ProcessReply(returncode, bytes(buffers["stdout"]), bytes(buffers["stderr"]))
    except (OSError, subprocess.TimeoutExpired):
        raise AdapterError("TRANSPORT_RESULT_UNKNOWN", attempted=True, outcome_unknown=True) from None
    finally:
        if not completed:
            # Only our newly created process group is addressed. Killing the
            # transport is not proof that Android cancelled an in-flight call.
            # Do not poll/reap the leader first: it may have exited while a
            # descendant still holds the pipes. Its unreaped PID pins the
            # group identity until this best-effort cleanup has been issued.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                try:
                    process.kill()
                except OSError:
                    pass
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                pass
        for stream in (process.stdin, process.stdout, process.stderr):
            try:
                stream.close()
            except OSError:
                pass
