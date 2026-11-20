#!/usr/bin/env python3
"""Correct only the one stale CURRENT resume sentence to the authorized 39+3 scope."""
import copy
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import types

ROOT = Path('/home/alex/work/p4-cp3a-bootstrap-20261120-runtimeaudit-r1')
OUT = ROOT / 'scope-correction'
CURRENT_SHA = '69e836deed4aeebd1377a67b3e24413aaa281e076f02ad89448fab40af5f6c3a'
OLD = 'Integrate ProductionMain owned AppBridge and current app producers, obtain three missing official deliveries, and execute all42 current-version contracts; source tests and historical runs confer no Android business acceptance.'
NEW = 'Integrate ProductionMain owned AppBridge and current app producers, then execute the 39 required current-version contracts; TextNow, TextFree, and Uber Rider are the three explicitly exempt unavailable-APK apps. Source tests and historical runs confer no Android business acceptance.'


def load(path, expected, name):
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise RuntimeError('EXACT_REVIEWED_HELPER_REQUIRED:' + name)
    module = types.ModuleType(name); module.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    return module


def main():
    h.need(os.getuid() == os.geteuid() == 0 and not OUT.exists(), 'ROOT_CREATE_ONLY_SCOPE_CORRECTION')
    os.umask(0o077)
    raw, before_ref, f9 = h.read(c.CURRENT, maximum=2 * 1024 * 1024)
    h.need(before_ref['sha256'] == CURRENT_SHA, 'FRESH_EXPECTED_CURRENT_PREIMAGE')
    before = json.loads(raw)
    h.need(before['resume_order'][3] == OLD, 'EXACT_ONE_STALE_RESUME_SENTENCE')
    owner = before['foreground_owner']; expected = {**before_ref, 'f9': f9}
    c.current_matches(expected, owner)
    inventory = json.loads(c.read_ref(before['final_selected_application_acceptance']['latest_artifact_inventory'])[0])
    h.need(inventory['required_count'] == 39 and inventory['selected_count'] == 42
           and {v['package'] for v in inventory['exemptions']} == {
               'com.enflick.android.TextNow', 'com.pinger.textfree', 'com.ubercab'}, 'EXISTING_AUTHORIZED_REQUIRED_SCOPE')
    after = copy.deepcopy(before); after['resume_order'][3] = NEW
    restored = copy.deepcopy(after); restored['resume_order'][3] = OLD
    h.need(restored == before, 'NO_OTHER_JSON_CHANGE')
    for flag in ('all_blockers_closed', 'production_ready', 'runtime_qualified', 'final_candidate_deployed'):
        h.need(after[flag] is before[flag] is False, 'RUNTIME_FLAGS_UNCHANGED_FALSE')
    draft = (json.dumps(after, sort_keys=True, separators=(',', ':')) + '\n').encode()
    h.need(len(draft) < 2 * 1024 * 1024, 'ORIGINAL_COMPACT_CURRENT_BOUND')
    h.mkdir(OUT)
    original_copy = h.write(OUT / 'BEFORE-CURRENT.json', raw)
    draft_ref = h.write(OUT / 'AFTER-CURRENT.reviewed.json', draft)
    intent = h.write(OUT / 'INTENT.json', h.encoded({'schema': 'pocket4-required39-resume-scope-cas-intent-v1',
        'before': expected, 'before_copy': original_copy, 'draft': draft_ref, 'JSON_pointer': '/resume_order/3',
        'old': OLD, 'new': NEW, 'all_other_JSON_values_unchanged': True, 'owner_unchanged': True,
        'runtime_qualified': False, 'production_ready': False}))
    canonical = c.directory(c.CANON); locks = []; held = None
    try:
        for name, identity in c.LOCKS:
            fd = os.open(name, os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=canonical)
            h.need(h.metadata(os.fstat(fd)) == identity
                   == h.metadata(os.stat(name, dir_fd=canonical, follow_symlinks=False)), 'ORIGINAL_LOCK_ONLY')
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB); locks.append(fd)
        c.check_locks(locks); c.check_directories(); c.current_matches(expected, owner); c.writers(f9[:2])
        name = '.CONTINUATION_CURRENT.required39-20261120-runtimeaudit-r1.tmp'
        held = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                       0o600, dir_fd=canonical)
        os.fchown(held, 1000, 1000)
        offset = 0
        while offset < len(draft):
            n = os.write(held, draft[offset:]); h.need(n > 0, 'WRITE_PROGRESS'); offset += n
        os.fsync(held); os.fsync(canonical)
        temp = h.metadata(os.fstat(held))
        h.need(os.pread(held, len(draft) + 1, 0) == draft, 'EXACT_HELD_DRAFT_BYTES')
        c.current_matches(expected, owner); c.check_locks(locks); c.check_directories(); c.writers(f9[:2])
        h.need(h.metadata(os.stat('CONTINUATION_CURRENT.json', dir_fd=canonical, follow_symlinks=False)) == f9,
               'IMMEDIATE_EXACT_PREIMAGE')
        h.need(temp == h.metadata(os.fstat(held))
               == h.metadata(os.stat(name, dir_fd=canonical, follow_symlinks=False)), 'IMMEDIATE_EXACT_DRAFT')
        os.replace(name, 'CONTINUATION_CURRENT.json', src_dir_fd=canonical, dst_dir_fd=canonical)
        os.fsync(canonical)
        h.need(h.metadata(os.fstat(held))
               == h.metadata(os.stat('CONTINUATION_CURRENT.json', dir_fd=canonical, follow_symlinks=False)),
               'PUBLISHED_HELD_DRAFT')
        rb, reference, final_f9 = h.read(c.CURRENT, h.ref(c.CURRENT, draft), maximum=2 * 1024 * 1024)
        h.need(rb == draft and json.loads(rb) == after and final_f9[2:6] == f9[2:6], 'WHOLE_CURRENT_READBACK')
        c.check_locks(locks); c.check_directories()
        result = {'schema': 'pocket4-required39-resume-scope-cas-result-v1',
            'completed_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'intent': intent,
            'before': expected, 'after': {**reference, 'f9': final_f9}, 'changed_JSON_pointer': '/resume_order/3',
            'old': OLD, 'new': NEW, 'all_other_JSON_values_unchanged': True,
            'owner_generation_expiry_unchanged': True, 'original_lock_inodes_unchanged': True,
            'source_selection_and_route_map_unchanged': True, 'whole_CURRENT_readback': True,
            'selected_inventory_count_unchanged': 42, 'required_count': 39, 'exempt_count': 3,
            'Android_actions': 0, 'APK_installs': 0, 'runtime_qualified': False, 'production_ready': False}
        result_ref = h.write(OUT / 'RESULT.json', h.encoded(result))
        print(json.dumps({'result': result_ref, 'current': result['after'], 'only_changed': '/resume_order/3'}, sort_keys=True))
    finally:
        if held is not None:
            os.close(held)
        for fd in reversed(locks):
            fcntl.flock(fd, fcntl.LOCK_UN); os.close(fd)
        for fd, _, _, _ in reversed(list(c.DIRS.values())):
            os.close(fd)


if __name__ == '__main__':
    h = load(ROOT / 'prepare_bootstrap.py', '5981eda642b2cc35a18979fddb2fd98e7a7ae0ba038a92f5f37370e2a808b401', 'source_helper')
    c = load(ROOT / 'commit_source_selection.py', '59838bd2d1fd65fdf74163cb4ed1c7ea8ad087008f01600aa71b2d4b36cc8678', 'original_cas_helpers')
    c.h = h
    main()
