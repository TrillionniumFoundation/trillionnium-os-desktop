"""Finite owned FD cleanup, including cancellation during file acquisition.

Only acquisition/registration and close loops block cancellation. Pending
signals are delivered when the mask is restored; no cancellation is swallowed.
The object never unlinks a path or retries an Android operation.
"""
import os
import signal

SIGNALS = {signal.SIGINT, signal.SIGTERM, signal.SIGALRM}

class OwnedHandles:
    def __init__(self):
        self.fds = []

    def _acquire(self, factory):
        previous = signal.pthread_sigmask(signal.SIG_BLOCK, SIGNALS)
        try:
            fd = factory()
            self.fds.append(fd)
            return fd
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, previous)

    def open_root(self, target, path, flags):
        return self._acquire(lambda: target.open_root(path, flags | os.O_CLOEXEC))

    def open_child(self, name, flags, directory):
        if directory not in self.fds or not name or '/' in name or name in ('.', '..'):
            raise RuntimeError('ONLY_THIS_OWNED_DIRECTORY_FD_AND_ONE_CHILD_NAME')
        return self._acquire(lambda: os.open(name, flags | os.O_CLOEXEC, dir_fd=directory))

    def close_one(self, fd):
        previous = signal.pthread_sigmask(signal.SIG_BLOCK, SIGNALS)
        try:
            if self.fds.count(fd) != 1:
                raise RuntimeError('EXACTLY_ONE_THIS_OBJECT_OWNED_DESCRIPTOR')
            self.fds.remove(fd)
            os.close(fd)
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, previous)

    def close(self):
        previous = signal.pthread_sigmask(signal.SIG_BLOCK, SIGNALS)
        first = None
        try:
            while self.fds:
                fd = self.fds.pop()
                try:
                    os.close(fd)
                except BaseException as error:
                    if first is None:
                        first = error
                    else:
                        first.add_note('OWNED_FD_CLOSE:' + type(error).__name__)
            if first is not None:
                raise first
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, previous)
