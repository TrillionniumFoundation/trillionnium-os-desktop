"""Bounded read-only file and complete directory witnesses for candidate checks."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat


def sibling(name):
    descriptor = importlib.util.spec_from_file_location('p4_candidate_' + name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(descriptor)
    descriptor.loader.exec_module(module)
    return module


def need(value, message):
    if not value:
        raise RuntimeError(message)


def f9(value):
    return [getattr(value, key) for key in ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')]


def parents(path):
    path = Path(path)
    need(path.is_absolute() and '..' not in path.parts and str(path) == os.path.normpath(path), 'canonical absolute path required')
    observed = {}
    for parent in reversed(path.parents):
        info = parent.lstat()
        need(stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode), 'symlink or non-directory ancestor: ' + str(parent))
        observed[str(parent)] = f9(info)
    return observed


def read_file(path, maximum=256 * 1024**2, contents=False):
    path = Path(path)
    before_parents = parents(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and 0 <= before.st_size <= maximum, 'bounded single-link regular file required: ' + str(path))
        digest = hashlib.sha256(); pieces = []; size = 0
        while True:
            part = os.read(fd, 1024**2)
            if not part:
                break
            size += len(part); need(size <= maximum, 'file grew beyond bound')
            digest.update(part)
            if contents:
                pieces.append(part)
        need(size == before.st_size and f9(before) == f9(os.fstat(fd)) == f9(path.lstat()), 'file identity changed while hashing: ' + str(path))
        # Reading may update atime; the nine identity fields deliberately omit it.
        need(parents(path) == before_parents, 'parent identity changed while hashing: ' + str(path))
        row = {'path': str(path), 'bytes': size, 'sha256': digest.hexdigest(), 'identity': f9(before)}
        return (row, b''.join(pieces)) if contents else row
    finally:
        os.close(fd)


def strict_json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            need(key not in result, 'duplicate JSON key: ' + key)
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique, parse_constant=lambda value: (_ for _ in ()).throw(RuntimeError('non-finite JSON number')))


def read_json(path, maximum=16 * 1024**2):
    ref, raw = read_file(path, maximum, True)
    return strict_json(raw), ref


def exact_file(row, path, maximum=256 * 1024**2, identity=False):
    need(type(row) is dict and row.get('path') == str(path), 'file path differs: ' + str(path))
    ref = read_file(path, maximum)
    need(type(row.get('bytes')) is int and row['bytes'] == ref['bytes'] and row.get('sha256') == ref['sha256'], 'whole file bytes differ: ' + str(path))
    if identity:
        need(row.get('identity') == ref['identity'], 'whole file F9 differs: ' + str(path))
    return ref


def directory_refs(root, skip_git=False):
    root = Path(root); parents(root)
    seen = {}; pending = [root]
    while pending:
        path = pending.pop(); before = path.lstat()
        need(stat.S_ISDIR(before.st_mode), 'real tree directory required: ' + str(path))
        relative = '.' if path == root else path.relative_to(root).as_posix()
        seen[relative] = {'path': str(path), 'identity': f9(before)}
        children = sorted(path.iterdir())
        for child in children:
            if skip_git and path == root and child.name == '.git':
                continue
            info = child.lstat()
            if stat.S_ISDIR(info.st_mode):
                pending.append(child)
            else:
                need(stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode), 'unsupported tree member')
        need(f9(path.lstat()) == f9(before), 'directory changed during inventory')
        need(len(seen) <= 20000, 'finite recipe directory bound exceeded')
    for row in seen.values():
        need(f9(Path(row['path']).lstat()) == row['identity'], 'directory changed across inventory')
    return seen


def verify_directories(root, expected, skip_git=False):
    need(type(expected) is dict and '.' in expected, 'complete directory map including root required')
    actual = directory_refs(root, skip_git)
    need(actual == expected, 'exact directory membership/F9 changed: ' + str(root))
    return actual


def leaf_names(root, skip_git=False):
    root = Path(root); names = set()
    for directory, dirs, files in os.walk(root, followlinks=False):
        if skip_git and Path(directory) == root:
            dirs[:] = [name for name in dirs if name != '.git']
        for name in list(dirs):
            if (Path(directory) / name).is_symlink():
                files.append(name); dirs.remove(name)
        for name in files:
            path = Path(directory) / name
            need(path.is_file() or path.is_symlink(), 'unsupported recipe leaf')
            names.add(path.relative_to(root).as_posix())
    return names
