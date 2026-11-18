"""Pure checks for one observed R36 owner window; never an acquisition or renewal.

The observed CURRENT projection establishes the owner/record bytes. A separate
original no-follow whole-file read establishes its complete acquisition F9.
The three original root-owned CAS event bodies independently establish a
publication chain. They do not establish original-lock custody, source review,
retirement proof contents, storage admission, or a fresh Full-B admission. Callers must still
use the original live-CURRENT, source, lock, image, lifetime and reserve checks.
"""
import datetime
import hashlib
import json
import pathlib
import stat

GENERATION = 'e6ac-storage-r8-r36-v2-r2'
OWNER_GENERATION = '20261118-e6ac-r36'
OWNER_ID = 'p4-current-r36-independent-owner-e6ac-r6'
OWNER_NAME = 'foreground-root-e6ac9e05361c'
WINDOW_START = '2026-11-18T01:53:12.988458+00:00'
WINDOW_END = '2026-11-20T01:53:12.988458+00:00'
OBSERVED_OWNER_RECORD_SHA256 = '5b04ba83f8415da9e0c5e0b3b1310a6deea3369ec0d90113e0641584fca7736d'
ARCHIVED_V1_RECORD_SHA256 = '9e745c0c2142304e22c930d23290f7cd59cc73b725671b54a0fb8742a5007d20'
SUPERSEDED_R35_OWNER_SHA256 = '6b9cdfca278d005e4143ca82a0fd5cb0753ba8339cb79a240682d63bf589e883'
CURRENT_PATH = '/home/alex/work/pocket4-android-final/CONTINUATION_CURRENT.json'
CURRENT_BYTES = 1569610
CURRENT_SHA256 = 'a5d9fe0a6c3d9209be1e0953fdd9c28ed86365ac677298f1c470cd704b41fa27'
CURRENT_OBSERVED_IDENTITY = (66306, 40394025, 33152, 1000, 1000, 1, 1569610,
                             1794970664573351721, 1794970664608353432)
CURRENT_OBSERVED_VERSION = tuple(CURRENT_OBSERVED_IDENTITY[i] for i in (0, 1, 6, 7, 8))
FROZEN_R8_NONCE = '6cf6434eda1e2e196fcb5fc2dde3d777276573d609e9038615994f7480f11326'
FROZEN_R34_ROOT = '/home/alex/work/p4-current-r34-ROOT-actual-acceptance-e6ac-r2.json'
FROZEN_R34_ROOT_SHA256 = 'a98fc9acf15c897b6d99f31b0d641f4a4e262de713ab81c21c37489ca24ab1b9'

FROZEN_R36_R1_NONCE = 'ec2b1c090aab0ac11cb992a95ae5ea241e0925e354e7a394e161786c59ee91f6'
CAS_SOURCE_SHA256 = 'd79c56592efd2f70ce7d553bfce80be0e28ea1f6c1bcec7d5c834b38ccc85c2f'
CAS_PLAN_SHA256 = '06980190d1296ecfe89503ad153e1dcf98d753a8d78b29c88283eb0b47b8240e'
CAS_DIRECTORY = {'identity': [66306, 40394022, 16832, 0, 0, 2, 4096, 1794970664611353579, 1794970664611353579],
 'path': '/home/alex/work/p4-current-r36-owner-commit-e6ac-r6'}
CAS_EVENT_REFS = {'INTENT.json': {'bytes': 1585,
                 'identity': [66306,
                              40394024,
                              33024,
                              0,
                              0,
                              1,
                              1585,
                              1794970664571351623,
                              1794970664571351623],
                 'path': '/home/alex/work/p4-current-r36-owner-commit-e6ac-r6/INTENT.json',
                 'sha256': '1adffc8dcd6e97fe70c68e7bcef427a91a9e0ecda0baa4b7dd60a7cc0c53773c'},
 'REPLACE-BOUNDARY.json': {'bytes': 925,
                           'identity': [66306,
                                        40394026,
                                        33024,
                                        0,
                                        0,
                                        1,
                                        925,
                                        1794970664603353188,
                                        1794970664603353188],
                           'path': '/home/alex/work/p4-current-r36-owner-commit-e6ac-r6/REPLACE-BOUNDARY.json',
                           'sha256': '016fc43be5b2fc6c1e1e72a8601151877d2beae523b816c01ecfecdb3beae7c1'},
 'RESULT.json': {'bytes': 464,
                 'identity': [66306, 40394027, 33024, 0, 0, 1, 464, 1794970664611353579, 1794970664611353579],
                 'path': '/home/alex/work/p4-current-r36-owner-commit-e6ac-r6/RESULT.json',
                 'sha256': '442c93097e69c4510a2788f5958bcee80330ee17be9ed61e9d50bae20dfa6090'}}
