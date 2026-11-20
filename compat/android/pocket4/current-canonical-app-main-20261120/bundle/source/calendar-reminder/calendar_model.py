"""Original reminder model, lexically bound to one fresh Scope nonce."""
from pathlib import Path
import hashlib, json, os, re, stat, types
from datetime import datetime, timezone
from urllib.parse import urlencode, quote as url_quote

def bind(nonce):
    if not isinstance(nonce, str) or re.fullmatch('[0-9a-f]{32}', nonce) is None:
        raise RuntimeError('EXACT_NEW_REMINDER_SCOPE_NONCE_REQUIRED')
    RUN = 'calendar-reminder22-' + nonce
    CALENDAR_LABEL = 'Pocket4 Calendar QA ' + RUN
    TITLE = 'Pocket4 Calendar reminder ' + RUN
    EDITED = TITLE
    UNSAVED = TITLE + ' Not saved'
    ACCOUNT = 'Droidloom local calendars'
    DB = '/data/user/0/com.android.providers.calendar/databases/calendar.db'
    TABLES = ('Calendars', 'Events', 'Reminders', 'Attendees', 'Instances', 'CalendarAlerts', 'EventsRawTimes', 'ExtendedProperties')
    CALENDAR_COLUMNS = ('_id', 'account_name', 'account_type', 'name', 'calendar_displayName', 'ownerAccount', 'calendar_access_level', 'visible', 'sync_events', 'calendar_timezone')
    EVENT_COLUMNS = ('_id', 'calendar_id', 'title', 'dtstart', 'dtend', 'duration', 'eventTimezone', 'allDay', 'rrule', 'rdate', 'exrule', 'exdate', 'hasAlarm', 'deleted', '_sync_id', 'original_id', 'eventLocation', 'description')
    INSTANCE_COLUMNS = ('_id', 'event_id', 'begin', 'end')
    REMINDER_COLUMNS = ('_id', 'event_id', 'minutes', 'method')
    ALERT_COLUMNS = ('_id', 'event_id', 'begin', 'end', 'alarmTime', 'creationTime', 'receivedTime', 'notifyTime', 'minutes', 'state')
    CHILDREN = ('Reminders', 'Attendees', 'Instances', 'CalendarAlerts', 'EventsRawTimes', 'ExtendedProperties')

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
        children = 'json_object(' + ','.join((quote(t) + ',(SELECT COUNT(*) FROM ' + t + ' WHERE event_id IS NULL OR event_id NOT IN (' + event_ids + '))' for t in CHILDREN)) + ')'
        counts = 'json_object(' + ','.join((quote(t) + ',(SELECT COUNT(*) FROM ' + t + ')' for t in TABLES)) + ')'
        return "PRAGMA query_only=ON;BEGIN;SELECT json_object('counts'," + counts + ",'calendars',json(" + json_rows('Calendars', CALENDAR_COLUMNS, where) + ')' + ",'events',json(" + json_rows('Events', EVENT_COLUMNS, event_where) + ')' + ",'owned_instances',json(" + json_rows('Instances', INSTANCE_COLUMNS, 'event_id IN (' + event_ids + ')', 'begin,end,_id') + ')' + ",'owned_reminders',json(" + json_rows('Reminders', REMINDER_COLUMNS, 'event_id IN (' + event_ids + ')') + ')' + ",'owned_alerts',json(" + json_rows('CalendarAlerts', ALERT_COLUMNS, 'event_id IN (' + event_ids + ')') + ')' + ",'foreign_children'," + children + ') AS payload;ROLLBACK;'

    def validate_projection(value):
        need(set(value) == {'counts', 'calendars', 'events', 'owned_instances', 'owned_reminders', 'owned_alerts', 'foreign_children'} and set(value['counts']) == set(TABLES), 'PROVIDER_RECORD_SHAPE')
        need(all((type(n) is int and n >= 0 for n in value['counts'].values())), 'PROVIDER_COUNTS_INVALID')
        for key in ('calendars', 'events', 'owned_instances', 'owned_reminders', 'owned_alerts'):
            need(isinstance(value[key], list) and len(value[key]) <= 1, 'ONE_OWNED_OBJECT_MAX:' + key)
        for key, table in (('calendars', 'Calendars'), ('events', 'Events'), ('owned_instances', 'Instances'), ('owned_reminders', 'Reminders'), ('owned_alerts', 'CalendarAlerts')):
            need(value['counts'][table] == len(value[key]), 'FOREIGN_OR_MULTIPLE_PROVIDER_ROWS:' + table)
        need(set(value['foreign_children']) == set(CHILDREN) and all((type(n) is int and n == 0 for n in value['foreign_children'].values())), 'FOREIGN_DERIVED_ROWS_APPEARED')
        for key, columns in (('owned_instances', INSTANCE_COLUMNS), ('owned_reminders', REMINDER_COLUMNS), ('owned_alerts', ALERT_COLUMNS)):
            need(all((set(row) == set(columns) and all((type(x) is int for x in row.values())) and (row['_id'] > 0) and (row['event_id'] > 0) for row in value[key])), 'OWNED_CHILD_ROW_SHAPE:' + key)
        need(value['counts']['Attendees'] == value['counts']['ExtendedProperties'] == 0 and value['counts']['EventsRawTimes'] <= 1, 'UNEXPECTED_REMINDER_CHILDREN')
        return value

    def reminder_plan(guest_seconds):
        need(type(guest_seconds) is int and guest_seconds > 0, 'BOUND_GUEST_SECONDS_REQUIRED')
        begin = (guest_seconds + 240 + 59) // 60 * 60000
        end = begin + 15 * 60000
        need(240000 <= begin - guest_seconds * 1000 < 300000, 'REMINDER_LEAD_BOUND')
        return {'dtstart': begin, 'dtend': end, 'timezone': 'GMT', 'reminder_minutes': 0, 'natural_due_ms': begin, 'latest_due_readback_ms': begin + 60000, 'date_utc': datetime.fromtimestamp(begin / 1000, timezone.utc).strftime('%Y-%m-%d'), 'timing_source': 'guest clock checked by existing diagnostics; UTC arithmetic only'}

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
            self.reminder_identity = None
            self.alert_identity = None

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
            need(row['account_name'] == row['ownerAccount'] == ACCOUNT and row['account_type'] == 'LOCAL' and (row['calendar_displayName'] == CALENDAR_LABEL) and re.fullmatch('droidloom-local-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', row['name']) and (row['calendar_access_level'] == 700) and (row['visible'] == row['sync_events'] == 1) and (row['calendar_timezone'] in ('GMT', 'UTC')), 'LOCAL_CALENDAR_OWNER_DIFFERS')
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
            need(set(event) == set(EVENT_COLUMNS) and type(event['_id']) is int and (event['_id'] > 0) and (event['calendar_id'] == self.calendar['_id']) and (event['title'] == title) and (event['dtstart'] == begin) and (event['dtend'] == end) and (event['allDay'] == 0) and (event['deleted'] == 0) and (event['_sync_id'] is None) and (event['original_id'] is None) and (event['hasAlarm'] == 1) and (event['eventTimezone'] in ('GMT', 'UTC')) and (event['eventLocation'] in (None, '')) and (event['description'] in (None, '')) and all((event[k] in (None, '') for k in ('duration', 'rrule', 'rdate', 'exrule', 'exdate'))), 'EXACT_OWNED_REMINDER_EVENT_DIFFERS')
            need(len(value['owned_reminders']) == 1, 'ONE_UI_SAVED_REMINDER_REQUIRED')
            reminder = value['owned_reminders'][0]
            need(reminder['event_id'] == event['_id'] and reminder['minutes'] == 0 and (reminder['method'] == 1), 'EXACT_AT_START_ALERT_REMINDER_REQUIRED')
            if self.reminder_identity is None:
                self.reminder_identity = dict(reminder)
            need(reminder == self.reminder_identity, 'UI_REMINDER_ROW_CHANGED')
            if self.event_id is None:
                self.event_id = event['_id']
            need(event['_id'] == self.event_id, 'UI_EVENT_ID_CHANGED')
            if self.single_snapshot is None:
                self.single_snapshot = dict(event)
            need(event == self.single_snapshot, 'OWNED_EVENT_CHANGED_WHILE_WAITING')
            for item in value['owned_instances']:
                need(item['event_id'] == self.event_id and item['begin'] == begin and (item['end'] == end), 'EXACT_INSTANCE_REQUIRED')
            for item in value['owned_alerts']:
                need(item['event_id'] == self.event_id and item['begin'] == begin and (item['end'] == end) and (item['alarmTime'] == begin) and (item['minutes'] == 0) and (item['creationTime'] > 0) and (item['state'] in (0, 1, 2)) and (item['receivedTime'] >= 0) and (item['notifyTime'] >= 0), 'EXACT_PROVIDER_ALERT_TUPLE_REQUIRED')
                identity = {k: item[k] for k in ('_id', 'event_id', 'begin', 'end', 'alarmTime', 'creationTime', 'minutes')}
                if self.alert_identity is None:
                    self.alert_identity = identity
                need(identity == self.alert_identity, 'OWNED_ALERT_IDENTITY_CHANGED')
            need(self.alert_identity is None or len(value['owned_alerts']) == 1, 'OWNED_ALERT_DISAPPEARED_BEFORE_UI_DELETE')
            return event

        def require_fired(self, value, begin, end):
            self.require_event(value, TITLE, begin, end)
            need(len(value['owned_alerts']) == 1, 'ONE_NATURALLY_DELIVERED_ALERT_REQUIRED')
            row = value['owned_alerts'][0]
            need(row['state'] == 1 and row['receivedTime'] >= row['alarmTime'], 'OWNED_REMINDER_NOT_FIRED')
            return row

        def deletion_request(self):
            need(self.calendar is not None, 'NO_BOUND_OWNED_CALENDAR')
            row = self.calendar
            fields = ('_id', 'account_name', 'account_type', 'name', 'calendar_displayName', 'ownerAccount')
            where = ' AND '.join((k + '=' + quote(row[k]) for k in fields))
            where += ' AND NOT EXISTS (SELECT 1 FROM Events WHERE calendar_id=' + str(row['_id']) + ')'
            uri = 'content://com.android.calendar/calendars?' + urlencode({'caller_is_syncadapter': 'true', 'account_name': ACCOUNT, 'account_type': 'LOCAL'}, quote_via=url_quote)
            return (uri, where)
    return types.SimpleNamespace(RUN=RUN, CALENDAR_LABEL=CALENDAR_LABEL, TITLE=TITLE, EDITED=EDITED, UNSAVED=UNSAVED, ACCOUNT=ACCOUNT, DB=DB, TABLES=TABLES, CALENDAR_COLUMNS=CALENDAR_COLUMNS, EVENT_COLUMNS=EVENT_COLUMNS, INSTANCE_COLUMNS=INSTANCE_COLUMNS, REMINDER_COLUMNS=REMINDER_COLUMNS, ALERT_COLUMNS=ALERT_COLUMNS, CHILDREN=CHILDREN, need=need, quote=quote, fp=fp, owner_where=owner_where, json_rows=json_rows, observation_sql=observation_sql, validate_projection=validate_projection, reminder_plan=reminder_plan, Model=Model)
