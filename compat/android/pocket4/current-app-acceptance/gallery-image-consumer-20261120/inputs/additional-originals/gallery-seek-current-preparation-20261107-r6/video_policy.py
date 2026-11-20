"""Literal original video operations, current owned tasks, and one-way effects."""
import base64
import json
import re

GALLERY = 'com.android.gallery3d'
RUN = 'c92c3d79180955ef'
PACKAGE = 'org.droidloom.qa.media.r12.n' + RUN
NATIVE = 'local.pocket4.actions.v2'
PACKAGES = {GALLERY, PACKAGE, NATIVE}
STAGE = '/data/local/tmp/pocket4-owned-galleryvideo-' + RUN + '/owned-media.apk'
VIDEO_SHA = 'eaeb797bff8f610373204451f5885dcba2fb1ffa2530410468b7dc480d5588da'


class Policy:
    def __init__(self, session):
        self.s = session; self.c = session.c
        self.install_sent = self.uninstall_sent = self.directory_sent = False
        self.helper_sent = set(); self.remove_sent = set(); self.views_sent = set()

    def command(self, argv, timeout):
        s, c, f = self.s, self.c, self.s.case
        c.need(type(argv) is list and argv and all(type(x) is str and x and '\0' not in x for x in argv)
            and type(timeout) in (int, float) and 5 < timeout <= 70, 'BOUNDED_ORIGINAL_VIDEO_COMMAND')
        if argv == ['/system/bin/cmd', 'activity', 'stack', 'list']:
            c.need(timeout == 15, 'ORIGINAL_VIDEO_TASK_READ_BOUND'); return False
        if argv == ['/system/bin/dumpsys', 'window', 'displays']:
            c.need(timeout == 6, 'ORIGINAL_VIDEO_FOCUS_READ_BOUND'); return False
        if len(argv) == 3 and argv[:2] == ['/system/bin/dumpsys', 'package']:
            c.need(argv[2] in PACKAGES and timeout in (12, 15, 20), 'EXACT_ORIGINAL_VIDEO_PACKAGE_READ'); return False
        if argv[:2] == ['/system/bin/pm', 'path']:
            c.need(len(argv) == 5 and argv[2:4] == ['--user', '0'] and argv[4] in PACKAGES
                and timeout in (12, 20), 'EXACT_ORIGINAL_VIDEO_APK_PATH_READ'); return False
        reads = [
            (['/system/bin/pm', 'list', 'packages', '-u', '-U', PACKAGE], 20),
            (['/system/bin/date', '+%s'], 8),
            (['/system/bin/dumpsys', 'activity', 'exit-info', GALLERY], 15),
            (['/system/bin/logcat', '-b', 'events', '-d', '-v', 'epoch', '-t', '2048'], 15),
            (['/system/bin/logcat', '--uid=10064', '-b', 'crash', '-d', '-v', 'epoch', '-t', '512'], 15),
        ]
        if (argv, timeout) in reads:
            return False
        if argv == ['/system/bin/pm', 'help']:
            c.need(timeout == 15 and s.pm_help_reading and s.pm_help_ref is None,
                'ONCE_CURRENT_VIDEO_PM_FLAG_OBSERVATION'); return False
        c.need(f is not None, 'BOUND_ORIGINAL_VIDEO_FLOW_REQUIRED')
        if argv == ['/system/bin/pm', 'install', '-R', '-t', '--user', '0', STAGE]:
            s.original_caller(['video_fixture.py'], {'install'})
            c.need(timeout == 60 and s.phase == 'business' and not self.install_sent
                and f.fixture.install_pending is True and f.fixture.installed is None
                and f.fixture.staged is not None and f.fixture.staged['guest'] == STAGE
                and f.ui.owned is None and f.pending is None and f.close_pending is None
                and s.pm_help_ref is not None, 'ONCE_CREATE_ONLY_ORIGINAL_VIDEO_HELPER')
            s.consume_intent('helper-install', argv); self.install_sent = True; return True
        if argv == ['/system/bin/pm', 'uninstall', PACKAGE]:
            s.original_caller(['video_fixture.py'], {'uninstall'})
            c.need(timeout == 60 and s.phase == 'final_cleanup' and self.install_sent and not self.uninstall_sent
                and f.fixture.uninstall_pending is True and f.fixture.installed is not None
                and f.ui.owned is None and f.pending is None and f.close_pending is None,
                'ONCE_KNOWN_ORIGINAL_VIDEO_HELPER_UNINSTALL')
            s.consume_intent('helper-uninstall', argv); self.uninstall_sent = True; return True
        if argv[:6] == ['/system/bin/am', 'instrument', '-w', '-r', '-e', 'run']:
            s.original_caller(['video_flow.py'], {'instrument'})
            c.need(len(argv) == 14 and argv[6:11] == [RUN, '-e', 'media', 'video', '-e']
                and argv[11] == 'op' and argv[13] == PACKAGE + '/.MediaFixture' and timeout == 55,
                'EXACT_ORIGINAL_VIDEO_FIXTURE_INSTRUMENTATION')
            op = argv[12]; calls = f.instrument_calls; index = len(calls) - 1
            token = 'video-' + op + '-' + str(index)
            c.need(op in {'seed', 'verify', 'delete'} and 0 <= index < 5 and calls[-1:] == [op]
                and f.pending == token and token not in self.helper_sent and f.ui.owned is None
                and f.close_pending is None and f.fixture.installed is not None
                and not f.fixture.install_pending and not f.fixture.uninstall_pending,
                'ONCE_ORIGINAL_VIDEO_FIXTURE_PHASE')
            if op == 'seed':
                c.need(s.phase == 'business' and calls == ['seed'], 'ONE_ORIGINAL_VIDEO_SEED')
            elif op == 'verify':
                c.need(s.phase == 'business' and index in (1, 2) and calls == ['seed'] + ['verify'] * index,
                    'ONLY_ORIGINAL_TWO_VIDEO_REOPEN_CHECKS')
            else:
                c.need(s.phase == 'final_cleanup' and calls[0] == 'seed'
                    and calls[1:-1] == ['verify'] * (index - 1) and index in (1, 2, 3),
                    'ONCE_KNOWN_ORIGINAL_VIDEO_DELETE')
            s.consume_intent('fixture-' + token, argv); self.helper_sent.add(token); return True
        if argv[:2] == ['/system/bin/am', 'start-activity']:
            s.original_caller(['video_flow.py'], {'video_round'})
            c.need(s.phase == 'business' and f.ui.owned is not None and f.media is not None
                and f.media['sha256'] == VIDEO_SHA and timeout == 35, 'CURRENT_OWNED_VIDEO_VIEW_ONLY')
            task, preserved = f.ui.owned; index = f.intent_calls - 1
            c.need(index in (0, 1) and index not in self.views_sent and f.pending == 'movie-view-' + str(index)
                and task in s.claimed_tasks and task not in preserved and s.native_launches == index + 1,
                'ONCE_ORIGINAL_VIEW_PER_ACTUAL_NEW_TASK')
            uri = f.media['uri']; c.need(re.fullmatch(r'content://media/external_primary/video/media/[1-9][0-9]*', uri),
                'EXACT_ACTUALLY_CREATED_VIDEO_URI')
            wanted = ['/system/bin/am', 'start-activity', '-W', '--user', '0', '--display', '0', '--task', str(task),
                '--activity-clear-top', '-a', 'android.intent.action.VIEW', '-d', uri, '-t', 'video/mp4',
                '--ez', 'android.intent.extra.finishOnCompletion', 'false', '-n', GALLERY + '/.app.MovieActivity']
            c.need(argv == wanted, 'NO_OTHER_VIDEO_VIEW_ARGUMENTS')
            s.check_owned_task(); s.consume_intent('view', argv); self.views_sent.add(index); return True
        if argv[:4] == ['/system/bin/cmd', 'activity', 'stack', 'remove']:
            s.original_caller(['video_ui.py'], {'close'})
            c.need(len(argv) == 5 and timeout == 15 and re.fullmatch('[1-9][0-9]*', argv[4]),
                'EXACT_ORIGINAL_VIDEO_TASK_REMOVE')
            task = int(argv[4]); c.need(task not in self.remove_sent and task in s.claimed_tasks
                and f.ui.owned is None and f.close_pending == {'task': task, 'automatic_retry': False}
                and s.last_stacks is not None, 'ONCE_ACTUALLY_NEW_VIDEO_TASK_ONLY')
            roots, tasks = s.last_stacks; claim = s.claimed_tasks[task]
            c.need(tasks == set(claim['prelaunch_tasks']) | {task} and task not in claim['prelaunch_tasks']
                and s.components['video_ui.py'].exact_leaf(roots, task), 'CURRENT_ORIGINAL_VIDEO_EXACT_LEAF')
            s.consume_intent('task-remove', argv); self.remove_sent.add(task); return True
        if argv[:2] == ['/system/bin/content', 'delete']:
            s.original_caller(['video_flow.py'], {'clean_folder'})
            c.need(s.phase == 'final_cleanup' and timeout == 25 and not self.directory_sent
                and f.pending == 'delete-owned-directory-index' and f.ui.owned is None
                and f.close_pending is None and f.directory_row is not None and f.held_folder() == [],
                'ONCE_KNOWN_ORIGINAL_EMPTY_VIDEO_DIRECTORY')
            row = f.directory_row; mod = s.components['video_flow.py']; identity = row['_id']
            c.need(type(identity) is int and identity > 0 and row['_data'] == mod.GUEST_FOLDER
                and row['_display_name'] == mod.FOLDER and row['relative_path'] == 'DCIM/'
                and row['media_type'] == 0 and row['is_pending'] == 0 and row['owner_package_name'] is None,
                'FULL_ORIGINAL_EMPTY_DIRECTORY_ROW_REQUIRED')
            predicate = '_id=' + str(identity) + " AND _data='" + mod.GUEST_FOLDER + "' AND _display_name='" + mod.FOLDER + "' AND relative_path='DCIM/' AND media_type=0 AND is_pending=0 AND owner_package_name IS NULL"
            c.need(argv == ['/system/bin/content', 'delete', '--user', '0', '--uri',
                'content://media/external_primary/file/' + str(identity), '--where', predicate],
                'EXACT_ORIGINAL_VIDEO_DIRECTORY_DELETE_TUPLE')
            s.consume_intent('directory-delete', argv); self.directory_sent = True; return True
        raise RuntimeError('COMMAND_OUTSIDE_ORIGINAL_VIDEO_SCOPE')

    def observe(self, argv, raw):
        s, c = self.s, self.c
        if argv[:2] == ['/system/bin/pm', 'path']:
            rows = raw.decode('utf-8', 'strict').splitlines()
            c.need(len(rows) == 1 and rows[0].startswith('package:/') and rows[0].endswith('.apk'),
                'SINGLE_CURRENT_VIDEO_PACKAGE_APK')
            s.apk_paths[argv[-1]] = rows[0][8:]
        if argv == ['/system/bin/cmd', 'activity', 'stack', 'list']:
            s.last_stacks = s.components['video_ui.py'].parse_stacks(raw.decode('utf-8', 'strict'))
            s.observe_owned_task()

    def root_sql(self, label, argv, timeout):
        s, c, f = self.s, self.c, self.s.case; m = s.components['video_flow.py']; b = s.components['video_base.py']
        c.need(f is not None and s.active_api is None and timeout == 14
            and re.fullmatch('[A-Za-z0-9_-]{1,160}', label), 'ORIGINAL_VIDEO_ROOT_READ_SCOPE')
        prefix = ['/system/bin/env', '-i'] + [k + '=' + s.environment[k] for k in sorted(s.environment)]
        prefix += ['/system/bin/timeout', '-k', '2', '10', '/system/bin/sqlite3', '-readonly', '-json', b.DB]
        c.need(argv[:-1] == prefix, 'EXACT_ORIGINAL_VIDEO_READONLY_SQL_PREFIX')
        fields = '_id,_data,_display_name,relative_path,owner_package_name,media_type,mime_type,_size,width,height,is_pending'
        allowed = {'SELECT ' + fields + " FROM files WHERE relative_path='" + m.RELATIVE + "' OR _data IN ('" +
            m.GUEST_FOLDER + "','" + m.GUEST_FILE + "') OR _display_name IN ('" + m.FOLDER + "','" + m.NAME +
            "') OR owner_package_name='" + PACKAGE + "' ORDER BY _id",
            "SELECT _id,media_type,mime_type,_size,width,height,is_pending FROM files WHERE media_type IN (1,3) AND (owner_package_name IS NULL OR owner_package_name!='" + PACKAGE + "') ORDER BY _id"}
        if f.directory_row is not None:
            row = f.directory_row; c.need(type(row['_id']) is int and row['_id'] > 0 and row['_data'] == m.GUEST_FOLDER,
                'CURRENT_OWNED_VIDEO_DIRECTORY_ROW_ONLY')
            allowed.add('SELECT _id FROM files WHERE parent=' + str(row['_id']) + " OR _data GLOB '" + m.GUEST_FOLDER + "/*' ORDER BY _id")
        c.need(argv[-1] in {'PRAGMA query_only=ON;BEGIN;' + sql + ';ROLLBACK;' for sql in allowed},
            'ONLY_ORIGINAL_VIDEO_METADATA_AND_OWNED_NAMESPACE_READS')
        return argv