CAS_NAMES = ('INTENT.json', 'REPLACE-BOUNDARY.json', 'RESULT.json')
MISSING_ACCEPTANCE = 'R36 original-lock custody and source review remain unverified; publication cannot seal or admit'


def require(ok, detail):
    if not ok:
        raise RuntimeError(detail)


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'),
                       ensure_ascii=True, allow_nan=False) + '\n').encode()


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def full_reference(value, label, owner=(1000, 1000), mode=0o100600):
    require(type(value) is dict and set(value) == {'path', 'bytes', 'sha256', 'identity'},
            label + ': actual complete reference required')
    path = value['path']
    require(type(path) is str and path.startswith('/') and '\0' not in path and
            pathlib.PurePosixPath(path).as_posix() == path and
            all(part not in ('', '.', '..') for part in path.split('/')[1:]),
            label + ': canonical absolute original path')
    identity = value['identity']
    require(type(identity) is list and len(identity) == 9 and
            all(type(n) is int for n in identity), label + ': nine native integers')
    require(identity[0] > 0 and identity[1] > 0 and identity[2] == mode and
            stat.S_ISREG(identity[2]) and identity[3:6] == [*owner, 1] and
            type(value['bytes']) is int and 0 < value['bytes'] == identity[6] <= 2 * 1024**2,
            label + ': exact source owner, mode, link count and bounded length')
    sha = value['sha256']
    require(type(sha) is str and len(sha) == 64 and
            all(c in '0123456789abcdef' for c in sha), label + ': complete SHA256')
    return value


def validate_owner_record_v2(owner, record):
    """Validate the observed declaration only; deliberately return no permission."""
    require(type(owner) is dict and type(record) is dict and
            record.get('schema') == 'p4-independent-foreground-owner-acquisition-v2',
            'only the separately observed R36 v2 record, never a v1 reinterpretation')
    require(digest({'owner': owner, 'record': record}) == OBSERVED_OWNER_RECORD_SHA256,
            'exact observed R36 owner and complete record, including all archived history')
    require(record['generation'] == owner['generation'] == OWNER_GENERATION and
            record['acquisition_id'] == owner['acquisition_id'] == OWNER_ID and
            record['owner_name'] == owner['name'] == OWNER_NAME and
            record['active_until_utc'] == owner['active_until_utc'] == WINDOW_END and
            record['window_started_at_utc'] == WINDOW_START,
            'one exact acquired owner and fixed endpoint; never now plus a fresh window')
    start = datetime.datetime.fromisoformat(record['window_started_at_utc'])
    end = datetime.datetime.fromisoformat(record['active_until_utc'])
    require(start.utcoffset() == end.utcoffset() == datetime.timedelta(0) and
            type(record['window_seconds']) is int and record['window_seconds'] == 172800 and
            end - start == datetime.timedelta(seconds=172800), 'the original bounded UTC window')
    budgets = {
        'maximum_native_budget_seconds': 145200,
        'native_stop_timeout_seconds': 1200,
        'maximum_native_hard_envelope_seconds': 146400,
        'preparation_reserve_seconds': 600,
        'required_remaining_at_commit_seconds': 147000,
        'whole_planned_schedule_seconds': 140700,
    }
    require(all(type(record[key]) is int and record[key] == wanted for key, wanted in budgets.items()) and
            record['maximum_native_budget_seconds'] + record['native_stop_timeout_seconds'] ==
            record['maximum_native_hard_envelope_seconds'] and
            record['maximum_native_hard_envelope_seconds'] + record['preparation_reserve_seconds'] ==
            record['required_remaining_at_commit_seconds'], 'original v2 budget relationships')
    require(digest(record['superseded_acquisition_record']) == ARCHIVED_V1_RECORD_SHA256 and
            digest(record['superseded_owner']) == SUPERSEDED_R35_OWNER_SHA256,
            'complete unchanged R34 acquisition history and its R35 owner observation')
    require(all(record[key] is True for key in ('effective_only_after_reviewed_CAS',
            'old_owner_history_preserved_in_full', 'inherited_bindings_are_not_new_window_runtime_admissions')) and
            all(record[key] is False for key in ('existing_actor_deadlines_extended',
            'existing_storage_deadlines_extended', 'new_storage_admission_issued',
            'fresh_full_B_admitted', 'C_D_admitted', 'production_ready')) and
            all(type(record[key]) is int and record[key] == 0 for key in ('new_storage_START', 'Android_starts')) and
            all(record[key] is None for key in ('future_storage_source_manifest_sha256',
            'future_full_B_source_manifest_sha256', 'future_storage_binding', 'future_full_B_binding')),
            'owner acquisition alone authorizes no storage, Full-B or Android start')
    full_reference(record['accepted_r8_retirement_ROOT'], 'declared R8 retirement metadata',
                   owner=(0, 0), mode=0o100444)
    return {'owner_record_consistent': True, 'owner_cas_root_contents_verified': False,
            'retirement_reference_contents_verified': False, 'new_storage_admitted': False,
            'fresh_full_B_admitted': False, 'production_ready': False}


