"""Independent new-Main component; no historical Session, Main or execute entry."""
from pathlib import Path
from datetime import datetime, timezone
import argparse, hashlib, json, os, re, signal, stat, sys, time, types
PINS = {}
TASK_PROOF_SHA = '9cb008b7050d3bb0b8da2221140c02b39ebde973833b5ee24039932e266e90a5'
PACKAGE = 'org.droidloom.qa.calendar.r12.n11d95b10e4c4545d'
RUN = 'pocket4-calendar-r12-11d95b10e4c4545d'
GRANTS = ('android.permission.READ_CALENDAR', 'android.permission.WRITE_CALENDAR')
CALENDAR = 'com.android.calendar'
CALENDAR_SHA = 'c8a9d40dbfb3c975748e7c0520515316a5ef573414193e3128efa9ed400665e1'
MAIN = CALENDAR + '.AllInOneActivity'
EDITOR = CALENDAR + '.event.EditEventActivity'
EDITOR_ALIAS = CALENDAR + '.EditEventActivity'
INFO = CALENDAR + '.EventInfoActivity'
ROUTES = {(CALENDAR, value) for value in (MAIN, EDITOR, EDITOR_ALIAS, INFO)}
TITLE = 'Pocket4 event calendar-recurrence21-6c978e4da120b35f'
EDITED = 'Pocket4 event calendar-recurrence21-6c978e4da120b35f Edited'
DB = '/data/user/0/com.android.providers.calendar/databases/calendar.db'
TABLES = ('Calendars', 'Events', 'Reminders', 'Attendees', 'Instances', 'CalendarAlerts', 'EventsRawTimes', 'ExtendedProperties')
LEASE_SECONDS = 720
CLEANUP_SECONDS = 120
NODE_FIELDS = ('resource-id', 'text', 'content-desc', 'hint', 'class', 'enabled', 'clickable', 'editable', 'password', 'bounds_array', 'selected', 'checked', 'focused', 'focusable', 'scrollable', 'visible', 'window_id')

def need(value, reason):
    if not value:
        raise RuntimeError(reason)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def stamp():
    return datetime.now(timezone.utc).isoformat()

def fp(s):
    return {k: getattr(s, k) for k in ('st_dev', 'st_ino', 'st_uid', 'st_gid', 'st_mode', 'st_nlink')}

def permission_rows(raw, package):
    sections = re.findall('^Packages:\\n(.*?)(?=^\\S|\\Z)', raw, re.M | re.S)
    need(len(sections) == 1 and re.findall('^  Package \\[([^]]+)\\]', sections[0], re.M) == [package], 'PERMISSION_PACKAGE_SECTION')
    rows = sorted((line.strip() for line in sections[0].splitlines() if re.search('android\\.permission\\.[A-Z_]+: granted=', line)))
    need(rows, 'NO_PERMISSION_ROWS')
    return rows

def permission_granted(rows, name):
    matches = [re.match(re.escape(name) + ': granted=(true|false)(?:,|$)', row) for row in rows]
    found = [m[1] for m in matches if m]
    need(len(found) == 1, 'PERMISSION_STATE_NOT_UNIQUE:' + name)
    return found[0] == 'true'

