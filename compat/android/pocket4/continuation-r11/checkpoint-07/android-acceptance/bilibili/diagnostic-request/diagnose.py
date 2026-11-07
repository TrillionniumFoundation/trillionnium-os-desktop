#!/usr/bin/env python3
"""Metadata-only diagnosis of three exact shared-helper admission inputs.

No original flow replay. No namespace/Android entry. Only the already pinned
qualification JSON may be read as content; paths named inside it are reported,
not opened. The original limit and source are not changed by this probe.
"""
import argparse
import hashlib
import json
import os
import stat

INPUTS = (
    ('helper_source', '/home/alex/work/pocket4-owned-held-ns-runner-r4-01/held_namespace_entry.rs', 131072),
    ('helper_binary', '/home/alex/work/pocket4-owned-held-ns-runner-r4-01/held-namespace-entry', 4194304),
    ('helper_qualification', '/home/alex/work/pocket4-owned-held-ns-runner-r4-export-01/qualification.json', 131072),
)
QUALIFICATION_SHA = '3e3dd5c9ae1b4e913d7a688bb338507162cbc211bb897658a539948ffb6f93e3'


def inspect():
    assert os.geteuid() == 0
    rows, evidence_paths = [], []
    for name, path, limit in INPUTS:
        row = {'name': name, 'path': path, 'original_bound_bytes': limit}
        fd = None
        try:
            fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
            value = os.fstat(fd)
            row.update(device=value.st_dev, inode=value.st_ino, mode=value.st_mode,
                       uid=value.st_uid, gid=value.st_gid, nlink=value.st_nlink, bytes=value.st_size,
                       mtime_ns=value.st_mtime_ns, ctime_ns=value.st_ctime_ns,
                       is_regular=stat.S_ISREG(value.st_mode), single_link=value.st_nlink == 1,
                       within_original_bound=value.st_size <= limit)
            row['original_shape_condition'] = row['is_regular'] and row['single_link'] and row['within_original_bound']
            if name == 'helper_qualification' and row['original_shape_condition']:
                raw = bytearray()
                while len(raw) <= limit:
                    part = os.read(fd, min(65536, limit + 1 - len(raw)))
                    if not part:
                        break
                    raw.extend(part)
                after = os.fstat(fd)
                assert len(raw) == value.st_size and all(getattr(value, field) == getattr(after, field)
                    for field in ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns'))
                row['sha256'] = hashlib.sha256(raw).hexdigest()
                assert row['sha256'] == QUALIFICATION_SHA
                qualification = json.loads(raw)
                assert set(qualification['evidence']) == {'host14', 'sixns', 'main_readonly'}
                evidence_paths = [{'name': kind, 'path': item['path'], 'expected_sha256': item['sha256'],
                                   'original_bound_bytes': 4194304, 'opened_by_this_probe': False}
                                  for kind, item in sorted(qualification['evidence'].items())]
        except BaseException as error:
            row['diagnostic_error'] = {'type': type(error).__name__, 'errno': getattr(error, 'errno', None),
                                       'message': str(error)}
        finally:
            if fd is not None:
                os.close(fd)
        rows.append(row)
    print(json.dumps({'schema': 1, 'scope': 'three fixed shared-helper input metadata records and one hash-pinned qualification JSON',
        'rows': rows, 'qualification_evidence_paths_not_read': evidence_paths,
        'original_flow_replayed': False, 'original_limits_changed': False,
        'UI_audio_Android_entry': False, 'whole_app_production_ready': False}, sort_keys=True))


parser = argparse.ArgumentParser()
parser.add_argument('--inspect', action='store_true')
args = parser.parse_args()
if args.inspect:
    inspect()
else:
    print(json.dumps({'state': 'PLAN_ONLY', 'fixed_inputs': INPUTS, 'other_paths_opened': False}))