def validate_acquisition_current_reference(value, canonical_path=CURRENT_PATH):
    """Require the complete actually read F9; a version-derived guess is not an input."""
    current = full_reference(value, 'R36 acquisition CURRENT')
    require(current['path'] == canonical_path == CURRENT_PATH and
            current['bytes'] == CURRENT_BYTES and current['sha256'] == CURRENT_SHA256 and
            tuple(current['identity']) == CURRENT_OBSERVED_IDENTITY,
            'the actually read complete acquisition CURRENT, not the later live binding CURRENT')
    return current


def validate_owner_declaration_v2(contract):
    """Check frozen declaration and publication references; grant no acceptance."""
    acquisition = contract.get('owner_acquisition')
    require(type(acquisition) is dict and
            set(acquisition) == {'owner', 'record', 'current', 'root_acceptance'},
            'four explicit acquisition slots; unresolved references are not executable')
    owner, record = acquisition['owner'], acquisition['record']
    validate_owner_record_v2(owner, record)
    require(contract['generation'] == GENERATION and contract['owner_acquisition_id'] == OWNER_ID and
            encoded(contract['superseded_foreground_owner']) == encoded(record['superseded_owner']),
            'new candidate generation bound to the exact R36 acquisition')
    require(sum(contract['rotation_schedule'].values()) == record['whole_planned_schedule_seconds'] and
            contract['storage_runtime_max_seconds'] == record['maximum_native_budget_seconds'] and
            contract['storage_stop_seconds'] == record['native_stop_timeout_seconds'],
            'new contract retains the observed whole schedule and native envelope')
    require(contract['nonce'] not in (FROZEN_R8_NONCE, FROZEN_R36_R1_NONCE),
            'neither frozen R8 nor the earlier R36 candidate nonce authorizes this generation')
    current = validate_acquisition_current_reference(acquisition['current'], contract['canonical']['path'])
    validate_owner_cas_publication_reference(contract.get('owner_cas_publication'))
    return {'owner_declaration_consistent': True, 'source_check_only': True,
            'owner_cas_publication_verified': False, 'original_lock_verified': False,
            'source_review_verified': False, 'owner_acquisition_acceptance_verified': False,
            'new_storage_admitted': False, 'fresh_full_B_admitted': False,
            'production_ready': False}


