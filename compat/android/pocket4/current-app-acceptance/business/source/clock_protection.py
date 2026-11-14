"""Original Clock protection snapshot through one fresh held Main.

All SQL is the fixed original SELECT set, sqlite -readonly -json, query_only,
BEGIN/ROLLBACK, inner 12 s + kill 2 s and outer 16 s. There is no SQL write,
permission/settings write, package installation, launch, or task removal here.
"""
from datetime import datetime, timezone
import os
from pathlib import Path
import stat
import time

PACKAGE = 'com.android.deskclock'
UID = 10063
FINGERPRINT_SQL = 'SELECT * FROM alarm_templates ORDER BY _id;'


class Session:
    def __init__(self, common, plan, preservation, journal, deadline, packet_verify, phase_commands):
        self.c, self.plan, self.p = common, plan, preservation
        self.journal_dir = common.private_dir(journal, create=True)
        self.deadline = deadline; self.packet_verify = packet_verify; self.view = None; self.commands = []
        self.identity_receipt = common.parse(common.read_ref(plan['target_identity']))
        self.helper_receipt = common.parse(common.read_ref(plan['helper_identity']))
        self.epoch_sha256 = plan['framework_epoch_sha256']
        self.view = common.MainView(plan['baseline'], plan['qualification'], self.journal_dir,
            self.admit, support_ref=common.CLOCK_SUPPORT_REF)
        self.target = self.view.target; self.environment = self.view.environment
        self.artifacts = None
        try:
            self.artifacts = common.HeldArtifacts(self.target, [self.identity_receipt, self.helper_receipt])
            self.view.extra_guard = self._extra_guard
            self.view.commands = phase_commands(self.view.commands, self)
            self.guard()
        except BaseException as primary:
            for obj in (self.artifacts, self.view):
                if obj is not None:
                    try:
                        obj.close()
                    except BaseException as secondary:
                        primary.add_note('CLOCK_SESSION_CLOSE:' + type(secondary).__name__)
            raise

    def _extra_guard(self, *, attempted=False):
        self.c.need(time.monotonic() < self.deadline, 'ORIGINAL_CLOCK_READ_LEASE_EXPIRED')
        self.packet_verify()
        self.artifacts.verify()

    def guard(self):
        return self.view.guard()

    def admit(self, argv, timeout, root, private):
        self.c.need(private is False, 'CLOCK_ORIGINAL_PRIVATE_JOURNAL_REQUIRED')
        if root:
            allowed = [self.sql_argv(sql) for sql in list(self.p.QUERIES.values()) + [FINGERPRINT_SQL]]
            self.c.need(argv in allowed and timeout == 16, 'FIXED_CLOCK_ROOT_READONLY_SQL_ONLY')
            return
        allowed = [
            ['/system/bin/pm', 'path', PACKAGE], ['/system/bin/dumpsys', 'package', PACKAGE],
            ['/system/bin/cmd', 'appops', 'get', '--user', '0', PACKAGE, 'POST_NOTIFICATION'],
            ['/system/bin/dumpsys', 'audio'], ['/system/bin/cmd', 'activity', 'stack', 'list'],
            ['/system/bin/dumpsys', 'alarm'], ['/system/bin/cat', '/proc/uptime'],
            ['/system/bin/dumpsys', 'window', 'displays']]
        allowed += [['/system/bin/settings', '--user', '0', 'get', 'system', key] for key in self.p.SOUND_KEYS]
        self.c.need(argv in allowed and 6 <= timeout <= 20, 'ORIGINAL_CLOCK_READ_ALLOWLIST_ONLY')
        if argv == ['/system/bin/dumpsys', 'window', 'displays']:
            self.c.need(timeout == 6, 'ORIGINAL_SIX_SECOND_FOCUS_READ_BOUND')
        if argv == ['/system/bin/dumpsys', 'alarm']:
            self.c.need(timeout == 15, 'ORIGINAL_SCHEDULER_READ_BOUND')

    def android(self, argv, timeout=20):
        raw, row = self.view.command(argv, timeout, output_bound=16 * 1024 * 1024)
        self.last_command = {'logical': row['logical'], 'result': self.c.regular(row['path'], contents=False),
                             'transport': row['transport']}
        self.commands.append(self.last_command)
        return raw

    def sql_argv(self, sql):
        return ['/system/bin/sqlite3', '-readonly', '-json', self.p.DB,
                'PRAGMA query_only=ON;BEGIN;' + sql + 'ROLLBACK;']

    def sql(self, sql):
        raw, row = self.view.command(self.sql_argv(sql), 16, root=True, inner_timeout=12,
                                     output_bound=16 * 1024 * 1024)
        self.last_command = {'logical': row['logical'], 'result': self.c.regular(row['path'], contents=False),
                             'transport': row['transport']}
        self.commands.append(self.last_command)
        return raw

    def state(self, include_schema=False):
        labels = ['counts', 'template-ids', 'instance-ids', 'enabled-count', 'marker-count']
        if include_schema:
            labels.append('schema')
        value = {}
        for label in labels:
            raw = self.sql(self.p.QUERIES[label]); rows = self.c.parse(raw) if raw.strip() else []
            self.c.need(type(rows) is list, 'ORIGINAL_SQL_JSON_ROWS_REQUIRED')
            value[label] = rows
        value['epoch_sha256'] = self.epoch_sha256
        return value

    def timer_read(self):
        raw, _ = self.target.read_file(self.p.PREFS, 1024 * 1024)
        result = self.p.parse(raw); self.guard()
        return result

    def identity(self):
        guest = self.identity_receipt['artifacts'][0]['guest_path']
        paths = self.android(['/system/bin/pm', 'path', PACKAGE]).decode('utf-8', 'strict').splitlines()
        self.c.need(paths == ['package:' + guest], 'CLOCK_ACTIVE_PATH_CHANGED')
        raw = self.android(['/system/bin/dumpsys', 'package', PACKAGE])
        identity = self.p.parse_identity(raw.decode('utf-8', 'strict'), guest)
        self.guard()
        return identity

    def fingerprint(self):
        raw = self.sql(FINGERPRINT_SQL)
        value = self.c.sha(raw)
        self.c.need(value == self.p.ALARM_SHA, 'ORIGINAL_COMPLETE_ALARM_TEMPLATE_CONTENT_CHANGED')
        return value

    def snapshot(self, label):
        first_command = len(self.commands)
        identity = self.identity(); guest = self.identity_receipt['artifacts'][0]['guest_path']
        data, _ = self.target.read_file(guest, 16 * 1024 * 1024)
        self.c.need(len(data) == 7597225 and self.c.sha(data) ==
            '433ff501b92a21bb9265c896add220b52bc16fc4124662eaf45310da99243a0d', 'ORIGINAL_CLOCK_APK_CHANGED')
        directories = {}
        for key, path in (('ce', '/data/user/0/' + PACKAGE), ('de', '/data/user_de/0/' + PACKAGE)):
            fd = self.target.open_root(path, os.O_PATH | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                info = os.fstat(fd)
                directories[key] = {'device': info.st_dev, 'inode': info.st_ino, 'uid': info.st_uid,
                                    'gid': info.st_gid, 'mode': stat.S_IMODE(info.st_mode)}
            finally:
                os.close(fd)
            self.c.need(info.st_uid == info.st_gid == UID and info.st_ino == identity[key + '_inode'],
                        'CLOCK_DATA_DIRECTORY_OWNER_OR_INODE_CHANGED')
        alarms = self.state(); self.p.verify_before(alarms)
        self.c.need(self.p.baseline_ids(alarms) == {1, 2}, 'ORIGINAL_ALARM_TEMPLATE_SET_CHANGED')
        fingerprint = self.fingerprint()
        preferences, _ = self.target.read_file(self.p.PREFS, 2 * 1024 * 1024)
        self.p.empty(self.p.parse(preferences))
        preference_metadata = self.p.preference_metadata(preferences)
        appop = self.android(['/system/bin/cmd', 'appops', 'get', '--user', '0', PACKAGE, 'POST_NOTIFICATION'])
        self.c.need(self.p.appop_allow(appop.decode('utf-8', 'strict')), 'CLOCK_NOTIFICATION_APPOP_NOT_ALLOW')
        audio = self.android(['/system/bin/dumpsys', 'audio'])
        sounds = {'streams': self.p.audio_streams(audio.decode('utf-8', 'strict')), 'settings': {}}
        for key in self.p.SOUND_KEYS:
            sounds['settings'][key] = self.android(['/system/bin/settings', '--user', '0', 'get', 'system', key]).decode().strip()
        tasks = self.android(['/system/bin/cmd', 'activity', 'stack', 'list'])
        self.c.need(PACKAGE not in tasks.decode('utf-8', 'strict'), 'CLOCK_TASK_ALREADY_PRESENT')
        self.guard()
        result = {'package': PACKAGE, 'epoch_sha256': self.epoch_sha256, 'identity': identity,
            'directories': directories, 'observed_utc': datetime.now(timezone.utc).isoformat(),
            'alarm_state': alarms, 'alarm_content_sha256': fingerprint, 'preferences_sha256': self.c.sha(preferences),
            'preferences_metadata': preference_metadata, 'timer_and_stopwatch_empty': True,
            'notification_appop_allow': True, 'sound_state': sounds, 'tasks_sha256': self.c.sha(tasks),
            'apk': {'guest_path': guest, 'bytes': len(data), 'sha256': self.c.sha(data)},
            'commands': self.commands[first_command:]}
        self.c.write_new(self.journal_dir / (label + '.json'), result)
        return result

    def close(self):
        try:
            if self.artifacts is not None:
                self.artifacts.close()
        finally:
            if self.view is not None:
                self.view.close()
