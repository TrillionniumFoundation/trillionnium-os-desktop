#!/usr/bin/python3 -I
"""One Clock-only update or exact APK rollback; default inert, no app-data writes."""
from pathlib import Path
from datetime import datetime, timezone
import argparse, hashlib, io, json, os, re, stat, time, types, zipfile

ROOT = Path('/home/alex/work/pocket4-clock-foreground-timer-20261105-r12-01')
RUN = ROOT / 'install-01'
CLOCK = Path('/home/alex/work/pocket4-clock-session-tools-20261105-r12-01')
CANDIDATE = ROOT / 'build/DeskClock-pocket4-foreground-timer.apk'
OLD_SHA = 'ded49b00e5045bdd184c2a4f09b1b8650ce8f708134ac9f0f8c4cf0594bb0fae'
NEW_SHA = 'cc7eece9d0429267d1950f0ca9287b041493bc5c05602ffc2119e1866381fb73'
OLD_BYTES, NEW_BYTES = 7449572, 7593129
PACKAGE, UID, VERSION = 'com.android.deskclock', 10063, 37
FACTORY = '/product/app/DeskClock/DeskClock.apk'
MODEL_SHA = 'fd3ffdfbb397b561bf251236c117966ea18b2ca176e4908c6a31ad0db4cc0048'
TIMER_SHA = 'c3bf02f38e05ab7a55285ca2245ffe2bda3eb528cc1f85d54723294047948b08'
BUILD_SHA = 'cdc31d06f7d43cb9e6de5a7a67bbbc89301b6c4456b644e3b8dcb79ec5a6394a'
ALARM_SHA = '655c545ee9487dc380100d6300376d0bb82d0d12beddd96f283ab7814ff19fea'
SOUND_KEYS = ('volume_alarm','volume_ring','volume_notification','volume_music',
              'alarm_alert','notification_sound','ringtone')


def require(value, reason):
    if not value:
        raise RuntimeError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def load(path, expected):
    raw = path.read_bytes(); require(sha(raw) == expected, 'FROZEN_READER_CHANGED')
    module = types.ModuleType('clock_install_' + path.stem); module.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    return module


def modules():
    model = load(CLOCK/'read_clock.py', MODEL_SHA)
    return model, model.load_session(), load(CLOCK/'read_timer.py', TIMER_SHA)


def parse_identity(text, guest):
    blocks = re.findall(r'^Packages:\n(.*?)(?=^\S|\Z)', text, re.M | re.S)
    require(len(blocks) == 1, 'ONE_ACTIVE_CLOCK_PACKAGE_REQUIRED')
    block = blocks[0]
    require(re.findall(r'^  Package \[([^]]+)\]', block, re.M) == [PACKAGE], 'ACTIVE_PACKAGE_IS_NOT_CLOCK')
    def one(pattern, source=block):
        values = re.findall(pattern, source, re.M)
        require(len(values) == 1, 'CLOCK_PACKAGE_FIELD_AMBIGUOUS:' + pattern)
        return values[0]
    user = one(r'^    User 0: (.*)$')
    require('installed=true' in user and 'hidden=false' in user and 'suspended=false' in user, 'CLOCK_USER_STATE_CHANGED')
    version = one(r'^    versionCode=(\d+) minSdk=(\d+) targetSdk=(\d+)$')
    require(version == ('37','37','30'), 'CLOCK_VERSION_OR_SDK_CHANGED')
    permissions = re.findall(r'^        (android\.permission\.[A-Z_]+): granted=(true|false), flags=\[(.*?)\]$', block, re.M)
    require(permissions and len(permissions) == len({x[0] for x in permissions}), 'CLOCK_PERMISSION_SET_AMBIGUOUS')
    perms = {p:{'granted':g == 'true','flags':f} for p,g,f in permissions}
    require(perms.get('android.permission.POST_NOTIFICATIONS',{}).get('granted') is True,
            'CLOCK_NOTIFICATION_REPAIR_NOT_PRESENT')
    result = {'uid':int(one(r'^    appId=(\d+)$')), 'version':37, 'min_sdk':37, 'target_sdk':30,
        'ce_inode':int(one(r'\bceDataInode=(\d+)',user)), 'de_inode':int(one(r'\bdeDataInode=(\d+)',user)),
        'data_dir':one(r'^      dataDir=(.*)$'), 'first_install_time':one(r'^      firstInstallTime=(.*)$'),
        'runtime_permissions':perms}
    require(result['uid'] == UID and result['data_dir'] == '/data/user/0/' + PACKAGE, 'CLOCK_UID_OR_DATA_PATH_CHANGED')
    require(str(Path(guest).parent) == one(r'^    codePath=(.*)$'), 'CLOCK_ACTIVE_APK_PATH_MISMATCH')
    return result