def validate_storage_owner_v2(contract):
    """Fail closed until actual original-lock and source-review evidence exists.

    No accepted schema or actual proof for those missing facts has been supplied.
    Neither a single shape-valid file nor a publication bundle can fill the slot.
    This unconditional boundary intentionally has no JSON boolean override.
    """
    validate_owner_declaration_v2(contract)
    require(contract['owner_acquisition']['root_acceptance'] is None,
            'unreviewed root_acceptance object cannot replace missing source/lock proof')
    raise RuntimeError(MISSING_ACCEPTANCE)


def publication_reference():
    """Public metadata pins only; no original operation body is embedded here."""
    return json.loads(encoded({'schema': 'p4-current-r36-owner-CAS-publication-v1',
        'directory': CAS_DIRECTORY, 'records': CAS_EVENT_REFS}))


def directory_identity(identity, mode, label):
    require(type(identity) is list and len(identity) == 9 and
            all(type(value) is int for value in identity) and
            identity[0] > 0 and identity[1] > 0 and identity[2] == mode and
            stat.S_ISDIR(identity[2]) and identity[3:5] == [0, 0] and
            identity[5] >= 2 and identity[6] > 0 and
            0 < identity[7] <= identity[8], label + ': exact root directory F9')
    return identity


def publication_reference_shape(reference):
    require(type(reference) is dict and set(reference) == {'schema', 'directory', 'records'} and
            reference['schema'] == 'p4-current-r36-owner-CAS-publication-v1',
            'one explicit three-event publication reference')
    directory = reference['directory']
    require(type(directory) is dict and set(directory) == {'path', 'identity'},
            'publication directory metadata only')
    root = directory['path']
    require(type(root) is str and root.startswith('/') and '\0' not in root and
            pathlib.PurePosixPath(root).as_posix() == root and
            all(part not in ('', '.', '..') for part in root.split('/')[1:]),
            'canonical absolute publication directory')
    identity = directory_identity(directory['identity'], 0o40700, 'publication directory')
    records = reference['records']
    require(type(records) is dict and set(records) == set(CAS_NAMES),
            'all and only original INTENT, REPLACE-BOUNDARY and RESULT references')
    inodes = set()
    for name in CAS_NAMES:
        ref = full_reference(records[name], name, owner=(0, 0), mode=0o100400)
        require(ref['path'] == root + '/' + name and ref['bytes'] <= 4096 and
                ref['identity'][0] == identity[0] and
                0 < ref['identity'][7] <= ref['identity'][8],
                'fixed original event name, filesystem and bounded raw body')
        inodes.add(tuple(ref['identity'][:2]))
    require(len(inodes) == 3, 'three distinct original event inodes')
    return reference


def validate_owner_cas_publication_reference(reference):
    publication_reference_shape(reference)
    require(encoded(reference) == encoded(publication_reference()),
            'exact observed R36 event pins; no old ROOT, retirement reference or alternate copy')
    return reference


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        require(key not in value, 'duplicate event JSON key')
        value[key] = item
    return value


def _invalid_number(value):
    raise RuntimeError('non-finite event JSON number: ' + value)


def publication_payloads(reference, raw_records):
    """Authenticate supplied bytes against caller-pinned references, without I/O.

    The production entry point below first requires the exact observed pins.
    This separate byte/shape layer also permits plainly synthetic unit fixtures.
    """
    publication_reference_shape(reference)
    require(type(raw_records) is dict and set(raw_records) == set(CAS_NAMES),
            'three complete raw event bodies required')
    bodies = {}
    for name in CAS_NAMES:
        raw, ref = raw_records[name], reference['records'][name]
        require(type(raw) is bytes and len(raw) == ref['bytes'] and
                hashlib.sha256(raw).hexdigest() == ref['sha256'],
                'exact original raw event bytes: ' + name)
        bodies[name] = json.loads(raw.decode('utf-8', 'strict'),
                                 object_pairs_hook=_unique_object, parse_constant=_invalid_number)
        require(type(bodies[name]) is dict, 'event object: ' + name)
    return bodies