def ui_class(base):

    class CalendarUI(base.Adapter):

        def check_tasks(self, label, admit=False):
            roots, tasks = self.stacks(label)
            need(self.baseline is not None and tasks == self.baseline | set(self.owned), 'CALENDAR_TASK_SET_CHANGED')
            need(len(self.owned) <= 1, 'SINGLE_OWNED_CALENDAR_TASK_REQUIRED')
            for task, owner in self.owned.items():
                need(base.leaf(roots, task), 'OWNED_CALENDAR_NOT_SINGLE_LEAF')
                component = roots[task]['children'][0]['component']
                package, activity = component.split('/', 1)
                observed = (package, base.expand(package, activity))
                need(observed in ROUTES, 'OWNED_TASK_COMPONENT_OUTSIDE_CALENDAR_ROUTES')
                owner['component'] = observed
            return (roots, tasks)

        def launch(self):
            self.budget()
            roots, tasks = self.stacks('before-calendar-launch')
            if self.baseline is None:
                need(not any((c['component'].split('/')[0] in (CALENDAR, PACKAGE) for r in roots.values() for c in r['children'])), 'PREEXISTING_TARGET_TASK_PRESERVED')
                self.baseline = tasks
            need(tasks == self.baseline and (not self.owned) and (not self.pending), 'PREVIOUS_OWNED_TASK_NOT_CLOSED')
            need(self.launches < 2, 'TWO_NATIVE_LAUNCHES_MAX')
            argv = [*self.tx.ALEX_PREFIX, 'launch', CALENDAR, '--component', CALENDAR + '/.AllInOneActivity', '--json']
            token = 'launch-' + str(self.launches + 1)
            self.record(token + '-intent', {'argv': argv, 'automatic_retry': False})
            self.actions += 1
            self.launches += 1
            self.pending[token] = {'input_acknowledged': False}
            reply = self.s.run_host(token, argv, 45)
            need(reply['rc'] == 0 and reply['joined'] and (not reply['timed_out']), 'NATIVE_LAUNCH_UNKNOWN')
            value = json.loads(reply['stdout'])
            self.record(token + '-reply', value)
            need(value.get('ok') is True and value.get('state') == 'running' and (value.get('host_pid') == self.tx.MAIN_HOST) and (value.get('outcome_unknown') is not True), 'NATIVE_LAUNCH_NOT_VERIFIED')
            match = re.fullmatch('object=(\\d+) composer_display=(\\d+) android_display=(\\d+) task=(\\d+)', value.get('launch', ''))
            need(match and int(match[3]) == 0, 'NATIVE_LAUNCH_TASK_UNKNOWN')
            task = int(match[4])
            need(task not in roots and task not in tasks, 'TASK_PREEXISTED')
            self.owned[task] = {'component': (CALENDAR, MAIN), 'source': token}
            self.check_tasks('after-calendar-launch')
            del self.pending[token]
    return CalendarUI

