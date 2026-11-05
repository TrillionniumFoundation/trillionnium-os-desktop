#!/usr/bin/python3 -I
"""One Clock-only update or exact APK rollback; default inert, no app-data writes."""
from pathlib import Path
from datetime import datetime, timezone
import argparse, hashlib, io, json, os, re, stat, time, types, zipfile
import xml.etree.ElementTree as ET

ROOT = Path('/home/alex/work/pocket4-clock-alarm-dispatch-20261105-r12-04')
RUN = ROOT / 'install-04'
CLOCK = Path('/home/alex/work/pocket4-clock-session-tools-20261105-r12-01')
CANDIDATE = ROOT / 'build/DeskClock-pocket4-alarm-dispatch.apk'
OLD_SHA = 'e4ff4b46a651ff3ac77397705b7b749c7fbaaeb94fe1d00818debb31dea34172'
NEW_SHA = '433ff501b92a21bb9265c896add220b52bc16fc4124662eaf45310da99243a0d'
OLD_BYTES, NEW_BYTES = 7593129, 7597225
PACKAGE, UID, VERSION = 'com.android.deskclock', 10063, 37
FACTORY = '/product/app/DeskClock/DeskClock.apk'
MODEL_SHA = 'fd3ffdfbb397b561bf251236c117966ea18b2ca176e4908c6a31ad0db4cc0048'
TIMER_SHA = 'c3bf02f38e05ab7a55285ca2245ffe2bda3eb528cc1f85d54723294047948b08'
BUILD_SHA = '4b4e23003f52b80f896cff316b930095ef4dd959e0fdbcb99b2ea0fc674b6881'
DEX_SHA = 'deff3873f215d97ab47908c7f60cb6ab62d4a6e4f6274dc3f3130023f0630c98'
ART_RESULT = Path('/home/alex/work/pocket4-clock-alarm-art-20261105-r12-04/result.json')
ART_SHA = 'cb6ebadca9c9736ce9e60877f13d33698d5f7a1bb918ae178e37d7c6da697ac9'
TRANSPORT_SHA = 'b2274355ea9acc9d3f82f4e245dceef01aae86e689221744f0fb2afaff679470'
ACTIVATION_SHA = '7e490c14586d891f6b121341f879f41c955414c9122e3a68053f04665c12e615'
ART_TARGETS = (
    'Lcom/android/deskclock/alarms/AlarmService;',
    'Lcom/android/deskclock/alarms/AlarmStateManager$AlarmManagerStateChangeScheduler;',
    'Lcom/android/deskclock/alarms/AlarmStateManager$Companion;',
    'Lcom/android/deskclock/alarms/AlarmStateManager;',
)
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
    require(model.SOURCE_SHA == TRANSPORT_SHA, 'ORIGINAL_STRICT_TRANSPORT_REQUIRED')
    tx = model.load_session()
    require(tx.ACTIVATION_SHA == ACTIVATION_SHA, 'ORIGINAL_STRICT_RESOURCE_PROFILE_REQUIRED')
    return model, tx, load(CLOCK/'read_timer.py', TIMER_SHA)


