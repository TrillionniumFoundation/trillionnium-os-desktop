"""Only the original two cases' literal reads and once-owned mutations."""
import base64
import json
import re

CONTACTS_ACCOUNT = "set -o pipefail; /system/bin/dumpsys account | /system/bin/sed -n -e 's/^[[:space:]]*Accounts: \\([0-9][0-9]*\\)[[:space:]]*$/Accounts: \\1/p' -e 's/^[[:space:]]*Account {.*type=\\([^}]*\\)}[[:space:]]*$/AccountType: \\1/p'"


class Policy:
    native_timeout = 45
    def __init__(self, runtime):
        self.r = runtime; self.s = runtime.session; self.c = runtime.c
        self.contact_name_row = None; self.remove_sent = False; self.provider_delete_sent = False

    def admit(self, argv, timeout, mutation, private):
        c, s = self.c, self.s
        c.need(type(argv) is list and argv and all(type(x) is str and x and '\0' not in x for x in argv)
            and type(timeout) in (int, float) and 5 < timeout <= 70 and type(mutation) is bool,
            'ORIGINAL_CASE_TYPED_COMMAND_REQUIRED')
        if private:
            c.need(s.ui_dispatch_admission == (argv, timeout, mutation), 'ONLY_CURRENT_TYPED_BACKEND_CALL')
            return
        if s.ordinary_admission == (argv, timeout, mutation):
            return
        c.need(mutation is False, 'MUTATIONS_REQUIRE_SESSION_ONCE_INTENT_ADMISSION')
        expected_mutation = self.command(argv, timeout)
        c.need(mutation is expected_mutation, 'ORIGINAL_MUTATION_CLASSIFICATION_CHANGED')

    def command(self, argv, timeout):
        c, s, r = self.c, self.s, self.r
        if argv == c.STACKS:
            c.need(timeout in (6, 15), 'ORIGINAL_TASK_READ_TIMEOUT'); return False
        if argv == c.FOREGROUND:
            c.need(timeout == 6, 'ORIGINAL_OWNED_FOCUS_READ_TIMEOUT'); return False
        packages = {x['metadata']['package'] for x in s.identities}
        if len(argv) == 3 and argv[:2] == ['/system/bin/dumpsys', 'package']:
            c.need(argv[2] in packages and timeout == (12 if s.kind == 'calendar_reminder' and argv[2] == r.scope['package'] else 20)
                or s.kind == 'calendar_reminder' and argv[2] == 'com.android.shell' and timeout == 15
                or argv[2] == r.scope['package'] and timeout == 20,
                'ONLY_ORIGINAL_PACKAGE_AND_PERMISSION_READS')
            return False
        if argv[:2] == ['/system/bin/pm', 'path']:
            c.need(timeout == 20 and (len(argv) == 3 and s.kind == 'contacts_search' and argv[2] in packages
                or len(argv) == 5 and argv[2:4] == ['--user', '0'] and argv[4] in packages),
                'ORIGINAL_ACTUAL_PACKAGE_PATH_READ_ONLY')
            return False
        if s.kind == 'contacts_search':
            if argv == ['/system/bin/sh', '-c', CONTACTS_ACCOUNT]:
                c.need(timeout == 20, 'ORIGINAL_ACCOUNT_METADATA_TIMEOUT'); return False
            if self.contacts_query(argv, timeout):
                return False
            if argv[:2] == ['/system/bin/content', 'delete']:
                self.contacts_delete(argv, timeout); return True
        else:
            if argv == ['/system/bin/pm', 'list', 'packages', '-U', '--user', '0', 'com.android.shell']:
                c.need(timeout == 12, 'ORIGINAL_EXISTING_SHELL_UID_READ'); return False
            diagnostics = [(['/system/bin/date', '+%s'], 8),
                (['/system/bin/getprop', 'persist.sys.timezone'], 8),
                (['/system/bin/pm', 'list', 'packages', '-U', '--user', '0'], 15),
                (['/system/bin/dumpsys', 'notification', '--noredact', '--package', 'com.android.calendar'], 12),
                (['/system/bin/dumpsys', 'activity', 'exit-info', 'com.android.calendar'], 15),
                (['/system/bin/logcat', '-b', 'events', '-d', '-v', 'epoch', '-t', '2048'], 15),
                (['/system/bin/logcat', '--uid=10061', '-b', 'crash', '-d', '-v', 'epoch', '-t', '512'], 15)]
            if (argv, timeout) in diagnostics:
                return False
            if self.calendar_query(argv, timeout):
                return False
            if argv[:2] == ['/system/bin/content', 'delete']:
                self.calendar_delete(argv, timeout); return True
            if argv[:2] == ['/system/bin/am', 'start-activity']:
                self.calendar_route(argv, timeout); return True
        if argv[:4] == ['/system/bin/cmd', 'activity', 'stack', 'remove']:
            c.need(len(argv) == 5 and timeout == 15 and re.fullmatch('[1-9][0-9]*', argv[4]),
                   'ORIGINAL_EXACT_TASK_REMOVE')
            selected = r.selected_task(); task = selected['task']
            c.need(int(argv[4]) == task and not self.remove_sent and selected['cleanup_allowed'] is True
                and selected['prelaunch_absent'] is True and s.last_stacks is not None,
                'ONCE_ACTUALLY_NEW_OWNED_TASK_ONLY')
            roots, tasks = s.last_stacks
            c.need(tasks == set(selected['prelaunch_task_ids']) | {task}
                and r.tasks.exact_leaf(roots, task, r.scope['package']), 'FRESH_EXACT_OWNED_LEAF_BEFORE_REMOVE')
            s.consume_original_intent('remove', argv)
            c.write_new(r.root / 'cleanup-attempted.json', {'scope': r.scope_ref, 'phase_lease': r.phase_lease_ref,
                'selected': selected, 'argv': argv, 'automatic_retry': False,
                'Binder_UID_cleanup_verified': False})
            self.remove_sent = True
            return True
        raise RuntimeError('COMMAND_NOT_IN_ORIGINAL_CONTACTS_OR_CALENDAR_CASE')

    def contacts_query(self, argv, timeout):
        c, s = self.c, self.s; m = s.components['contacts_model.py']
        prefix = ['/system/bin/content', 'query', '--user', '0', '--uri']
        if argv[:len(prefix)] != prefix:
            return False
        base = 'content://com.android.contacts/'
        raw = prefix + [base + 'raw_contacts', '--projection', '_id:contact_id:deleted']
        names = prefix + [base + 'data', '--projection', '_id:raw_contact_id:contact_id:mimetype:data1', '--where',
            "mimetype='" + m.NAME_MIME + "' AND (data1='" + m.NAME + "' OR data1='" + m.EDITED + "')"]
        c.need(timeout == 20, 'ORIGINAL_CONTACTS_PROJECTION_TIMEOUT')
        if argv in (raw, names):
            return True
        c.need(self.contact_name_row is not None, 'OWNED_NAME_ROW_MUST_PRECEDE_ACCOUNT_PROJECTION')
        expected = prefix + [base + 'raw_contacts', '--projection',
            '_id:contact_id:account_name:account_type:data_set:deleted', '--where', '_id=' + self.contact_name_row['raw_contact_id']]
        c.need(argv == expected, 'ONLY_ACTUALLY_OBSERVED_OWNED_CONTACT_ACCOUNT_ROW')
        return True

    def observe(self, argv, raw):
        if (self.s.kind == 'contacts_search' and len(argv) >= 8 and argv[0:2] == ['/system/bin/content', 'query']
                and argv[5] == 'content://com.android.contacts/data'):
            m = self.s.components['contacts_model.py']
            rows = m.parse_rows(raw.decode('utf-8', 'strict'), ('_id', 'raw_contact_id', 'contact_id', 'mimetype', 'data1'))
            self.c.need(len(rows) <= 1 and all(re.fullmatch('[1-9][0-9]*', r['raw_contact_id'] or '')
                and r['mimetype'] == m.NAME_MIME and r['data1'] in (m.NAME, m.EDITED) for r in rows),
                'ONE_ACTUAL_OWNED_MARKER_PROJECTION')
            self.contact_name_row = rows[0] if rows else None

    def contacts_delete(self, argv, timeout):
        c, s = self.c, self.s; f = s.case
        c.need(s.phase_name == 'final_cleanup' and f is not None and f.created is not None and f.ownership_journal
            and f.c.pending is None and f.close_pending is None and f.cleanup_dispatched is True
            and f.commit_tag is None and f.effect_pending['kind'] == 'cleanup'
            and f.effect_pending['tag'] == 'exact-owned-fallback' and not self.provider_delete_sent,
            'ORIGINAL_DURABLY_OWNED_CONTACT_FAILURE_CLEANUP_ONLY')
        m = s.components['contacts_model.py']; name = f.created['owned']['name_row']['data1']
        proof = m.validate_owned(f.created, name)
        where = '_id=' + proof['raw_contact_id'] + ' AND contact_id=' + proof['contact_id'] + ' AND account_name IS NULL AND account_type IS NULL AND data_set IS NULL AND deleted=0'
        c.need(argv == ['/system/bin/content', 'delete', '--user', '0', '--uri',
            'content://com.android.contacts/raw_contacts', '--where', where] and timeout == 15,
            'EXACT_ORIGINAL_OWNED_LOCAL_NULL_ACCOUNT_PREDICATE')
        s.consume_original_intent('provider-delete', argv); self.provider_delete_sent = True

    def calendar_query(self, argv, timeout):
        c, s = self.c, self.s
        if argv[:2] != ['/system/bin/content', 'query']:
            return False
        f = s.case; c.need(f is not None, 'ACTUAL_ORIGINAL_CALENDAR_MODEL_REQUIRED')
        m = f.model
        uri, where = m.deletion_request()
        c.need(s.phase_name == 'final_cleanup' and argv == ['/system/bin/content', 'query', '--user', '0',
            '--uri', uri, '--projection', '_id', '--where', where] and timeout == 15,
            'ONLY_EXACT_OWNED_EMPTY_CALENDAR_PREDICATE_QUERY')
        return True

    def calendar_delete(self, argv, timeout):
        c, s = self.c, self.s; f = s.case
        c.need(s.phase_name == 'final_cleanup' and f is not None and not f.ui.owned and not f.ui.pending
            and not f.business_pending and f.cleanup_pending is True and f.cleanup_calls == 1
            and not self.provider_delete_sent and ('deleted_in_calendar_ui' in f.result['gates']
                or f.roles.get('save-create', 0) == 0), 'ORIGINAL_EVENT_FREE_CALENDAR_CLEANUP_GATE')
        uri, where = f.model.deletion_request()
        c.need(argv == ['/system/bin/content', 'delete', '--user', '0', '--uri', uri, '--where', where]
            and timeout == 20, 'EXACT_OWNER_AND_NOT_EXISTS_EVENT_ATOMIC_PREDICATE')
        s.consume_original_intent('provider-delete', argv); self.provider_delete_sent = True

    def calendar_route(self, argv, timeout):
        c, s, r = self.c, self.s, self.r; f = s.case
        c.need(s.phase_name == 'business' and f is not None and not f.helper_pending
            and len(f.ui.owned) == 1 and 1 <= f.intent_calls <= 2 and timeout == 35,
            'ORIGINAL_CALENDAR_OWNED_ROUTE_PHASE')
        task = r.selected_task()['task']; c.need(task in f.ui.owned, 'ROUTE_TASK_NOT_ACTUAL_NEW_CLAIM')
        base = ['/system/bin/am', 'start-activity', '-W', '--user', '0', '--display', '0', '--task', str(task), '--activity-clear-top']
        if f.intent_calls == 1:
            c.need(f.phase == 'CREATING' and f.lease is not None, 'ONE_DECLARED_INSERT_ROUTE')
            expected = base + ['-n', 'com.android.calendar/.EditEventActivity', '-a', 'android.intent.action.INSERT',
                '-d', 'content://com.android.calendar/events', '-t', 'vnd.android.cursor.dir/event',
                '--es', 'title', s.model.TITLE, '--el', 'beginTime', str(f.lease['dtstart']),
                '--el', 'endTime', str(f.lease['dtend']), '--ez', 'allDay', 'false', '--es', 'eventTimezone', 'UTC']
        else:
            c.need(f.phase in ('CREATED', 'DELIVERED') and type(f.event_id) is int and f.event_id > 0,
                   'VERIFIED_SAME_EVENT_DETAIL_ROUTE')
            expected = base + ['-n', 'com.android.calendar/.EventInfoActivity', '-a', 'android.intent.action.VIEW',
                '-d', 'content://com.android.calendar/events/' + str(f.event_id), '-t', 'vnd.android.cursor.item/event',
                '--el', 'beginTime', str(f.lease['dtstart']), '--el', 'endTime', str(f.lease['dtend'])]
        c.need(argv == expected, 'EXACT_CURRENT_ORIGINAL_EVENT_ROUTE_ARGUMENTS')
        s.consume_original_intent('route', argv)


