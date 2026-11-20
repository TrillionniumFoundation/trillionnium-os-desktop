#!/usr/bin/env python3
"""Finalize and commit the exact reviewed Pocket4 source-pointer transition.

No owner, deadline, runtime authorization, APK install, or deployment is changed.
The two original lock inodes and whole-CURRENT byte/F9 CAS are mandatory.
"""
import argparse
import copy
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import types

ROOT = Path('/home/alex/work/p4-cp3a-bootstrap-20261120-runtimeaudit-r1')
OUT = ROOT / 'selection-integration'
CANON = Path('/home/alex/work/pocket4-android-final')
CURRENT = CANON / 'CONTINUATION_CURRENT.json'
HELPER_SHA = '5981eda642b2cc35a18979fddb2fd98e7a7ae0ba038a92f5f37370e2a808b401'
HANDOFF_SHA = 'cd65abd448cb936bff6aecd5f17311882537add6356ba62542fb5b5ec39d2a07'
FILES = {
    'AFTER-CURRENT.reviewed.json': (1582648, '69e836deed4aeebd1377a67b3e24413aaa281e076f02ad89448fab40af5f6c3a'),
    'APP-ROUTE-MAP.json': (99043, '880ffd517f97a141944b363394debea843514dd7d6d3ae0b15e717d37aed0eb6'),
    'BEFORE-CURRENT.json': (1579957, 'b29be8cb340b4744c73df67046be421faf33ad00ea04bff84c4516e6def1d3bc'),
    'README.md': (869, 'e7b3104454dec67ef8d154a7889589502cd13530eca3b4ba008d72c44e6758b4'),
    'SOURCE-SELECTION-VALIDATION.json': (18191, '3830f997545859090c5a152590657ef8e2d1e679c8fe71fcbb4c0de801580c68'),
    'selection-13.json': (14276, '24629e7533bf3d63c3f08ee6aa09aaffd76f4ef6673783c36c4c5290b2e294d0'),
}
KEYS = {'application_qualification_preparations', 'application_qualification_preparations_previous',
        'application_qualification_preparation_selection_scope', 'application_current_route_audit',
        'application_current_IHG_identity'}
LOCKS = (
    ('.CONTINUATION_CURRENT.lock', [66306, 41719172, 33152, 0, 0, 1, 0, 1794130437217307659, 1794130437217307659]),
    ('.qpr1-kernel-control-8b88.lock', [66306, 41719533, 33152, 0, 0, 1, 0, 1794178693266232511, 1794178693266232511]),
)
DIRS = {}


def pin(value):
    return {k: value[k] for k in ('path', 'bytes', 'sha256')}


def read_ref(value, maximum=16 * 1024 * 1024):
    return h.read(value['path'], pin(value), maximum=maximum)


def fixed(name):
    size, sha = FILES[name]
    return h.read(OUT / name, {'path': str(OUT / name), 'bytes': size, 'sha256': sha})


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def transition(before, after):
    changed = {k for k in set(before) | set(after) if before.get(k) != after.get(k)}
    h.need(changed == KEYS, 'EXACT_FIVE_SOURCE_POINTER_KEYS_ONLY')
    h.need(before['foreground_owner'] == after['foreground_owner'], 'OWNER_OR_EXPIRY_CHANGED')
    for flag in ('all_blockers_closed', 'production_ready', 'runtime_qualified', 'final_candidate_deployed'):
        h.need(before[flag] is after[flag] is False, 'RUNTIME_FLAG_CANNOT_BE_ENABLED')
    h.need(after['application_current_IHG_identity']['runtime_qualified'] is False
           and after['application_current_route_audit']['runtime_qualified'] is False,
           'SOURCE_METADATA_CANNOT_GRANT_RUNTIME')