def publication_chain(reference, bodies, acquisition_id, previous_current, current,
                      source_sha256, plan_sha256):
    """Check publication links only; this is not original-lock or source review."""
    publication_reference_shape(reference)
    require(type(bodies) is dict and set(bodies) == set(CAS_NAMES), 'complete publication event set')
    previous_current = full_reference(previous_current, 'superseded CURRENT')
    current = full_reference(current, 'published CURRENT')
    root = reference['directory']['path']
    directory = reference['directory']['identity']
    refs = reference['records']
    intent, boundary, result = (bodies[name] for name in CAS_NAMES)
    require(set(intent) == {'schema', 'acquisition_id', 'automatic_rollback', 'before', 'draft',
            'minimal_diff', 'plan_sha256', 'source_sha256', 'temporary_basename',
            'unknown_effect_requires_reconciliation'} and
            intent['schema'] == 'p4-current-r36-owner-CAS-intent-v1' and
            type(acquisition_id) is str and intent['acquisition_id'] == acquisition_id and
            intent['automatic_rollback'] is False and
            intent['unknown_effect_requires_reconciliation'] is True and
            intent['source_sha256'] == source_sha256 and intent['plan_sha256'] == plan_sha256,
            'exact acquisition intent and declared source/plan; no rollback or retry credit')
    require(all(type(value) is str and len(value) == 64 and
                all(c in '0123456789abcdef' for c in value)
                for value in (source_sha256, plan_sha256)), 'complete declared source and plan hashes')
    full_reference(intent['before'], 'intent original CURRENT')
    require(encoded(intent['before']) == encoded(previous_current) and
            previous_current['path'] == current['path'] and
            previous_current['sha256'] != current['sha256'] and
            previous_current['identity'][:2] != current['identity'][:2],
            'the declared superseded whole CURRENT is the actual intent predecessor')
    draft = full_reference(intent['draft'], 'intent prepared draft')
    diff = full_reference(intent['minimal_diff'], 'declared minimal diff', owner=(0, 0), mode=0o100400)
    require((draft['bytes'], draft['sha256']) == (current['bytes'], current['sha256']) and
            len({draft['path'], diff['path'], current['path']}) == 3 and
            draft['identity'][:2] != current['identity'][:2],
            'separate prepared draft equals the published bytes; diff contents remain unread')
    basename = intent['temporary_basename']
    import re
    require(type(basename) is str and
            re.fullmatch(r'\.CURRENT\.r36-owner-[0-9a-f]{64}\.tmp', basename) is not None,
            'one bounded temporary basename, never an alternate path')
    require(set(boundary) == {'attempted', 'canonical_directory_identity', 'draft_sha256',
            'protected_temporary', 'rename_uses_held_directory_FDs', 'temporary_directory_identity'} and
            boundary['attempted'] is True and boundary['rename_uses_held_directory_FDs'] is True and
            boundary['draft_sha256'] == draft['sha256'], 'actual held-directory rename boundary')
    canonical_directory = directory_identity(boundary['canonical_directory_identity'],
                                             0o40750, 'original canonical directory')
    temporary_directory = directory_identity(boundary['temporary_directory_identity'],
                                             0o40700, 'protected temporary directory')
    require(temporary_directory[:7] == directory[:7] and
            canonical_directory[:2] != temporary_directory[:2] and
            canonical_directory[0] == directory[0],
            'same protected original directory and distinct canonical directory on one filesystem')
    temporary = full_reference(boundary['protected_temporary'], 'protected publication inode')
    require(temporary['path'] == root + '/' + basename and
            (temporary['bytes'], temporary['sha256']) == (current['bytes'], current['sha256']) and
            temporary['identity'][:8] == current['identity'][:8] and
            temporary['identity'][0] == directory[0] and
            temporary['identity'][8] <= current['identity'][8],
            'the original protected inode, unchanged bytes and mtime, is the published CURRENT')
    require(set(result) == {'automatic_rollback', 'current', 'passed', 'protected_held_inode_published'} and
            result['automatic_rollback'] is False and result['passed'] is True and
            result['protected_held_inode_published'] is True,
            'original successful publication result, never a request or an assumed result')
    full_reference(result['current'], 'result canonical CURRENT')
    require(encoded(result['current']) == encoded(current), 'result matches the independently read CURRENT F9 and SHA')
    event_inodes = {tuple(refs[name]['identity'][:2]) for name in CAS_NAMES}
    require(tuple(current['identity'][:2]) not in event_inodes and
            tuple(previous_current['identity'][:2]) not in event_inodes,
            'publication event inodes cannot be current or predecessor aliases')
    for index in (7, 8):
        ordered = [temporary_directory[index], refs['INTENT.json']['identity'][index],
                   temporary['identity'][index], refs['REPLACE-BOUNDARY.json']['identity'][index],
                   current['identity'][8], refs['RESULT.json']['identity'][index], directory[index]]
        require(ordered == sorted(ordered), 'original event/inode metadata chronology')
    return {'owner_cas_publication_verified': True, 'source_check_only': True,
            'original_lock_verified': False, 'source_review_verified': False,
            'source_plan_contents_verified': False, 'minimal_diff_contents_verified': False,
            'owner_acquisition_acceptance_verified': False,
            'retirement_reference_contents_verified': False, 'owner_handoff_issued': False,
            'existing_deadlines_extended': False, 'new_storage_admitted': False,
            'fresh_full_B_admitted': False, 'C_D_admitted': False, 'production_ready': False}


