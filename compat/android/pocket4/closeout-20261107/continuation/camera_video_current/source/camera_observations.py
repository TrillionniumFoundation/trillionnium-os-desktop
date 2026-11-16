"""Exact source-derived observations; no historical runtime constructors.

Functions run only when explicitly called by the new bounded Camera case.
Importing this module performs no file, DBus, process or Android operation.
"""
import json
import os
from pathlib import Path
import re
import stat

PACKAGE = 'com.android.camera2'
UID = 10062
VERSION = 20002000
PERMISSIONS = frozenset({'android.permission.POST_NOTIFICATIONS', 'android.permission.CAMERA',
    'android.permission.RECORD_AUDIO', 'android.permission.ACCESS_FINE_LOCATION',
    'android.permission.ACCESS_COARSE_LOCATION'})
OWNER_LOCK = Path('/run/pocket4-live-camera/owner.lock')
DEVICE = Path('/dev/v4l/by-id/usb-SunplusIT_Inc_Integrated_Camera_JX20250923V2-video-index0')
USB = Path('/sys/bus/usb/devices/3-4')


def require(ok, reason):
    if not ok:
        raise RuntimeError(reason)

def parse_identity(package_dump, guest_path):
    """Only the active package section; the factory copy is not installed state."""
    sections = re.findall(r'^Packages:\n(.*?)(?=^\S|\Z)', package_dump, re.M | re.S)
    require(len(sections) == 1, 'ACTIVE_PACKAGE_SECTION_AMBIGUOUS')
    block = sections[0]
    require(re.findall(r'^  Package \[([^]]+)\]', block, re.M) == [PACKAGE], 'CAMERA_ACTIVE_PACKAGE_REQUIRED')

    def one(pattern, text=block):
        values = re.findall(pattern, text, re.M)
        require(len(values) == 1, 'ACTIVE_PACKAGE_FIELD_AMBIGUOUS')
        return values[0]

    user = one(r'^    User 0: (.*)$')
    require('installed=true' in user and 'hidden=false' in user and 'suspended=false' in user,
            'CAMERA_USER_STATE_INVALID')
    permissions = re.findall(r'^        (android\.permission\.[A-Z_]+): granted=(true|false), flags=\[(.*?)\]$', block, re.M)
    require(len(permissions) == len(PERMISSIONS) and {x[0] for x in permissions} == PERMISSIONS,
            'CAMERA_PERMISSION_SET_DIFFERS')
    value = {'uid': int(one(r'^    appId=(\d+)$')),
             'ce_inode': int(one(r'^ceDataInode=(\d+)', user)),
             'de_inode': int(one(r'\bdeDataInode=(\d+)', user)),
             'version': int(one(r'^    versionCode=(\d+) minSdk=37 targetSdk=1000$')),
             'data_dir': one(r'^      dataDir=(.*)$'),
             'first_install_time': one(r'^      firstInstallTime=(.*)$'),
             'runtime_permissions': {p: {'granted': g == 'true', 'flags': f} for p, g, f in permissions}}
    require(value['uid'] == UID and value['version'] == VERSION and
            value['data_dir'] == '/data/user/0/' + PACKAGE, 'CAMERA_IDENTITY_DIFFERS')
    require(str(Path(guest_path).parent) == one(r'^    codePath=(.*)$'), 'APK_PATH_AND_PACKAGE_DIFFER')
    return value

def provider_owner():
    """Read lock identity only. Never flock, open for write, or signal its owner."""
    item = OWNER_LOCK.stat()
    owners = []
    for line in Path('/proc/locks').read_text().splitlines():
        match = re.fullmatch(r'\d+:\s+FLOCK\s+ADVISORY\s+WRITE (\d+) ([0-9a-f]+):([0-9a-f]+):(\d+) 0 EOF', line)
        if match and (int(match[2], 16), int(match[3], 16), int(match[4])) == (
                os.major(item.st_dev), os.minor(item.st_dev), item.st_ino):
            owners.append(int(match[1]))
    require(len(owners) == 1 and owners[0] > 1, 'PROVIDER_OWNER_UNKNOWN')
    pid = owners[0]
    raw = Path('/proc/%d/stat' % pid).read_text()
    return {'device': item.st_dev, 'inode': item.st_ino, 'pid': pid,
            'start_ticks': int(raw[raw.rfind(')') + 2:].split()[19])}

def focus_metadata(raw):
    focus_lines = [line.strip() for line in raw.splitlines() if 'mCurrentFocus=' in line]
    app_lines = [line.strip() for line in raw.splitlines() if 'mFocusedApp=' in line]
    focus = re.findall('mCurrentFocus=Window\\{([0-9a-fA-F]+)\\s+u(\\d+)\\s+([A-Za-z0-9_.]+)/([A-Za-z0-9_.$]+)', raw)
    app = re.findall('mFocusedApp=ActivityRecord\\{[^\\n]*?\\bu(\\d+)\\s+([A-Za-z0-9_.]+)/([A-Za-z0-9_.$]+)\\s+t(\\d+)\\b', raw)
    if len(set(focus_lines)) != 1 or len(set(app_lines)) != 1 or len(set(focus)) != 1 or (len(set(app)) != 1):
        return {'verified': False, 'reason': 'FOCUS_OR_ACTIVITY_NOT_UNIQUE', 'focus_lines': focus_lines + app_lines}
    token, user, package, activity = focus[0]
    app_user, app_package, app_activity, task = app[0]
    return {'verified': user == app_user == '0' and package == app_package, 'package': package, 'activity': activity, 'window_token': token.lower(), 'focused_activity': app_activity, 'task': int(task), 'user': int(user)}

def physical_identity():
    named = DEVICE.lstat()
    require(stat.S_ISLNK(named.st_mode), 'fixed camera by-id is not a symlink')
    target = DEVICE.resolve(strict=True)
    require(target.parent == Path('/dev') and target.name.startswith('video') and
            target.name[5:].isdecimal(), 'fixed camera target is not a video node')
    node = target.stat()
    require(stat.S_ISCHR(node.st_mode), 'fixed camera target is not a character device')
    usb = USB.resolve(strict=True)
    sys_video = (Path('/sys/class/video4linux') / target.name / 'device').resolve(strict=True)
    require(sys_video.is_relative_to(usb), 'video node is not on built-in USB port 3-4')
    attributes = {key: (USB / key).read_text().strip()
                  for key in ('idVendor', 'idProduct', 'serial', 'devnum')}
    require((attributes['idVendor'], attributes['idProduct'], attributes['serial']) ==
            ('1e08', '5520', 'JX20250923V2'), 'built-in Sunplus USB identity differs')
    return {'by_id': str(DEVICE), 'target': str(target), 'device': node.st_dev,
            'inode': node.st_ino, 'rdev': node.st_rdev, 'symlink_inode': named.st_ino,
            'usb_path': str(usb), 'video_sysfs': str(sys_video), 'usb': attributes}

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

def make_physical_cycles():
    DEVICE = str(globals()['DEVICE'])
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
    return physical_cycles

physical_cycles = make_physical_cycles()

