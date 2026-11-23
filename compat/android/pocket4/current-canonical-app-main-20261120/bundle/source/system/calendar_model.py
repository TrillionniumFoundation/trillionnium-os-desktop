"""Independent new-Main component; no historical Session, Main or execute entry."""
from pathlib import Path
import hashlib, io, json, os, re, stat
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import urlencode, quote as url_quote
RUN = 'calendar-recurrence21-6c978e4da120b35f'
CALENDAR_LABEL = 'Pocket4 Calendar QA ' + RUN
TITLE = 'Pocket4 event ' + RUN
EDITED = TITLE + ' Edited'
UNSAVED = TITLE + ' Not saved'
ACCOUNT = 'Droidloom local calendars'
DB = '/data/user/0/com.android.providers.calendar/databases/calendar.db'
TABLES = ('Calendars', 'Events', 'Reminders', 'Attendees', 'Instances', 'CalendarAlerts', 'EventsRawTimes', 'ExtendedProperties')
CALENDAR_COLUMNS = ('_id', 'account_name', 'account_type', 'name', 'calendar_displayName', 'ownerAccount', 'calendar_access_level', 'visible', 'sync_events', 'calendar_timezone')
EVENT_COLUMNS = ('_id', 'calendar_id', 'title', 'dtstart', 'dtend', 'duration', 'eventTimezone', 'allDay', 'rrule', 'rdate', 'exrule', 'exdate', 'hasAlarm', 'deleted', '_sync_id', 'original_id', 'eventLocation', 'description')
INSTANCE_COLUMNS = ('_id', 'event_id', 'begin', 'end')
TARGET_ZONE = 'Hongkong'
HOST_TARGET_ZONE = 'Asia/Hong_Kong'
TZDATA_EVIDENCE_SHA = '3daae03a1795e880836ee3c4443552d0d45aac3f73bf00d2f3cb0b7b811a2928'
HOST_TZFILES = {'GMT': ('/usr/share/zoneinfo/GMT', 114, '6d9f378883c079f86c0387a5547a92c449869d806e07de10084ab04f0249018d'), 'Asia/Hong_Kong': ('/usr/share/zoneinfo/Asia/Hong_Kong', 1233, '6a5fcee243e5ab92698242d88c4699ceb7208a22ee97d342d11e41ebd2555a17')}
MONTHS = ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec')

def need(value, reason):
    if not value:
        raise RuntimeError(reason)

def quote(value):
    return "'" + str(value).replace("'", "''") + "'"

def fp(info):
    return {k: getattr(info, k) for k in ('st_dev', 'st_ino', 'st_uid', 'st_gid', 'st_mode')}

def owner_where():
    return ' AND '.join((k + '=' + quote(v) for k, v in {'account_name': ACCOUNT, 'account_type': 'LOCAL', 'ownerAccount': ACCOUNT, 'calendar_displayName': CALENDAR_LABEL}.items()))

def json_rows(table, columns, where, order='_id'):
    values = ','.join((quote(c) + ',' + c for c in columns))
    return '(SELECT json_group_array(json_object(' + values + ')) FROM (SELECT ' + ','.join(columns) + ' FROM ' + table + ' WHERE ' + where + ' ORDER BY ' + order + ' LIMIT 2))'

def observation_sql():
    where = owner_where()
    event_where = 'calendar_id IN (SELECT _id FROM Calendars WHERE ' + where + ')'
    event_ids = 'SELECT _id FROM Events WHERE ' + event_where
    children = 'json_object(' + ','.join((quote(t) + ',(SELECT COUNT(*) FROM ' + t + ' WHERE event_id IS NULL OR event_id NOT IN (' + event_ids + '))' for t in ('Instances', 'EventsRawTimes'))) + ')'
    counts = 'json_object(' + ','.join((quote(t) + ',(SELECT COUNT(*) FROM ' + t + ')' for t in TABLES)) + ')'
    return "PRAGMA query_only=ON;BEGIN;SELECT json_object('counts'," + counts + ",'calendars',json(" + json_rows('Calendars', CALENDAR_COLUMNS, where) + ')' + ",'events',json(" + json_rows('Events', EVENT_COLUMNS, event_where) + ')' + ",'owned_instances',json(" + json_rows('Instances', INSTANCE_COLUMNS, 'event_id IN (' + event_ids + ')', 'begin,end,_id') + ')' + ",'foreign_children'," + children + ') AS payload;ROLLBACK;'

