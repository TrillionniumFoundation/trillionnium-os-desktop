#!/usr/bin/env python3
"""Bounded source-link inventory and fixed local Rust tool identity only."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess

BASE = Path('/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source')
ROOT = Path('/home/alex/work/pocket4-blueprint-source-layout-and-rust-tools-readonly-01-20261105')
SOURCES = ('build/blueprint', 'external/pogreb')
RUSTUP = '/home/alex/.cargo/bin/rustup'
ENV = {'HOME': '/home/alex', 'PATH': '/usr/bin:/bin',
       'CARGO_HOME': '/home/alex/.cargo', 'RUSTUP_HOME': '/home/alex/.rustup',
       'RUSTUP_SKIP_UPDATE_CHECK': '1', 'LC_ALL': 'C'}

def stamp(st):
    return [st.st_dev, st.st_ino, st.st_mode, st.st_size, st.st_mtime_ns, st.st_ctime_ns]

def save(name, value):
    raw = (json.dumps(value, indent=2) + '\n').encode()
    fd = os.open(ROOT / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return {'path': str(ROOT / name), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}

def inventory(relative):
    source = BASE / relative
    row = {'path': str(source), 'symlinks': [], 'directories': 0, 'regular_files': 0,
           'other': [], 'skipped_metadata': [], 'followed_symlinks': 0}
    for component in (source, *source.parents):
        if not stat.S_ISDIR(component.lstat().st_mode):
            raise RuntimeError('source parent is not a real directory: ' + str(component))
    rootfd = os.open(source, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
    before = os.fstat(rootfd)
    row['held_before'] = stamp(before)
    def visit(fd, prefix, depth):
        if depth > 32 or row['directories'] >= 512:
            raise RuntimeError('directory/depth bound exceeded')
        row['directories'] += 1
        names = sorted(os.listdir(fd))
        if len(names) > 4096:
            raise RuntimeError('directory entry bound exceeded')
        for name in names:
            rel = prefix + name
            old = os.stat(name, dir_fd=fd, follow_symlinks=False)
            if stat.S_ISLNK(old.st_mode):
                target = os.readlink(name, dir_fd=fd)
                new = os.stat(name, dir_fd=fd, follow_symlinks=False)
                if stamp(old) != stamp(new):
                    raise RuntimeError('link changed: ' + rel)
                row['symlinks'].append({'relative': rel, 'target': target,
                                        'lstat_before': stamp(old), 'lstat_after': stamp(new)})
                if len(row['symlinks']) > 1024:
                    raise RuntimeError('symlink bound exceeded')
            elif name == '.git':
                row['skipped_metadata'].append({'relative': rel, 'lstat': stamp(old)})
            elif stat.S_ISDIR(old.st_mode):
                child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=fd)
                try:
                    if stamp(old) != stamp(os.fstat(child)):
                        raise RuntimeError('directory changed before held traversal: ' + rel)
                    visit(child, rel + '/', depth + 1)
                    if stamp(old) != stamp(os.fstat(child)) or stamp(old) != stamp(os.stat(name, dir_fd=fd, follow_symlinks=False)):
                        raise RuntimeError('directory changed during traversal: ' + rel)
                finally:
                    os.close(child)
            elif stat.S_ISREG(old.st_mode):
                row['regular_files'] += 1
                if row['regular_files'] > 4096:
                    raise RuntimeError('regular-file bound exceeded')
            else:
                row['other'].append({'relative': rel, 'lstat': stamp(old)})
    try:
        visit(rootfd, '', 0)
        row['held_after'] = stamp(os.fstat(rootfd))
        row['named_after'] = stamp(source.lstat())
        if row['held_before'] != row['held_after'] or row['held_after'] != row['named_after']:
            raise RuntimeError('source root changed during inventory')
        row['complete'] = True
    finally:
        os.close(rootfd)
    return row

def tool_identity(path):
    original = Path(path)
    resolved = original.resolve(strict=True)
    if not (resolved.is_relative_to('/home/alex/.rustup/toolchains') or
            resolved.is_relative_to('/usr/bin') or resolved == Path(RUSTUP)):
        raise RuntimeError('unexpected resolved tool path: ' + str(resolved))
    fd = os.open(resolved, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        old = os.fstat(fd)
        if not stat.S_ISREG(old.st_mode) or not old.st_mode & 0o111 or old.st_size > 256*1024*1024:
            raise RuntimeError('unexpected tool size/type')
        digest = hashlib.sha256()
        total = 0
        while True:
            data = os.read(fd, 65536)
            if not data:
                break
            total += len(data)
            digest.update(data)
        new = os.fstat(fd)
        if total != old.st_size or stamp(old) != stamp(new) or stamp(new) != stamp(resolved.lstat()) or original.resolve(strict=True) != resolved:
            raise RuntimeError('tool identity changed during read')
        return {'requested_path': path, 'resolved_path': str(resolved), 'bytes': total,
                'sha256': digest.hexdigest(), 'held_before': stamp(old), 'held_after': stamp(new)}
    finally:
        os.close(fd)

def query(argv):
    result = subprocess.run(argv, cwd='/', env=ENV, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5, check=False)
    if len(result.stdout) > 32768 or len(result.stderr) > 32768:
        raise RuntimeError('tool metadata output bound exceeded')
    return {'argv': argv, 'returncode': result.returncode,
            'stdout': result.stdout.decode('utf-8', errors='strict'),
            'stderr': result.stderr.decode('utf-8', errors='strict')}

def main():
    if os.getuid() != 1000 or os.geteuid() != 1000:
        raise RuntimeError('ordinary operator UID required')
    os.umask(0o077)
    for parent in (ROOT.parent, *ROOT.parent.parents):
        if not stat.S_ISDIR(parent.lstat().st_mode):
            raise RuntimeError('evidence parent aliases non-directory')
    ROOT.mkdir(mode=0o700)
    result = {'schema': 1, 'scope': 'two fixed source trees, no symlink traversal, Rust/linker metadata only',
              'started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'uid': os.getuid(), 'Main_actions': 0, 'source_changes': 0, 'builds_started': 0,
              'install_update_actions': 0, 'source_inventories': [], 'tool_queries': [], 'tools': [], 'errors': []}
    for relative in SOURCES:
        try:
            result['source_inventories'].append(inventory(relative))
        except Exception as error:
            result['errors'].append({'source': relative, 'error': repr(error)})
    try:
        rustup_before = tool_identity(RUSTUP)
        result['tools'].append(rustup_before)
        for name in ('cargo', 'rustc'):
            answer = query([RUSTUP, 'which', name])
            result['tool_queries'].append(answer)
            if answer['returncode'] != 0:
                raise RuntimeError('rustup which failed: ' + name)
            resolved = answer['stdout'].strip()
            if not Path(resolved).is_absolute() or Path(resolved).name != name or not Path(resolved).is_relative_to('/home/alex/.rustup/toolchains'):
                raise RuntimeError('unexpected rustup tool result')
            item = tool_identity(resolved)
            result['tools'].append(item)
            result['tool_queries'].append(query([resolved, '-vV' if name == 'rustc' else '--version']))
            if tool_identity(resolved) != item:
                raise RuntimeError('tool changed during version query: ' + name)
        for path in ('/usr/bin/cc', '/usr/bin/ld', '/usr/bin/ar', '/usr/bin/as'):
            result['tools'].append(tool_identity(path))
        if tool_identity(RUSTUP) != rustup_before:
            raise RuntimeError('rustup changed during query')
    except Exception as error:
        result['errors'].append({'phase': 'tool identity', 'error': repr(error)})
    result['finished_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    result['complete'] = len(result['source_inventories']) == 2 and not result['errors']
    descriptor = save('result.json', result)
    print(json.dumps({'complete': result['complete'], 'result': descriptor,
                      'source_inventory_count': len(result['source_inventories']),
                      'tool_count': len(result['tools']), 'errors': result['errors']}), flush=True)
    return 0 if result['complete'] else 1

if __name__ == '__main__':
    raise SystemExit(main())