def native_request(c, outer, request, action_used):
    c.need(type(request) is dict and request.get('expected_package') == GALLERY and request.get('display') == 0
        and request.get('accessibility_mode') == 'none', 'EXACT_ORIGINAL_VIDEO_NATIVE_WINDOW')
    if request.get('op') in ('meta', 'dump'):
        c.need(set(request) == {'op', 'expected_package', 'display', 'accessibility_mode'},
            'ONLY_ORIGINAL_VIDEO_NATIVE_READ_FIELDS'); return False
    c.need(not action_used and outer.get('op') == 'click' and request == outer
        and outer.get('method') in ('mouse', 'accessibility'), 'ONLY_ORIGINAL_CURRENT_OBSERVED_VIDEO_CONTROL')
    return True


def backend_android(c, outer, argv, timeout, action_used):
    if argv == ['/system/bin/screencap', '-p']:
        c.need(timeout == 20, 'ORIGINAL_VIDEO_SCREENSHOT_BOUND'); return False, True
    if len(argv) == 8 and argv[:6] == ['/system/bin/am', 'instrument', '-w', '-r', '-e', 'request']:
        c.need(argv[-1] == NATIVE + '/.ActionRunner' and timeout == 70, 'EXACT_CURRENT_VIDEO_NATIVE_RUNNER')
        raw = base64.b64decode(argv[6], validate=True); c.need(len(raw) <= 65536, 'BOUNDED_VIDEO_NATIVE_REQUEST')
        request = c.parse(raw)
        c.need(base64.b64encode(json.dumps(request, ensure_ascii=True, separators=(',', ':')).encode()).decode() == argv[6],
            'UNCHANGED_VIDEO_NATIVE_WIRE_ENCODING')
        return native_request(c, outer, request, action_used), False
    raise RuntimeError('BACKEND_COMMAND_OUTSIDE_ORIGINAL_VIDEO_API')
