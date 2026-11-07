#!/usr/bin/python3 -I
"""Read Clock-specific notification prerequisites; no launch, grant or setting write."""
from pathlib import Path
from datetime import datetime, timezone
import argparse, hashlib, json, re, types

HERE = Path(__file__).resolve().parent
ROOT = Path('/home/alex/work/pocket4-clock-notification-read-20261105-r12-01')
PACKAGE = 'com.android.deskclock'
MODEL_SHA = 'fd3ffdfbb397b561bf251236c117966ea18b2ca176e4908c6a31ad0db4cc0048'
ACTION = 'android.settings.APP_NOTIFICATION_SETTINGS'


def require(value, reason):
    if not value:
        raise RuntimeError(reason)


def model():
    path = HERE / 'read_clock.py'; raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == MODEL_SHA, 'CLOCK_READER_CHANGED')
    value = types.ModuleType('notification_private_clock_reader'); value.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), value.__dict__)
    return value


def permission(dump):
    blocks = re.findall(r'^Packages:\n(.*?)(?=^\S|\Z)', dump, re.M | re.S)
    require(len(blocks) == 1, 'ONE_ACTIVE_PACKAGE_SECTION_REQUIRED')
    found = re.findall(r'^        android\.permission\.POST_NOTIFICATIONS: granted=(true|false), flags=\[([^\]]*)\]',
                       blocks[0], re.M)
    require(len(found) == 1, 'EXACT_NOTIFICATION_PERMISSION_FLAGS_REQUIRED')
    granted, raw_flags = found[0]
    flags = sorted(flag.strip() for flag in raw_flags.split('|') if flag.strip())
    return {'granted': granted == 'true', 'flags': flags,
        'observed_user_decision_flag': any(x in flags for x in ('USER_SET', 'USER_FIXED')),
        'policy_fixed': any(x in flags for x in ('POLICY_FIXED', 'SYSTEM_FIXED'))}


def collect():
    reader = model(); tx = reader.load_session()
    result = {'state': 'READ_ONLY_METADATA_COLLECTED', 'UI_actions': 0, 'permission_writes': 0,
        'alarm_writes': 0, 'timer_writes': 0, 'global_sound_writes': 0,
        'source_pin': MODEL_SHA, 'started_utc': datetime.now(timezone.utc).isoformat()}
    ROOT.mkdir(mode=0o700)
    with tx.CameraSession(ROOT / 'commands') as session:
        result['identity_before'] = reader.identity(session)
        raw = session.android(['/system/bin/dumpsys', 'package', PACKAGE]).decode('utf-8', 'strict')
        result['permission'] = permission(raw)
        require(result['permission']['granted'] == result['identity_before']['notifications_granted'],
                'PERMISSION_SNAPSHOT_CHANGED')
        # Resolving an Intent is read-only. Do not launch a component inferred
        # from an upstream manifest or silently navigate a generic Settings page.
        argv = ['/system/bin/cmd', 'package', 'resolve-activity', '--brief', '--user', '0',
            '-a', ACTION, '-p', 'com.android.settings',
            '--es', 'android.provider.extra.APP_PACKAGE', PACKAGE, '--ei', 'app_uid', '10063']
        resolved = session.android(argv).decode('utf-8', 'strict').strip()
        result['notification_settings_resolution'] = {'intent_action': ACTION,
            'target_app_package': PACKAGE, 'target_app_uid': 10063, 'raw_component': resolved,
            'expected_component': 'com.android.settings/.Settings$AppNotificationSettingsActivity',
            'matches_expected_component': resolved in (
                'com.android.settings/.Settings$AppNotificationSettingsActivity',
                'com.android.settings/com.android.settings.Settings$AppNotificationSettingsActivity')}
        appop = session.android(['/system/bin/cmd', 'appops', 'get', '--user', '0', PACKAGE,
                                 'POST_NOTIFICATION']).decode('utf-8', 'strict')
        tx.write_new(ROOT / 'clock-post-notification-appop.txt', appop.encode())
        result['appop_text'] = appop.strip()
        # Official NotificationManagerService accepts this package filter. Keep
        # default redaction and private raw output; no notification content is
        # copied into the public result or any action selector.
        notifications = session.android(['/system/bin/dumpsys', 'notification', '--package', PACKAGE], 15)
        tx.write_new(ROOT / 'clock-notification-redacted.txt', notifications)
        result['private_notification_dump'] = {'bytes': len(notifications),
            'sha256': hashlib.sha256(notifications).hexdigest(), 'redaction_disabled': False,
            'exact_package_filter': PACKAGE}
        result['identity_after'] = reader.identity(session)
        require(result['identity_before'] == result['identity_after'], 'CLOCK_IDENTITY_CHANGED_DURING_READ')
        result['epoch_sha256'] = session.epoch_sha256
        result['finished_utc'] = datetime.now(timezone.utc).isoformat()
        result['actual_UI_control_observed'] = False
        result['permission_change_qualified'] = False
        session.caller_status('clock-notification-read-final-caller')
        tx.write_new(ROOT / 'result.json', result)
        tx.write_new(HERE / 'clock-notification-preflight01-result.json', result, alex_readable=True)
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--collect', action='store_true')
    if parser.parse_args().collect:
        collect()
    else:
        print(json.dumps({'state': 'PLAN_ONLY', 'UI_actions': 0, 'permission_writes': 0}))