def verify_sources():
    observed = {name: fixed(name) for name in FILES}
    before = json.loads(observed['BEFORE-CURRENT.json'][0])
    after = json.loads(observed['AFTER-CURRENT.reviewed.json'][0])
    transition(before, after)
    validation = json.loads(observed['SOURCE-SELECTION-VALIDATION.json'][0])
    handoff_raw, handoff_ref, _ = h.read(ROOT / 'HANDOFF.json')
    h.need(handoff_ref['sha256'] == HANDOFF_SHA, 'EXACT_SOURCE_HANDOFF')
    handoff = json.loads(handoff_raw)
    candidate = json.loads(read_ref(handoff['candidate_manifest'])[0])
    h.bookend(candidate['original_input_bookends'])
    for value in validation['entries']:
        read_ref(value['preparation']); read_ref(value['entry'])
    for value in validation['current_payload_bookends']:
        _, _, f9 = read_ref(value['ref'], maximum=128 * 1024 * 1024)
        h.need(f9 == value['f9'], 'CURRENT_PAYLOAD_FULL9_CHANGED')
    read_ref(validation['current_inventory'])
    for value in validation['profile_checks']:
        read_ref(value['source_custody_receipt'])
    for value in (handoff['bootstrap_verification'], handoff['camera_display']['verification']):
        read_ref(value)
    selection = json.loads(observed['selection-13.json'][0])
    routes = json.loads(observed['APP-ROUTE-MAP.json'][0])
    h.need(after['application_qualification_preparations'] == observed['selection-13.json'][1]
           and after['application_current_route_audit']['map'] == observed['APP-ROUTE-MAP.json'][1]
           and routes['inputs']['selected_preparations'] == observed['selection-13.json'][1],
           'FORMAL_SELECTION_ROUTE_POINTERS_MUST_AGREE')
    h.need(selection['selected_preparations'] == [r['preparation'] for r in validation['entries']]
           and len(selection['selected_preparations']) == 13
           and len(validation['profile_checks']) == 9
           and len(validation['current_payload_bookends']) == 6, 'COMPLETE_SELECTED_SOURCE_VALIDATION')
    for row in routes['rows']:
        h.need(row['runtime_qualified'] is False and row['production_ready'] is False
               and row['accepted_gates'] == 0, 'NO_BUSINESS_ACCEPTANCE_CREDIT')
        for leaf in row['existing_leaf_entries']:
            v = validation['entries'][leaf['selection_index']]
            h.need(leaf['entry_source'] == v['entry'] and leaf['preparation'] == v['preparation'],
                   'ROUTE_LEAF_EXACT_SELECTED_SOURCE')
    return observed, before, after, validation, handoff_ref, handoff


def current_matches(expected, owner):
    raw, actual, f9 = h.read(CURRENT, pin(expected), maximum=2 * 1024 * 1024)
    h.need(f9 == expected['f9'], 'CURRENT_FULL9_CAS_PREIMAGE_CHANGED')
    obj = json.loads(raw)
    h.need(obj['foreground_owner'] == owner, 'ORIGINAL_OWNER_CHANGED')
    h.need(owner['name'] == 'foreground-root-e6ac9e05361c'
           and owner['generation'] == '20261120-2331-r37'
           and owner['acquisition_id'] == 'p4-current-r37-independent-continuation-2331-r1',
           'EXACT_EXISTING_FOREGROUND_OWNER')
    expiry = datetime.datetime.fromisoformat(owner['active_until_utc'].replace('Z', '+00:00'))
    h.need((expiry - datetime.datetime.now(datetime.timezone.utc)).total_seconds() > 600,
           'ORIGINAL_OWNER_WINDOW_EXPIRED_OR_TOO_SHORT')
    return raw, actual, f9