def validate_projection(value):
    need(set(value) == {'counts', 'calendars', 'events', 'owned_instances', 'foreign_children'} and set(value['counts']) == set(TABLES), 'PROVIDER_RECORD_SHAPE')
    need(all((type(n) is int and n >= 0 for n in value['counts'].values())), 'PROVIDER_COUNTS_INVALID')
    need(isinstance(value['calendars'], list) and len(value['calendars']) <= 1 and isinstance(value['events'], list) and (len(value['events']) <= 1), 'ONE_OWNED_CALENDAR_EVENT_MAX')
    need(value['counts']['Calendars'] == len(value['calendars']) and value['counts']['Events'] == len(value['events']), 'NON_OWNED_PROVIDER_ROWS_APPEARED')
    need(set(value['foreign_children']) == {'Instances', 'EventsRawTimes'} and all((type(n) is int and n == 0 for n in value['foreign_children'].values())), 'FOREIGN_DERIVED_ROWS_APPEARED')
    need(isinstance(value['owned_instances'], list) and len(value['owned_instances']) == min(value['counts']['Instances'], 2) and all((set(row) == set(INSTANCE_COLUMNS) and all((type(x) is int for x in row.values())) and (row['_id'] > 0) and (row['event_id'] > 0) and (row['end'] > row['begin']) for row in value['owned_instances'])), 'OWNED_INSTANCE_RECORD_SHAPE')
    return value

def date_text(value):
    return MONTHS[value.month - 1] + ' ' + str(value.day) + ', ' + str(value.year)

def series_plan(event):
    need(event['eventTimezone'] in ('UTC', 'GMT') and event['dtend'] - event['dtstart'] == 2700000, 'OBSERVED_INITIAL_UTC_45_MINUTE_EVENT_REQUIRED')
    begin = datetime.fromtimestamp(event['dtstart'] / 1000, ZoneInfo(event['eventTimezone']))
    end = datetime.fromtimestamp(event['dtend'] / 1000, ZoneInfo(event['eventTimezone']))
    need(begin.date() == end.date() and (begin.hour, begin.minute, end.hour, end.minute) == (12, 0, 12, 45), 'INITIAL_NOON_45_MINUTE_EVENT_REQUIRED')
    delta = 1 if begin.day <= 27 else -1
    target = begin.date() + timedelta(days=delta)
    start = begin.replace(year=target.year, month=target.month, day=target.day, tzinfo=ZoneInfo(HOST_TARGET_ZONE))
    finish = end.replace(year=target.year, month=target.month, day=target.day, tzinfo=ZoneInfo(HOST_TARGET_ZONE))
    first = int(start.timestamp() * 1000)
    last = int(finish.timestamp() * 1000)
    need(start.utcoffset() == timedelta(hours=8) and last - first == 2700000, 'EXPECTED_TARGET_ZONE_RULE_CHANGED')
    return {'original_date': begin.date().isoformat(), 'target_date': target.isoformat(), 'original_date_text': date_text(begin.date()), 'target_date_text': date_text(target), 'original_timezone': event['eventTimezone'], 'timezone': TARGET_ZONE, 'dtstart': first, 'first_end': last, 'duration': 'PT2700S', 'rrule': 'FREQ=DAILY', 'second_begin': first + 86400000, 'second_end': last + 86400000, 'second_date_text': date_text(target + timedelta(days=1))}

def preflight_series(begin, end):
    """Resolve and exercise both host timezones before any UI or fixture write."""
    need(type(begin) is int and type(end) is int, 'INTEGER_PREFLIGHT_EVENT_TIME_REQUIRED')
    pinned_zones = {}
    files = {}
    for key, (path, size, pin) in HOST_TZFILES.items():
        fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC)
        try:
            before = os.fstat(fd)
            need(stat.S_ISREG(before.st_mode) and before.st_uid == 0 and (not before.st_mode & 18) and (before.st_size == size) and (0 < size <= 32768), 'PINNED_HOST_TZFILE_TYPE_OWNER_SIZE_REQUIRED:' + key)
            raw = os.pread(fd, size + 1, 0)
            after = os.fstat(fd)
            keys = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
            need(all((getattr(before, k) == getattr(after, k) for k in keys)) and len(raw) == size and (hashlib.sha256(raw).hexdigest() == pin), 'PINNED_HOST_TZFILE_BYTES_CHANGED:' + key)
        finally:
            os.close(fd)
        pinned_zones[key] = ZoneInfo.from_file(io.BytesIO(raw), key=key)
        files[key] = {'path': path, 'bytes': size, 'sha256': pin, 'device': before.st_dev, 'inode': before.st_ino, 'uid': before.st_uid, 'mode': before.st_mode}
    need(set(pinned_zones) == {'GMT', HOST_TARGET_ZONE} and TARGET_ZONE == 'Hongkong', 'EXACT_HOST_AND_ANDROID_ZONE_BINDING_REQUIRED')
    event = {'dtstart': begin, 'dtend': end, 'eventTimezone': 'GMT'}
    plan = series_plan(event)
    instants = (begin, end, plan['dtstart'], plan['first_end'], plan['second_begin'], plan['second_end'])
    for key, pinned in pinned_zones.items():
        named = ZoneInfo(key)
        for instant in instants:
            actual = datetime.fromtimestamp(instant / 1000, named)
            expected = datetime.fromtimestamp(instant / 1000, pinned)
            need(actual.isoformat() == expected.isoformat() and actual.utcoffset() == timedelta(hours=0 if key == 'GMT' else 8), 'HOST_NAMED_AND_PINNED_TIMEZONE_DISAGREE:' + key)
    return {'verified': True, 'ui_and_store_timezone': TARGET_ZONE, 'host_computation_timezone': HOST_TARGET_ZONE, 'timezone_evidence_sha256': TZDATA_EVIDENCE_SHA, 'input_event': event, 'tzfiles': files, 'checked_instants_utc_ms': list(instants), 'plan': plan}