def artifact_preconditions(build, art, tx):
    require(build['state'] == 'SIGNED_OFFLINE_CANDIDATE_VERIFIED'
        and build['original_apk_sha256'] == OLD_SHA
        and build['candidate_apk']['sha256'] == NEW_SHA
        and build['candidate_apk']['bytes'] == NEW_BYTES
        and build['candidate_apk']['certificate_sha256'] == tx.CERT_SHA
        and build['candidate_dex']['sha256'] == DEX_SHA
        and build['inputs_tools_and_clock_state_unchanged'] is True,
        'OFFLINE_CANDIDATE_NOT_VERIFIED')
    payload = build['payload_verification']; semantic = build['semantic_verification']
    require(payload['members'] == 1281 and payload['only_changed_payload'] == 'classes.dex'
        and all(payload[key] is True for key in ('alignment_16k_verified',
            'same_certificate_verified','signature_v3_verified'))
        and semantic['all_2941_class_IR_compared'] is True
        and semantic['all_original_methods_retained'] is True
        and semantic['non_target_semantic_changes'] == 0
        and len(semantic['differences']) == 5 and len(semantic['added_methods']) == 6,
        'BUILD_CHANGE_SCOPE_NOT_VERIFIED')
    require(art['state'] == 'ALL_FOUR_MODIFIED_CLOCK_CLASSES_ART_VERIFIED_NOT_INSTALLED'
        and art.get('error') is None and art['apk_sha256'] == NEW_SHA
        and art['build_result_sha256'] == BUILD_SHA
        and art['transport_sha256'] == TRANSPORT_SHA
        and art['activation_sha256'] == ACTIVATION_SHA
        and art['guard_before'] == art['guard_after']
        and art['guard_after']['epoch_sha256'] == tx.EPOCH_SHA
        and art['all_four_target_classes_stored_status_verified'] is True
        and art['input_boot_apex_classpaths_unchanged'] is True
        and art['installed_clock_and_shared_libraries_unchanged'] is True
        and art['fd_proof']['all_descriptor_identities_exact'] is True,
        'ACTUAL_ART_OR_RUNTIME_BINDING_NOT_VERIFIED')
    proof = art['target_status_proof']
    require(tuple(art['expected_targets']) == ART_TARGETS
        and proof['expected_target_classes'] == 4
        and set(proof['target_statuses']) == set(ART_TARGETS)
        and proof['missing'] == [] and proof['unverified'] == {}
        and proof['other_nonverified_statuses'] == {}
        and all(row['status'] == 'Verified' and row['compilation_kind'] == 'NoneCompiled'
            for row in proof['target_statuses'].values()), 'ACTUAL_ART_TARGET_SET_NOT_VERIFIED')
    for key in ('compiler','oatdump','android_compiler_log'):
        command = art[key]
        require(command['rc'] == 0 and command['joined'] is True
            and command['timed_out'] is False, 'ACTUAL_ART_COMMAND_FAILED:' + key)
    limits = {'cpu.max':'200000 100000','memory.max':'2147483648',
              'memory.swap.max':'0','pids.max':'64'}
    for key in ('resource_admission','resource_usage'):
        value = art[key]
        require(value['limits'] == limits and value['memory_peak_bytes'] < int(limits['memory.max'])
            and all(value['memory_events'].get(name) == 0 for name in ('max','oom','oom_kill')),
            'ART_RESOURCE_BOUNDARY_NOT_PRESERVED')
    return {'build_result_sha256':BUILD_SHA,'art_result_sha256':ART_SHA,
        'actual_art_target_classes_verified':4,'actual_art_epoch_sha256':tx.EPOCH_SHA,
        'actual_art_finished_utc':art['finished_utc'],'business_success_inferred':False}


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


def preference_metadata(raw):
    """Only mask the one observed Android-generated global intent counter value.

    All other bytes, including unrelated keys, order and XML formatting, remain
    part of the hash. No preference content is written or returned.
    """
    root = ET.fromstring(raw)
    require(root.tag == 'map', 'PREFERENCES_XML_MAP_REQUIRED')
    items = [item for item in root if item.get('name') == 'intent.extra.alarm.global.id']
    require(len(items) == 1 and items[0].tag == 'int'
        and set(items[0].attrib) == {'name','value'}, 'ONE_GLOBAL_INTENT_COUNTER_REQUIRED')
    value = items[0].get('value')
    require(re.fullmatch(r'-?(?:0|[1-9][0-9]*)',value or '') is not None
        and -2147483648 <= int(value) < 2147483647, 'GLOBAL_INTENT_COUNTER_OUT_OF_SCOPE')
    pattern = rb'(<int name="intent\.extra\.alarm\.global\.id" value=")(-?[0-9]+)(" />)'
    matches = list(re.finditer(pattern,raw))
    require(len(matches) == 1 and matches[0][2].decode() == value, 'OBSERVED_COUNTER_XML_FORMAT_CHANGED')
    match = matches[0]
    masked = raw[:match.start(2)] + b'REVIEWED_GLOBAL_INTENT_COUNTER' + raw[match.end(2):]
    return {'global_intent_id':int(value),'all_other_preference_bytes_sha256':sha(masked)}


