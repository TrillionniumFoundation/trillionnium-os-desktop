"""Pure original DeskClock parsers and preservation assessments.

No session, root entry, installer, task, UI, or execution entry point is included.
Old identity constants remain original case requirements, never a fresh result.
"""
from pathlib import Path
import hashlib
import re
import xml.etree.ElementTree as ET

PACKAGE, UID, VERSION = 'com.android.deskclock', 10063, 37

ALARM_SHA = '655c545ee9487dc380100d6300376d0bb82d0d12beddd96f283ab7814ff19fea'

SOUND_KEYS = ('volume_alarm','volume_ring','volume_notification','volume_music',
              'alarm_alert','notification_sound','ringtone')

def require(value, reason):
    if not value:
        raise RuntimeError(reason)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def parse_identity(text, guest):
    blocks = re.findall(r'^Packages:\n(.*?)(?=^\S|\Z)', text, re.M | re.S)
    require(len(blocks) == 1, 'ONE_ACTIVE_CLOCK_PACKAGE_REQUIRED')
    block = blocks[0]
    require(re.findall(r'^  Package \[([^]]+)\]', block, re.M) == [PACKAGE], 'ACTIVE_PACKAGE_IS_NOT_CLOCK')
    def one(pattern, source=block):
        values = re.findall(pattern, source, re.M)
        require(len(values) == 1, 'CLOCK_PACKAGE_FIELD_AMBIGUOUS:' + pattern)
        return values[0]
    user = one(r'^    User 0: (.*)$')
    require('installed=true' in user and 'hidden=false' in user and 'suspended=false' in user, 'CLOCK_USER_STATE_CHANGED')
    version = one(r'^    versionCode=(\d+) minSdk=(\d+) targetSdk=(\d+)$')
    require(version == ('37','37','30'), 'CLOCK_VERSION_OR_SDK_CHANGED')
    permissions = re.findall(r'^        (android\.permission\.[A-Z_]+): granted=(true|false), flags=\[(.*?)\]$', block, re.M)
    require(permissions and len(permissions) == len({x[0] for x in permissions}), 'CLOCK_PERMISSION_SET_AMBIGUOUS')
    perms = {p:{'granted':g == 'true','flags':f} for p,g,f in permissions}
    require(perms.get('android.permission.POST_NOTIFICATIONS',{}).get('granted') is True,
            'CLOCK_NOTIFICATION_REPAIR_NOT_PRESENT')
    result = {'uid':int(one(r'^    appId=(\d+)$')), 'version':37, 'min_sdk':37, 'target_sdk':30,
        'ce_inode':int(one(r'\bceDataInode=(\d+)',user)), 'de_inode':int(one(r'\bdeDataInode=(\d+)',user)),
        'data_dir':one(r'^      dataDir=(.*)$'), 'first_install_time':one(r'^      firstInstallTime=(.*)$'),
        'runtime_permissions':perms}
    require(result['uid'] == UID and result['data_dir'] == '/data/user/0/' + PACKAGE, 'CLOCK_UID_OR_DATA_PATH_CHANGED')
    require(str(Path(guest).parent) == one(r'^    codePath=(.*)$'), 'CLOCK_ACTIVE_APK_PATH_MISMATCH')
    return result

def appop_allow(raw):
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    matches = [re.fullmatch(r'(?:Uid mode: )?POST_NOTIFICATION: ([a-z_]+)(?:;[^\n]*)?',line) for line in lines]
    modes = [match[1] for match in matches if match is not None]
    return (len(lines) in (1,2) and len(modes) == len(lines) and all(x == 'allow' for x in modes)
            or lines == ['No operations.','Default mode: allow'])