def finalize():
    h.need(not (OUT / 'CAS-PLAN.json').exists(), 'CREATE_ONLY_PLAN')
    observed, before, after, validation, handoff_ref, handoff = verify_sources()
    expected = validation['current_preimage']
    raw, _, _ = current_matches(expected, before['foreground_owner'])
    h.need(raw == observed['BEFORE-CURRENT.json'][0], 'WHOLE_CURRENT_PREFLIGHT_BYTES_CHANGED')
    plan = {'schema': 'pocket4-exact-source-selection-cas-plan-v1', 'created_utc': utc(),
        'current_preimage': expected, 'before_copy': observed['BEFORE-CURRENT.json'][1],
        'reviewed_draft': observed['AFTER-CURRENT.reviewed.json'][1], 'changed_keys': sorted(KEYS),
        'expected_before_values': {k: before[k] for k in sorted(KEYS)},
        'replacement_values': {k: after[k] for k in sorted(KEYS)},
        'source_selection': observed['selection-13.json'][1], 'route_map': observed['APP-ROUTE-MAP.json'][1],
        'validation': observed['SOURCE-SELECTION-VALIDATION.json'][1],
        'evidence': [handoff_ref, handoff['candidate_manifest'], handoff['bootstrap_verification'],
            handoff['camera_display']['verification'], *[observed[n][1] for n in ('selection-13.json',
            'APP-ROUTE-MAP.json', 'README.md', 'SOURCE-SELECTION-VALIDATION.json')], validation['current_inventory']],
        'original_owner': before['foreground_owner'], 'source_only': True, 'Android_actions': 0,
        'runtime_qualified': False, 'production_ready': False,
        'finalization_note': 'The original source verifier completed its draft then refused its default 16 MiB bookend bound for the exact 47,680,737-byte IHG APK. This finalizer uses the same original 128 MiB bounded APK reader as initial hashing and rechecks the complete exact F9/SHA; no existing verifier or runtime bound changed.'}
    result = h.write(OUT / 'CAS-PLAN.json', h.encoded(plan))
    print(json.dumps({'plan': result, 'reviewed_draft': plan['reviewed_draft'],
        'source_selection': plan['source_selection'], 'route_map': plan['route_map'],
        'current_unchanged': True, 'source_only': True}, sort_keys=True))


def di(s):
    return [s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_gid]


def directory(path):
    path = Path(path)
    if str(path) in DIRS:
        return DIRS[str(path)][0]
    if path == Path('/'):
        parent, name = None, None
        fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    else:
        parent, name = directory(path.parent), path.name
        fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
    identity = di(os.fstat(fd))
    h.need(stat.S_ISDIR(identity[2]) and identity == di(path.lstat()), 'HELD_DIRECTORY_BINDING')
    DIRS[str(path)] = (fd, identity, parent, name)
    return fd


def check_directories():
    for path, (fd, identity, parent, name) in DIRS.items():
        h.need(di(os.fstat(fd)) == identity == di(os.lstat(path)), 'DIRECTORY_CHANGED')
        if parent is not None:
            h.need(di(os.stat(name, dir_fd=parent, follow_symlinks=False)) == identity, 'DIRECTORY_PARENT_CHANGED')


def check_locks(fds):
    for (name, expected), fd in zip(LOCKS, fds):
        h.need(h.metadata(os.fstat(fd)) == expected
               == h.metadata(os.stat(name, dir_fd=directory(CANON), follow_symlinks=False)), 'ORIGINAL_LOCK_INODE_CHANGED')


def writers(identity):
    found = []
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit() or int(proc.name) == os.getpid():
            continue
        try:
            for fd in (proc / 'fd').iterdir():
                try:
                    s = fd.stat()
                    if [s.st_dev, s.st_ino] != identity:
                        continue
                    flags = next(line.split(':', 1)[1].strip() for line in
                                 (proc / 'fdinfo' / fd.name).read_text().splitlines() if line.startswith('flags:'))
                    if int(flags, 8) & os.O_ACCMODE:
                        found.append({'pid': int(proc.name), 'fd': int(fd.name)})
                except (FileNotFoundError, ProcessLookupError):
                    pass
        except (FileNotFoundError, ProcessLookupError):
            pass
    h.need(not found, 'OTHER_LIVE_CURRENT_WRITER')
    return found


