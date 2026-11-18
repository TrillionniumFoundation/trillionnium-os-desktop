"""Pure checks for one observed R36 owner window; never an acquisition or renewal.

The observed CURRENT projection establishes the owner/record bytes. A separate
original no-follow whole-file read establishes its complete acquisition F9.
Neither establishes the missing owner/CAS ROOT acceptance, retirement proof
contents, new storage admission, or a fresh Full-B admission. Callers must still
use the original live-CURRENT, source, lock, image, lifetime and reserve checks.
"""
import datetime
import hashlib
import json
import pathlib
import stat

GENERATION = 'e6ac-storage-r8-r36-v2-r1'
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


def validate_storage_owner_v2(contract):
    """Require both real acquisition references before any new source binding.

    This is still a pure source check. The existing admission path subsequently
    pins the separately adopted live CURRENT and ROOT body and rechecks the
    exact owner, source binding, original allocation lock, image and resources.
    """
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
    require(contract['nonce'] != FROZEN_R8_NONCE, 'the frozen R8 nonce cannot authorize a new generation')
    current = validate_acquisition_current_reference(acquisition['current'], contract['canonical']['path'])
    root = full_reference(acquisition['root_acceptance'], 'R36 owner/CAS ROOT acceptance')
    require(root['path'] not in (CURRENT_PATH, FROZEN_R34_ROOT,
            record['accepted_r8_retirement_ROOT']['path']) and
            root['sha256'] not in (current['sha256'], FROZEN_R34_ROOT_SHA256,
            record['accepted_r8_retirement_ROOT']['sha256']) and
            root['identity'][:2] != current['identity'][:2],
            'a distinct actual R36 owner/CAS acceptance, never old owner or retirement metadata')
    return {'owner_acquisition_references_required': True,
            'source_check_only': True, 'new_storage_admitted': False,
            'fresh_full_B_admitted': False, 'production_ready': False}
