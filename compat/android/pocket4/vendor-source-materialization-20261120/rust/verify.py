#!/usr/bin/env python3
"""Replay one hash-bound source fix after verifying the complete parent tree.

The unchanged read/membership/Git-tree helpers below are copied from PR315's
runtime-current-source-r1/verify.py (SHA256 0a669e37...f7f0e1).
No original capsule, expected target list or release qualification is edited.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat

HERE = Path(__file__).resolve().parent
PARENT_INVENTORY = '075affecd123cc60e30eadf70ae95cc9ec34d5686694bedf0914014c36d04c0b'
PARENT_VERIFY_SHA = '0a669e373aca985a7b3f86b4d5f02782e38fac57ebe098738692897eebf7f0e1'
PARENT_TREE = '64f57a4de88053fea58cfa5112cd089e45b20be6'
CHANGED_PATH = 'tools/droidloom-source/src/lib.rs'

def need(value, message):
    if not value:
        raise RuntimeError(message)



def f9(s):
    return (s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_gid, s.st_nlink,
            s.st_size, s.st_mtime_ns, s.st_ctime_ns)



def digest(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}



def object_id(kind, raw):
    return hashlib.sha1(kind.encode() + b' ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()



def safe(name):
    need(isinstance(name, str) and name and not name.startswith('/') and '\\' not in name
         and all(part not in ('', '.', '..', '.git') for part in name.split('/'))
         and all(ord(char) >= 32 and ord(char) != 127 for char in name), 'invalid exact relative path')
    return Path(name)



def regular(path, cap=64 * 1024 * 1024):
    path = Path(path).absolute()
    need(path.resolve() == path, 'input path contains an alias: ' + str(path))
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and 0 <= before.st_size <= cap,
             'bounded independent regular input required')
        with os.fdopen(os.dup(fd), 'rb') as stream:
            raw = stream.read(cap + 1)
        need(len(raw) == before.st_size and f9(before) == f9(os.fstat(fd)) == f9(path.lstat()),
             'input changed during complete held read')
        return raw
    finally:
        os.close(fd)



def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        need(key not in result, 'duplicate JSON key: ' + key)
        result[key] = value
    return result



def decode(raw):
    return json.loads(raw, object_pairs_hook=unique_pairs)



def check(path, expected):
    raw = regular(path)
    need(digest(raw) == {key: expected[key] for key in ('bytes', 'sha256')}, 'exact input differs: ' + str(path))
    if 'git_blob' in expected:
        need(object_id('blob', raw) == expected['git_blob'], 'Git blob identity differs: ' + str(path))
    return raw



def member_names(root, skip_root_git=False):
    root = Path(root).absolute()
    need(root.resolve() == root and stat.S_ISDIR(root.lstat().st_mode), 'canonical existing directory required')
    names, directories = set(), {'.': f9(root.lstat())}
    for directory, children, files in os.walk(root, followlinks=False):
        current = Path(directory)
        if current == root and skip_root_git and '.git' in children:
            git = current / '.git'
            need(stat.S_ISDIR(git.lstat().st_mode) and not git.is_symlink(), 'root Git metadata must be a directory')
            children.remove('.git')
        for name in children:
            path = current / name
            relative = path.relative_to(root).as_posix()
            safe(relative)
            need(stat.S_ISDIR(path.lstat().st_mode) and not path.is_symlink(), 'directory alias or special entry rejected')
            directories[relative] = f9(path.lstat())
        for name in files:
            relative = (current / name).relative_to(root).as_posix()
            safe(relative)
            need(relative not in names, 'duplicate physical member')
            names.add(relative)
    return names, directories



def validate_rows(rows, count):
    need(isinstance(rows, list) and len(rows) == count, 'complete source inventory required')
    result = {}
    for row in rows:
        need(set(row) == {'path', 'bytes', 'sha256', 'git_blob', 'mode'}, 'complete exact source row required')
        safe(row['path'])
        need(row['path'] not in result and row['mode'] in ('100644', '100755')
             and type(row['bytes']) is int and 0 <= row['bytes'] <= 64 * 1024 * 1024
             and re.fullmatch('[0-9a-f]{64}', row['sha256'])
             and re.fullmatch('[0-9a-f]{40}', row['git_blob']), 'unique bounded original file required')
        result[row['path']] = row
    return result



def tree_id(rows):
    root = {}
    for row in rows:
        parts = safe(row['path']).parts
        node = root
        for part in parts[:-1]:
            node = node.setdefault(part, {})
            need(isinstance(node, dict), 'source file/directory collision')
        need(parts[-1] not in node, 'duplicate source tree member')
        node[parts[-1]] = (row['mode'], row['git_blob'])

    def encode(node):
        entries = []
        for name, value in node.items():
            if isinstance(value, dict):
                mode, oid, sortname = '40000', encode(value), name.encode() + b'/'
            else:
                mode, oid = value
                sortname = name.encode()
            entries.append((sortname, mode.encode() + b' ' + name.encode() + b'\0' + bytes.fromhex(oid)))
        return object_id('tree', b''.join(body for _, body in sorted(entries)))
    return encode(root)



def source_snapshot(root, rows, expected_tree):
    root = Path(root).absolute()
    wanted = validate_rows(rows, len(rows))
    need(tree_id(rows) == expected_tree, 'complete declared root tree differs')
    names, directories = member_names(root, skip_root_git=True)
    expected_dirs = {'.'} | {str(parent) for name in wanted for parent in Path(name).parents if str(parent) != '.'}
    need(names == set(wanted) and set(directories) == expected_dirs, 'complete producer file or directory membership changed')
    files = {}
    for name, row in sorted(wanted.items()):
        path = root / name
        before = f9(path.lstat())
        need(stat.S_ISREG(before[2]) and stat.S_IMODE(before[2]) == (int(row['mode'], 8) & 0o777),
             'producer original regular mode differs: ' + name)
        check(path, row)
        need(f9(path.lstat()) == before, 'producer identity changed during verification')
        files[name] = before
    after_names, after_dirs = member_names(root, skip_root_git=True)
    need(names == after_names and directories == after_dirs, 'producer membership changed during full audit')
    need(all(f9((root / name).lstat()) == identity for name, identity in files.items()), 'producer F9 changed during full audit')
    return {'files': files, 'directories': directories, 'tree': expected_tree}



def fresh_destination(path, protected):
    path = Path(path).absolute()
    need(path.resolve() == path and not os.path.lexists(path), 'fresh destination without any parent alias required')
    for root in protected:
        root = Path(root).absolute()
        need(root.resolve() == root and not path.is_relative_to(root), 'destination must be outside every input and producer')
    return path



def write_report(path, value, protected):
    path = fresh_destination(path, protected); path.parent.mkdir(parents=True, exist_ok=True)
    body = (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        with os.fdopen(os.dup(fd), 'wb') as stream:
            stream.write(body); stream.flush(); os.fsync(stream.fileno())
    finally: os.close(fd)


def strict_patch(before, patch, relative=CHANGED_PATH):
    """Apply only exact line-numbered hunks; no fuzz, offsets or extra files."""
    lines = patch.splitlines(keepends=True)
    need(lines[:2] == [('--- a/' + relative + '\n').encode(),
                       ('+++ b/' + relative + '\n').encode()],
         'patch must name only the exact source file')
    original = before.splitlines(keepends=True)
    result = []
    cursor = 0
    index = 2
    hunks = 0
    while index < len(lines):
        match = re.fullmatch(rb'@@ -(\d+),(\d+) \+(\d+),(\d+) @@[^\n]*\n', lines[index])
        need(match is not None, 'exact bounded unified hunk required')
        old_start, old_count, new_start, new_count = map(int, match.groups())
        need(old_start >= cursor + 1 and old_count > 0 and new_count > 0,
             'ordered nonempty exact hunks required')
        result.extend(original[cursor:old_start - 1])
        cursor = old_start - 1
        need(new_start == len(result) + 1, 'patch output line position differs')
        used = added = 0
        index += 1
        while index < len(lines) and not lines[index].startswith(b'@@ '):
            line = lines[index]
            need(line[:1] in (b' ', b'+', b'-') and line.endswith(b'\n'),
                 'ordinary complete patch lines required')
            if line[:1] in (b' ', b'-'):
                need(cursor < len(original) and original[cursor] == line[1:],
                     'patch context or removed line differs')
                cursor += 1
                used += 1
            if line[:1] in (b' ', b'+'):
                result.append(line[1:])
                added += 1
            index += 1
        need((used, added) == (old_count, new_count), 'hunk line counts differ')
        hunks += 1
    need(hunks > 0, 'nonempty exact patch required')
    result.extend(original[cursor:])
    return b''.join(result)


def verify_packet(expected_inventory_sha):
    need(re.fullmatch('[0-9a-f]{64}', expected_inventory_sha), 'external inventory SHA required')
    index = regular(HERE / 'FILES.sha256', 65536)
    need(hashlib.sha256(index).hexdigest() == expected_inventory_sha, 'external packet pin differs')
    inventory = {}
    for line in index.decode('utf-8', 'strict').splitlines():
        match = re.fullmatch(r'([0-9a-f]{64})  ([^\r\n]+)', line)
        need(match is not None, 'exact inventory row required')
        name = match[2]
        safe(name)
        need(name not in inventory and name != 'FILES.sha256', 'unique nonrecursive packet member required')
        inventory[name] = match[1]
    names, _ = member_names(HERE)
    need(names == set(inventory) | {'FILES.sha256'}, 'packet membership differs')
    for name, sha in inventory.items():
        need(hashlib.sha256(regular(HERE / name)).hexdigest() == sha, 'packet member differs: ' + name)
    manifest = decode(regular(HERE / 'MANIFEST.json'))
    need(manifest['schema'] == 'p4-source-materialization-successor-v1'
         and manifest['parent_packet']['inventory_sha256'] == PARENT_INVENTORY
         and manifest['parent_packet']['verify_sha256'] == PARENT_VERIFY_SHA
         and manifest['parent_packet']['source_tree'] == PARENT_TREE
         and manifest['change']['path'] == CHANGED_PATH,
         'fixed complete parent and one source change required')
    before = decode(check(HERE / manifest['parent_rows']['path'], manifest['parent_rows']))
    old = validate_rows(before, 2351)
    need(tree_id(before) == PARENT_TREE and sum(row['bytes'] for row in before) == 44223952,
         'complete original source manifest differs')
    change = manifest['change']
    need(old[CHANGED_PATH] == change['before'] and change['after']['path'] == CHANGED_PATH
         and change['after']['mode'] == change['before']['mode'] == '100644',
         'single source preimage and preserved mode required')
    after = [change['after'] if row['path'] == CHANGED_PATH else row for row in before]
    validate_rows(after, 2351)
    need(tree_id(after) == manifest['successor']['source_tree']
         and len(after) == manifest['successor']['source_files']
         and sum(row['bytes'] for row in after) == manifest['successor']['source_bytes'],
         'complete successor identity differs')
    patch = check(HERE / change['patch']['path'], change['patch'])
    return {'manifest': manifest, 'before': before, 'after': after, 'patch': patch,
            'inventory_sha256': expected_inventory_sha}


def verify_parent_packet(path, packet):
    """Authenticate before importing the unchanged parent capsule verifier."""
    path = Path(path).absolute()
    need(hashlib.sha256(regular(path / 'verify.py')).hexdigest() == PARENT_VERIFY_SHA,
         'fixed parent verifier required')
    need(hashlib.sha256(regular(path / 'FILES.sha256')).hexdigest() == PARENT_INVENTORY,
         'fixed parent inventory required')
    spec = importlib.util.spec_from_file_location('materialization_fixed_parent', path / 'verify.py')
    parent = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(parent)
    need(hashlib.sha256(regular(path / 'verify.py')).hexdigest() == PARENT_VERIFY_SHA,
         'parent verifier changed during import')
    verified = parent.verify_capsule(PARENT_INVENTORY)
    need(verified['rows'] == packet['before'], 'complete parent capsule rows differ')
    return verified


def replay(packet, parent_source, output):
    parent_source = Path(parent_source).absolute()
    before_snapshot = source_snapshot(parent_source, packet['before'], PARENT_TREE)
    output = fresh_destination(output, [HERE, parent_source])
    old = check(parent_source / CHANGED_PATH, packet['manifest']['change']['before'])
    changed = strict_patch(old, packet['patch'])
    after_row = packet['manifest']['change']['after']
    need(digest(changed) == {key: after_row[key] for key in ('bytes', 'sha256')}
         and object_id('blob', changed) == after_row['git_blob'], 'exact patch postimage differs')
    output.mkdir(mode=0o700)
    for row in packet['before']:
        name = row['path']
        body = check(parent_source / name, row)
        if name == CHANGED_PATH:
            body = changed
        dest = output / safe(name)
        dest.parent.mkdir(parents=True, exist_ok=True)
        need(dest.parent.resolve() == dest.parent, 'new output parent alias rejected')
        fd = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        try:
            with os.fdopen(os.dup(fd), 'wb') as stream:
                stream.write(body)
                stream.flush()
                os.fsync(stream.fileno())
            os.fchmod(fd, int(row['mode'], 8) & 0o777)
        finally:
            os.close(fd)
    need(source_snapshot(parent_source, packet['before'], PARENT_TREE) == before_snapshot,
         'parent source changed during complete replay')
    snapshot = source_snapshot(output, packet['after'], packet['manifest']['successor']['source_tree'])
    return {'parent_snapshot': before_snapshot, 'source_snapshot': snapshot}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--inventory-sha256', required=True)
    parser.add_argument('--parent-packet', type=Path)
    parser.add_argument('--parent-source', type=Path)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--output', type=Path)
    group.add_argument('--producer', type=Path)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    packet = verify_packet(args.inventory_sha256)
    if args.parent_packet:
        verify_parent_packet(args.parent_packet, packet)
        if args.output:
            fresh_destination(args.output, [args.parent_packet])
    result = {'schema': 'p4-materialization-source-replay-v1', 'state': 'COMPLETE',
              'packet_inventory_sha256': args.inventory_sha256,
              'parent_packet_verified': args.parent_packet is not None,
              'parent_tree': PARENT_TREE, **packet['manifest']['successor'],
              'changed_paths': [CHANGED_PATH], **packet['manifest']['scope']}
    protected = [HERE] + ([args.parent_packet] if args.parent_packet else [])
    if args.output:
        need(args.parent_source is not None, 'complete original source required for replay')
        result.update(replay(packet, args.parent_source, args.output))
        protected += [args.parent_source, args.output]
    else:
        need(args.parent_source is None, 'no parent source with verify-only mode')
        result['source_snapshot'] = source_snapshot(
            args.producer, packet['after'], packet['manifest']['successor']['source_tree'])
        protected.append(args.producer)
    verify_packet(args.inventory_sha256)
    if args.parent_packet:
        verify_parent_packet(args.parent_packet, packet)
    write_report(args.report, result, protected)
    print(json.dumps({key: value for key, value in result.items()
                      if key not in ('parent_snapshot', 'source_snapshot')}, sort_keys=True))


if __name__ == '__main__':
    main()

