#!/usr/bin/env python3
"""Independent readback of the single-field required-39 metadata correction."""
import copy
import datetime
import hashlib
import json
import os
from pathlib import Path
import stat

ROOT = Path('/home/alex/work/p4-cp3a-bootstrap-20261120-runtimeaudit-r1/scope-correction')
CURRENT = Path('/home/alex/work/pocket4-android-final/CONTINUATION_CURRENT.json')
LOCKS = [
    ('/home/alex/work/pocket4-android-final/.CONTINUATION_CURRENT.lock', [66306,41719172,33152,0,0,1,0,1794130437217307659,1794130437217307659]),
    ('/home/alex/work/pocket4-android-final/.qpr1-kernel-control-8b88.lock', [66306,41719533,33152,0,0,1,0,1794178693266232511,1794178693266232511]),
]


def f9(value):
    return [value.st_dev,value.st_ino,value.st_mode,value.st_uid,value.st_gid,value.st_nlink,
            value.st_size,value.st_mtime_ns,value.st_ctime_ns]


def read(path, expected):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = f9(os.fstat(fd))
        assert stat.S_ISREG(before[2]) and before[5] == 1 and before[6] < 2 * 1024 * 1024
        raw = b''
        while len(raw) <= before[6]:
            part = os.read(fd, min(65536, before[6] + 1 - len(raw)))
            if not part:
                break
            raw += part
        assert before == f9(os.fstat(fd)) == f9(os.stat(path, follow_symlinks=False))
        assert len(raw) == before[6] and hashlib.sha256(raw).hexdigest() == expected
        return raw, before
    finally:
        os.close(fd)


def main():
    assert os.getuid() == os.geteuid() == 0
    os.umask(0o077)
    for path, expected in LOCKS:
        assert f9(os.stat(path, follow_symlinks=False)) == expected
    before_raw, _ = read(ROOT / 'BEFORE-CURRENT.json', '69e836deed4aeebd1377a67b3e24413aaa281e076f02ad89448fab40af5f6c3a')
    after_raw, after_f9 = read(CURRENT, '091f53bb8ad9623c9825c5e94a91e7226157ba90205fa1bddf06eb362aa0875b')
    before, after = json.loads(before_raw), json.loads(after_raw)
    assert after['resume_order'][3] == ('Integrate ProductionMain owned AppBridge and current app producers, then execute the 39 required current-version contracts; TextNow, TextFree, and Uber Rider are the three explicitly exempt unavailable-APK apps. Source tests and historical runs confer no Android business acceptance.')
    restored = copy.deepcopy(after); restored['resume_order'][3] = before['resume_order'][3]
    assert restored == before and after != before
    assert after_raw == (json.dumps(after, sort_keys=True, separators=(',', ':')) + '\n').encode()
    assert after['foreground_owner'] == before['foreground_owner']
    for key in ('all_blockers_closed', 'production_ready', 'runtime_qualified', 'final_candidate_deployed'):
        assert after[key] is before[key] is False
    for key in ('application_qualification_preparations', 'application_qualification_preparation_selection_scope',
                'application_current_route_audit', 'application_current_IHG_identity', 'final_selected_application_acceptance'):
        assert after[key] == before[key]
    assert after['production_qualification_limits']['final_selected_apps_total'] == 42
    assert after_raw == read(CURRENT, hashlib.sha256(after_raw).hexdigest())[0]
    for path, expected in LOCKS:
        assert f9(os.stat(path, follow_symlinks=False)) == expected
    report = {'schema': 'pocket4-required39-independent-readback-v1',
        'checked_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'current': {'path': str(CURRENT), 'sha256': hashlib.sha256(after_raw).hexdigest(),
                    'bytes': len(after_raw), 'f9': after_f9},
        'single_changed_JSON_pointer': '/resume_order/3', 'all_other_JSON_values_unchanged': True,
        'source_pointers_and_current_IHG_unchanged': True, 'owner_generation_expiry_unchanged': True,
        'original_lock_inodes_unchanged': True, 'compact_JSON_within_original_2MiB_bound': True,
        'scope': {'required': 39, 'exempt': ['TextNow', 'TextFree', 'Uber Rider'], 'selected_inventory': 42},
        'whole_CURRENT_independent_process_readback': True, 'runtime_qualified': False, 'production_ready': False}
    raw = (json.dumps(report, sort_keys=True, indent=2) + '\n').encode()
    path = ROOT / 'INDEPENDENT-READBACK.json'
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        with os.fdopen(fd, 'wb', closefd=False) as out:
            out.write(raw); out.flush(); os.fsync(fd)
    finally:
        os.close(fd)
    assert read(path, hashlib.sha256(raw).hexdigest())[0] == raw
    print(json.dumps({'independent_readback': {'path': str(path), 'bytes': len(raw),
        'sha256': hashlib.sha256(raw).hexdigest()}, 'current': report['current']}, sort_keys=True))


if __name__ == '__main__':
    main()
