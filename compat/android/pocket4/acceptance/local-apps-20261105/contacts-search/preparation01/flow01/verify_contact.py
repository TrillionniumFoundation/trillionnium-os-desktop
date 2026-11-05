#!/usr/bin/python3 -I
"""Read-only proof for one UI-owned, local-only Contacts create/edit/delete loop.

This verifier has no UI dispatch, contact write, account change or sync command.
Run each phase once, in order, around separately observed UI actions. A repeated
phase cannot overwrite its receipt. An uncertain UI action is read back before
any further decision; it is never retried by this program.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import types

SESSION = Path('/home/alex/work/pocket4-camera-release08-20261105-r12/transaction-tools-01/camera_transaction.py')
SESSION_SHA = 'b2274355ea9acc9d3f82f4e245dceef01aae86e689221744f0fb2afaff679470'
ROOT = Path('/home/alex/work/pocket4-contacts-search-model-20261105-r12-01')
NAME = 'Pocket4 Search QA r12 c83f16a2'
EDITED = NAME + ' Edited'
NAME_MIME = 'vnd.android.cursor.item/name'
PINS = {
    'com.android.contacts': {'uid': 10055, 'version': 10734,
        'path': '/product/priv-app/Contacts/Contacts.apk', 'bytes': 11839391,
        'sha256': '11f8be5fd46dd79ee4f7524d5d1334e21ce0f9e23892b2940a5b6091e2f349d0'},
    'com.android.providers.contacts': {'uid': 10015, 'version': 37,
        'path': '/system/priv-app/ContactsProvider/ContactsProvider.apk', 'bytes': 872865,
        'sha256': '9a8d8238565ff977a025ad6eb3f1496b5bd2ea9c819b3229278d62e29da0c313'},
}
PHASES = ('before', 'created', 'edited', 'persisted', 'deleted')


def require(condition, code):
    if not condition:
        raise RuntimeError(code)


def session_module():
    raw = SESSION.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == SESSION_SHA, 'FROZEN_SESSION_CHANGED')
    tx = types.ModuleType('contacts_verifier_frozen_session')
    tx.__file__ = str(SESSION)
    exec(compile(raw, str(SESSION), 'exec'), tx.__dict__)
    return tx


def parse_rows(raw, columns):
    """Exact content CLI projection; owned test values contain no commas."""
    if raw.strip() == 'No result found.':
        return []
    require(bool(raw.strip()), 'CONTENT_RESPONSE_EMPTY_UNKNOWN')
    rows = []
    for number, line in enumerate(raw.splitlines()):
        match = re.fullmatch(r'Row: (\d+) (.*)', line)
        require(match is not None and int(match[1]) == number, 'CONTENT_ROW_FORMAT_UNKNOWN')
        fields = match[2].split(', ')
        require(len(fields) == len(columns), 'CONTENT_PROJECTION_ARITY_CHANGED')
        row = {}
        for column, field in zip(columns, fields):
            require(field.startswith(column + '='), 'CONTENT_PROJECTION_ORDER_CHANGED')
            value = field[len(column) + 1:]
            row[column] = None if value in ('NULL', 'null') else value
        rows.append(row)
    return rows


def query(session, table, columns, where=None):
    require(table in ('raw_contacts', 'data'), 'TABLE_OUTSIDE_CONTACTS_SCOPE')
    command = ['/system/bin/content', 'query', '--user', '0', '--uri', 'content://com.android.contacts/' + table,
               '--projection', ':'.join(columns)]
    if where is not None:
        command += ['--where', where]
    return parse_rows(session.android(command).decode('utf-8', 'strict'), columns)


def identity(session):
    for package, pin in PINS.items():
        path = session.android(['/system/bin/pm', 'path', package]).decode('utf-8', 'strict').splitlines()
        require(path == ['package:' + pin['path']], 'CONTACTS_APK_PATH_CHANGED')
        data, _ = session.target.read_file(pin['path'], 48 * 1024 * 1024)
        require(len(data) == pin['bytes'] and hashlib.sha256(data).hexdigest() == pin['sha256'],
                'CONTACTS_APK_BYTES_CHANGED')
        dump = session.android(['/system/bin/dumpsys', 'package', package]).decode('utf-8', 'strict')
        active = re.findall(r'^Packages:\n(.*?)(?=^\S|\Z)', dump, re.M | re.S)
        require(len(active) == 1 and re.findall(r'^  Package \[([^]]+)\]', active[0], re.M) == [package],
                'CONTACTS_ACTIVE_PACKAGE_AMBIGUOUS')
        require(re.findall(r'^    appId=(\d+)$', active[0], re.M) == [str(pin['uid'])] and
                re.findall(r'^    versionCode=(\d+)\b', active[0], re.M) == [str(pin['version'])],
                'CONTACTS_UID_OR_VERSION_CHANGED')
    session.guard()


def unchanged_account_topology(session):
    command = ("set -o pipefail; /system/bin/dumpsys account | /system/bin/sed -n "
        "-e 's/^[[:space:]]*Accounts: \\([0-9][0-9]*\\)[[:space:]]*$/Accounts: \\1/p' "
        "-e 's/^[[:space:]]*Account {.*type=\\([^}]*\\)}[[:space:]]*$/AccountType: \\1/p'")
    raw = session.android(['/system/bin/sh', '-c', command]).decode('utf-8', 'strict')
    counts = [int(value) for value in re.findall(r'^Accounts: (\d+)$', raw, re.M)]
    types_found = re.findall(r'^AccountType: (.*)$', raw, re.M)
    require(counts == [1] and types_found == ['com.ss.android.ugc.aweme'],
            'OBSERVED_ACCOUNT_TOPOLOGY_CHANGED')
    return {'counts': counts, 'types': types_found, 'existing_account_unchanged': True}


def current_state(session):
    raw_rows = query(session, 'raw_contacts', ('_id', 'contact_id', 'deleted'))
    names = query(session, 'data', ('_id', 'raw_contact_id', 'contact_id', 'mimetype', 'data1'),
        "mimetype='" + NAME_MIME + "' AND (data1='" + NAME + "' OR data1='" + EDITED + "')")
    require(len({row['_id'] for row in raw_rows}) == len(raw_rows), 'DUPLICATE_RAW_CONTACT_IDS')
    for row in raw_rows:
        require(re.fullmatch(r'[1-9]\d*', row['_id'] or '') is not None and row['deleted'] in ('0', '1'),
                'RAW_CONTACT_IDENTITY_INVALID')
    own = None
    if names:
        require(len(names) == 1 and names[0]['mimetype'] == NAME_MIME and
                names[0]['data1'] in (NAME, EDITED), 'OWNED_MARKER_NOT_UNIQUE')
        raw_id = names[0]['raw_contact_id']
        require(re.fullmatch(r'[1-9]\d*', raw_id or '') is not None, 'OWNED_RAW_ID_INVALID')
        accounts = query(session, 'raw_contacts',
            ('_id', 'contact_id', 'account_name', 'account_type', 'data_set', 'deleted'), '_id=' + raw_id)
        require(len(accounts) == 1, 'OWNED_RAW_CONTACT_MISSING')
        own = {'name_row': names[0], 'raw_contact': accounts[0]}
    session.guard()
    return {'raw_rows': raw_rows, 'marker_rows': names, 'owned': own}


def validate_before(state):
    require(state['raw_rows'] == [] and state['marker_rows'] == [] and state['owned'] is None,
            'BASELINE_NOT_EMPTY_OR_MARKER_PREEXISTS')


def validate_owned(state, expected_name, original=None):
    own = state['owned']
    require(own is not None and own['name_row']['data1'] == expected_name, 'OWNED_NAME_NOT_OBSERVED')
    raw = own['raw_contact']
    require(raw['account_name'] is None and raw['account_type'] is None and raw['data_set'] is None,
            'OWNED_CONTACT_IS_NOT_DEVICE_LOCAL')
    require(raw['deleted'] == '0' and raw['contact_id'] == own['name_row']['contact_id'],
            'OWNED_CONTACT_IS_DELETED_OR_AGGREGATED_DIFFERENTLY')
    require(len(state['raw_rows']) == 1 and state['raw_rows'][0]['_id'] == raw['_id'] and
            state['raw_rows'][0]['deleted'] == '0', 'CONTACT_SET_CHANGED_OUTSIDE_OWNED_RECORD')
    if original is not None:
        old = original['owned']
        require(old is not None and raw['_id'] == old['raw_contact']['_id'] and
                raw['contact_id'] == old['raw_contact']['contact_id'], 'EDIT_CHANGED_OWNED_RECORD_IDENTITY')
    return {'raw_contact_id': raw['_id'], 'contact_id': raw['contact_id'],
            'name_data_id': own['name_row']['_id'], 'name': expected_name, 'local_null_account': True}


def validate_deleted(state, original):
    owned_id = original['owned']['raw_contact']['_id']
    require(state['marker_rows'] == [] and state['owned'] is None, 'OWNED_CONTACT_STILL_VISIBLE')
    # Local deletion should remove the raw row; an exact owned tombstone is also
    # reported accurately. Never turn a tombstone into a global provider purge.
    require(all(row['_id'] == owned_id and row['deleted'] == '1' for row in state['raw_rows']),
            'LIVE_CONTACT_REMAINS_OR_UNOWNED_RECORD_APPEARED')
    return {'active_owned_contact_absent': True, 'owned_tombstone_count': len(state['raw_rows']),
            'database_returned_to_empty': state['raw_rows'] == []}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', choices=('plan',) + PHASES, default='plan')
    args = parser.parse_args()
    if args.phase == 'plan':
        print(json.dumps({'state': 'PLAN_ONLY', 'marker': NAME, 'edited_marker': EDITED,
            'root': str(ROOT), 'phases': PHASES, 'ui_actions': 0, 'contact_writes': 0,
            'requires_observed_device_editor_before_any_save': True}, indent=2))
        return 0
    tx = session_module()
    if args.phase == 'before':
        ROOT.mkdir(mode=0o700)
    else:
        require(ROOT.is_dir(), 'BASELINE_RECEIPT_REQUIRED')
    folder = ROOT / args.phase
    require(not folder.exists(), 'PHASE_ALREADY_RECORDED_NO_REPLAY')
    result = {'schema': 1, 'phase': args.phase, 'state': 'READBACK_FAILED', 'marker': NAME,
              'edited_marker': EDITED, 'ui_actions': 0, 'contacts_written': 0, 'sync_actions': 0,
              'source_sha256': SESSION_SHA, 'whole_app_production_ready': False}
    try:
        with tx.CameraSession(folder) as session:
            identity(session)
            result['epoch_sha256'] = session.epoch_sha256
            result['account_topology'] = unchanged_account_topology(session)
            observed = current_state(session)
            result['observed'] = observed
            if args.phase == 'before':
                validate_before(observed)
                result['state'] = 'EMPTY_BASELINE_VERIFIED_DEVICE_EDITOR_STILL_REQUIRED'
            else:
                before = json.loads(tx.read_regular(ROOT / 'before/result.json'))
                require(before['state'] == 'EMPTY_BASELINE_VERIFIED_DEVICE_EDITOR_STILL_REQUIRED' and
                        before['epoch_sha256'] == session.epoch_sha256 and before['marker'] == NAME,
                        'ORIGINAL_BASELINE_DIFFERS')
                if args.phase == 'created':
                    result['owned_identity'] = validate_owned(observed, NAME)
                    result['state'] = 'LOCAL_CONTACT_CREATED_VERIFIED'
                else:
                    original = json.loads(tx.read_regular(ROOT / 'created/result.json'))
                    require(original['state'] == 'LOCAL_CONTACT_CREATED_VERIFIED' and
                            original['epoch_sha256'] == session.epoch_sha256, 'OWNED_CREATION_NOT_VERIFIED')
                    if args.phase == 'deleted':
                        result.update(validate_deleted(observed, original['observed']))
                        result['state'] = ('LOCAL_CONTACT_DELETED_BASELINE_RESTORED' if
                            result['database_returned_to_empty'] else 'LOCAL_CONTACT_DELETED_OWNED_TOMBSTONE_RETAINED')
                    else:
                        result['owned_identity'] = validate_owned(observed, EDITED, original['observed'])
                        result['state'] = 'LOCAL_CONTACT_EDIT_READBACK_VERIFIED'
                        if args.phase == 'persisted':
                            result['close_reopen_evidence_required_separately'] = True
            session.guard()
    except BaseException as exc:
        result['error'] = type(exc).__name__ + ': ' + str(exc)
        result['state'] = 'READBACK_FAILED'
    if folder.is_dir():
        tx.write_new(folder / 'result.json', result)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 1 if result['state'] == 'READBACK_FAILED' else 0


if __name__ == '__main__':
    raise SystemExit(main())
