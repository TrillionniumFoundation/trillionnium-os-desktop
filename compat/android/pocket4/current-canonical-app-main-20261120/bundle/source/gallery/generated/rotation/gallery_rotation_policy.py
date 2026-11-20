"""Literal original Gallery rotation operations and exact once-only effects.

The source-owned state machine remains the authority for business transitions.
This layer independently admits only the original two-image/helper namespace,
the current owned tasks, and the final backend's actual wire commands.
"""
import base64
import json
import re

GALLERY = 'com.android.gallery3d'
PACKAGE = 'org.droidloom.qa.galleryrotation.r12.nd24b61ed8f7c9a03'
RUN = 'd24b61ed8f7c9a03'
NATIVE = 'local.pocket4.actions.v2'
PACKAGES = {GALLERY, PACKAGE, NATIVE}
STAGE = '/data/local/tmp/pocket4-owned-galleryrotation-' + RUN + '/owned-rotation.apk'


class Policy:
    def __init__(self, session):
        self.s = session; self.c = session.c
        self.install_sent = self.uninstall_sent = False
        self.helper_sent = set(); self.remove_sent = set(); self.directory_sent = set()

    def command(self, argv, timeout):
        s, c, f = self.s, self.c, self.s.case
        c.need(type(argv) is list and argv and all(type(x) is str and x and '\0' not in x for x in argv)
            and type(timeout) in (int, float) and 5 < timeout <= 70, 'BOUNDED_GALLERY_LOGICAL_COMMAND')
        if argv == ['/system/bin/cmd', 'activity', 'stack', 'list']:
            c.need(timeout in (6, 12, 15), 'ORIGINAL_GALLERY_TASK_READ_TIMEOUT'); return False
        if argv == ['/system/bin/dumpsys', 'window', 'displays']:
            c.need(timeout == 6, 'ORIGINAL_GALLERY_FOCUS_READ_TIMEOUT'); return False
        if len(argv) == 3 and argv[:2] == ['/system/bin/dumpsys', 'package']:
            c.need(argv[2] in PACKAGES and timeout in (15, 20), 'ORIGINAL_GALLERY_PACKAGE_READ'); return False
        if argv[:2] == ['/system/bin/pm', 'path']:
            c.need(len(argv) == 5 and argv[2:4] == ['--user', '0'] and argv[4] in PACKAGES
                and timeout in (12, 20), 'ORIGINAL_GALLERY_APK_PATH_READ'); return False
        reads = [
            (['/system/bin/pm', 'list', 'packages', '-u', '-U', PACKAGE], 20),
            (['/system/bin/pm', 'list', 'packages', '-U', '--user', '0'], 15),
            (['/system/bin/dumpsys', 'activity', 'package', PACKAGE, 'permissions'], 20),
            (['/system/bin/dumpsys', 'activity', 'activities', GALLERY], 12),
            (['/system/bin/date', '+%s'], 8),
            (['/system/bin/logcat', '-b', 'events', '-d', '-v', 'epoch', '-t', '2048'], 15),
            (['/system/bin/dumpsys', 'activity', 'exit-info', GALLERY], 15),
            (['/system/bin/logcat', '--uid=' + str(s.gallery_uid), '-b', 'crash', '-d', '-v', 'epoch', '-t', '512'], 15),
        ]
        if (argv, timeout) in reads:
            return False
        if argv == ['/system/bin/pm', 'help']:
            c.need(timeout == 15 and s.pm_help_reading and s.pm_help_ref is None,
                'ONE_CURRENT_MAIN_PM_FLAG_OBSERVATION'); return False
        c.need(f is not None, 'ORIGINAL_BOUND_GALLERY_FLOW_REQUIRED')
        if argv == ['/system/bin/pm', 'install', '-R', '-t', '--user', '0', STAGE]:
            c.need(timeout == 60 and s.phase == 'business' and not self.install_sent
                and f.pkg.install_pending is True and f.pkg.installed is None
                and f.pkg.staged is not None and f.pkg.staged['guest'] == STAGE
                and not f.ui.owned and not f.ui.pending and s.pm_help_ref is not None,
                'ONCE_CREATE_ONLY_OWNED_HELPER_INSTALL')
            s.consume_intent('helper-install', argv); self.install_sent = True; return True
        if argv == ['/system/bin/pm', 'uninstall', PACKAGE]:
            c.need(timeout == 60 and s.phase == 'final_cleanup' and self.install_sent
                and not self.uninstall_sent and f.pkg.uninstall_pending is True
                and f.pkg.installed is not None and not f.ui.owned and not f.ui.pending
                and f.helper_pending is None and f.rotation_pending is None and f.client_pending is None
                and f.media.directory_pending is None, 'ONCE_KNOWN_OWNED_HELPER_UNINSTALL')
            s.consume_intent('helper-uninstall', argv); self.uninstall_sent = True; return True
        if argv[:6] == ['/system/bin/am', 'instrument', '-w', '-r', '-e', 'run']:
            c.need(len(argv) == 11 and argv[6:9] == [RUN, '-e', 'op']
                and argv[10] == PACKAGE + '/.MediaFixture' and timeout == 55,
                'EXACT_ORIGINAL_GALLERY_FIXTURE_INSTRUMENTATION')
            operation = argv[9]
            c.need(operation in {'seed', 'seal-first-unchanged', 'seal-first-clockwise', 'seal-reopen-clockwise', 'delete'}
                and operation not in self.helper_sent and f.helper_pending == operation
                and f.instrument_calls[-1:] == [operation] and not f.ui.owned and not f.ui.pending
                and f.pkg.installed is not None and f.pkg.install_pending is False
                and (operation != 'seed' or s.phase == 'business')
                and (operation != 'delete' or s.phase == 'final_cleanup'),
                'ONCE_ORIGINAL_HELPER_STATE_AND_TASK_BOUNDARY')
            s.consume_intent('fixture-' + operation, argv); self.helper_sent.add(operation); return True
        if argv[:4] == ['/system/bin/cmd', 'activity', 'stack', 'remove']:
            c.need(len(argv) == 5 and timeout == 15 and re.fullmatch('[1-9][0-9]*', argv[4]),
                'EXACT_ORIGINAL_GALLERY_TASK_REMOVAL')
            task = int(argv[4]); token = 'close-' + argv[4]
            c.need(task not in self.remove_sent and token in f.ui.pending
                and not f.ui.pending[token]['input_acknowledged'] and task not in f.ui.owned
                and task in s.claimed_tasks and s.last_stacks is not None, 'ACTUALLY_NEW_UNREMOVED_TASK_ONLY')
            roots, tasks = s.last_stacks; claim = s.claimed_tasks[task]
            c.need(tasks == f.ui.baseline | set(f.ui.owned) | {task} and task not in f.ui.baseline
                and s.components['rotation_ui.py'].leaf(roots, task, tuple(claim['component'])),
                'CURRENT_EXACT_GALLERY_OWNED_LEAF_BEFORE_REMOVE')
            s.consume_intent('task-remove', argv); self.remove_sent.add(task); return True
        if argv[:2] == ['/system/bin/content', 'query']:
            self.directory(argv, timeout, False); return False
        if argv[:2] == ['/system/bin/content', 'delete']:
            self.directory(argv, timeout, True); return True
        raise RuntimeError('COMMAND_OUTSIDE_ORIGINAL_GALLERY_ROTATION_SCOPE')

    def observe(self, argv, raw):
        s, c = self.s, self.c
        if argv[:2] == ['/system/bin/pm', 'path']:
            package = argv[-1]; rows = raw.decode('utf-8', 'strict').splitlines()
            c.need(len(rows) == 1 and rows[0].startswith('package:/') and rows[0].endswith('.apk'),
                'SINGLE_ACTUAL_ORIGINAL_PACKAGE_APK')
            s.apk_paths[package] = rows[0][8:]
        if argv == ['/system/bin/cmd', 'activity', 'stack', 'list']:
            s.last_stacks = s.components['rotation_ui.py'].parse_stacks(raw.decode('utf-8', 'strict'))
            s.observe_owned_tasks()

    def directory(self, argv, timeout, mutation):
        s, c, m = self.s, self.c, self.s.case.media
        c.need(s.phase == 'final_cleanup' and timeout == 25 and m.media is not None
            and s.case.helper_pending is None and not s.case.ui.owned and not s.case.ui.pending,
            'ORIGINAL_KNOWN_EMPTY_DIRECTORY_CLEANUP_ONLY')
        mod = s.components['owned_media.py']; matched = []
        for role, row in m.directory_rows.items():
            prefix = ['/system/bin/content', 'delete' if mutation else 'query', '--user', '0', '--uri',
                'content://media/external_primary/file/' + str(row['_id'])]
            if not mutation:
                prefix += ['--projection', '_id']
            expected = prefix + ['--where', mod.exact_row_predicate(row)]
            if argv == expected:
                matched.append((role, row))
        c.need(len(matched) == 1, 'EXACT_ORIGINAL_FULL_DIRECTORY_TUPLE_REQUIRED')
        role, row = matched[0]
        c.need(row['media_type'] == 0 and row['owner_package_name'] is None
            and row['_data'] == mod.folder(role), 'ONLY_ORIGINAL_OWNED_EMPTY_DIRECTORY_ROW')
        if mutation:
            c.need(role not in self.directory_sent and m.directory_pending == 'delete-' + role,
                'ONCE_KNOWN_DIRECTORY_PROVIDER_DELETE')
            s.consume_intent('directory-delete', argv); self.directory_sent.add(role)

    def root_sql(self, label, command, timeout):
        s, c = self.s, self.c; m = s.components['owned_media.py']; obj = s.case.media
        c.need(s.active_api is None and timeout == 14 and re.fullmatch('[A-Za-z0-9_-]{1,160}', label),
            'ORIGINAL_MEDIA_READONLY_SQL_CALL')
        prefix = ['/system/bin/env', '-i'] + [k + '=' + s.environment[k] for k in sorted(s.environment)]
        prefix += ['/system/bin/timeout', '-k', '2', '10', '/system/bin/sqlite3', '-readonly', '-json', m.DB]
        c.need(command[:-1] == prefix, 'EXACT_ORIGINAL_TEN_SECOND_ROOT_SQL_PREFIX')
        clauses = ['owner_package_name=' + m.q(PACKAGE)]
        for role in m.FOLDERS:
            clauses += ['relative_path=' + m.q(m.relative(role)),
                '_data IN (' + m.q(m.folder(role)) + ',' + m.q(m.folder(role) + '/' + m.NAMES[role]) + ')',
                '_display_name IN (' + m.q(m.FOLDERS[role]) + ',' + m.q(m.NAMES[role]) + ')']
        allowed = {'SELECT ' + m.FIELDS + ' FROM files WHERE ' + ' OR '.join(clauses) + ' ORDER BY _id',
            'SELECT _id,media_type,mime_type,_size,width,height,is_pending,orientation,date_modified '
            'FROM files WHERE media_type IN (1,3) AND (owner_package_name IS NULL OR owner_package_name!=' +
            m.q(PACKAGE) + ') ORDER BY _id'}
        if obj.media is not None:
            for role in m.FOLDERS:
                bucket = obj.media[role]['metadata']['bucket_id']
                c.need(type(bucket) is int and -(2**31) <= bucket < 2**31, 'ACTUAL_SEEDED_BUCKET_ONLY')
                allowed.add('SELECT _id FROM files WHERE media_type=1 AND bucket_id=' + str(bucket) + ' ORDER BY _id')
        for role, row in obj.directory_rows.items():
            allowed.add('SELECT _id FROM files WHERE parent=' + str(row['_id']) +
                ' OR _data GLOB (' + m.q(m.folder(role)) + "||'/*') ORDER BY _id")
        c.need(command[-1] in {'PRAGMA query_only=ON;BEGIN;' + sql + ';ROLLBACK;' for sql in allowed},
            'ONLY_ORIGINAL_METADATA_AND_CURRENT_OWNED_NAMESPACE_SQL')
        return command