class Model:

    def __init__(self, session, record):
        self.s, self.record = (session, record)
        self.birth = None
        self.calendar = None
        self.event_id = None
        self.sequence = 0
        self.series = None
        self.series_snapshot = None
        self.single_snapshot = None

    def read(self, label):
        self.s.guard()
        fd = self.s.target.open_root(DB, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            info, mapped_owner = self.s.c.mapped_file_info(self.s.flow.view, fd, 10017)
            need(stat.S_ISREG(info.st_mode) and info.st_uid == mapped_owner[0], 'CALENDAR_DB_IDENTITY')
            birth = fp(info)
        finally:
            os.close(fd)
        if self.birth is None:
            self.birth = birth
        need(birth == self.birth, 'CALENDAR_DATABASE_REPLACED')
        sql = observation_sql()
        args = ['/system/bin/env', '-i'] + [k + '=' + self.s.environment[k] for k in sorted(self.s.environment)]
        args += ['/system/bin/timeout', '-k', '2', '10', '/system/bin/sqlite3', '-readonly', '-json', DB, sql]
        self.sequence += 1
        reply = self.s.root_query('calendar-owned-read', args, 14)
        need(reply['rc'] == 0 and reply['joined'] and (not reply['timed_out']), 'OWNED_PROVIDER_READ_FAILED')
        outer = json.loads(reply['stdout'])
        need(len(outer) == 1 and set(outer[0]) == {'payload'}, 'PROVIDER_READ_SHAPE')
        value = json.loads(outer[0]['payload'])
        validate_projection(value)
        fd = self.s.target.open_root(DB, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            need(fp(os.fstat(fd)) == self.birth, 'DB_CHANGED_DURING_READ')
        finally:
            os.close(fd)
        self.s.guard()
        self.record('owned-read-' + label, {'db_identity': self.birth, 'value': value})
        return value

    @staticmethod
    def require_empty(value):
        need(not value['calendars'] and (not value['events']) and all((n == 0 for n in value['counts'].values())), 'ZERO_PROVIDER_BASELINE_REQUIRED')

    def bind_calendar(self, value):
        need(len(value['calendars']) == 1, 'ONE_UI_CREATED_LOCAL_CALENDAR_REQUIRED')
        row = value['calendars'][0]
        need(set(row) == set(CALENDAR_COLUMNS) and type(row['_id']) is int and (row['_id'] > 0), 'CALENDAR_ROW_SCHEMA')
        need(row['account_name'] == row['ownerAccount'] == ACCOUNT and row['account_type'] == 'LOCAL' and (row['calendar_displayName'] == CALENDAR_LABEL) and re.fullmatch('droidloom-local-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', row['name']) and (row['calendar_access_level'] == 700) and (row['visible'] == row['sync_events'] == 1), 'LOCAL_CALENDAR_OWNER_DIFFERS')
        if self.calendar is None:
            self.calendar = dict(row)
        need(row == self.calendar, 'OWNED_CALENDAR_IDENTITY_CHANGED')
        return row

    def require_no_event(self, value):
        self.bind_calendar(value)
        need(not value['events'] and value['counts'] == dict.fromkeys(TABLES, 0) | {'Calendars': 1}, 'OWNED_EVENT_OR_CHILD_ROWS_REMAIN')

    def require_event(self, value, title, begin, end):
        self.bind_calendar(value)
        need(len(value['events']) == 1, 'ONE_COMMITTED_UI_EVENT_REQUIRED')
        event = value['events'][0]
        need(set(event) == set(EVENT_COLUMNS) and type(event['_id']) is int and (event['_id'] > 0) and (event['calendar_id'] == self.calendar['_id']) and (event['title'] == title) and (event['dtstart'] == begin) and (event['dtend'] == end) and (event['allDay'] == 0) and (event['deleted'] == 0) and (event['_sync_id'] is None) and (event['original_id'] is None) and (event['hasAlarm'] == 0) and (event['eventLocation'] in (None, '')) and (event['description'] in (None, '')) and all((event[k] in (None, '') for k in ('duration', 'rrule', 'rdate', 'exrule', 'exdate'))), 'EXACT_OWNED_SINGLE_EVENT_DIFFERS')
        need(all((value['counts'][k] == 0 for k in ('Reminders', 'Attendees', 'CalendarAlerts', 'ExtendedProperties'))) and value['counts']['Instances'] <= 1 and (value['counts']['EventsRawTimes'] <= 1), 'UNEXPECTED_EVENT_CHILD_ROWS')
        if self.event_id is None:
            self.event_id = event['_id']
        need(event['_id'] == self.event_id, 'UI_EVENT_ID_CHANGED')
        if self.single_snapshot is None:
            self.single_snapshot = dict(event)
        need(event == self.single_snapshot, 'ORIGINAL_EVENT_PROJECTION_CHANGED_BEFORE_SERIES_SAVE')
        return event

    def require_series(self, value):
        self.bind_calendar(value)
        need(self.series is not None and len(value['events']) == 1, 'ONE_PLANNED_OWNED_SERIES_REQUIRED')
        row = value['events'][0]
        plan = self.series
        need(set(row) == set(EVENT_COLUMNS) and row['_id'] == self.event_id and (row['calendar_id'] == self.calendar['_id']) and (row['title'] == EDITED) and (row['dtstart'] == plan['dtstart']) and (row['dtend'] is None) and (row['duration'] == plan['duration']) and (row['eventTimezone'] == plan['timezone']) and (row['rrule'] == plan['rrule']) and (row['allDay'] == row['deleted'] == row['hasAlarm'] == 0) and (row['_sync_id'] is None) and (row['original_id'] is None) and (self.single_snapshot is not None) and (row['eventLocation'] == self.single_snapshot['eventLocation']) and (row['description'] == self.single_snapshot['description']) and all((row[k] in (None, '') for k in ('rdate', 'exrule', 'exdate'))), 'EXACT_EDITED_SERIES_DATES_TIMEZONE_OR_RECURRENCE_DIFFERS')
        need(all((value['counts'][k] == 0 for k in ('Reminders', 'Attendees', 'CalendarAlerts', 'ExtendedProperties'))) and value['counts']['EventsRawTimes'] <= 1 and (value['counts']['Instances'] <= 4096), 'UNEXPECTED_SERIES_CHILD_ROWS')
        if self.series_snapshot is None:
            self.series_snapshot = dict(row)
        need(row == self.series_snapshot, 'SERIES_ROW_CHANGED_AFTER_FIRST_VERIFIED_SAVE')
        return row

    def second_occurrence(self):
        need(self.series_snapshot is not None, 'VERIFIED_SAME_ID_SERIES_REQUIRED')
        plan = self.series
        begin, end = (plan['second_begin'], plan['second_end'])
        uri = 'content://com.android.calendar/instances/when/' + str(begin) + '/' + str(begin + 1)
        where = 'event_id=' + str(self.event_id) + ' AND begin=' + str(begin) + ' AND end=' + str(end)
        argv = ['/system/bin/content', 'query', '--user', '0', '--uri', uri, '--projection', 'event_id:begin:end', '--where', where]
        self.record('second-occurrence-query', {'argv': argv, 'event_id': self.event_id, 'normal_provider_instance_cache_may_expand': True, 'event_or_reminder_write': False})
        raw = self.s.android(argv, 20).decode('utf-8', 'strict')
        expected = 'Row: 0 event_id=' + str(self.event_id) + ', begin=' + str(begin) + ', end=' + str(end) + '\n'
        self.record('second-occurrence-readback', {'raw': raw, 'expected': expected})
        need(raw == expected, 'EXACT_SECOND_PROVIDER_OCCURRENCE_NOT_OBSERVED')
        after = self.read('after-instance-expansion')
        self.require_series(after)
        need(any((row['event_id'] == self.event_id and row['begin'] == begin and (row['end'] == end) for row in after['owned_instances'])), 'SECOND_INSTANCE_NOT_IN_PHYSICAL_OWNED_ROWS')
        return {'event_id': self.event_id, 'begin': begin, 'end': end, 'provider': after, 'series_row_unchanged': True, 'event_or_reminder_write': False}

    def deletion_request(self):
        need(self.calendar is not None, 'NO_BOUND_OWNED_CALENDAR')
        row = self.calendar
        fields = ('_id', 'account_name', 'account_type', 'name', 'calendar_displayName', 'ownerAccount')
        where = ' AND '.join((k + '=' + quote(row[k]) for k in fields))
        where += ' AND NOT EXISTS (SELECT 1 FROM Events WHERE calendar_id=' + str(row['_id']) + ')'
        uri = 'content://com.android.calendar/calendars?' + urlencode({'caller_is_syncadapter': 'true', 'account_name': ACCOUNT, 'account_type': 'LOCAL'}, quote_via=url_quote)
        return (uri, where)