def audio_streams(raw):
    values = {}
    lines = raw.splitlines()
    for index,line in enumerate(lines):
        if not re.match(r'^[ \t]*- STREAM_',line):
            continue
        # Actual AudioService dump: "- STREAM_SYSTEM (aliased to: STREAM_RING):".
        # Each stream block ends with its own blank line, before volume groups.
        match = re.fullmatch(r'[ \t]*- (STREAM_[A-Z0-9_]+)(?: \(aliased to: (STREAM_[A-Z0-9_]+)\))?:',line)
        require(match is not None, 'AUDIO_STREAM_HEADER_UNRECOGNIZED')
        fields = []
        for child in lines[index+1:]:
            if not child.strip():
                break
            require(child.startswith('   '), 'AUDIO_STREAM_BOUNDARY_CHANGED')
            if re.match(r'^\s*(Muted(?: Internally)?|Min|Max|streamVolume|Current):',child):
                fields.append(child.strip())
        require(match[1] not in values, 'AUDIO_STREAM_DUPLICATE')
        values[match[1]] = {'alias':match[2],'fields':fields}
    require({'STREAM_ALARM','STREAM_RING','STREAM_MUSIC','STREAM_NOTIFICATION'} <= set(values),
            'ACTUAL_SOUND_STREAMS_NOT_OBSERVED')
    for item in values.values():
        fields = item['fields']
        require(all(sum(line.startswith(key + ':') for line in fields) == 1
                    for key in ('Muted','Muted Internally','Min','Max','Current'))
            and sum(line.startswith('streamVolume:') for line in fields) <= 1,
                'AUDIO_VOLUME_FIELDS_AMBIGUOUS')
    return values

def preference_metadata(raw):
    """Only mask the one observed Android-generated global intent counter value.

    All other bytes, including unrelated keys, order and XML formatting, remain
    part of the hash. No preference content is written or returned.
    """
    root = ET.fromstring(raw)
    require(root.tag == 'map', 'PREFERENCES_XML_MAP_REQUIRED')
    items = [item for item in root if item.get('name') == 'intent.extra.alarm.global.id']
    require(len(items) == 1 and items[0].tag == 'int'
        and set(items[0].attrib) == {'name','value'}, 'ONE_GLOBAL_INTENT_COUNTER_REQUIRED')
    value = items[0].get('value')
    require(re.fullmatch(r'-?(?:0|[1-9][0-9]*)',value or '') is not None
        and -2147483648 <= int(value) < 2147483647, 'GLOBAL_INTENT_COUNTER_OUT_OF_SCOPE')
    pattern = rb'(<int name="intent\.extra\.alarm\.global\.id" value=")(-?[0-9]+)(" />)'
    matches = list(re.finditer(pattern,raw))
    require(len(matches) == 1 and matches[0][2].decode() == value, 'OBSERVED_COUNTER_XML_FORMAT_CHANGED')
    match = matches[0]
    masked = raw[:match.start(2)] + b'REVIEWED_GLOBAL_INTENT_COUNTER' + raw[match.end(2):]
    return {'global_intent_id':int(value),'all_other_preference_bytes_sha256':sha(masked)}

def preference_review(before,after):
    old_hash,new_hash = before.get('preferences_sha256'),after.get('preferences_sha256')
    same = (isinstance(old_hash,str) and re.fullmatch('[0-9a-f]{64}',old_hash) is not None
        and old_hash == new_hash)
    a,b = before.get('preferences_metadata',{}),after.get('preferences_metadata',{})
    delta = (type(a.get('global_intent_id')) is int and type(b.get('global_intent_id')) is int
        and b['global_intent_id'] == a['global_intent_id'] + 1
        and isinstance(a.get('all_other_preference_bytes_sha256'),str)
        and re.fullmatch('[0-9a-f]{64}',a['all_other_preference_bytes_sha256']) is not None
        and a['all_other_preference_bytes_sha256'] == b.get('all_other_preference_bytes_sha256'))
    return {'preferences_bytes_identical':same,'accepted':same or delta,
        'only_documented_global_intent_counter_increment':not same and delta,
        'global_intent_id_before':a.get('global_intent_id'),
        'global_intent_id_after':b.get('global_intent_id'),
        'other_preference_bytes_preserved':same or delta,'preference_write_commands':0}

