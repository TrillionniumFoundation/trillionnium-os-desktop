#!/usr/bin/env python3
"""Verify and reconstruct the complete current source capsule for CI."""
import argparse
import io
import tarfile
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess

HERE = Path(__file__).resolve().parent
HEAD_COMMIT = '61a38baa745483fbfb757466a1cf352febc20552'
HEAD_TREE = 'db6249e80209abeda8000eeced6d045a1d57e0a2'


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


def successful_cargo_stream(raw):
    rows=[decode(line) for line in raw.decode().splitlines() if line]
    terminals=[row for row in rows if row.get('reason')=='build-finished']
    need(rows and terminals==[{'reason':'build-finished','success':True}] and rows[-1]==terminals[0],
         'one complete successful Cargo terminal required')
    need(not any(row.get('reason')=='compiler-message' and row.get('message',{}).get('level')=='error' for row in rows),
         'successful Cargo stream contains an error')
    return rows


def test_terminal(text, passed, ignored=(), filtered=None):
    passed,ignored=set(passed),set(ignored)
    need(not passed.intersection(ignored),'passed and ignored identities must be distinct')
    records=[];running=[];summaries=[]
    for line in text.splitlines():
        if line.startswith('test result:'):
            summaries.append(line)
        elif line.startswith('test '):
            match=re.fullmatch(r'test (\S+) \.\.\. (ok|FAILED|ignored)(?:, (.+))?',line)
            need(match is not None,'malformed Rust test record')
            name,status,reason=match.groups()
            need(reason is None or status=='ignored','unexpected test reason')
            records.append((name,status))
        elif line.startswith('running '):
            need(re.fullmatch(r'running \d+ tests?',line),'malformed Rust running count')
            running.append(line)
    total=len(passed)+len(ignored)
    need(len(records)==total and len({name for name,status in records})==total and
         {name for name,status in records if status=='ok'}==passed and
         {name for name,status in records if status=='ignored'}==ignored and
         all(status in ('ok','ignored') for name,status in records),'complete exact Rust identities/statuses required')
    need(running==[f'running {total} '+('test' if total==1 else 'tests')] and len(summaries)==1,
         'exactly one complete Rust harness required')
    match=re.fullmatch(r'test result: ok\. (\d+) passed; 0 failed; (\d+) ignored; 0 measured; (\d+) filtered out; finished in [0-9]+(?:\.[0-9]+)?s',summaries[0])
    need(match is not None and int(match[1])==len(passed) and int(match[2])==len(ignored),
         'successful Rust summary must equal every actual record')
    need(filtered is None or int(match[3])==filtered,'unexpected Rust filter count')
    return {'passed':sorted(passed),'ignored':sorted(ignored),'filtered':int(match[3])}


CAPSULE = {'bytes': 7696708, 'sha256': '7ab244365184ef670c244b6a0ed75857c6f942897f3fc59c00e6375e76f51816'}
MANIFEST = {'bytes': 673996, 'sha256': '62194b76e735e879c596befe4b07dcf0442ae5d6c4612c6fd63cb3bc54fc038a'}
COMMIT = {'bytes': 331, 'sha256': '879f0ac4412540cc03fb3593933aa2ea5cc6519c1d3e6e4fd3251cd393148e2d'}


def archive_entries(raw):
    entries = {}
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:xz') as archive:
        members = archive.getmembers()
        need(len(members) == 2224 and sum(m.size for m in members) == 41226493,
             'complete bounded current source archive required')
        for member in members:
            safe(member.name)
            need(member.isfile() and not member.linkname and member.name not in entries
                 and 0 <= member.size <= 64 * 1024 * 1024, 'unique ordinary source members only')
            body = archive.extractfile(member).read(member.size + 1)
            need(len(body) == member.size, 'whole archive member required')
            entries[member.name] = (member.mode, body)
    return entries