def validate_owner_cas_publication(contract, raw_records, original_directory_identity):
    """Verify the supplied original bytes, preserving fixed R36 identity and window."""
    validate_owner_declaration_v2(contract)
    reference = validate_owner_cas_publication_reference(contract['owner_cas_publication'])
    directory_identity(original_directory_identity, 0o40700, 'observed original CAS directory')
    require(original_directory_identity == reference['directory']['identity'],
            'same actually observed original root directory; never a copy directory identity')
    bodies = publication_payloads(reference, raw_records)
    acquisition = contract['owner_acquisition']
    result = publication_chain(reference, bodies, acquisition['owner']['acquisition_id'],
        acquisition['record']['superseded_current'], acquisition['current'],
        CAS_SOURCE_SHA256, CAS_PLAN_SHA256)
    # These are filesystem event metadata, not a newly sampled commit or lease clock.
    result['observed_event_interval_ns'] = [reference['records']['INTENT.json']['identity'][7],
                                           reference['records']['RESULT.json']['identity'][8]]
    result['window_started_at_utc'] = WINDOW_START
    result['lease_until_utc'] = WINDOW_END
    return result


def read_publication_records(reference, pin, directory_f9):
    """Bounded three-record reader with raw-byte and full-reference bookends."""
    publication_reference_shape(reference)
    before = directory_f9(reference['directory']['path'])
    require(before == reference['directory']['identity'], 'original CAS directory before read')
    raw_records = {}
    for pass_number in range(2):
        for name in CAS_NAMES:
            expected = reference['records'][name]
            actual, raw = pin(expected['path'], expected, limit=4096)
            full_reference(actual, name, owner=(0, 0), mode=0o100400)
            require(encoded(actual) == encoded(expected), 'complete original event identity: ' + name)
            require(type(raw) is bytes and len(raw) == expected['bytes'] and
                    hashlib.sha256(raw).hexdigest() == expected['sha256'],
                    'complete original event bytes: ' + name)
            if pass_number:
                require(raw == raw_records[name], 'same original event raw-byte bookend: ' + name)
            else:
                raw_records[name] = raw
    after = directory_f9(reference['directory']['path'])
    require(before == after == reference['directory']['identity'], 'original CAS directory after read')
    return raw_records, after


def read_owner_cas_publication(contract, pin, directory_f9):
    """Read-only consumer adapter; pin all three originals and directory bookends.

    Callers supply the existing no-follow whole-file pin implementation. This
    never resolves paths in the intent body, such as the draft or minimal diff.
    A successful diagnostic still cannot satisfy validate_storage_owner_v2.
    """
    validate_owner_declaration_v2(contract)
    reference = validate_owner_cas_publication_reference(contract['owner_cas_publication'])
    raw_records, after = read_publication_records(reference, pin, directory_f9)
    result = validate_owner_cas_publication(contract, raw_records, after)
    return {'reference': reference, 'verification': result}
