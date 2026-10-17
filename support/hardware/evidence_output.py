"""A09 immutable evidence publication (read-only hardware probes; no GPU I/O).

Use a new, private, same-directory staging inode and fsync before exposing the
final name via an exclusive hard link. Never replace an old evidence record.
Trust the chosen output directory; this is not cryptographic attestation.
"""
import os
import secrets
import stat

MAX_EVIDENCE_OUTPUT_BYTES = 32 * 1024 * 1024


def write_evidence_output(path, payload):
    """Publish only a complete UTF-8 record under a previously absent name.

    The directory must be trusted. Linux local-filesystem durability is best
    effort (filesystem/underlying storage still matters). Neither this
    function nor an unsigned JSON manifest proves hardware execution.
    """
    if not isinstance(payload, str):
        raise TypeError("A09 evidence payload must be text")
    raw = payload.encode("utf-8")
    if len(raw) > MAX_EVIDENCE_OUTPUT_BYTES:
        raise ValueError("A09 evidence output exceeds bounded 32MiB size")
    path = os.fspath(path)
    if not isinstance(path, str):
        raise TypeError("A09 evidence pathname must be text")
    if path == "-":
        print(payload, end="")
        return

    parent, name = os.path.split(path)
    if not name or name in (".", ".."):
        raise ValueError("A09 evidence output must name a new regular file")

    # A directory fd pins the actual parent even if an ancestor is renamed.
    # O_NOFOLLOW also rejects a symlink in the *last* parent component.
    dirfd = os.open(parent or ".", os.O_RDONLY | os.O_DIRECTORY |
                    os.O_NOFOLLOW | os.O_CLOEXEC)
    temp_name = None
    fd = None
    published = False
    try:
        for _ in range(8):
            candidate = ".a09-evidence-" + secrets.token_hex(16) + ".pending"
            try:
                fd = os.open(candidate, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                             os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                             0o600, dir_fd=dirfd)
                temp_name = candidate
                break
            except FileExistsError:
                continue
        if fd is None:
            raise FileExistsError("A09 failed to allocate unique pending evidence")
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise OSError("A09 pending evidence is not a regular file")
        offset = 0
        while offset < len(raw):
            written = os.write(fd, raw[offset:])
            if written <= 0:
                raise OSError("A09 pending evidence write did not progress")
            offset += written
        os.fsync(fd)
        # Atomic create-only publication; fails with EEXIST for file, link,
        # symlink, directory, FIFO or a competing writer. No rename overwrite.
        os.link(temp_name, name, src_dir_fd=dirfd, dst_dir_fd=dirfd,
                follow_symlinks=False)
        published = True
        os.fsync(dirfd)
    finally:
        try:
            if fd is not None:
                os.close(fd)
        finally:
            try:
                if temp_name is not None:
                    os.unlink(temp_name, dir_fd=dirfd)
                if published:
                    os.fsync(dirfd)
            finally:
                os.close(dirfd)
