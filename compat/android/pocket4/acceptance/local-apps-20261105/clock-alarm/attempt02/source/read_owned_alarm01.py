#!/usr/bin/python3 -I
"""Read-only ownership and state checks for exactly one UI-created Clock alarm."""
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import os
import re
import stat
import struct
import xml.etree.ElementTree as ET
import zipfile

PACKAGE = 'com.android.deskclock'
UID = 10063
MARKER = 'Pocket4 QA alarm 19d75a2c'
ORIGINAL_IDS = [1, 2]
ORIGINAL_SHA = '655c545ee9487dc380100d6300376d0bb82d0d12beddd96f283ab7814ff19fea'
PREFS = '/data/user_de/0/com.android.deskclock/shared_prefs/com.android.deskclock_preferences.xml'
TEMPLATE_FIELDS = '_id,hour,minutes,daysofweek,enabled,vibrate,label,ringtone,delete_after_use'
INSTANCE_FIELDS = '_id,alarm_id,year,month,day,hour,minutes,vibrate,label,ringtone,alarm_state'
RESOURCE_IDS = {'clock': 0x7f0a00c4, 'onoff': 0x7f0a01a0, 'arrow': 0x7f0a0064,
    'label': 0x7f0a00de, 'delete': 0x7f0a00ba, 'dismiss': 0x7f0a00cd,
    'alarm_button': 0x7f0a004b, 'alert_title': 0x7f0a0053, 'repeat': 0x7f0a01d9}
STRING_IDS = {'add': 0x7f1201ba, 'label_message': 0x7f1201fc,
    'label_description': 0x7f12028d}


def need(ok, why):
    if not ok:
        raise RuntimeError(why)


def fingerprint(session, model):
    # Old labels, ringing times and other original contents never leave Android.
    script = ('set -o pipefail; /system/bin/sqlite3 -readonly -json ' + model.DB
        + " 'PRAGMA query_only=ON;BEGIN;SELECT * FROM alarm_templates WHERE _id IN (1,2) ORDER BY _id;ROLLBACK;'"
        + ' | /system/bin/sha256sum')
    argv = ['/system/bin/env', '-i'] + [k + '=' + session.environment[k] for k in sorted(session.environment)]
    argv += ['/system/bin/timeout', '-k', '2', '12', '/system/bin/sh', '-c', script]
    with session.target.entry(argv) as (command, descriptors):
        value = session.run_host('alarm-original-digest', command, 16, descriptors)
    need(value['rc'] == 0 and value['joined'] and not value['timed_out']
        and value['stdout'].decode().strip() == ORIGINAL_SHA + '  -', 'ORIGINAL_ALARM_CONTENT_CHANGED')
    return ORIGINAL_SHA