def preference_review(before,after):
    old_hash,new_hash = before.get('preferences_sha256'),after.get('preferences_sha256')
    same = (isinstance(old_hash,str) and re.fullmatch('[0-9a-f]{64}',old_hash) is not None
        and old_hash == new_hash)
    a,b = before.get('preferences_metadata',{}),after.get('preferences_metadata',{})
    delta = (type(a.get('global_intent_id')) is int and type(b.get('global_intent_id')) is int
        and b['global_intent_id'] == a['global_intent_id'] + 1
        and isinstance(a.get('all_other_preference_bytes_sha256'),str)
        and re.fullmatch('[0-9a-f]{64}',a['all_other_preference_bytes_sha256']) is not None
        and a['all_other_preference_bytes_sha256'] == b.get('all_other_preference_bytes_sha256'))
    return {'preferences_bytes_identical':same,'accepted':same or delta,
        'only_documented_global_intent_counter_increment':not same and delta,
        'global_intent_id_before':a.get('global_intent_id'),
        'global_intent_id_after':b.get('global_intent_id'),
        'other_preference_bytes_preserved':same or delta,'preference_write_commands':0}


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
    pref_meta = preference_metadata(preferences)
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
        'observed_utc':datetime.now(timezone.utc).isoformat(),
        'alarm_state':alarms,'alarm_content_sha256':ALARM_SHA,'preferences_sha256':sha(preferences),
        'preferences_metadata':pref_meta,
        'timer_and_stopwatch_empty':True,'notification_appop_allow':True,'sound_state':sounds,'tasks_sha256':sha(tasks.encode()),
        'apk':{'guest_path':guest,'bytes':len(apk),'sha256':sha(apk)}}
    tx.write_new(session.journal_dir/(label+'.json'),result)
    return result


def preserved(before,after,include_preferences=True,include_tasks=True):
    keys = ['package','epoch_sha256','identity','directories','alarm_state','alarm_content_sha256',
            'timer_and_stopwatch_empty','notification_appop_allow','sound_state']
    if include_tasks:
        keys.append('tasks_sha256')
    return (all(before.get(k) == after.get(k) for k in keys)
        and (not include_preferences or preference_review(before,after)['accepted']))


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
            DEX_SHA, 'CLOCK_PAYLOAD_CHANGE_EXCEEDS_REVIEW')


def verify_signature(session,tx,path,label):
    signer = Path('/usr/bin/apksigner').resolve(strict=True)
    pin = '52947059a664b85f0475bcdc3dbbe6089b50f8f59e3aa051e6e74cf0ba7db70f'
    tx.read_regular(signer,pin)
    value = session.run_host(label,[str(signer),'verify','--verbose','--print-certs',str(path)],25)
    require(value['rc'] == 0 and value['joined'] and not value['timed_out'], 'APK_SIGNATURE_FAILED')
    text = value['stdout'].decode('utf-8','strict')
    require(re.findall(r'^Signer #\d+ certificate SHA-256 digest: (\w+)$',text,re.M) == [tx.CERT_SHA]
        and 'Verified using v3 scheme (APK Signature Scheme v3): true' in text, 'APK_SIGNER_OR_V3_DIFFERS')
    tx.read_regular(signer,pin)