def verify_capsule(expected_inventory_sha):
    need(re.fullmatch('[0-9a-f]{64}', expected_inventory_sha), 'external inventory SHA required')
    index = regular(HERE / 'FILES.sha256', 65536)
    need(hashlib.sha256(index).hexdigest() == expected_inventory_sha, 'external inventory pin differs')
    inventory = {}
    for line in index.decode('utf-8', 'strict').splitlines():
        match = re.fullmatch(r'([0-9a-f]{64})  ([^\r\n]+)', line)
        need(match is not None, 'complete inventory record required')
        name = match[2]; safe(name)
        need(name not in inventory and name != 'FILES.sha256', 'distinct nonrecursive inventory members')
        inventory[name] = match[1]
    names, _ = member_names(HERE)
    need(names == set(inventory) | {'FILES.sha256'}, 'exact current capsule file membership')
    for name, sha in inventory.items():
        need(hashlib.sha256(regular(HERE / name)).hexdigest() == sha, 'capsule input differs: ' + name)
    entries = archive_entries(check(HERE / 'SOURCE-CAPSULE.tar.xz', CAPSULE))
    need('SOURCE-MANIFEST.json' in entries and 'SOURCE-COMMIT.txt' in entries,
         'source manifest and exact commit object required')
    manifest_body = entries['SOURCE-MANIFEST.json'][1]; commit_body = entries['SOURCE-COMMIT.txt'][1]
    need(digest(manifest_body) == MANIFEST and digest(commit_body) == COMMIT
         and object_id('commit', commit_body) == HEAD_COMMIT, 'original manifest and commit object must match')
    manifest = decode(manifest_body)
    need(manifest['schema'] == 'p4-portable-qualified-source-manifest-v2'
         and manifest['head'] == HEAD_COMMIT and manifest['tree'] == HEAD_TREE
         and manifest['file_count'] == 2222 and manifest['file_bytes'] == 40552166
         and manifest['commit'] == COMMIT and len(manifest['files']) == 2222,
         'exact complete current source generation required')
    need(commit_body.startswith(('tree ' + HEAD_TREE + '\n').encode()), 'original commit tree differs')
    rows = [{'path': name, 'bytes': row['bytes'], 'sha256': row['sha256'],
             'git_blob': row['git_blob'], 'mode': row['git_mode']}
            for name, row in sorted(manifest['files'].items())]
    wanted = validate_rows(rows, 2222)
    need(set(entries) == {'source/' + name for name in wanted}
         | {'SOURCE-MANIFEST.json', 'SOURCE-COMMIT.txt'}, 'missing or undeclared source member')
    for name, row in wanted.items():
        mode, body = entries['source/' + name]
        need(mode == (int(row['mode'], 8) & 0o777)
             and digest(body) == {key: row[key] for key in ('bytes', 'sha256')}
             and object_id('blob', body) == row['git_blob'], 'source body, mode or Git blob differs: ' + name)
    need(tree_id(rows) == HEAD_TREE and sum(row['bytes'] for row in rows) == 40552166,
         'every source byte must contribute to the complete Git tree')
    return {'manifest': manifest, 'rows': rows, 'entries': entries, 'inventory_sha256': expected_inventory_sha}


def replay(capsule, destination):
    destination = fresh_destination(destination, [HERE]); destination.mkdir(mode=0o700)
    for row in capsule['rows']:
        name = row['path']; path = destination / safe(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        need(path.parent.resolve() == path.parent, 'new source parent alias rejected')
        body = capsule['entries']['source/' + name][1]
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        try:
            view = memoryview(body)
            while view:
                count = os.write(fd, view); need(count > 0, 'complete source write'); view = view[count:]
            os.fchmod(fd, int(row['mode'], 8) & 0o777); os.fsync(fd)
        finally: os.close(fd)
    return source_snapshot(destination, capsule['rows'], HEAD_TREE)


def write_report(path, value, protected):
    path = fresh_destination(path, protected); path.parent.mkdir(parents=True, exist_ok=True)
    body = (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        with os.fdopen(os.dup(fd), 'wb') as stream:
            stream.write(body); stream.flush(); os.fsync(stream.fileno())
    finally: os.close(fd)


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--inventory-sha256', required=True)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--output', type=Path); group.add_argument('--producer', type=Path)
    parser.add_argument('--report', type=Path); args = parser.parse_args()
    capsule = verify_capsule(args.inventory_sha256)
    result = {'schema': 'p4-current-complete-source-verification-v1', 'source_commit': HEAD_COMMIT,
              'source_tree': HEAD_TREE, 'source_files': 2222, 'source_bytes': 40552166,
              'full_source_archive_verified': True, 'historical_tests_counted_as_fresh': 0,
              'Android_builds': 0, 'Android_starts': 0, 'runtime_qualified': False, 'production_ready': False}
    protected = [HERE]
    if args.output:
        destination = args.output.absolute(); result['source_snapshot'] = replay(capsule, destination)
        result['full_source_verified'] = True; protected.append(destination)
    elif args.producer:
        producer = args.producer.absolute()
        result['source_snapshot'] = source_snapshot(producer, capsule['rows'], HEAD_TREE)
        result['full_source_verified'] = True; protected.append(producer)
    if args.report: write_report(args.report, result, protected)
    print(json.dumps({key: value for key, value in result.items() if key != 'source_snapshot'}, sort_keys=True))


if __name__ == '__main__': main()