def appop_allow(raw):
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    matches = [re.fullmatch(r'(?:Uid mode: )?POST_NOTIFICATION: ([a-z_]+)(?:;[^\n]*)?',line) for line in lines]
    modes = [match[1] for match in matches if match is not None]
    return (len(lines) in (1,2) and len(modes) == len(lines) and all(x == 'allow' for x in modes)
            or lines == ['No operations.','Default mode: allow'])


def audio_streams(raw):
    values = {}
    lines = raw.splitlines()
    for index,line in enumerate(lines):
        if not re.match(r'^[ \t]*- STREAM_',line):
            continue
        # Actual AudioService dump: "- STREAM_SYSTEM (aliased to: STREAM_RING):".
        # Each stream block ends with its own blank line, before volume groups.
        match = re.fullmatch(r'[ \t]*- (STREAM_[A-Z0-9_]+)(?: \(aliased to: (STREAM_[A-Z0-9_]+)\))?:',line)
        require(match is not None, 'AUDIO_STREAM_HEADER_UNRECOGNIZED')
        fields = []
        for child in lines[index+1:]:
            if not child.strip():
                break
            require(child.startswith('   '), 'AUDIO_STREAM_BOUNDARY_CHANGED')
            if re.match(r'^\s*(Muted(?: Internally)?|Min|Max|streamVolume|Current):',child):
                fields.append(child.strip())
        require(match[1] not in values, 'AUDIO_STREAM_DUPLICATE')
        values[match[1]] = {'alias':match[2],'fields':fields}
    require({'STREAM_ALARM','STREAM_RING','STREAM_MUSIC','STREAM_NOTIFICATION'} <= set(values),
            'ACTUAL_SOUND_STREAMS_NOT_OBSERVED')
    for item in values.values():
        fields = item['fields']
        require(all(sum(line.startswith(key + ':') for line in fields) == 1
                    for key in ('Muted','Muted Internally','Min','Max','Current'))
            and sum(line.startswith('streamVolume:') for line in fields) <= 1,
                'AUDIO_VOLUME_FIELDS_AMBIGUOUS')
    return values