def installed_observation(session,tx,after,label,expected_sha,expected_bytes):
    """Independent readback identity; no business credit or build-only identity."""
    require(after['apk']['sha256'] == expected_sha and after['apk']['bytes'] == expected_bytes,
            'IDENTITY_REQUIRES_EXACT_INSTALLED_APK_READBACK')
    evidence = session.journal_dir/(label+'.json')
    raw = tx.read_regular(evidence)
    require(json.loads(raw) == after, 'INSTALLED_SNAPSHOT_EVIDENCE_CHANGED')
    return {'schema':'clock-installed-identity-observation-v1','package':PACKAGE,
        'observed_utc':after['observed_utc'],'epoch_sha256':after['epoch_sha256'],
        'android_user':0,'uid':after['identity']['uid'],
        'version_code':after['identity']['version'],'min_sdk':after['identity']['min_sdk'],
        'target_sdk':after['identity']['target_sdk'],
        'all_observed_apk_files':[after['apk']], 'installed_apk_sha256':expected_sha,
        'certificate_sha256':tx.CERT_SHA,
        'certificate_basis':'Installed whole APK bytes equal the independently v3-verified staged APK.',
        'package_and_apk_readback_verified':True,'snapshot_evidence_path':str(evidence),
        'snapshot_evidence_sha256':sha(raw),'transport_sha256':TRANSPORT_SHA,
        'activation_sha256':ACTIVATION_SHA,'whole_app_production_ready':False,
        'business_review_from_prior_APK_inherited':False}


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
            art = json.loads(tx.read_regular(ART_RESULT,ART_SHA))
            result['artifact_preconditions'] = artifact_preconditions(build,art,tx)
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
                verify_signature(session,tx,backup,'clock-original-signature')
                verify_signature(session,tx,staged,'clock-candidate-signature')
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
                result['protected_business_and_sound_state_preserved'] = after is not None and preserved(before,after)
                result['preferences_review'] = preference_review(before,after) if after else None
                if after and after['apk']['sha256'] == NEW_SHA and after['apk']['bytes'] == NEW_BYTES:
                    observation = installed_observation(session,tx,after,'after',NEW_SHA,NEW_BYTES)
                    tx.write_new(RUN/'latest-installed-identity.json',observation,alex_readable=True)
                    result['installed_identity_observation'] = observation
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
                # Preserve current preferences except the separately reported one
                # global intent counter increment generated by package replacement.
                require(preserved(original,current,include_preferences=False,include_tasks=False),
                        'ROLLBACK_IDENTITY_OR_PROTECTED_STATE_CHANGED')
                verify_signature(session,tx,backup,'clock-rollback-signature')
                result['state'] = 'ROLLBACK_DISPATCHED'
                call = tx.install_once(session,backup,OLD_SHA,'clock-rollback')
                result['rollback_response_verified'] = tx.verified_response(call)
                after = snapshot(session,tx,model,timers,'after-rollback')
                result['observed_apk'] = after['apk']
                result['current_protected_business_and_sound_preserved'] = preserved(current,after)
                result['preferences_review'] = preference_review(current,after)
                if after['apk']['sha256'] == OLD_SHA and after['apk']['bytes'] == OLD_BYTES:
                    observation = installed_observation(session,tx,after,'after-rollback',OLD_SHA,OLD_BYTES)
                    tx.write_new(folder/'latest-installed-identity.json',observation,alex_readable=True)
                    result['installed_identity_observation'] = observation
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
            'protected_business_and_sound_state_preserved':preserved(before,current),
            'preferences_review':preference_review(before,current),'installation_replayed':False,
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
        value['actual_art_result_sha256'] = ART_SHA
    else:
        require(os.geteuid() == 0 and (args.mode == 'reconcile' or args.execute), 'EXPLICIT_ROOT_EXECUTION_REQUIRED')
        value = {'install':update,'rollback':rollback,'reconcile':reconcile}[args.mode]()
    print(json.dumps(value,sort_keys=True))
    return 0 if value['state'] in ('PLAN_ONLY','INSTALLED_VERIFIED','ROLLED_BACK_VERIFIED','READ_ONLY_RECONCILIATION') else 1


if __name__ == '__main__':
    raise SystemExit(main())