def native_request(c, outer, request, action_used):
    package = outer.get('package', outer.get('expected_package'))
    c.need(type(request) is dict and request.get('display') == 0 and request.get('accessibility_mode') == 'none'
        and request.get('expected_package') == package and package in {GALLERY, PACKAGE},
        'EXACT_ORIGINAL_GALLERY_NATIVE_PACKAGE_SCOPE')
    if request.get('op') in ('meta', 'dump'):
        c.need(set(request) == {'op', 'expected_package', 'display', 'accessibility_mode'},
            'ONLY_ORIGINAL_READONLY_NATIVE_FIELDS'); return False
    c.need(not action_used and outer.get('op') == 'click' and outer.get('method') == 'accessibility'
        and outer.get('expected_package') == GALLERY and request == outer,
        'ONLY_ORIGINAL_DIRECT_MORE_OPTIONS_ACTION_CLICK')
    return True


def backend_android(c, outer, argv, timeout, action_used):
    if argv == ['/system/bin/screencap', '-p']:
        c.need(timeout == 20, 'ORIGINAL_GALLERY_SCREENSHOT_TIMEOUT'); return False, True
    if len(argv) == 8 and argv[:6] == ['/system/bin/am', 'instrument', '-w', '-r', '-e', 'request']:
        c.need(argv[-1] == NATIVE + '/.ActionRunner' and timeout == 70, 'EXACT_ORIGINAL_NATIVE_RUNNER')
        raw = base64.b64decode(argv[6], validate=True); c.need(len(raw) <= 65536, 'BOUNDED_ORIGINAL_NATIVE_REQUEST')
        request = c.parse(raw)
        c.need(base64.b64encode(json.dumps(request, ensure_ascii=True, separators=(',', ':')).encode()).decode() == argv[6],
            'UNCHANGED_NATIVE_WIRE_ENCODING')
        return native_request(c, outer, request, action_used), False
    if outer.get('op') == 'snapshot-tap':
        point = outer.get('coords')
        c.need(type(point) is list and len(point) == 2 and all(type(x) is int for x in point)
            and outer.get('input_source') == 'touch' and not action_used and timeout == 30
            and argv == ['/system/bin/input', '-d', '0', 'tap', str(point[0]), str(point[1])],
            'ONLY_ACTUAL_ORIGINAL_FRAME_BOUND_TOUCH')
        return True, False
    raise RuntimeError('BACKEND_COMMAND_OUTSIDE_ORIGINAL_GALLERY_API')