def native_request(c, outer, request, action_used):
    c.need(type(request) is dict and request.get('display') == 0 and request.get('accessibility_mode') == 'none'
        and request.get('expected_package') == outer.get('package', outer.get('expected_package')),
        'EXACT_ORIGINAL_NATIVE_WINDOW_PACKAGE_SCOPE')
    if request.get('op') in ('meta', 'dump'):
        c.need(set(request) == {'op', 'expected_package', 'display', 'accessibility_mode'},
               'ONLY_ORIGINAL_READONLY_NATIVE_FIELDS')
        return False
    c.need(not action_used and outer.get('op') in ('click', 'set-text', 'scroll-forward', 'scroll-backward'),
           'NO_SECOND_OR_UNDECLARED_NATIVE_ACTION')
    expected = {k: v for k, v in outer.items() if k in {'op', 'selector', 'value', 'display', 'accessibility_mode', 'method'}}
    expected['expected_package'] = outer['package']
    c.need(request == expected, 'UNCHANGED_FINAL_BACKEND_NATIVE_PROJECTION_REQUIRED')
    return True


def backend_android(c, outer, argv, timeout, action_used):
    if argv == ['/system/bin/screencap', '-p']:
        c.need(timeout == 20, 'ORIGINAL_SCREENSHOT_TIMEOUT'); return False, True
    if (len(argv) == 8 and argv[:6] == ['/system/bin/am', 'instrument', '-w', '-r', '-e', 'request']
            and argv[-1] == 'local.pocket4.actions.v2/.ActionRunner'):
        c.need(timeout == 70, 'ORIGINAL_NATIVE_INSTRUMENTATION_TIMEOUT')
        raw = base64.b64decode(argv[6], validate=True); c.need(len(raw) <= 65536, 'BOUNDED_ORIGINAL_NATIVE_REQUEST')
        request = c.parse(raw)
        c.need(base64.b64encode(json.dumps(request, ensure_ascii=True, separators=(',', ':')).encode()).decode() == argv[6],
               'ACTUAL_UNCHANGED_NATIVE_REQUEST_ENCODING')
        return native_request(c, outer, request, action_used), False
    if outer.get('op') == 'snapshot-tap':
        point = outer.get('coords')
        c.need(type(point) is list and len(point) == 2 and all(type(x) is int for x in point)
            and outer.get('input_source') == 'touch' and not action_used and timeout == 30
            and argv == ['/system/bin/input', '-d', '0', 'tap', str(point[0]), str(point[1])],
            'ONLY_ORIGINAL_PIXEL_BOUND_TOUCH_COORDINATES')
        return True, False
    raise RuntimeError('NO_OTHER_BACKEND_ANDROID_COMMAND')
