#!/usr/bin/python3 -I
"""Held, read-only DeskClock counts and owned-record verification; no UI or SQL writes."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import types

SOURCE = Path('/home/alex/work/pocket4-camera-release08-20261105-r12/transaction-tools-01/camera_transaction.py')
SOURCE_SHA = 'b2274355ea9acc9d3f82f4e245dceef01aae86e689221744f0fb2afaff679470'
PACKAGE = 'com.android.deskclock'
APK_PATH = '/data/app/~~xsYWlTJZScitaVx0PPhpRg==/com.android.deskclock-1Osktcwu1xSJkGkIxMeuoQ==/base.apk'
APK_SHA = 'cc7eece9d0429267d1950f0ca9287b041493bc5c05602ffc2119e1866381fb73'
APK_BYTES = 7593129
DB = '/data/user_de/0/com.android.deskclock/databases/alarms.db'
MARKER = 'Pocket4 Local QA r12 clock 2e73c4a9'
QUERIES = {
    'schema': "SELECT name,sql FROM sqlite_master WHERE type='table' ORDER BY name;",
    'counts': "SELECT 'alarm_templates' AS kind,COUNT(*) AS count FROM alarm_templates UNION ALL SELECT 'alarm_instances',COUNT(*) FROM alarm_instances;",
    'template-ids': 'SELECT _id FROM alarm_templates ORDER BY _id;',
    'instance-ids': 'SELECT _id,alarm_id,alarm_state FROM alarm_instances ORDER BY _id;',
    'enabled-count': 'SELECT COUNT(*) AS enabled_count FROM alarm_templates WHERE enabled<>0;',
    'marker-count': "SELECT COUNT(*) AS marker_count FROM alarm_templates WHERE label='" + MARKER + "';",
}


def require(value, reason):
    if not value:
        raise RuntimeError(reason)


def load_session():
    raw = SOURCE.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == SOURCE_SHA, 'FROZEN_SESSION_CHANGED')
    module = types.ModuleType('clock_frozen_transport')
    module.__file__ = str(SOURCE)
    exec(compile(raw, str(SOURCE), 'exec'), module.__dict__)
    return module


def identity(session):
    data, _ = session.target.read_file(APK_PATH, 16 * 1024 * 1024)
    require(len(data) == APK_BYTES and hashlib.sha256(data).hexdigest() == APK_SHA, 'CLOCK_APK_CHANGED')
    paths = session.android(['/system/bin/pm', 'path', PACKAGE]).decode().splitlines()
    require(paths == ['package:' + APK_PATH], 'CLOCK_ACTIVE_PATH_CHANGED')
    dump = session.android(['/system/bin/dumpsys', 'package', PACKAGE]).decode()
    blocks = re.findall(r'^Packages:\n(.*?)(?=^\S|\Z)', dump, re.M | re.S)
    require(len(blocks) == 1 and re.findall(r'^    appId=(\d+)$', blocks[0], re.M) == ['10063']
            and re.findall(r'^    versionCode=(\d+)\b', blocks[0], re.M) == ['37'], 'CLOCK_UID_VERSION_CHANGED')
    permission = re.findall(r'^        android\.permission\.POST_NOTIFICATIONS: granted=(true|false),', blocks[0], re.M)
    require(len(permission) == 1, 'NOTIFICATION_PERMISSION_UNRECOGNIZED')
    session.guard()
    return {'uid': 10063, 'version_code': 37, 'apk_sha256': APK_SHA,
            'notifications_granted': permission[0] == 'true'}


def read_sql(session, label, sql):
    require(re.fullmatch('[a-z0-9-]+', label) is not None, 'QUERY_LABEL_INVALID')
    require(sql.startswith('SELECT ') and not re.search(r'\b(INSERT|UPDATE|DELETE|DROP|ALTER|ATTACH)\b', sql), 'READ_ONLY_SQL_REQUIRED')
    # android() intentionally drops to UID 2000. Root SQL instead enters through
    # the same already-held namespace/root FDs; no new discovery or numeric PID.
    command = ['/system/bin/env', '-i'] + [k + '=' + session.environment[k] for k in sorted(session.environment)]
    command += ['/system/bin/timeout', '-k', '2', '12', '/system/bin/sqlite3', '-readonly', '-json',
                DB, 'PRAGMA query_only=ON;BEGIN;' + sql + 'ROLLBACK;']
    with session.target.entry(command) as (entry, descriptors):
        result = session.run_host('clock-sql-' + label, entry, 16, descriptors)
    require(result['rc'] == 0 and not result['timed_out'] and result['joined'], 'CLOCK_READ_QUERY_FAILED')
    raw = result['stdout'].decode('utf-8', 'strict')
    rows = json.loads(raw) if raw.strip() else []
    require(isinstance(rows, list), 'SQL_JSON_ROWS_REQUIRED')
    return rows


def state(session, include_schema=False):
    labels = ('counts', 'template-ids', 'instance-ids', 'enabled-count', 'marker-count')
    result = {label: read_sql(session, label, QUERIES[label]) for label in labels}
    if include_schema:
        result['schema'] = read_sql(session, 'schema', QUERIES['schema'])
    result['epoch_sha256'] = session.epoch_sha256
    return result


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


def owned_record(session, baseline, current):
    require(baseline.get('epoch_sha256') == current.get('epoch_sha256') == session.epoch_sha256, 'OWNED_RECORD_EPOCH_CHANGED')
    old = baseline_ids(baseline)
    now = baseline_ids(current)
    require(old <= now and len(now - old) == 1, 'ONE_OWNED_NEW_ALARM_REQUIRED')
    owned = next(iter(now - old))
    query = ('SELECT _id,hour,minutes,daysofweek,enabled,vibrate,label,ringtone,delete_after_use '
             'FROM alarm_templates WHERE _id=' + str(owned) + " AND label='" + MARKER + "';")
    rows = read_sql(session, 'owned-alarm', query)
    require(len(rows) == 1 and rows[0]['_id'] == owned and rows[0]['label'] == MARKER, 'OWNED_MARKER_NOT_VERIFIED')
    require(rows[0]['daysofweek'] == 0 and rows[0]['delete_after_use'] == 0, 'ONE_SHOT_PERSISTENT_ALARM_REQUIRED')
    return rows[0]


def verify_deleted(baseline, current):
    require(baseline.get('epoch_sha256') == current.get('epoch_sha256'), 'DELETE_READBACK_EPOCH_CHANGED')
    require(baseline_ids(current) == baseline_ids(baseline) and current['counts'] == baseline['counts']
            and current['enabled-count'] == baseline['enabled-count'] and current['instance-ids'] == baseline['instance-ids']
            and current['marker-count'] == [{'marker_count': 0}], 'OWNED_ALARM_OR_INSTANCE_NOT_CLEANED')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--collect', type=Path)
    args = parser.parse_args()
    if args.collect is None:
        print(json.dumps({'state': 'PLAN_ONLY', 'UI_actions': 0, 'alarm_writes': 0, 'marker': MARKER}))
        return 0
    require(args.collect.is_absolute(), 'ABSOLUTE_NEW_JOURNAL_REQUIRED')
    tx = load_session()
    with tx.CameraSession(args.collect) as session:
        result = {'read_only': True, 'UI_actions': 0, 'alarm_writes': 0, 'existing_labels_returned': False,
                  'identity': identity(session), 'state': state(session, include_schema=True)}
        tx.write_new(args.collect / 'result.json', result)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
