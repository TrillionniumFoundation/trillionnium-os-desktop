#!/usr/bin/python3 -I
"""Read current installed Clock identity/audio and saved expiry evidence; no UI or writes to Android."""
from pathlib import Path
from datetime import datetime, timezone
import argparse, hashlib, json, os, re, types

ROOT = Path('/home/alex/work/pocket4-clock-foreground-timer-20261105-r12-01')
OUT = ROOT / 'after-expiry02-read01'
EXPIRY = Path('/home/alex/work/pocket4-clock-timer-expiry-20261105-r12-02')
INSTALLER = ROOT / 'transaction02/clock_install02.py'
INSTALLER_SHA = '256587c900380cfffbfd7daaf66586630654c8125185d82d058f7455624b2707'
EXPIRY_RESULT = Path('/home/alex/work/pocket4-clock-session-tools-20261105-r12-01/clock-timer-expiry02-result.json')
EXPIRY_SHA = '61f2bd63c63f637d858417e89f831bceb107d23432ed4815e0e77a8b5299d0cb'
POST_INSTALL_SHA = '0f7faef704da224ba669f688862cfadef0009e890000ad9c13a0cffa4f9d9807'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load_installer():
    raw = INSTALLER.read_bytes()
    if sha(raw) != INSTALLER_SHA:
        raise RuntimeError('FROZEN_INSTALL_READER_CHANGED')
    module = types.ModuleType('read_only_clock_install02')
    module.__file__ = str(INSTALLER)
    exec(compile(raw, str(INSTALLER), 'exec'), module.__dict__)
    return module


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps({'state':'INERT','UI_actions':0,'Android_writes':0}))
        return 0
    if os.geteuid() != 0:
        raise RuntimeError('ROOT_HELD_READER_REQUIRED')
    install = load_installer()
    model, tx, timers = install.modules()
    expiry_raw = tx.read_regular(EXPIRY_RESULT, EXPIRY_SHA)
    expiry = json.loads(expiry_raw)
    before_raw = tx.read_regular(ROOT/'install-02/commands/after.json', POST_INSTALL_SHA)
    before = json.loads(before_raw)
    OUT.mkdir(mode=0o750)
    os.chown(OUT, 0, 1000)
    os.chmod(OUT, 0o750)
    result = {'state':'READ_STARTED','UI_actions':0,'Android_writes':0,
        'global_volume_or_ringtone_actions':0,'package_install_calls':0,
        'started_utc':datetime.now(timezone.utc).isoformat(),
        'source_sha256':sha(Path(__file__).read_bytes()),
        'expiry02_original_sha256':EXPIRY_SHA,'expiry02_original_state':expiry['state'],
        'expiry02_original_error':expiry['error'],'post_install_snapshot_sha256':POST_INSTALL_SHA}
    try:
        files = {}
        selected = {}
        names = {
            'expired-notifications.txt':expiry['notifications']['expired']['sha256'],
            'actual-expired-services-private.txt':expiry['runtime_observations']['actual-expired']['commands']['services']['sha256'],
            'after-owned-close-services-private.txt':expiry['runtime_observations']['after-owned-close']['commands']['services']['sha256'],
        }
        for name, expected in names.items():
            raw = tx.read_regular(EXPIRY/name, expected)
            files[name] = tx.write_new(OUT/('saved-'+name), raw, alex_readable=True)
            text = raw.decode('utf-8','strict')
            if name == 'expired-notifications.txt':
                selected[name] = [line for line in text.splitlines() if re.search(
                    r'NotificationRecord|pkg=|uid=|user=|id=2147483644|fullScreen|Fullscreen|fullscreen|FullScreen|channel=|mId=|mImportance|mSound|mVibration|mDeleted|mUserLocked|mBypassDnd|sound=|vibrat|importance=|mAllowFgs|mUseFullScreen|mPermission',line)]
            else:
                selected[name] = text.splitlines()
        result['saved_evidence_files'] = files
        result['selected_saved_evidence'] = selected
        with tx.CameraSession(OUT/'commands') as session:
            current = install.snapshot(session,tx,model,timers,'current')
            install.require(current['apk']['sha256'] == install.NEW_SHA
                and current['apk']['bytes'] == install.NEW_BYTES,'CURRENT_INSTALLED_CANDIDATE_DIFFERS')
            captured, _ = session.target.read_file(current['apk']['guest_path'],16*1024*1024,single_link=True)
            install.require(sha(captured) == install.NEW_SHA,'APK_CHANGED_DURING_READBACK')
            installed_copy = OUT/'actual-installed.apk'
            tx.write_new(installed_copy,captured)
            install.verify_signature(session,tx,installed_copy,'actual-installed-signature')
            package = tx.read_regular(session.journal_dir/'current-package.txt').decode()
            active = re.findall(r'^Packages:\n(.*?)(?=^\S|\Z)',package,re.M|re.S)
            install.require(len(active) == 1,'ONE_ACTIVE_PACKAGE_REQUIRED')
            versions = re.findall(r'^    versionName=(.*)$',active[0],re.M)
            install.require(versions == ['17'],'CURRENT_VERSION_NAME_CHANGED')
            checks = {key:before.get(key) == current.get(key) for key in (
                'package','epoch_sha256','identity','directories','alarm_state','alarm_content_sha256',
                'timer_and_stopwatch_empty','notification_appop_allow','sound_state')}
            result['current_snapshot'] = current
            result['post_install_comparisons'] = checks
            result['preferences_hash_same_as_post_install'] = before['preferences_sha256'] == current['preferences_sha256']
            # Other apps may now use the UI; original expiry task restoration remains separately preserved.
            result['tasks_hash_same_as_post_install'] = before['tasks_sha256'] == current['tasks_sha256']
            result['latest_installed_identity'] = {'package':install.PACKAGE,'uid':current['identity']['uid'],
                'user_id':0,'version_code':current['identity']['version'],'version_name':versions[0],
                'epoch_sha256':session.epoch_sha256,'apk_path':current['apk']['guest_path'],
                'apk_bytes':len(captured),'apk_sha256':sha(captured),'certificate_sha256':tx.CERT_SHA,
                'v3_signature_verified':True,'evidence_kind':'live_pm_path_package_and_held_apk_bytes_plus_certificate_verify',
                'observed_utc':datetime.now(timezone.utc).isoformat()}
            session.caller_status('after-expiry-readonly-final-caller')
            session.guard()
            result['state'] = 'READ_VERIFIED' if all(checks.values()) else 'CURRENT_STATE_DIFFERENCES_OBSERVED'
    except BaseException as error:
        result['state'] = 'READ_FAILED'
        result['error'] = type(error).__name__+': '+str(error)
    result['finished_utc'] = datetime.now(timezone.utc).isoformat()
    output = tx.write_new(OUT/'result.json', result, alex_readable=True)
    print(json.dumps({'state':result['state'],'error':result.get('error'),'result':output,
        'latest_installed_identity':result.get('latest_installed_identity'),
        'comparisons':result.get('post_install_comparisons'),
        'UI_actions':0,'Android_writes':0},sort_keys=True))
    return 0 if result['state'] == 'READ_VERIFIED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
