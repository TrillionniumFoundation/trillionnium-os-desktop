# Exact observed function from the active helper; demonstration fixture only.
# Parent file SHA256: 22e7e85962c52a5cf44759dd99610d16293a0f8573ee68b8b9da4c89b1c7911a
import os
from pathlib import Path

def now():
    return "fixture"

def live_references(roots):
    root_bytes = [(r, r.encode()) for r in roots]
    def owner(target):
        target = target.removesuffix(' (deleted)')
        return next((r for r in roots if target == r or target.startswith(r + '/')), None)
    hits, mounts, errors, namespaces = [], [], [], set()
    count = 0
    for p in Path('/proc').iterdir():
        if not p.name.isdigit() or int(p.name) == os.getpid():
            continue
        count += 1
        try:
            for name in ('cwd', 'exe', 'root'):
                try:
                    target = os.readlink(p / name)
                    old = owner(target)
                    if old:
                        hits.append({'pid': int(p.name), 'kind': name, 'root': old})
                except (FileNotFoundError, ProcessLookupError):
                    pass
            for fd in (p / 'fd').iterdir():
                try:
                    old = owner(os.readlink(fd))
                    if old:
                        hits.append({'pid': int(p.name), 'kind': 'fd', 'fd': fd.name, 'root': old})
                except (FileNotFoundError, ProcessLookupError):
                    pass
            with (p / 'maps').open() as f:
                for line in f:
                    fields = line.rstrip().split(None, 5)
                    old = owner(fields[5]) if len(fields) == 6 else None
                    if old:
                        hits.append({'pid': int(p.name), 'kind': 'maps', 'root': old})
            # Only matching old-root names are retained; no argument content is emitted.
            args = (p / 'cmdline').read_bytes()
            for root, token in root_bytes:
                if token in args:
                    hits.append({'pid': int(p.name), 'kind': 'owner_argument_reference', 'root': root})
            ns = os.readlink(p / 'ns/mnt')
            if ns not in namespaces:
                namespaces.add(ns)
                with (p / 'mountinfo').open() as f:
                    for line in f:
                        for root in roots:
                            if root in line:
                                mounts.append({'pid': int(p.name), 'namespace': ns, 'root': root})
        except (FileNotFoundError, ProcessLookupError):
            pass
        except PermissionError:
            errors.append({'pid': int(p.name), 'error': 'permission'})
    return {'observed_utc': now(), 'processes': count, 'mount_namespaces': len(namespaces),
            'process_or_owner_hits': hits, 'mount_hits': mounts, 'coverage_errors': errors,
            'command_line_contents_retained': False, 'open_file_contents_read': False}

