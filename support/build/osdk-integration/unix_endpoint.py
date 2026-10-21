"""Own a private AF_UNIX GDB listener through QEMU descriptor handoff.

Path identity checks cover this task's private-directory lifecycle. They are
not an atomic connect-to-inode primitive or a defense against malicious code
running with the same UID. The pathname inode and socket-FD inode belong to
different filesystems and are recorded separately.
"""
import os
from pathlib import Path
import re
import socket
import stat
import tempfile


def path_identity(path):
    observed = Path(path).lstat()
    return {"device": observed.st_dev, "inode": observed.st_ino,
            "mode": observed.st_mode, "uid": observed.st_uid}


def verify_endpoint(identity, listener=None):
    """Reject stale/replaced paths before and after a real GDB connection."""
    path = Path(identity["path"])
    parent = Path(identity["directory"]["path"])
    if identity.get("transport") != "unix" or not path.is_absolute() \
            or path.parent != parent or path.resolve() != path \
            or not re.fullmatch(r"/[A-Za-z0-9_./-]+", str(path)) \
            or len(os.fsencode(path)) >= 104:
        raise ValueError("UNIX GDB endpoint must have a private, absolute, short safe path")
    parent_now = path_identity(parent)
    if parent_now != identity["directory"]["identity"] \
            or not stat.S_ISDIR(parent_now["mode"]) \
            or stat.S_IMODE(parent_now["mode"]) != 0o700 \
            or parent_now["uid"] != os.getuid():
        raise ValueError("UNIX GDB private directory identity changed")
    socket_now = path_identity(path)
    if socket_now != identity["socket"] or not stat.S_ISSOCK(socket_now["mode"]) \
            or socket_now["uid"] != os.getuid():
        raise ValueError("UNIX GDB socket pathname identity changed")
    if listener is not None:
        descriptor = os.fstat(listener.fileno())
        if listener.family != socket.AF_UNIX \
                or listener.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE) != socket.SOCK_STREAM \
                or listener.getsockopt(socket.SOL_SOCKET, socket.SO_ACCEPTCONN) != 1 \
                or listener.getsockname() != str(path) \
                or {"device": descriptor.st_dev, "inode": descriptor.st_ino} != identity["listener_fd"]:
            raise ValueError("UNIX GDB inherited listener descriptor identity changed")
    return True


def reserve_endpoint(temporary_root):
    """Bind once; callers keep this listener until the actual QEMU spawn."""
    directory = Path(tempfile.mkdtemp(prefix="a01g-", dir=temporary_root)).resolve()
    directory.chmod(0o700)
    path = directory / "gdb.sock"
    identity = {"transport": "unix", "path": str(path),
                "directory": {"path": str(directory), "identity": path_identity(directory)},
                "created_by_pid": os.getpid()}
    listener = None
    try:
        if not re.fullmatch(r"/[A-Za-z0-9_./-]+", str(path)) or len(os.fsencode(path)) >= 104:
            raise ValueError("temporary directory cannot provide a short safe UNIX GDB path")
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(path))
        identity["socket"] = path_identity(path)
        listener.listen(1)
        descriptor = os.fstat(listener.fileno())
        identity["listener_fd"] = {"device": descriptor.st_dev, "inode": descriptor.st_ino}
        verify_endpoint(identity, listener)
        return listener, identity
    except BaseException:
        if listener is not None:
            listener.close()
        release_endpoint(identity)
        raise


def release_endpoint(identity):
    """Unlink only the originally owned socket; never remove a replacement."""
    path = Path(identity["path"])
    directory = Path(identity["directory"]["path"])
    if path_identity(directory) != identity["directory"]["identity"]:
        raise ValueError("refusing to remove a replaced UNIX GDB directory")
    if os.path.lexists(path):
        if "socket" not in identity or path_identity(path) != identity["socket"]:
            raise ValueError("refusing to unlink a replaced UNIX GDB endpoint")
        path.unlink()
    directory.rmdir()
    return {"socket_removed": True, "private_directory_removed": True,
            "identity_checked": True}
