"""Independent new-Main component; no historical Session, Main or execute entry."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import types
NAME = 'Pocket4 Search QA r12 f4a76c9d'
EDITED = NAME + ' Edited'
NAME_MIME = 'vnd.android.cursor.item/name'
PINS = {'com.android.contacts': {'uid': 10055, 'version': 10734, 'path': '/product/priv-app/Contacts/Contacts.apk', 'bytes': 11896473, 'sha256': 'f91e45e89b3a302198c9269a60bb07387150c0f40def95feb873b765520ae028'}, 'com.android.providers.contacts': {'uid': 10015, 'version': 37, 'path': '/system/priv-app/ContactsProvider/ContactsProvider.apk', 'bytes': 872865, 'sha256': '9a8d8238565ff977a025ad6eb3f1496b5bd2ea9c819b3229278d62e29da0c313'}}
PHASES = ('before', 'created', 'edited', 'persisted', 'deleted')

def require(condition, code):
    if not condition:
        raise RuntimeError(code)

def parse_rows(raw, columns):
    """Exact content CLI projection; owned test values contain no commas."""
    if raw.strip() == 'No result found.':
        return []
    require(bool(raw.strip()), 'CONTENT_RESPONSE_EMPTY_UNKNOWN')
    rows = []
    for number, line in enumerate(raw.splitlines()):
        match = re.fullmatch('Row: (\\d+) (.*)', line)
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
    command = ['/system/bin/content', 'query', '--user', '0', '--uri', 'content://com.android.contacts/' + table, '--projection', ':'.join(columns)]
    if where is not None:
        command += ['--where', where]
    return parse_rows(session.android(command).decode('utf-8', 'strict'), columns)

def identity(session):
    for package, pin in PINS.items():
        path = session.android(['/system/bin/pm', 'path', package]).decode('utf-8', 'strict').splitlines()
        require(path == ['package:' + pin['path']], 'CONTACTS_APK_PATH_CHANGED')
        data, _ = session.target.read_file(pin['path'], 48 * 1024 * 1024)
        require(len(data) == pin['bytes'] and hashlib.sha256(data).hexdigest() == pin['sha256'], 'CONTACTS_APK_BYTES_CHANGED')
        dump = session.android(['/system/bin/dumpsys', 'package', package]).decode('utf-8', 'strict')
        active = re.findall('^Packages:\\n(.*?)(?=^\\S|\\Z)', dump, re.M | re.S)
        require(len(active) == 1 and re.findall('^  Package \\[([^]]+)\\]', active[0], re.M) == [package], 'CONTACTS_ACTIVE_PACKAGE_AMBIGUOUS')
        require(re.findall('^    appId=(\\d+)$', active[0], re.M) == [str(pin['uid'])] and re.findall('^    versionCode=(\\d+)\\b', active[0], re.M) == [str(pin['version'])], 'CONTACTS_UID_OR_VERSION_CHANGED')
    session.guard()

def unchanged_account_topology(session):
    command = "set -o pipefail; /system/bin/dumpsys account | /system/bin/sed -n -e 's/^[[:space:]]*Accounts: \\([0-9][0-9]*\\)[[:space:]]*$/Accounts: \\1/p' -e 's/^[[:space:]]*Account {.*type=\\([^}]*\\)}[[:space:]]*$/AccountType: \\1/p'"
    raw = session.android(['/system/bin/sh', '-c', command]).decode('utf-8', 'strict')
    counts = [int(value) for value in re.findall('^Accounts: (\\d+)$', raw, re.M)]
    types_found = re.findall('^AccountType: (.*)$', raw, re.M)
    require(counts == [1] and types_found == ['com.ss.android.ugc.aweme'], 'OBSERVED_ACCOUNT_TOPOLOGY_CHANGED')
    return {'counts': counts, 'types': types_found, 'existing_account_unchanged': True}

def current_state(session):
    raw_rows = query(session, 'raw_contacts', ('_id', 'contact_id', 'deleted'))
    names = query(session, 'data', ('_id', 'raw_contact_id', 'contact_id', 'mimetype', 'data1'), "mimetype='" + NAME_MIME + "' AND (data1='" + NAME + "' OR data1='" + EDITED + "')")
    require(len({row['_id'] for row in raw_rows}) == len(raw_rows), 'DUPLICATE_RAW_CONTACT_IDS')
    for row in raw_rows:
        require(re.fullmatch('[1-9]\\d*', row['_id'] or '') is not None and row['deleted'] in ('0', '1'), 'RAW_CONTACT_IDENTITY_INVALID')
    own = None
    if names:
        require(len(names) == 1 and names[0]['mimetype'] == NAME_MIME and (names[0]['data1'] in (NAME, EDITED)), 'OWNED_MARKER_NOT_UNIQUE')
        raw_id = names[0]['raw_contact_id']
        require(re.fullmatch('[1-9]\\d*', raw_id or '') is not None, 'OWNED_RAW_ID_INVALID')
        accounts = query(session, 'raw_contacts', ('_id', 'contact_id', 'account_name', 'account_type', 'data_set', 'deleted'), '_id=' + raw_id)
        require(len(accounts) == 1, 'OWNED_RAW_CONTACT_MISSING')
        own = {'name_row': names[0], 'raw_contact': accounts[0]}
    session.guard()
    return {'raw_rows': raw_rows, 'marker_rows': names, 'owned': own}

def validate_before(state):
    require(state['raw_rows'] == [] and state['marker_rows'] == [] and (state['owned'] is None), 'BASELINE_NOT_EMPTY_OR_MARKER_PREEXISTS')

def validate_owned(state, expected_name, original=None):
    own = state['owned']
    require(own is not None and own['name_row']['data1'] == expected_name, 'OWNED_NAME_NOT_OBSERVED')
    raw = own['raw_contact']
    require(raw['account_name'] is None and raw['account_type'] is None and (raw['data_set'] is None), 'OWNED_CONTACT_IS_NOT_DEVICE_LOCAL')
    require(raw['deleted'] == '0' and raw['contact_id'] == own['name_row']['contact_id'], 'OWNED_CONTACT_IS_DELETED_OR_AGGREGATED_DIFFERENTLY')
    require(len(state['raw_rows']) == 1 and state['raw_rows'][0]['_id'] == raw['_id'] and (state['raw_rows'][0]['deleted'] == '0'), 'CONTACT_SET_CHANGED_OUTSIDE_OWNED_RECORD')
    if original is not None:
        old = original['owned']
        require(old is not None and raw['_id'] == old['raw_contact']['_id'] and (raw['contact_id'] == old['raw_contact']['contact_id']), 'EDIT_CHANGED_OWNED_RECORD_IDENTITY')
    return {'raw_contact_id': raw['_id'], 'contact_id': raw['contact_id'], 'name_data_id': own['name_row']['_id'], 'name': expected_name, 'local_null_account': True}

def validate_deleted(state, original):
    owned_id = original['owned']['raw_contact']['_id']
    require(state['marker_rows'] == [] and state['owned'] is None, 'OWNED_CONTACT_STILL_VISIBLE')
    require(all((row['_id'] == owned_id and row['deleted'] == '1' for row in state['raw_rows'])), 'LIVE_CONTACT_REMAINS_OR_UNOWNED_RECORD_APPEARED')
    return {'active_owned_contact_absent': True, 'owned_tombstone_count': len(state['raw_rows']), 'database_returned_to_empty': state['raw_rows'] == []}
