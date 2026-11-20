"""Original Clock protection methods on the new same-process held session.

No private old Main/session is loaded. SQL stays the original fixed SELECT set,
readonly 12+2/16 seconds, and snapshots still require the complete empty state.
"""
from datetime import datetime,timezone
import os
from pathlib import Path
import stat,time,types
PACKAGE='com.android.deskclock'
UID=10063
FINGERPRINT_SQL='SELECT * FROM alarm_templates ORDER BY _id;'

class Protection:
    def __init__(self,session):
        self.s=session;self.c=session.c;self.p=session.components['clock_preservation.py']
        self.target=session.target;self.commands=[]
        self.journal_dir=self.c.private_dir(session.root/'protection',create=True)
        self.identity_receipt=session.identities[PACKAGE]
        self.epoch_sha256=session.baseline.value['framework_epoch']['sha256']
    def guard(self):return self.s.guard()
    def android(self,argv,timeout=20):
        value=self.s.android(argv,timeout);self.commands.append(self.s.records[-1]);return value
    def sql(self,sql):
        value=self.s.sql('original-protection',sql);self.commands.append(self.s.records[-1]);return value

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
        self.c.need(len(data) == 7665498 and self.c.sha(data) ==
            '9f24ea5fa57bca4a453556ab7cb44fbad1813cb3d15292a8e572cfb40fff7a77', 'ORIGINAL_CLOCK_APK_CHANGED')
        directories = {}
        for key, path in (('ce', '/data/user/0/' + PACKAGE), ('de', '/data/user_de/0/' + PACKAGE)):
            fd = self.target.open_root(path, os.O_PATH | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                info, mapped_owner = self.c.mapped_file_info(self.s.view, fd, UID)
                directories[key] = {'device': info.st_dev, 'inode': info.st_ino, 'uid': info.st_uid,
                                    'gid': info.st_gid, 'mode': stat.S_IMODE(info.st_mode)}
            finally:
                os.close(fd)
            self.c.need((info.st_uid, info.st_gid) == mapped_owner and info.st_ino == identity[key + '_inode'],
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
