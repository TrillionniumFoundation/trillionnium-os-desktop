#!/usr/bin/env python3
"""Qualify two real Camera2/UVC cycles in one freshly authenticated Main epoch.

Uses the frozen framework namespace and owned-child implementation. Installs only
the fixed diagnostic package through the normal desktop control client. The sole
service restart reloads the newly deployed observer; no Android unit is restarted.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import select
import stat
import sys
import time
import types

ROOT = Path('/home/alex/work/pocket4-android-final/camera')
FRAMEWORK_PATH = '/home/alex/work/pocket4-android-final/framework/runtime_qualify.py'
FRAMEWORK_SHA = 'fa4ce85a063ead3c3db4da5b846c0b272eee23cea9ac4614f4b5111d34ba2b8f'
CONSUMER_PATH = '/home/alex/work/pocket4-android-final/consumers/manifest.json'
CONSUMER_SHA = 'b8cdea5cff9e67d87cfc5a11418068e25bfec5975ed9bae51b7547e936e3729b'
APK_SHA = '40f18312068307c611e67126eca0250fbb31819a3ce698e6e2f08fe291c85fb0'
PACKAGE = 'local.hepta.pocket4.cameraqualification'
UNIT = 'pocket4-live-camera.service'
UNIT_PATH = '/etc/systemd/system/pocket4-live-camera.service'
DEVICE = '/dev/v4l/by-id/usb-SunplusIT_Inc_Integrated_Camera_JX20250923V2-video-index0'
CAMERA_FILES = {
    'manager.py': '38357312bc841ab076de5c1036ef9c96e64b6c88158a790b431e3dc022c6ba50',
    'uvc_capture': '727ed998b46e000af6f434dded5cc00665a38a7030979ebb8fbfe84db19517d0',
    'virtual_camera': '5edc63a03e6f96d33e785baed80ed3631aacd2aa21e8ea2a6fde3de4b434737f',
    'live-camera-producer.jar': '353a9cf8ea87db07c2dbda110cc164858bf2def6389c0a9cf82d62cf6e8b91e2',
}
CONSUMER_TARGETS = {
    '/usr/local/bin/android-app', '/usr/local/libexec/android-digitalis-observe-helper',
    '/usr/local/libexec/android-digitalis-helper', '/usr/local/libexec/android-digitalis-validation-helper',
    '/usr/local/bin/android-app-digitalis', '/usr/local/bin/android-app-digitalis-validation',
}


def require(value, message):
    if not value:
        raise RuntimeError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def load_framework():
    fd = os.open(FRAMEWORK_PATH, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        raw = os.read(fd, 128 * 1024)
        require(os.read(fd, 1) == b'' and digest(raw) == FRAMEWORK_SHA, 'frozen framework adapter differs')
    finally:
        os.close(fd)
    module = types.ModuleType('camera_frozen_framework_runtime')
    module.__file__ = FRAMEWORK_PATH
    exec(compile(raw, FRAMEWORK_PATH, 'exec'), module.__dict__)
    return module


def parse_instrumentation(raw):
    text = raw.decode('utf-8', 'strict')
    require(not any(marker in text for marker in ('INSTRUMENTATION_FAILED', 'INSTRUMENTATION_ABORTED')), 'instrumentation aborted')
    lines = text.splitlines()
    values = [line.split('qualification_json=', 1)[1] for line in lines
              if line.startswith('INSTRUMENTATION_RESULT: qualification_json=')]
    require(len(values) == 1 and lines.count('INSTRUMENTATION_CODE: -1') == 1, 'instrumentation result/code absent or ambiguous')
    result = json.loads(values[0])
    require(result.get('schema') == 'pocket4-android-camera-frame-qualification-v1' and result.get('ok') is True, 'Camera2 probe did not pass')
    require(result.get('pixel_files_created') == 0, 'probe unexpectedly persisted pixels')
    cycles = result.get('cycles')
    require(type(cycles) is list and len(cycles) == 2, 'two complete camera cycles required')
    previous = 0
    camera_id = None
    for number, cycle in enumerate(cycles, 1):
        require(cycle.get('cycle') == number and cycle.get('ok') is True, 'camera cycle failed')
        require(cycle.get('width') == 640 and cycle.get('height') == 480 and
                type(cycle.get('frames')) is int and cycle['frames'] >= 8, 'camera dimensions/frame count differ')
        require(cycle.get('pixel_files_created') == 0 and all(cycle.get(key) is True for key in
                ('session_closed', 'device_closed', 'worker_joined')), 'camera resources did not close')
        if camera_id is None:
            camera_id = cycle.get('camera_id')
            require(type(camera_id) is str and camera_id, 'camera ID missing')
        require(cycle.get('camera_id') == camera_id, 'camera changed between cycles')
        samples = cycle.get('samples')
        require(type(samples) is list and len(samples) == 8, 'eight raw frame metadata samples required')
        for ordinal, sample in enumerate(samples, 1):
            require(sample.get('frame') == ordinal, 'sample ordinal differs')
            timestamp = sample.get('timestamp_ns')
            require(type(timestamp) is str and re.fullmatch('[0-9]{1,19}', timestamp), 'invalid frame timestamp')
            current = int(timestamp)
            require(current > previous, 'frame timestamps are not strictly increasing')
            previous = current
            require(type(sample.get('luma_bytes')) is int and 640 * 480 <= sample['luma_bytes'] <= 4 * 1024 * 1024, 'invalid luma plane length')
            require(type(sample.get('luma_crc32')) is str and re.fullmatch('[0-9a-f]{1,8}', sample['luma_crc32']), 'invalid measured luma CRC32')
    require(int(result['finished_elapsed_ns']) > int(result['started_elapsed_ns']) > 0, 'probe elapsed interval invalid')
    return result


def journal_events(raw, invocation, manager_pid, boot_id):
    result = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        require(row.get('_SYSTEMD_INVOCATION_ID') == invocation, 'journal includes another service invocation')
        require(row.get('_BOOT_ID', '').replace('-', '') == boot_id.replace('-', ''), 'journal boot differs')
        message = row.get('MESSAGE')
        if type(message) is not str or not message.startswith('{'):
            continue
        event = json.loads(message)
        require(int(row['_PID']) == manager_pid, 'camera event from another manager PID')
        event['journal_monotonic_us'] = int(row['__MONOTONIC_TIMESTAMP'])
        event['cursor'] = row['__CURSOR']
        result.append(event)
    return result


def physical_cycles(events, start_us, end_us, expected=2):
    cycles = []
    current = None
    for row in events:
        event = row.get('event')
        if event not in ('physical_camera_open', 'live_frames', 'physical_camera_closed'):
            require(event not in ('cleanup_failed', 'waiting'), 'camera service reported failure during probe')
            if event == 'capture_ended':
                require(row.get('reason') in ('consumer_closed', '[Errno 32] Broken pipe',
                    '[Errno 104] Connection reset by peer'), 'physical capture ended unexpectedly')
            continue
        require(start_us <= row['journal_monotonic_us'] <= end_us, 'physical frame event outside measured probe interval')
        if event == 'physical_camera_open':
            require(current is None and row.get('device') == DEVICE, 'physical camera open identity/sequence differs')
            require(type(row.get('capture_pid')) is int and row['capture_pid'] > 1, 'physical capture PID absent')
            current = {'open': row, 'live': []}
        elif event == 'live_frames':
            require(current is not None and type(row.get('frames')) is int and row['frames'] > 0 and
                    type(row.get('age_ms')) in (int, float) and 0 <= row['age_ms'] <= 1000, 'physical frame evidence invalid')
            current['live'].append(row)
        else:
            require(current is not None and current['live'], 'physical camera closed without live frames')
            require(type(row.get('frames')) is int and row['frames'] >= 8 and row.get('exit') in (0, -15), 'physical capture count/retirement failed')
            require(row['frames'] >= max(item['frames'] for item in current['live']), 'physical frame counter regressed')
            current['close'] = row
            cycles.append(current)
            current = None
    require(current is None and len(cycles) == expected, 'physical camera cycles incomplete or ambiguous')
    return cycles


def exact_package_lines(raw, all_users=False):
    rows = []
    for line in raw.decode('utf-8', 'strict').splitlines():
        if not line.strip():
            continue
        uid_pattern = r'[0-9]+(?:,[0-9]+)*' if all_users else r'[0-9]+'
        match = re.fullmatch(r'package:([^\s]+)(?: uid:(' + uid_pattern + r'))?', line.strip())
        require(match is not None, 'unexpected package-manager output')
        if match.group(1) == PACKAGE:
            uids = [int(value) for value in match.group(2).split(',')] if match.group(2) else []
            row = {'package': PACKAGE, 'uid': uids[0] if len(uids) == 1 else None}
            if all_users:
                row['uids'] = uids
            rows.append(row)
    return rows


def package_query_argv(all_users=False):
    argv = ['/system/bin/cmd', 'package', 'list', 'packages']
    if all_users:
        # The pinned PackageManager defines KNOWN as ANY_USER | UNINSTALLED.
        # The API traverses the settings map, including retained-data packages.
        argv.append('-a')
    return [*argv, '-u', '-U', '--user', 'all' if all_users else '0', PACKAGE]


class CameraRunner:
    def __init__(self, spec, output):
        self.fw = load_framework()
        self.spec, self.out = spec, output
        self.r = self.fw.Runner(spec, output)
        self.common_guard = self.r.guard
        self.r.guard = self.guard
        self.r.guest_jar = ''
        self.deadline = time.monotonic() + 360
        self.cleanup_deadline = None
        self.manager = None
        self.manager_pidfd = None
        self.current_mutation = False
        self.command_labels = {}
        self.install_attempted = False
        self.install_resolved = False
        self.instrument_attempted = False
        self.instrument_completed = False
        self.service_restart_attempted = False
        self.service_restart_confirmed = False
        self.installed_owned = False
        self.preflight_absent = False
        self.host_stage = None
        self.cleanup = {'package_uninstalled': False, 'package_absent': False, 'host_apk_removed': False,
                        'host_directory_removed': False, 'not_staged': True}
        self.results = {'schema': 'pocket4-camera-runtime-result-v1', 'transaction_id': spec.get('transaction_id'),
                        'success': False, 'runtime_qualified': False, 'automatic_retry': False}

    def verify_consumers(self):
        rows = self.consumers['files']
        require(len(rows) == 6 and {row['path'] for row in rows} == CONSUMER_TARGETS, 'six-consumer cohort changed')
        for row in rows:
            raw = self.fw.pinned({'path': row['path'], 'sha256': row['new_sha256']}, 1024 * 1024)
            st = os.stat(row['path'], follow_symlinks=False)
            require((st.st_uid, st.st_gid, stat.S_IMODE(st.st_mode), len(raw)) ==
                    (row['uid'], row['gid'], row['mode'], row['bytes']), 'installed consumer ownership/mode differs')

    def guard(self, label):
        require(time.monotonic() < (self.cleanup_deadline or self.deadline), 'camera qualification budget exhausted')
        self.common_guard(label)
        self.verify_consumers()
        self.fw.pinned(self.component['host_cli'], 64 * 1024 * 1024)
        self.fw.pinned(self.component['service_unit'], 65536)
        self.fw.pinned(self.component['service_manifest'], 65536)
        for name, expected in CAMERA_FILES.items():
            self.fw.pinned({'path': '/opt/pocket4-live-camera/' + name, 'sha256': expected}, 32 * 1024 * 1024)
        current = os.stat(DEVICE)
        require(stat.S_ISCHR(current.st_mode) and (current.st_dev, current.st_ino, current.st_rdev) == self.device_identity,
                'physical UVC device identity changed')
        if self.manager is not None:
            poller = select.poll()
            poller.register(self.manager_pidfd, select.POLLIN | select.POLLERR | select.POLLHUP)
            require(not poller.poll(0), 'camera manager exited during qualification')
            require(self.r.epoch.process_identity(self.manager['host_pid']) == self.manager, 'camera service manager identity changed')

    def invoke(self, label, argv, seconds, bound=1024 * 1024, guest=True, mutation=False):
        count = self.command_labels.get(label, 0) + 1
        self.command_labels[label] = count
        if count > 1:
            label += '_repeat_%d' % count
        self.current_mutation = mutation
        try:
            return self.r.invoke(label, argv, min(seconds, max(0, (self.cleanup_deadline or self.deadline) - time.monotonic() - 5)), bound, guest=guest)
        finally:
            self.current_mutation = False

    def init(self):
        require(os.geteuid() == 0, 'camera adapter requires existing root operator context')
        require(self.spec.get('schema') == 'pocket4-final-runtime-input-v1', 'wrong common input schema')
        require(re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,95}', self.spec.get('transaction_id', '')), 'unsafe transaction ID')
        self.component = self.spec['component_inputs']['camera']
        require(set(self.component) == {'probe', 'consumer_manifest', 'service_manifest', 'service_unit', 'host_cli'}, 'wrong camera component fields')
        require(self.component['probe']['sha256'] == APK_SHA, 'camera probe artifact differs')
        require(self.component['consumer_manifest'] == {'path': CONSUMER_PATH, 'sha256': CONSUMER_SHA}, 'consumer manifest pin differs')
        require(self.component['service_manifest']['path'] == '/opt/pocket4-live-camera/manifest.json', 'camera service manifest path differs')
        require(self.component['service_unit']['path'] == UNIT_PATH and self.component['host_cli']['path'] == '/usr/bin/droidloomctl', 'fixed host entry path differs')
        self.r.base = json.loads(self.fw.pinned(self.spec['baseline']))
        require(self.r.base.get('schema') == 'pocket4-final-main-baseline-v1' and
                self.r.base['deployment_manifest'] == self.spec['deployment_manifest'], 'fresh Main baseline/deployment mismatch')
        self.fw.pinned(self.spec['deployment_manifest'])
        require(self.spec['epoch_guard'] == {'path': self.fw.EPOCH_PATH, 'sha256': self.fw.EPOCH_SHA} and
                self.spec['observer_helper'] == {'path': self.fw.OBSERVER_PATH, 'sha256': self.fw.OBSERVER_SHA}, 'common guard/observer pin differs')
        require(self.r.base['init_host_pid'] == self.r.base['main_epoch']['binding']['processes']['init']['host_pid'] and
                set(self.r.base['host_processes']) == {'daemon', 'launcher', 'owner_intermediary', 'presenter'}, 'Main owner chain incomplete')
        self.r.epoch = self.fw.load_module(self.fw.EPOCH_PATH, self.fw.EPOCH_SHA, 'camera_common_epoch')
        lifecycle = self.fw.load_module(self.fw.LIFECYCLE_PATH, self.fw.LIFECYCLE_SHA, 'camera_original_owned_lifecycle')
        def invoke_owned(reaper, factory, *args, **kwargs):
            def marked_factory(*factory_args):
                if self.current_mutation:
                    self.r.attempted = True
                    if self.r.stage == 'command:install_probe':
                        self.install_attempted = True
                    elif self.r.stage == 'command:camera_instrumentation':
                        self.instrument_attempted = True
                    elif self.r.stage == 'command:reload_camera_helper':
                        self.service_restart_attempted = True
                return factory(*factory_args)
            return lifecycle.invoke_owned(reaper, marked_factory, *args, **kwargs)
        self.r.lifecycle = types.SimpleNamespace(OwnChildReaper=lifecycle.OwnChildReaper, invoke_owned=invoke_owned)
        self.consumers = json.loads(self.fw.pinned(self.component['consumer_manifest']))
        self.apk = self.fw.pinned(self.component['probe'], 1024 * 1024)
        service = json.loads(self.fw.pinned(self.component['service_manifest'], 65536))
        require(service.get('source') == 'real_UVC_memory_only' and service.get('sha256') == CAMERA_FILES, 'real UVC artifact set changed')
        for name, expected in CAMERA_FILES.items():
            self.fw.pinned({'path': '/opt/pocket4-live-camera/' + name, 'sha256': expected}, 32 * 1024 * 1024)
        device = os.stat(DEVICE)
        require(stat.S_ISCHR(device.st_mode) and os.path.realpath(DEVICE).startswith('/dev/video'), 'real UVC device unavailable')
        self.device_identity = (device.st_dev, device.st_ino, device.st_rdev)
        self.results['physical_device'] = {'by_id': DEVICE, 'resolved': os.path.realpath(DEVICE),
                                           'filesystem_device': device.st_dev, 'inode': device.st_ino,
                                           'major': os.major(device.st_rdev), 'minor': os.minor(device.st_rdev)}
        _, fd = self.fw.pinned(self.component['host_cli'], 64 * 1024 * 1024, retain=True)
        self.r.verifier_fd = self.r.hold(fd)
        self.r.bind_authorities()
        self.results['input_bindings'] = {'baseline': self.spec['baseline'], 'deployment_manifest': self.spec['deployment_manifest'],
                                         'camera': self.component, 'framework_runtime': {'path': FRAMEWORK_PATH, 'sha256': FRAMEWORK_SHA}}

    def package_rows(self, label, all_users=False):
        before = len(self.r.commands)
        raw = self.invoke(label, package_query_argv(all_users), 10)
        require(len(self.r.commands) == before + 1, 'package query command receipt absent')
        actual_label = self.r.commands[-1]['label']
        # runListPackages may skip an inaccessible user, write stderr, and exit 0.
        # Such an incomplete enumeration must never establish global absence.
        stderr = (self.out / (actual_label + '.stderr')).read_bytes()
        require(stderr == b'', 'package-manager query stderr is not empty')
        return exact_package_lines(raw, all_users=all_users)

    def require_absent(self):
        require(not self.package_rows('package_before_global', all_users=True),
                'diagnostic package exists in global known-package registry; refusing update/removal')
        self.preflight_absent = True

    def stage_apk(self):
        parent = self.r.hold(os.open('/run/user/1000', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC))
        st = os.fstat(parent)
        require(st.st_uid == 1000 and not st.st_mode & 0o022, 'desktop runtime directory ownership differs')
        name = 'pocket4-camera-qualification-' + self.spec['transaction_id']
        os.mkdir(name, 0o700, dir_fd=parent)
        created = os.stat(name, dir_fd=parent, follow_symlinks=False)
        self.host_stage = {'parent': parent, 'name': name, 'directory_identity': (created.st_dev, created.st_ino), 'fd': None, 'apk_fd': None}
        self.cleanup['not_staged'] = False
        directory = self.r.hold(os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=parent))
        self.host_stage['fd'] = directory
        require((os.fstat(directory).st_dev, os.fstat(directory).st_ino) == self.host_stage['directory_identity'], 'private host directory replaced')
        fd = self.r.hold(os.open('probe.apk', os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600, dir_fd=directory))
        self.host_stage['apk_fd'] = fd
        offset = 0
        while offset < len(self.apk):
            count = os.write(fd, self.apk[offset:])
            require(count > 0, 'APK copy made no progress')
            offset += count
        os.fsync(fd)
        os.fchown(fd, 1000, 1000)
        os.fchown(directory, 1000, 1000)
        require(digest(self.fw.read_fd(fd, 1024 * 1024)) == APK_SHA, 'host APK copy differs')
        self.host_apk = '/run/user/1000/' + name + '/probe.apk'

    def service_state(self, label):
        raw = self.invoke(label, ['/usr/bin/systemctl', 'show', UNIT,
            '--property=Id,ActiveState,SubState,MainPID,ControlGroup,InvocationID,FragmentPath,ExecStart'], 10, 65536, guest=False)
        result = dict(line.split('=', 1) for line in raw.decode().splitlines() if '=' in line)
        require(result.get('Id') == UNIT and result.get('FragmentPath') == UNIT_PATH and
                result.get('ControlGroup') == '/system.slice/' + UNIT and
                '/opt/pocket4-live-camera/manager.py' in result.get('ExecStart', ''), 'camera service definition differs')
        return result

    def restart_camera(self):
        before = self.service_state('camera_service_before')
        self.invoke('reload_camera_helper', ['/usr/bin/systemctl', 'restart', UNIT], 25, 65536, guest=False, mutation=True)
        after = self.service_state('camera_service_after')
        require(after.get('ActiveState') == 'active' and after.get('SubState') == 'running', 'camera service did not start')
        require(re.fullmatch('[0-9a-f]{32}', after.get('InvocationID', '')) and after['InvocationID'] != before.get('InvocationID'), 'camera service did not acquire fresh invocation')
        pid = int(after['MainPID'])
        self.manager = self.r.epoch.process_identity(pid)
        require('/opt/pocket4-live-camera/manager.py' in self.manager['cmdline'] and self.manager['uids'] == [0, 0, 0, 0], 'camera manager identity differs')
        self.manager_pidfd = self.r.hold(os.pidfd_open(pid, 0))
        self.r.reaper.protected_pids = self.r.reaper.protected_pids | {pid}
        self.r.reaper.record['protected_pid_count'] = len(self.r.reaper.protected_pids)
        self.invocation = after['InvocationID']
        self.service_restart_confirmed = True
        self.results['camera_service'] = {'before': before, 'after': after, 'manager_identity': self.manager}
        deadline = min(time.monotonic() + 15, self.deadline)
        while True:
            self.guard('camera_ready')
            try:
                fd = os.open('/run/pocket4-live-camera/status.json', os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
                try:
                    status = json.loads(self.fw.read_fd(fd, 65536))
                finally:
                    os.close(fd)
                if (status.get('android_init') == self.r.base['init_host_pid'] and status.get('source') == DEVICE
                        and status.get('transport') == 'live_mjpeg_memory_only' and status.get('capture') == 'on_demand'):
                    self.results['camera_ready_status'] = status
                    break
            except FileNotFoundError:
                pass
            require(time.monotonic() < deadline, 'camera manager did not bind this Main epoch')
            time.sleep(0.2)

    def journal(self, label):
        return self.invoke(label, ['/usr/bin/journalctl', '--no-pager', '--output=json', '--unit=' + UNIT,
            '_SYSTEMD_INVOCATION_ID=' + self.invocation], 10, 4 * 1024 * 1024, guest=False)

    def install(self):
        self.guard('before_install_copy_pin')
        require(digest(self.fw.read_fd(self.host_stage['apk_fd'], 1024 * 1024)) == APK_SHA, 'APK copy changed')
        command = ['/usr/sbin/runuser', '-u', 'alex', '--', '/usr/bin/env', '-u', 'WAYLAND_DISPLAY',
                   '-u', 'DISPLAY', '-u', 'XDG_CURRENT_DESKTOP', 'XDG_RUNTIME_DIR=/run/user/1000',
                   'DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus', '/usr/bin/droidloomctl',
                   '--json', 'install', self.host_apk, '--user', '0']
        response = json.loads(self.invoke('install_probe', command, 130, guest=False, mutation=True))
        require(response.get('ok') is True, 'normal installation was rejected')
        self.install_resolved = True
        self.results['normal_install_response'] = response
        self.verify_installed()

    def verify_installed(self):
        require(self.preflight_absent, 'package ownership preflight absent')
        rows = self.package_rows('installed_package_identity')
        require(len(rows) == 1 and type(rows[0]['uid']) is int and 10000 <= rows[0]['uid'] < 100000, 'installed diagnostic UID differs')
        raw = self.invoke('installed_package_path', ['/system/bin/cmd', 'package', 'path', '--user', '0', PACKAGE], 10)
        paths = [line[len('package:'):] for line in raw.decode().splitlines() if line.startswith('package:')]
        require(len(paths) == 1 and paths[0].startswith('/data/app/') and paths[0].endswith('/base.apk'), 'unexpected installed diagnostic APK path')
        fd = self.r.hold(self.r.open_guest(paths[0]))
        require(digest(self.fw.read_fd(fd, 1024 * 1024)) == APK_SHA, 'installed diagnostic APK bytes differ')
        self.installed_owned = True
        self.install_resolved = True
        self.results['installed_diagnostic'] = {'package': PACKAGE, 'uid': rows[0]['uid'], 'path': paths[0], 'sha256': APK_SHA}

    def run_probe(self):
        before_raw = self.journal('journal_before_probe')
        before = journal_events(before_raw, self.invocation, self.manager['host_pid'], self.r.base['main_epoch']['binding']['boot_id'])
        require(any(row.get('event') == 'generation_started' and row.get('android_init') == self.r.base['init_host_pid'] for row in before), 'camera journal does not bind current Android init')
        require(not any(row.get('event') in ('physical_camera_open', 'live_frames', 'physical_camera_closed') for row in before), 'another camera client already used this fresh service invocation')
        cursors = {row['cursor'] for row in before}
        start_us = time.monotonic_ns() // 1000
        raw = self.invoke('camera_instrumentation', ['/system/xbin/su', '2000', '/system/bin/am', 'instrument',
            '-w', '-r', '--user', '0', PACKAGE + '/.CameraQualification'], 145, mutation=True)
        self.results['android_camera'] = parse_instrumentation(raw)
        self.instrument_completed = True
        close_deadline = min(time.monotonic() + 6, self.deadline)
        last_error = None
        for attempt in range(4):
            after_raw = self.journal('journal_after_probe_%d' % attempt)
            events = [row for row in journal_events(after_raw, self.invocation, self.manager['host_pid'],
                      self.r.base['main_epoch']['binding']['boot_id']) if row['cursor'] not in cursors]
            try:
                self.results['physical_camera'] = physical_cycles(events, start_us, time.monotonic_ns() // 1000)
                break
            except RuntimeError as caught:
                last_error = caught
                if time.monotonic() >= close_deadline or attempt == 3:
                    raise
                time.sleep(0.2)
        require('physical_camera' in self.results, 'physical cycle verification incomplete: ' + str(last_error))
        self.results['instrumentation_started_monotonic_us'] = start_us
        self.results['pixel_files_created'] = 0
        self.guard('camera_final_measurement')

    def cleanup_package(self):
        if not self.install_attempted:
            self.cleanup['package_absent'] = self.preflight_absent
            return
        self.guard('before_package_cleanup')
        if not self.installed_owned:
            rows = self.package_rows('cleanup_package_lookup')
            if not rows:
                self.cleanup['package_absent'] = True
                require(self.install_resolved and not self.r.unknown, 'installation outcome unknown; absence cannot exclude pending install')
                return
            self.verify_installed()
        raw = self.invoke('uninstall_probe', ['/system/bin/cmd', 'package', 'uninstall', PACKAGE], 25, mutation=True)
        require(raw.decode().strip() == 'Success', 'diagnostic package uninstall did not report success')
        self.cleanup['package_uninstalled'] = True
        require(not self.package_rows('package_after_uninstall'), 'diagnostic package remains registered')
        self.cleanup['package_absent'] = True
        self.installed_owned = False

    def cleanup_host_copy(self):
        item = self.host_stage
        if item is None:
            return
        current = os.stat(item['name'], dir_fd=item['parent'], follow_symlinks=False)
        require((current.st_dev, current.st_ino) == item['directory_identity'], 'host probe directory replaced')
        if item['apk_fd'] is not None:
            owned = os.fstat(item['apk_fd'])
            current = os.stat('probe.apk', dir_fd=item['fd'], follow_symlinks=False)
            require((current.st_dev, current.st_ino) == (owned.st_dev, owned.st_ino), 'host APK path replaced')
            os.unlink('probe.apk', dir_fd=item['fd'])
        self.cleanup['host_apk_removed'] = True
        if item['fd'] is not None:
            require(os.listdir(item['fd']) == [], 'unexpected host probe directory entries')
        os.rmdir(item['name'], dir_fd=item['parent'])
        self.cleanup['host_directory_removed'] = True

    def run(self):
        error = None
        secondary = []
        try:
            self.init()
            self.require_absent()
            self.stage_apk()
            self.restart_camera()
            self.install()
            self.run_probe()
        except BaseException as caught:
            error = {'stage': self.r.stage, 'type': type(caught).__name__, 'message': str(caught), 'errno': getattr(caught, 'errno', None)}
            self.r.unknown |= bool(getattr(caught, 'outcome_unknown', False))
            if self.r.attempted and self.r.stage.startswith('guard:'):
                self.r.unknown = True
            if (self.instrument_attempted and not self.instrument_completed) or (self.service_restart_attempted and not self.service_restart_confirmed):
                self.r.unknown = True
        finally:
            self.cleanup_deadline = time.monotonic() + 40
            for name, action in [('uninstall_own_package', self.cleanup_package), ('remove_own_host_copy', self.cleanup_host_copy)]:
                try:
                    action()
                except BaseException as caught:
                    secondary.append({'stage': name, 'type': type(caught).__name__, 'message': str(caught)})
                    self.r.unknown |= self.r.attempted
            if error is None and not secondary:
                try:
                    self.guard('camera_final_after_cleanup')
                except BaseException as caught:
                    secondary.append({'stage': 'final_epoch_guard', 'type': type(caught).__name__, 'message': str(caught)})
                    self.r.unknown |= self.r.attempted
            if self.r.reaper is not None:
                try:
                    self.r.reaper.finish()
                except BaseException as caught:
                    secondary.append({'stage': 'owned_lifecycle_finish', 'type': type(caught).__name__, 'message': str(caught)})
                    self.r.unknown |= self.r.attempted
                self.results['subreaper'] = self.r.reaper.record
            close_errors = []
            for fd in reversed(self.r.fds):
                try:
                    os.close(fd)
                except OSError as caught:
                    close_errors.append({'fd': fd, 'errno': caught.errno})
            self.r.unknown |= bool(close_errors and self.r.attempted)
            success = error is None and not secondary and not close_errors and self.cleanup['package_absent'] and self.cleanup['host_directory_removed']
            self.results.update({'success': success, 'runtime_qualified': success, 'action_attempted': self.r.attempted,
                'outcome_unknown': self.r.unknown, 'error': error, 'secondary_errors': secondary, 'cleanup': self.cleanup,
                'commands': self.r.commands, 'guards': self.r.guards, 'all_held_authorities_closed': not close_errors,
                'close_errors': close_errors, 'finished_monotonic_ns': time.monotonic_ns()})
            self.fw.write_json(self.out / 'result.json', self.results)
        return 0 if self.results['success'] else (4 if self.r.unknown else (3 if self.r.attempted else 2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    output = args.output.absolute()
    require(output.parent.resolve().is_relative_to(ROOT.resolve()), 'output must be fresh under final/camera')
    output.mkdir(mode=0o700)
    raw = args.input.read_bytes()
    require(len(raw) <= 1024 * 1024, 'common input too large')
    (output / 'input.json').write_bytes(raw)
    runner = CameraRunner(json.loads(raw), output)
    code = runner.run()
    print(json.dumps({'result': str(output / 'result.json'), 'success': runner.results['success'],
                      'outcome_unknown': runner.results['outcome_unknown'], 'exit_code': code}))
    return code


if __name__ == '__main__':
    sys.exit(main())
