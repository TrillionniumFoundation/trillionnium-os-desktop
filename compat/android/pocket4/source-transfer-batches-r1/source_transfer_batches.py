"""Bound each rsync files-from list without widening the approved file set."""
from pathlib import PurePosixPath


def partition_filelist(raw, maximum_entries=8192):
    if type(raw) is not bytes or not raw or not raw.endswith(b'\0'):
        raise ValueError('complete nonempty NUL file list required')
    if type(maximum_entries) is not int or not 1 <= maximum_entries <= 8192:
        raise ValueError('strict bounded batch size required')
    names = raw[:-1].split(b'\0')
    if names != sorted(set(names)):
        raise ValueError('exact sorted unique file list required')
    for name in names:
        value = name.decode('utf-8', 'strict')
        path = PurePosixPath(value)
        if (not value or path.is_absolute() or '..' in path.parts
                or value != path.as_posix() or value.endswith('/')):
            raise ValueError('canonical relative file or symlink path required')
    batches = [b'\0'.join(names[start:start + maximum_entries]) + b'\0'
               for start in range(0, len(names), maximum_entries)]
    if b''.join(batches) != raw:
        raise RuntimeError('batch partition changed the original file list')
    return batches