def preserved(before,after,include_preferences=True,include_tasks=True):
    keys = ['package','epoch_sha256','identity','directories','alarm_state','alarm_content_sha256',
            'timer_and_stopwatch_empty','notification_appop_allow','sound_state']
    if include_tasks:
        keys.append('tasks_sha256')
    return (all(before.get(k) == after.get(k) for k in keys)
        and (not include_preferences or preference_review(before,after)['accepted']))

DB = '/data/user_de/0/com.android.deskclock/databases/alarms.db'

MARKER = 'Pocket4 QA alarm 67f3c942'

QUERIES = {
    'schema': "SELECT name,sql FROM sqlite_master WHERE type='table' ORDER BY name;",
    'counts': "SELECT 'alarm_templates' AS kind,COUNT(*) AS count FROM alarm_templates UNION ALL SELECT 'alarm_instances',COUNT(*) FROM alarm_instances;",
    'template-ids': 'SELECT _id FROM alarm_templates ORDER BY _id;',
    'instance-ids': 'SELECT _id,alarm_id,alarm_state FROM alarm_instances ORDER BY _id;',
    'enabled-count': 'SELECT COUNT(*) AS enabled_count FROM alarm_templates WHERE enabled<>0;',
    'marker-count': "SELECT COUNT(*) AS marker_count FROM alarm_templates WHERE label='" + MARKER + "';",
}

def baseline_ids(baseline):
    ids = [row['_id'] for row in baseline['template-ids']]
    require(all(type(x) is int and x > 0 for x in ids) and len(ids) == len(set(ids)), 'BASELINE_IDS_INVALID')
    counts = {row['kind']: row['count'] for row in baseline['counts']}
    require(counts == {'alarm_templates': len(ids), 'alarm_instances': len(baseline['instance-ids'])}, 'COUNT_ID_SNAPSHOT_INCONSISTENT')
    return set(ids)

def verify_before(baseline):
    baseline_ids(baseline)
    require(baseline['marker-count'] == [{'marker_count': 0}], 'MARKER_ALREADY_EXISTS')
    require(baseline['enabled-count'] == [{'enabled_count': 0}] and baseline['instance-ids'] == [],
            'EXISTING_ACTIVE_ALARM_NO_TEST_SCHEDULED')

PREFS = '/data/user_de/0/com.android.deskclock/shared_prefs/com.android.deskclock_preferences.xml'

UNUSED = -(1 << 63)

FIELDS = {
    'timer_state_': ('state', 'int'),
    'timer_setup_timet_': ('length_ms', 'long'),
    'timer_original_timet_': ('total_length_ms', 'long'),
    'timer_start_time_': ('last_start_ms', 'long'),
    'timer_wall_clock_time_': ('last_wall_ms', 'long'),
    'timer_time_left_': ('remaining_ms', 'long'),
    'timer_label_': ('label', 'string'),
    'delete_after_use_': ('delete_after_use', 'boolean'),
}

