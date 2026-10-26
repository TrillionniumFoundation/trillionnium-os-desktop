"""Reserve a shared Cargo cache across every product build and packaging step.

Cargo's own lock covers individual commands. This additional advisory lease
serializes cooperating product builders across the gaps between commands.
Direct Cargo users must also leave a leased product cache alone.
"""
import fcntl
import os
from pathlib import Path
import stat


class TargetLease:
    def __init__(self, target):
        target = Path(target)
        if not target.is_absolute():
            raise ValueError("Product target cache must be absolute")
        target.mkdir(parents=True, exist_ok=True)
        if target.resolve(strict=True) != target:
            raise ValueError("Product target cache must be canonical")
        path = target / ".trill-product-build.lock"
        descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
        try:
            info = os.fstat(descriptor)
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                    or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o600):
                raise ValueError("Product target lease custody differs; existing files are never repaired")
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise ValueError("Another product builder holds this target cache") from error
        except BaseException:
            os.close(descriptor)
            raise
        self.descriptor = descriptor
        self.path = path

    def record(self):
        return {"path": str(self.path), "scope": "exclusive cooperating-product-builder lease through packaging"}

    def close(self):
        if self.descriptor is not None:
            os.close(self.descriptor)
            self.descriptor = None

    def __enter__(self):
        return self

    def __exit__(self, *_error):
        self.close()
