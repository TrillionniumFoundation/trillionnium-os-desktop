#!/usr/bin/env python3
"""Diagnose the observed permission projection error; no Android operations."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import types
sys.dont_write_bytecode = True

source = Path(__file__).with_name('collect_readonly.py')
raw = source.read_bytes()
if hashlib.sha256(raw).hexdigest() != 'f00d7c06e849c62f1375fe9ea0dc8de6df292a72c7a9bb4663edfd9dd9acf5d7':
    raise RuntimeError('READER_SOURCE_MISMATCH')
c = types.ModuleType('p4_ro_reader')
c.__file__ = str(source)
exec(compile(raw, str(source), 'exec'), c.__dict__)
fds, budget = c.Descriptors(), c.Budget(60)
out = {'purpose': 'diagnose observed unsupported permission-name projection',
       'Android_commands': 0, 'writes': 0, 'errors': []}
guard = None
try:
    root = fds.own(os.open('/', os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC))
    host = c.Reader(root, fds, budget)
    raw, _ = host.read(c.GUARD_PATH, 65536, pin=c.GUARD_SHA)
    guard = types.ModuleType('p4_guard')
    guard.__file__ = c.GUARD_PATH
    exec(compile(raw, c.GUARD_PATH, 'exec'), guard.__dict__)
    out['before'] = c.validate_guard_result(guard.current_guard())
    held = c.HeldAndroidRoot(guard.current_baseline(), fds, budget)
    reader = c.Reader(held.root_fd, fds, budget)
    raw, meta = reader.read('/data/misc_de/0/apexdata/com.android.permission/access.abx', c.MAX_METADATA)
    doc = c.parse_xml(raw, budget.check)
    out['source'] = meta
    out['unusual_permission_names'] = []
    for section in doc.children:
        if section.tag != 'app-id-permissions':
            continue
        for node in section.children:
            if node.tag != 'app-id' or node.attrs.get('id') != 10143:
                continue
            seen, count = set(), 0
            for child in node.children:
                if child.tag != 'permission':
                    continue
                name = child.attrs.get('name')
                count += 1
                if not isinstance(name, str) or not c.NAME.fullmatch(name) or name in seen or len(seen) >= 256:
                    out['unusual_permission_names'].append({
                        'name': name, 'duplicate': name in seen, 'index': count,
                        'length': len(name) if isinstance(name, str) else None})
                seen.add(name)
            out['permission_count'] = count
    held.verify()
    reader.recheck()
    host.recheck()
    held.verify()
except BaseException as error:
    out['errors'].append(c.error_record(error))
finally:
    if guard is not None:
        try:
            out['after'] = c.validate_guard_result(guard.current_guard())
        except BaseException as error:
            out['errors'].append(c.error_record(error))
    fds.close_remaining()
    out['fds'] = fds.report()
print(json.dumps(out, ensure_ascii=True))