def data_identity(session, model):
    fd = session.target.open_root(model.DB, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        value = os.fstat(fd)
        need(stat.S_ISREG(value.st_mode) and value.st_nlink == 1
            and value.st_uid == value.st_gid == UID, 'ALARM_DATABASE_IDENTITY_UNVERIFIED')
        return {name: getattr(value, name) for name in ('st_dev', 'st_ino', 'st_uid', 'st_gid', 'st_mode')}
    finally:
        os.close(fd)


def sound_preferences(session):
    raw, _ = session.target.read_file(PREFS, 2 * 1024 * 1024)
    root = ET.fromstring(raw)
    need(root.tag == 'map', 'CLOCK_PREFERENCES_MAP_REQUIRED')
    selected = {}
    for item in root:
        key = item.get('name', '')
        if any(word in key.casefold() for word in ('ringtone', 'volume', 'sound')):
            need(key not in selected, 'SOUND_PREFERENCE_DUPLICATE')
            selected[key] = hashlib.sha256(ET.tostring(item)).hexdigest()
    session.guard()
    return selected


def clock(session):
    zone = session.android(['/system/bin/getprop', 'persist.sys.timezone']).decode().strip()
    need(re.fullmatch(r'[A-Za-z0-9_+./-]{1,96}', zone) is not None, 'TIMEZONE_PROPERTY_UNKNOWN')
    raw = session.android(['/system/bin/date', '+%s|%Y-%m-%dT%H:%M:%S%z']).decode().strip()
    match = re.fullmatch(r'(\d+)\|([0-9T:+-]+)', raw)
    need(match is not None, 'DEVICE_TIME_FORMAT_UNKNOWN')
    stamp = datetime.strptime(match[2], '%Y-%m-%dT%H:%M:%S%z')
    epoch = int(match[1])
    need(int(stamp.timestamp()) == epoch, 'DEVICE_WALL_TIME_INCONSISTENT')
    return {'epoch_seconds': epoch, 'local_iso': stamp.isoformat(), 'timezone_property': zone,
        'utc_offset_seconds': int(stamp.utcoffset().total_seconds())}


def target_time(now):
    # A minute boundary 181–240 seconds ahead; never change time or time zone.
    epoch = (now['epoch_seconds'] // 60 + 4) * 60
    local = datetime.fromtimestamp(epoch, timezone(timedelta(seconds=now['utc_offset_seconds'])))
    return {'epoch_seconds': epoch, 'local_iso': local.isoformat(),
        'timezone_property': now['timezone_property'], 'utc_offset_seconds': now['utc_offset_seconds'],
        'year': local.year, 'month': local.month - 1, 'day': local.day,
        'hour': local.hour, 'minutes': local.minute}


def integer(value):
    return type(value) is int and value > 0


def resource_contract(apk):
    """Resolve actual compiled IDs taken from the pinned, installed methods."""
    with zipfile.ZipFile(io.BytesIO(apk)) as archive:
        data = archive.read('resources.arsc')
    need(len(data) <= 16 * 1024 * 1024, 'RESOURCE_TABLE_TOO_LARGE')
    def h(p):
        need(0 <= p <= len(data) - 2, 'RESOURCE_HALFWORD_OUT_OF_RANGE')
        return struct.unpack_from('<H', data, p)[0]
    def w(p):
        need(0 <= p <= len(data) - 4, 'RESOURCE_WORD_OUT_OF_RANGE')
        return struct.unpack_from('<I', data, p)[0]
    def chunk(p, end):
        kind, header, size = h(p), h(p + 2), w(p + 4)
        need(8 <= header <= size and p + size <= end, 'RESOURCE_CHUNK_INVALID')
        return kind, header, size
    def pool(p):
        kind, header, size = chunk(p, len(data))
        need(kind == 1 and header >= 28 and w(p + 8) <= 200000, 'RESOURCE_STRING_POOL_INVALID')
        count, flags, start = w(p + 8), w(p + 16), w(p + 20)
        need(header + count * 4 <= size, 'RESOURCE_STRING_INDEX_INVALID')
        out = []
        for index in range(count):
            q = p + start + w(p + header + index * 4)
            if flags & 0x100:
                def size8(q):
                    need(p <= q < p + size, 'RESOURCE_UTF8_LENGTH_INVALID')
                    first = data[q]
                    return (((first & 127) << 8) | data[q + 1], q + 2) if first & 128 else (first, q + 1)
                _, q = size8(q); length, q = size8(q)
                need(q + length < p + size and data[q + length] == 0, 'RESOURCE_UTF8_STRING_INVALID')
                value = data[q:q + length].decode('utf-8', 'strict')
            else:
                length = h(q); q += 2
                if length & 0x8000:
                    length = ((length & 32767) << 16) | h(q); q += 2
                need(q + 2 * length + 2 <= p + size and h(q + 2 * length) == 0,
                    'RESOURCE_UTF16_STRING_INVALID')
                value = data[q:q + 2 * length].decode('utf-16-le', 'strict')
            out.append(value)
        return out
    wanted = set(RESOURCE_IDS.values()) | set(STRING_IDS.values())
    names, texts = {}, {}
    need(h(0) == 2 and w(4) == len(data), 'RESOURCE_TABLE_HEADER_INVALID')
    p = h(2); global_strings = None
    while p < len(data):
        kind, head, size = chunk(p, len(data))
        if kind == 1:
            need(global_strings is None, 'RESOURCE_GLOBAL_POOL_DUPLICATE')
            global_strings = pool(p)
        if kind == 0x200 and w(p + 8) == 0x7f:
            need(head >= 284 and (head < 288 or w(p + 284) == 0), 'RESOURCE_PACKAGE_FORMAT_UNKNOWN')
            types, keys = pool(p + w(p + 268)), pool(p + w(p + 276))
            q = p + head
            while q < p + size:
                k, header, length = chunk(q, p + size)
                if k == 0x201:
                    type_id, flags, count, start = data[q + 8], data[q + 9], w(q + 12), w(q + 16)
                    need(flags in (0, 1, 2) and 0 < type_id <= len(types), 'RESOURCE_TYPE_FORMAT_UNKNOWN')
                    requested = [v for v in wanted if (v >> 16) & 255 == type_id]
                    for resource in requested:
                        index = resource & 65535
                        if flags == 1:
                            need(header + 4 * count <= length, 'SPARSE_RESOURCE_INDEX_INVALID')
                            pairs = {h(q + header + 4 * i): h(q + header + 4 * i + 2) * 4 for i in range(count)}
                            offset = pairs.get(index, 0xffffffff)
                        elif index >= count:
                            offset = 0xffffffff
                        elif flags == 2:
                            small = h(q + header + 2 * index)
                            offset = 0xffffffff if small == 0xffff else small * 4
                        else:
                            offset = w(q + header + 4 * index)
                        if offset == 0xffffffff:
                            continue
                        entry = q + start + offset
                        need(q + header <= entry and entry + 8 <= q + length, 'RESOURCE_ENTRY_INVALID')
                        ef = h(entry + 2)
                        key_index = h(entry) if ef & 8 else w(entry + 4)
                        need(key_index < len(keys), 'RESOURCE_KEY_INVALID')
                        name = (types[type_id - 1], keys[key_index])
                        need(resource not in names or names[resource] == name, 'RESOURCE_NAME_AMBIGUOUS')
                        names[resource] = name
                        # Use only actual default-locale strings; unknown locale stops UI selection.
                        if resource in STRING_IDS.values() and data[q + 28:q + 32] == b'\0' * 4:
                            need(not ef & 1 and global_strings is not None, 'RESOURCE_STRING_VALUE_INVALID')
                            if ef & 8:
                                datatype, value = ef >> 8, w(entry + 4)
                            else:
                                at = entry + h(entry)
                                need(at + 8 <= q + length and h(at) == 8, 'RESOURCE_VALUE_SIZE_INVALID')
                                datatype, value = data[at + 3], w(at + 4)
                            need(datatype == 3 and value < len(global_strings), 'RESOURCE_STRING_REFERENCE_INVALID')
                            texts.setdefault(resource, set()).add(global_strings[value])
                q += length
        p += size
    need(set(names) == wanted, 'REQUIRED_COMPILED_RESOURCE_NOT_FOUND')
    ids = {role: PACKAGE + ':id/' + names[value][1] for role, value in RESOURCE_IDS.items()}
    need(all(names[v][0] == 'id' for v in RESOURCE_IDS.values()), 'RESOURCE_ROLE_IS_NOT_ID')
    need(all(names[v][0] == 'string' and len(texts.get(v, set())) == 1 for v in STRING_IDS.values()),
        'DEFAULT_RESOURCE_STRING_NOT_UNIQUE')
    return {'ids': ids, 'texts': {role: next(iter(texts[value])) for role, value in STRING_IDS.items()},
        'resources_arsc_sha256': hashlib.sha256(data).hexdigest(),
        'numeric_ids_from_actual_installed_methods': {k: hex(v) for k, v in {**RESOURCE_IDS, **STRING_IDS}.items()}}


class Read:
    def __init__(self, session, model):
        self.s, self.m = session, model
        self.database = data_identity(session, model)
        self.alarm_id = None
        self.target = None
        self.created = None
        self.instance = None
        self.removed = False
        self.sound = sound_preferences(session)
        self.zone = clock(session)

    def summary(self):
        before = data_identity(self.s, self.m)
        need(before == self.database, 'ALARM_DATABASE_REPLACED')
        rows = self.m.read_sql(self.s, 'alarm-summary',
            'SELECT (SELECT COUNT(*) FROM alarm_templates) AS template_count,'
            '(SELECT COUNT(*) FROM alarm_instances) AS instance_count,'
            '(SELECT COUNT(*) FROM alarm_templates WHERE enabled<>0) AS enabled_count,'
            '(SELECT COUNT(*) FROM alarm_templates WHERE _id IN(1,2) AND enabled<>0) AS original_enabled,'
            "(SELECT COUNT(*) FROM alarm_templates WHERE label='" + MARKER + "') AS marker_count;")
        need(len(rows) == 1 and all(type(x) is int and x >= 0 for x in rows[0].values()),
            'ALARM_SUMMARY_UNKNOWN')
        ids = self.m.read_sql(self.s, 'alarm-ids', 'SELECT _id FROM alarm_templates ORDER BY _id;')
        instances = self.m.read_sql(self.s, 'instance-ids',
            'SELECT _id,alarm_id,alarm_state FROM alarm_instances ORDER BY _id;')
        value = dict(rows[0], template_ids=[r['_id'] for r in ids], instance_ids=instances)
        need(value['original_enabled'] == 0, 'ORIGINAL_ALARM_ENABLED_CHANGED')
        need(all(integer(x) for x in value['template_ids'])
            and value['template_ids'] == sorted(set(value['template_ids']))
            and value['template_count'] == len(ids) and value['instance_count'] == len(instances),
            'ALARM_SUMMARY_TEMPORARILY_INCONSISTENT')
        need(data_identity(self.s, self.m) == before, 'ALARM_DATABASE_CHANGED_DURING_READ')
        return value

    def pristine(self):
        value = self.summary()
        need(value == {'template_count': 2, 'instance_count': 0, 'enabled_count': 0,
            'original_enabled': 0, 'marker_count': 0, 'template_ids': ORIGINAL_IDS, 'instance_ids': []},
            'EXACT_TWO_DISABLED_ORIGINALS_EMPTY_BASELINE_REQUIRED')
        fingerprint(self.s, self.m)
        return value

    def read(self, claim=False, original_digest=True):
        summary = self.summary()
        if original_digest:
            fingerprint(self.s, self.m)
        expected_ids = ORIGINAL_IDS + ([self.alarm_id] if self.alarm_id and not self.removed else [])
        if claim:
            need(self.alarm_id is None and self.target is not None, 'NEW_ALARM_CLAIM_ORDER_INVALID')
            extra = set(summary['template_ids']) - set(ORIGINAL_IDS)
            need(set(ORIGINAL_IDS) < set(summary['template_ids']) and len(extra) == 1
                and summary['template_count'] == 3, 'ONE_NEW_ALARM_REQUIRED')
            candidate = next(iter(extra))
        else:
            need(summary['template_ids'] == sorted(expected_ids), 'FOREIGN_OR_MISSING_ALARM')
            candidate = None if self.removed else self.alarm_id
        if candidate is None:
            need(summary['instance_count'] == summary['enabled_count'] == summary['marker_count'] == 0,
                'UNOWNED_ALARM_STATE')
            return {'summary': summary, 'alarm': None, 'instances': []}
        need(integer(candidate) and candidate not in ORIGINAL_IDS, 'OWNED_ALARM_ID_INVALID')
        rows = self.m.read_sql(self.s, 'owned-template', 'SELECT ' + TEMPLATE_FIELDS
            + ' FROM alarm_templates WHERE _id=' + str(candidate) + ';')
        need(len(rows) == 1, 'OWNED_TEMPLATE_NOT_UNIQUE')
        alarm = rows[0]
        need(alarm['_id'] == candidate and alarm['label'] in ('', MARKER)
            and alarm['hour'] == self.target['hour'] and alarm['minutes'] == self.target['minutes']
            and alarm['daysofweek'] == 0 and alarm['delete_after_use'] == 0
            and alarm['enabled'] in (0, 1) and alarm['vibrate'] == 1,
            'OWNED_TEMPLATE_CONTRACT_CHANGED')
        if self.created is not None:
            need(all(alarm[key] == self.created[key] for key in ('_id', 'hour', 'minutes', 'daysofweek',
                'vibrate', 'ringtone', 'delete_after_use')), 'OWNED_TEMPLATE_IDENTITY_CHANGED')
        instances = self.m.read_sql(self.s, 'owned-instances', 'SELECT ' + INSTANCE_FIELDS
            + ' FROM alarm_instances WHERE alarm_id=' + str(candidate) + ' ORDER BY _id;')
        need(len(instances) == summary['instance_count'] <= 1 and summary['enabled_count'] == alarm['enabled']
            and summary['marker_count'] == int(alarm['label'] == MARKER), 'FOREIGN_ALARM_INSTANCE_OR_LABEL')
        for instance in instances:
            need(integer(instance['_id']) and instance['alarm_id'] == candidate
                and all(instance[k] == self.target[k] for k in ('year', 'month', 'day', 'hour', 'minutes'))
                and all(instance[k] == alarm[k] for k in ('vibrate', 'label', 'ringtone'))
                and instance['alarm_state'] in range(8), 'OWNED_INSTANCE_CONTRACT_CHANGED')
            if self.instance is not None:
                need(all(instance[k] == v for k, v in self.instance.items() if k != 'alarm_state'),
                    'FROZEN_INSTANCE_IDENTITY_CHANGED')
        need(data_identity(self.s, self.m) == self.database, 'ALARM_DB_IDENTITY_CHANGED_AFTER_QUERY')
        if claim:
            need(alarm['enabled'] == 1 and alarm['label'] == '' and len(instances) == 1,
                'NEW_ENABLED_UNLABELLED_ALARM_REQUIRED')
            self.alarm_id, self.created = candidate, dict(alarm)
        return {'summary': summary, 'alarm': alarm, 'instances': instances}

    def freeze_labelled(self):
        value = self.read()
        need(value['alarm']['label'] == MARKER and value['alarm']['enabled'] == 1
            and len(value['instances']) == 1 and value['instances'][0]['alarm_state'] < 5,
            'LABELLED_ALARM_WITH_ONE_FUTURE_INSTANCE_REQUIRED')
        self.instance = dict(value['instances'][0])
        return value

    def zone_unchanged(self):
        now = clock(self.s)
        need(now['timezone_property'] == self.zone['timezone_property']
            and now['utc_offset_seconds'] == self.zone['utc_offset_seconds'], 'TIMEZONE_OR_UTC_OFFSET_CHANGED')
        return now

    def deleted(self):
        value = self.pristine()
        need(sound_preferences(self.s) == self.sound, 'DEFAULT_SOUND_PREFERENCES_CHANGED')
        self.zone_unchanged()
        self.removed = True
        return value


if __name__ == '__main__':
    print(json.dumps({'state': 'PLAN_ONLY', 'UI_actions': 0, 'SQL_writes': 0,
        'new_alarm_marker': MARKER, 'original_ids_preserved': ORIGINAL_IDS}))
