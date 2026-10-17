"""Create-only A09 evidence output; never overwrite previous observations.

This protects the final output pathname on Linux with O_EXCL/O_NOFOLLOW.
The caller must select a trusted parent directory: this does not prevent
symlinked ancestor directories, arbitrary concurrent mutations in that
parent, process crashes during writing, or forged/unsigned evidence.
"""
import os
import stat

MAX_EVIDENCE_OUTPUT_BYTES = 32 * 1024 * 1024


def write_evidence_output(path, payload):
    """Write a fresh UTF-8 JSON record; '-' prints to standard output.

    Return only after the entire regular file has been written and fsynced.
    Existing regular files, hard links, symlinks, FIFO and sockets are refused
    by exclusive creation. On I/O error the caller must NOT claim success.
    """
    if not isinstance(payload, str):
        raise TypeError("A09 evidence payload must be text")
    raw = payload.encode("utf-8")
    if len(raw) > MAX_EVIDENCE_OUTPUT_BYTES:
        raise ValueError("A09 evidence output exceeds bounded 32MiB size")
    if str(path) == "-":
        print(payload, end="")
        return
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                 os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise OSError("A09 evidence output must be a regular file")
        offset = 0
        while offset < len(raw):
            written = os.write(fd, raw[offset:])
            if written <= 0:
                raise OSError("A09 evidence output write did not progress")
            offset += written
        os.fsync(fd)
    finally:
        os.close(fd)