def parse(raw):
    tree = ET.fromstring(raw)
    require(tree.tag == 'map', 'CLOCK_PREFERENCES_FORMAT_UNKNOWN')
    entries, timer_values, watch = {}, {}, {}
    for entry in tree:
        key = entry.get('name', '')
        require(key and key not in entries, 'PREFERENCE_NAME_MISSING_OR_DUPLICATE')
        entries[key] = entry
        if key.startswith('sw_'):
            require(entry.tag in ('int', 'long') and re.fullmatch('-?[0-9]+', entry.get('value', '')),
                    'STOPWATCH_VALUE_UNKNOWN')
            watch[key] = int(entry.get('value'))
        if 'timer' in key.lower() or key.startswith('delete_after_use_'):
            timer_values[key] = ET.tostring(entry, encoding='unicode')
    if not timer_values:
        return {'ids': [], 'timers': [], 'values': {}, 'stopwatch': watch}
    metadata = {'timers_list', 'next_timer_id'}
    require('timers_list' in entries or set(timer_values) <= metadata, 'TIMER_ID_SET_REQUIRED')
    require('timers_list' not in entries or entries['timers_list'].tag == 'set', 'TIMER_ID_SET_REQUIRED')
    ids = []
    for item in entries.get('timers_list', ()):
        require(item.tag == 'string' and re.fullmatch('0|[1-9][0-9]*', item.text or ''), 'TIMER_ID_INVALID')
        ids.append(int(item.text))
    require(len(ids) == len(set(ids)) and len(ids) <= 8, 'TIMER_IDS_EMPTY_DUPLICATE_OR_TOO_MANY')
    if 'next_timer_id' in entries:
        require(entries['next_timer_id'].tag == 'int'
            and re.fullmatch('[0-9]+', entries['next_timer_id'].get('value', '')), 'NEXT_TIMER_ID_UNKNOWN')
    if not ids:
        # Empty membership and an allocation counter are metadata, not a timer.
        # Preserve their real bytes in evidence; never delete them to pass a test.
        require(set(timer_values) <= metadata, 'UNRECOGNIZED_OR_ORPHAN_TIMER_PREFERENCE')
        return {'ids': [], 'timers': [], 'values': dict(sorted(timer_values.items())), 'stopwatch': watch}
    require('next_timer_id' in entries, 'NEXT_TIMER_ID_UNKNOWN')
    require(int(entries['next_timer_id'].get('value')) > max(ids), 'NEXT_TIMER_ID_INCONSISTENT')
    expected = {'timers_list', 'next_timer_id'}
    timers = []
    for ident in sorted(ids):
        timer = {'id': ident}
        for prefix, (field, kind) in FIELDS.items():
            key = prefix + str(ident)
            entry = entries.get(key)
            # SharedPreferences.putString(null) removes an optional label.
            if entry is None and kind == 'string':
                timer[field] = None
                continue
            require(entry is not None and entry.tag == kind, 'TIMER_FIELD_MISSING_OR_WRONG_TYPE_' + field)
            expected.add(key)
            if kind in ('int', 'long'):
                require(re.fullmatch('-?[0-9]+', entry.get('value', '')), 'TIMER_NUMBER_UNKNOWN')
                value = int(entry.get('value'))
                require(-(1 << 63) <= value < (1 << 63), 'TIMER_NUMBER_OUT_OF_RANGE')
            elif kind == 'boolean':
                require(entry.get('value') in ('true', 'false'), 'TIMER_BOOLEAN_UNKNOWN')
                value = entry.get('value') == 'true'
            else:
                value = entry.text or ''
                require(len(value.encode()) <= 4096, 'TIMER_LABEL_TOO_LONG')
            timer[field] = value
        require(timer['state'] in (1, 2, 3, 4, 5) and timer['length_ms'] > 0
                and timer['total_length_ms'] >= 0, 'TIMER_STATE_OR_DURATION_UNKNOWN')
        timers.append(timer)
    require(set(timer_values) == expected, 'UNRECOGNIZED_OR_ORPHAN_TIMER_PREFERENCE')
    return {'ids': sorted(ids), 'timers': timers, 'values': dict(sorted(timer_values.items())), 'stopwatch': watch}

def empty(value):
    require(value['ids'] == value['timers'] == []
            and set(value['values']) <= {'timers_list', 'next_timer_id'}
            and value['stopwatch'] == {}, 'EMPTY_TIMER_AND_STOPWATCH_BASELINE_REQUIRED')

def owned(value, ident, duration):
    require(value['ids'] == [ident] and len(value['timers']) == 1 and value['stopwatch'] == {},
            'SOLE_OWNED_TIMER_AND_EMPTY_STOPWATCH_REQUIRED')
    timer = value['timers'][0]
    require(timer['id'] == ident and timer['length_ms'] == timer['total_length_ms'] == duration
            and timer['label'] in ('', None) and timer['delete_after_use'] is False,
            'OWNED_TIMER_FIELDS_CHANGED')
    return timer