def make_flow(evidence_root, ui_factory, diagnostic_factory, emit):

    class Flow:

        def __init__(self, session, tx, base, doc, diag):
            self.s, self.tx, self.doc, self.diag = (session, tx, doc, diag)
            self.ui = ui_factory(session, tx, evidence_root / 'ui')
            self.diagnostics = diagnostic_factory(session, tx, evidence_root / 'diagnostics')
            self.installed = self.staged = self.lease = self.event_id = self.db_birth = None
            self.install_pending = self.uninstall_pending = False
            self.helper_pending = {}
            self.helper_receipts = {}
            self.grant_pending = None
            self.helper_sequence = self.view_sequence = self.intent_calls = 0
            self.view_id = None
            self.obs = None
            self.phase = 'PREFLIGHT'
            self.roles = {}
            self.seen = set()
            self.result = {'schema': 'pocket4-owned-calendar-ui-flow-v1', 'state': 'FAILED', 'run_id': RUN, 'calendar_package': CALENDAR, 'temporary_package': PACKAGE, 'started_utc': stamp(), 'whole_app_production_ready': False, 'automatic_retry': False, 'gates': {}, 'lease_seconds': LEASE_SECONDS, 'cleanup_seconds': CLEANUP_SECONDS, 'helper_event_writes': 0, 'account_operations': 0, 'existing_app_permission_changes': 0, 'source_pins': PINS, 'helper_requests': [], 'ui_roles': []}

        def record(self, label, value):
            self.ui.record(label, value)

        def calendar_identity(self):
            value = self.doc.identity(self.s, CALENDAR, CALENDAR_SHA, 10061, 37)
            value['permissions'] = permission_rows(self.s.android(['/system/bin/dumpsys', 'package', CALENDAR], 12).decode(), CALENDAR)
            need(all((permission_granted(value['permissions'], x) for x in GRANTS)), 'EXISTING_CALENDAR_GRANTS_NOT_PRESENT')
            return value

        def counts(self, label):
            self.s.guard()
            fd = self.s.target.open_root(DB, os.O_RDONLY | os.O_NOFOLLOW)
            try:
                info = os.fstat(fd)
                need(stat.S_ISREG(info.st_mode) and info.st_uid == 10017, 'CALENDAR_DB_IDENTITY')
                before = fp(info)
                if self.db_birth is None:
                    self.db_birth = before
                need(before == self.db_birth, 'CALENDAR_DB_REPLACED')
            finally:
                os.close(fd)
            sql = ' UNION ALL '.join(("SELECT '" + name + "' AS name,COUNT(*) AS count FROM " + name for name in TABLES))
            argv = ['/system/bin/env', '-i'] + [k + '=' + self.s.environment[k] for k in sorted(self.s.environment)]
            argv += ['/system/bin/timeout', '-k', '2', '10', '/system/bin/sqlite3', '-readonly', '-json', DB, 'PRAGMA query_only=ON;BEGIN;' + sql + ';ROLLBACK;']
            reply = self.s.root_query('calendar-counts-' + label, argv, 14)
            need(reply['rc'] == 0 and reply['joined'] and (not reply['timed_out']), 'PHYSICAL_CALENDAR_COUNT_QUERY_FAILED')
            rows = json.loads(reply['stdout'])
            need(len(rows) == len(TABLES), 'PHYSICAL_COUNT_SHAPE')
            value = {r['name']: r['count'] for r in rows}
            need(set(value) == set(TABLES) and all((type(n) is int and n >= 0 for n in value.values())), 'PHYSICAL_COUNTS_INVALID')
            fd = self.s.target.open_root(DB, os.O_RDONLY | os.O_NOFOLLOW)
            try:
                need(fp(os.fstat(fd)) == before, 'CALENDAR_DB_CHANGED_DURING_QUERY')
            finally:
                os.close(fd)
            self.record('physical-counts-' + label, {'counts': value, 'db_identity': before, 'contents_read': False})
            self.s.guard()
            return value

        def observe(self, label):
            self.obs = self.ui.observe(label, ROUTES)
            self.view_sequence += 1
            self.view_id = 'view-' + str(self.view_sequence)
            emit({'type': 'observation', 'view': self.view_id, 'phase': self.phase, 'focus': self.obs['focus'], 'nodes': [{k: n.get(k) for k in NODE_FIELDS if k in n} for n in self.obs['nodes']], 'screenshot': self.obs['screenshot'], 'ui_pending': self.ui.pending, 'helper_pending': self.helper_pending, 'event_id': self.event_id})
            return self.obs

        def route(self, operation):
            need(operation in ('insert', 'view') and (not self.ui.pending) and (not self.helper_pending), 'ROUTE_PENDING_OR_SCOPE')
            self.ui.check_tasks('before-' + operation + '-route')
            need(len(self.ui.owned) == 1, 'ONE_ROUTE_TASK')
            task = next(iter(self.ui.owned))
            argv = ['/system/bin/am', 'start-activity', '-W', '--user', '0', '--display', '0', '--task', str(task), '--activity-clear-top']
            if operation == 'insert':
                need(self.intent_calls == 0 and self.lease is not None, 'INSERT_INTENT_ONCE')
                argv += ['-n', CALENDAR + '/.EditEventActivity', '-a', 'android.intent.action.INSERT', '-d', 'content://com.android.calendar/events', '-t', 'vnd.android.cursor.dir/event', '--es', 'title', TITLE, '--el', 'beginTime', str(self.lease['dtstart']), '--el', 'endTime', str(self.lease['dtend']), '--ez', 'allDay', 'false', '--es', 'eventTimezone', 'UTC']
            else:
                need(type(self.event_id) is int and self.event_id > 0, 'EXACT_BOUND_EVENT_REQUIRED')
                argv += ['-n', CALENDAR + '/.EventInfoActivity', '-a', 'android.intent.action.VIEW', '-d', 'content://com.android.calendar/events/' + str(self.event_id), '-t', 'vnd.android.cursor.item/event', '--el', 'beginTime', str(self.lease['dtstart']), '--el', 'endTime', str(self.lease['dtend'])]
            token = 'route-' + operation + '-' + str(self.intent_calls + 1)
            self.record(token + '-intent', {'argv': argv, 'task_option_proof_sha256': TASK_PROOF_SHA, 'automatic_retry': False})
            self.intent_calls += 1
            self.ui.pending[token] = {'input_acknowledged': False, 'kind': 'intent'}
            raw = self.s.android(argv, 35).decode()
            self.record(token + '-result', {'raw_stdout': raw})
            need(re.findall('^Status:\\s*(\\S+)', raw, re.M) == ['ok'] and 'Error:' not in raw and ('Exception' not in raw), 'ROUTE_ACK_UNKNOWN_NO_REPLAY')
            self.ui.pending[token]['input_acknowledged'] = True
            observed = self.observe('after-' + token)
            expected = {EDITOR, EDITOR_ALIAS} if operation == 'insert' else {INFO}
            need(observed['focus']['task'] == task and observed['focus']['activity'] in expected, 'ROUTE_RESULT_WRONG_ACTIVITY')
    return Flow