def commit(plan_sha):
    h.need(isinstance(plan_sha, str) and len(plan_sha) == 64, 'EXTERNAL_PLAN_PIN_REQUIRED')
    h.need(not (OUT / 'COMMIT-INTENT.json').exists(), 'SINGLE_UNREPLAYED_SOURCE_POINTER_COMMIT')
    raw, plan_ref, _ = h.read(OUT / 'CAS-PLAN.json')
    h.need(plan_ref['sha256'] == plan_sha, 'EXTERNAL_PLAN_PIN_CHANGED')
    plan = json.loads(raw)
    observed, before, after, validation, _, _ = verify_sources()
    h.need(set(plan['changed_keys']) == KEYS
           and plan['replacement_values'] == {k: after[k] for k in KEYS}
           and plan['expected_before_values'] == {k: before[k] for k in KEYS}, 'EXACT_REVIEWED_POINTER_TRANSITION')
    expected = plan['current_preimage']; current_matches(expected, plan['original_owner'])
    # Exercise exact refusal checks on memory-only negative inputs before any canonical mutation.
    rejected = []
    for label, bad in (('runtime-enable-rejected', {**after, 'runtime_qualified': True}),
                       ('unrelated-current-change-rejected', {**after, 'state': 'UNREVIEWED'})):
        try:
            transition(before, bad)
        except RuntimeError as error:
            rejected.append({'name': label, 'refused': True, 'error': str(error)})
        else:
            raise RuntimeError('NEGATIVE_TRANSITION_ACCEPTED')
    try:
        current_matches({**expected, 'sha256': '0' * 64}, plan['original_owner'])
    except RuntimeError as error:
        rejected.append({'name': 'stale-current-sha-rejected', 'refused': True, 'error': str(error)})
    else:
        raise RuntimeError('STALE_CURRENT_PIN_ACCEPTED')
    canonical = directory(CANON)
    lock_fds = []
    held_draft = None
    try:
        for name, f9 in LOCKS:
            fd = os.open(name, os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=canonical)
            h.need(h.metadata(os.fstat(fd)) == f9
                   == h.metadata(os.stat(name, dir_fd=canonical, follow_symlinks=False)), 'EXACT_EXISTING_LOCK_ONLY')
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            lock_fds.append(fd)
        check_locks(lock_fds); check_directories()
        current_matches(expected, plan['original_owner'])
        writers(expected['f9'][:2])
        draft_raw = observed['AFTER-CURRENT.reviewed.json'][0]
        h.need(len(draft_raw) < 2 * 1024 * 1024
               and draft_raw == (json.dumps(after, sort_keys=True, separators=(',', ':')) + '\n').encode(),
               'ORIGINAL_CURRENT_ENCODING_AND_BOUND')
        h.write(OUT / 'COMMIT-INTENT.json', h.encoded({'schema': 'pocket4-source-pointer-cas-intent-v1',
            'created_utc': utc(), 'plan': plan_ref, 'before': expected, 'draft': plan['reviewed_draft'],
            'locks': [{'path': str(CANON / name), 'f9': f9} for name, f9 in LOCKS],
            'changed_keys': sorted(KEYS), 'negative_controls': rejected, 'source_only': True}))
        name = '.CONTINUATION_CURRENT.cp3a-source-20261120-runtimeaudit-r1.tmp'
        held_draft = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                             0o600, dir_fd=canonical)
        os.fchown(held_draft, 1000, 1000)
        offset = 0
        while offset < len(draft_raw):
            written = os.write(held_draft, draft_raw[offset:]); h.need(written > 0, 'WRITE_PROGRESS'); offset += written
        os.fsync(held_draft); os.fsync(canonical)
        temp_f9 = h.metadata(os.fstat(held_draft))
        h.need(os.pread(held_draft, len(draft_raw) + 1, 0) == draft_raw, 'HELD_DRAFT_COMPLETE_READBACK')
        current_matches(expected, plan['original_owner'])
        for value in plan['evidence']:
            read_ref(value)
        writers(expected['f9'][:2]); check_locks(lock_fds); check_directories()
        h.need(h.metadata(os.stat('CONTINUATION_CURRENT.json', dir_fd=canonical, follow_symlinks=False)) == expected['f9'],
               'IMMEDIATE_EXACT_CURRENT_CAS_PREIMAGE')
        h.need(temp_f9 == h.metadata(os.fstat(held_draft))
               == h.metadata(os.stat(name, dir_fd=canonical, follow_symlinks=False)), 'EXACT_HELD_DRAFT_INODE')
        os.replace(name, 'CONTINUATION_CURRENT.json', src_dir_fd=canonical, dst_dir_fd=canonical)
        os.fsync(canonical)
        h.need(h.metadata(os.fstat(held_draft))
               == h.metadata(os.stat('CONTINUATION_CURRENT.json', dir_fd=canonical, follow_symlinks=False)),
               'PUBLISHED_CURRENT_IS_HELD_DRAFT')
        result_raw, result_ref, result_f9 = h.read(CURRENT, h.ref(CURRENT, draft_raw), maximum=2 * 1024 * 1024)
        h.need(result_raw == draft_raw and json.loads(result_raw) == after, 'COMPLETE_COMMITTED_CURRENT_READBACK')
        h.need(result_f9[2:6] == expected['f9'][2:6], 'CURRENT_MODE_OWNER_LINK_COUNT_PRESERVED')
        transition(before, json.loads(result_raw)); check_locks(lock_fds); check_directories()
        result = {'schema': 'pocket4-source-pointer-cas-result-v1', 'completed_utc': utc(),
            'before': expected, 'after': {**result_ref, 'f9': result_f9}, 'plan': plan_ref,
            'changed_keys': sorted(KEYS), 'only_five_source_metadata_keys_changed': True,
            'all_other_CURRENT_JSON_values_unchanged': True, 'owner_generation_expiry_unchanged': True,
            'original_lock_inodes_unchanged': True, 'other_live_CURRENT_writers_observed': 0,
            'source_selection': plan['source_selection'], 'route_map': plan['route_map'],
            'changed_selection_indices': list(range(8)), 'unchanged_selection_indices': list(range(8, 13)),
            'negative_controls': rejected, 'complete_readback_matches_reviewed_draft': True,
            'source_only': True, 'Android_actions': 0, 'APK_installs': 0,
            'runtime_qualified': False, 'production_ready': False, 'runtime_accepted_count': 0}
        result_pin = h.write(OUT / 'COMMIT-RESULT.json', h.encoded(result))
        print(json.dumps({'result': result_pin, 'current': result['after'],
            'source_selection': plan['source_selection'], 'route_map': plan['route_map'],
            'source_only': True, 'runtime_qualified': False}, sort_keys=True))
    finally:
        if held_draft is not None:
            os.close(held_draft)
        for fd in reversed(lock_fds):
            fcntl.flock(fd, fcntl.LOCK_UN); os.close(fd)
        for fd, _, _, _ in reversed(list(DIRS.values())):
            os.close(fd)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('finalize', 'commit'))
    parser.add_argument('--expect-plan-sha256')
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise RuntimeError('ROOT_EXACT_METADATA_OPERATOR_REQUIRED')
    code = (ROOT / 'prepare_bootstrap.py').read_bytes()
    if hashlib.sha256(code).hexdigest() != HELPER_SHA:
        raise RuntimeError('EXACT_SOURCE_HELPER_PIN_REQUIRED')
    h = types.ModuleType('source_helper'); h.__file__ = str(ROOT / 'prepare_bootstrap.py')
    exec(compile(code, h.__file__, 'exec'), h.__dict__)
    os.umask(0o077)
    if args.mode == 'finalize':
        h.need(args.expect_plan_sha256 is None, 'NO_EXISTING_PLAN_PIN_ON_FINALIZATION')
        finalize()
    else:
        commit(args.expect_plan_sha256)