def snapshot(session, tx, model, timers, label):
    lines = session.android(['/system/bin/pm','path',PACKAGE]).decode().splitlines()
    require(len(lines) == 1 and lines[0].startswith('package:'), 'ONE_ACTIVE_CLOCK_APK_REQUIRED')
    guest = lines[0][len('package:'):]
    require(guest == FACTORY or re.fullmatch(r'/data/app/[A-Za-z0-9_~+\.=-]+(?:/[A-Za-z0-9_~+\.=-]+)?/base\.apk',guest),
            'CLOCK_CODE_PATH_UNEXPECTED')
    package = session.android(['/system/bin/dumpsys','package',PACKAGE])
    tx.write_new(session.journal_dir/(label+'-package.txt'),package)
    identity = parse_identity(package.decode(),guest)
    apk,_ = session.target.read_file(guest,16*1024*1024,single_link=guest != FACTORY)
    directories = {}
    for key,path in [('ce','/data/user/0/'+PACKAGE),('de','/data/user_de/0/'+PACKAGE)]:
        fd = session.target.open_root(path,os.O_PATH|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            st = os.fstat(fd)
            directories[key] = {'device':st.st_dev,'inode':st.st_ino,'uid':st.st_uid,
                                'gid':st.st_gid,'mode':stat.S_IMODE(st.st_mode)}
        finally:
            os.close(fd)
        require(st.st_uid == st.st_gid == UID and st.st_ino == identity[key+'_inode'], 'CLOCK_DATA_DIRECTORY_CHANGED')
    alarms = model.state(session); model.verify_before(alarms)
    require(model.baseline_ids(alarms) == {1,2}, 'ORIGINAL_ALARM_SET_CHANGED')
    script = ('set -o pipefail; /system/bin/sqlite3 -readonly -json '+model.DB
        + " 'PRAGMA query_only=ON;BEGIN;SELECT * FROM alarm_templates ORDER BY _id;ROLLBACK;'"
        + ' | /system/bin/sha256sum')
    argv = ['/system/bin/env','-i']+[k+'='+session.environment[k] for k in sorted(session.environment)]
    argv += ['/system/bin/timeout','-k','2','12','/system/bin/sh','-c',script]
    with session.target.entry(argv) as (command,descriptors):
        value = session.run_host('clock-install-alarm-digest',command,16,descriptors)
    require(value['rc'] == 0 and value['joined'] and not value['timed_out']
        and value['stdout'].decode().strip() == ALARM_SHA+'  -', 'ORIGINAL_ALARM_CONTENT_CHANGED')
    preferences,_ = session.target.read_file(timers.PREFS,2*1024*1024)
    timer_state = timers.parse(preferences); timers.empty(timer_state)
    op = session.android(['/system/bin/cmd','appops','get','--user','0',PACKAGE,'POST_NOTIFICATION']).decode()
    require(appop_allow(op), 'CLOCK_NOTIFICATION_APPOP_NOT_ALLOW')
    tx.write_new(session.journal_dir/(label+'-notification-appop.txt'),op.encode())
    audio = session.android(['/system/bin/dumpsys','audio']).decode()
    tx.write_new(session.journal_dir/(label+'-audio-private.txt'),audio.encode())
    sounds = {'streams':audio_streams(audio),'settings':{}}
    for key in SOUND_KEYS:
        sounds['settings'][key] = session.android(['/system/bin/settings','--user','0','get','system',key]).decode().strip()
    tasks = session.android(['/system/bin/cmd','activity','stack','list']).decode()
    require(PACKAGE not in tasks, 'CLOCK_TASK_ALREADY_PRESENT')
    tx.write_new(session.journal_dir/(label+'-tasks.txt'),tasks.encode())
    session.guard()
    result = {'package':PACKAGE,'epoch_sha256':session.epoch_sha256,'identity':identity,'directories':directories,
        'alarm_state':alarms,'alarm_content_sha256':ALARM_SHA,'preferences_sha256':sha(preferences),
        'timer_and_stopwatch_empty':True,'notification_appop_allow':True,'sound_state':sounds,'tasks_sha256':sha(tasks.encode()),
        'apk':{'guest_path':guest,'bytes':len(apk),'sha256':sha(apk)}}
    tx.write_new(session.journal_dir/(label+'.json'),result)
    return result


def preserved(before,after,include_preferences=True,include_tasks=True):
    keys = ['package','epoch_sha256','identity','directories','alarm_state','alarm_content_sha256',
            'timer_and_stopwatch_empty','notification_appop_allow','sound_state']
    if include_tasks:
        keys.append('tasks_sha256')
    if include_preferences:
        keys.append('preferences_sha256')
    return all(before.get(k) == after.get(k) for k in keys)


def verify_payload(original,candidate):
    def keep(name):
        return name.upper() != 'META-INF/MANIFEST.MF' and re.fullmatch(r'META-INF/[^/]+\.(SF|RSA|DSA|EC)',name,re.I) is None
    with zipfile.ZipFile(io.BytesIO(original)) as a,zipfile.ZipFile(io.BytesIO(candidate)) as b:
        require(a.testzip() is None and b.testzip() is None and len(a.namelist()) == len(set(a.namelist()))
            and len(b.namelist()) == len(set(b.namelist())), 'APK_ZIP_INVALID')
        names = {n for n in a.namelist() if keep(n)}
        require(names == {n for n in b.namelist() if keep(n)} and len(names) == 1281, 'CLOCK_APK_PAYLOAD_SET_CHANGED')
        changed = [n for n in sorted(names) if a.read(n) != b.read(n)]
        require(changed == ['classes.dex'] and sha(b.read('classes.dex')) ==
            '8b7f0094b816a758d86599ba9c19866314dbb37cf78f57187a8602c2f3e3b77b', 'CLOCK_PAYLOAD_CHANGE_EXCEEDS_REVIEW')


def update():
    model,tx,timers = modules()
    with tx.ui_lock():
        root_stat = ROOT.lstat()
        require(stat.S_ISDIR(root_stat.st_mode) and root_stat.st_uid == 0
                and root_stat.st_gid == 1000 and stat.S_IMODE(root_stat.st_mode) == 0o750,
                'OWNED_INSTALL_ROOT_NOT_READABLE_BY_CALLER')
        RUN.mkdir(mode=0o750); os.chown(RUN,0,1000); os.chmod(RUN,0o750)
        result = {'state':'NOT_DISPATCHED','package':PACKAGE,'old_sha256':OLD_SHA,'new_sha256':NEW_SHA,
            'automatic_retry':False,'UI_actions':0,'app_data_write_commands':0,'production_ready':False,
            'started_utc':datetime.now(timezone.utc).isoformat()}
        tx.write_new(RUN/'claim.json',result)
        try:
            require(re.fullmatch('[0-9a-f]{64}',BUILD_SHA), 'ACTUAL_BUILD_RESULT_NOT_PINNED')
            build = json.loads(tx.read_regular(ROOT/'build/result.json',BUILD_SHA))
            require(build['state'] == 'SIGNED_OFFLINE_CANDIDATE_VERIFIED' and build['candidate_apk']['sha256'] == NEW_SHA
                and build['inputs_tools_and_clock_state_unchanged'] is True, 'OFFLINE_CANDIDATE_NOT_VERIFIED')
            with tx.CameraSession(RUN/'commands') as session:
                before = snapshot(session,tx,model,timers,'before')
                require(before['apk']['sha256'] == OLD_SHA and before['apk']['bytes'] == OLD_BYTES, 'EXACT_CLOCK_PREIMAGE_REQUIRED')
                original,_ = session.target.read_file(before['apk']['guest_path'],16*1024*1024)
                require(sha(original) == OLD_SHA, 'CLOCK_CHANGED_BEFORE_BACKUP')
                candidate = tx.read_regular(CANDIDATE,NEW_SHA)
                require(len(candidate) == NEW_BYTES, 'CLOCK_CANDIDATE_SIZE_CHANGED')
                verify_payload(original,candidate)
                backup,staged = RUN/'DeskClock-original-before.apk',RUN/'DeskClock-candidate.apk'
                tx.write_new(backup,original,alex_readable=True);tx.write_new(staged,candidate,alex_readable=True)
                tx.read_regular('/usr/bin/apksigner','52947059a664b85f0475bcdc3dbbe6089b50f8f59e3aa051e6e74cf0ba7db70f')
                tx.verify_signature(session,backup,'clock-original-signature')
                tx.verify_signature(session,staged,'clock-candidate-signature')
                tx.write_new(RUN/'before.json',before)
                result['state'] = 'INSTALL_DISPATCHED'
                call = tx.install_once(session,staged,NEW_SHA,'clock-install')
                result['install_response_verified'] = tx.verified_response(call)
                after = None
                try:
                    after = snapshot(session,tx,model,timers,'after')
                except Exception as error:
                    result['post_read_error'] = type(error).__name__+':'+str(error)
                if not result['install_response_verified']:
                    result['state'] = 'INSTALL_OUTCOME_UNKNOWN'
                elif after is None:
                    result['state'] = 'POST_INSTALL_READBACK_FAILED'
                elif after['apk']['sha256'] != NEW_SHA or after['apk']['bytes'] != NEW_BYTES:
                    result['state'] = 'POST_INSTALL_APK_DIFFERS'
                elif not preserved(before,after):
                    result['state'] = 'POST_INSTALL_STATE_DIFFERS'
                else:
                    result['state'] = 'INSTALLED_VERIFIED'
                result['observed_apk'] = after['apk'] if after else None
                result['data_and_sound_state_preserved'] = after is not None and preserved(before,after)
                session.caller_status('clock-install-caller-after');session.guard()
        except BaseException as error:
            result['error'] = type(error).__name__+':'+str(error)
            if result['state'] == 'INSTALL_DISPATCHED':
                result['state'] = 'INSTALL_OUTCOME_UNKNOWN'
            elif result['state'] == 'INSTALLED_VERIFIED':
                result['state_before_final_guard_failure'] = result['state'];result['state'] = 'FINAL_GUARD_FAILED'
        result['finished_utc'] = datetime.now(timezone.utc).isoformat()
        tx.write_new(RUN/'result.json',result,alex_readable=True)
        return result


def rollback():
    model,tx,timers = modules()
    old = json.loads(tx.read_regular(RUN/'result.json'))
    require(old.get('install_response_verified') is True and old['state'] in
        ('INSTALLED_VERIFIED','POST_INSTALL_READBACK_FAILED','POST_INSTALL_APK_DIFFERS','POST_INSTALL_STATE_DIFFERS','FINAL_GUARD_FAILED'),
        'ROLLBACK_REQUIRES_KNOWN_COMPLETED_UPDATE')
    original = json.loads(tx.read_regular(RUN/'before.json'))
    backup = RUN/'DeskClock-original-before.apk';tx.read_regular(backup,OLD_SHA)
    folder = RUN/'rollback-01'
    result = {'state':'ROLLBACK_NOT_DISPATCHED','package':PACKAGE,'automatic_retry':False,'UI_actions':0,
        'app_data_write_commands':0,'production_ready':False,'started_utc':datetime.now(timezone.utc).isoformat()}
    with tx.ui_lock():
        # Claim once, before the try/finally; a prior rollback directory is never
        # rewritten even if its original process died without a final receipt.
        folder.mkdir(mode=0o750); os.chown(folder,0,1000); os.chmod(folder,0o750)
        tx.write_new(folder/'claim.json',result)
        try:
            with tx.CameraSession(folder/'commands') as session:
                current = snapshot(session,tx,model,timers,'before-rollback')
                require(current['apk']['sha256'] == NEW_SHA and current['apk']['bytes'] == NEW_BYTES, 'ROLLBACK_REFUSES_FOREIGN_APK')
                # A completed owned timer test may change an empty allocation counter.
                # Preserve the CURRENT preferences byte-for-byte across rollback.
                require(preserved(original,current,include_preferences=False,include_tasks=False),
                        'ROLLBACK_IDENTITY_OR_PROTECTED_STATE_CHANGED')
                tx.read_regular('/usr/bin/apksigner','52947059a664b85f0475bcdc3dbbe6089b50f8f59e3aa051e6e74cf0ba7db70f')
                tx.verify_signature(session,backup,'clock-rollback-signature')
                result['state'] = 'ROLLBACK_DISPATCHED'
                call = tx.install_once(session,backup,OLD_SHA,'clock-rollback')
                result['rollback_response_verified'] = tx.verified_response(call)
                after = snapshot(session,tx,model,timers,'after-rollback')
                result['observed_apk'] = after['apk']
                result['current_data_and_sound_preserved'] = preserved(current,after)
                result['state'] = ('ROLLBACK_OUTCOME_UNKNOWN' if not result['rollback_response_verified'] else
                    'ROLLED_BACK_VERIFIED' if after['apk']['sha256'] == OLD_SHA and after['apk']['bytes'] == OLD_BYTES
                        and preserved(current,after) else 'ROLLBACK_READBACK_DIFFERS')
                session.caller_status('clock-rollback-caller-after');session.guard()
        except BaseException as error:
            result['error'] = type(error).__name__+':'+str(error)
            if result['state'] == 'ROLLBACK_DISPATCHED':
                result['state'] = 'ROLLBACK_OUTCOME_UNKNOWN'
            elif result['state'] == 'ROLLED_BACK_VERIFIED':
                result['state_before_final_guard_failure'] = result['state'];result['state'] = 'FINAL_GUARD_FAILED'
        if folder.exists():
            result['finished_utc'] = datetime.now(timezone.utc).isoformat()
            tx.write_new(folder/'result.json',result,alex_readable=True)
    return result


def reconcile():
    model,tx,timers = modules()
    claim = json.loads(tx.read_regular(RUN/'claim.json'))
    require(claim['package'] == PACKAGE and claim['old_sha256'] == OLD_SHA and claim['new_sha256'] == NEW_SHA,
            'ORIGINAL_CLOCK_TRANSACTION_REQUIRED')
    before = json.loads(tx.read_regular(RUN/'before.json'))
    with tx.ui_lock(),tx.CameraSession(RUN/('reconcile-'+str(time.time_ns()))) as session:
        os.chown(session.journal_dir,0,1000); os.chmod(session.journal_dir,0o750)
        current = snapshot(session,tx,model,timers,'reconciled-current')
        result = {'state':'READ_ONLY_RECONCILIATION','package':PACKAGE,'observed_apk':current['apk'],
            'data_and_sound_state_preserved':preserved(before,current),'installation_replayed':False,
            'rollback_dispatched':False,'historical_outcome_rewritten':False,'production_ready':False}
        tx.write_new(session.journal_dir/'reconciliation.json',result,alex_readable=True)
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',choices=('plan','install','rollback','reconcile'),default='plan')
    parser.add_argument('--execute',action='store_true');args = parser.parse_args()
    if args.mode == 'plan':
        value = {'state':'PLAN_ONLY','candidate':str(CANDIDATE),'candidate_sha256':NEW_SHA,
            'original_sha256':OLD_SHA,'host_uid':1000,'android_user':0,'package':PACKAGE,
            'candidate_bytes':NEW_BYTES,'original_bytes':OLD_BYTES,'install_path':str(RUN),'production_actions':0}
    else:
        require(os.geteuid() == 0 and (args.mode == 'reconcile' or args.execute), 'EXPLICIT_ROOT_EXECUTION_REQUIRED')
        value = {'install':update,'rollback':rollback,'reconcile':reconcile}[args.mode]()
    print(json.dumps(value,sort_keys=True))
    return 0 if value['state'] in ('PLAN_ONLY','INSTALLED_VERIFIED','ROLLED_BACK_VERIFIED','READ_ONLY_RECONCILIATION') else 1


if __name__ == '__main__':
    raise SystemExit(main())
