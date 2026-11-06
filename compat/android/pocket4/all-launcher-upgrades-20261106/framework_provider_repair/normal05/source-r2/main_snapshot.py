#!/usr/bin/env python3
"""Fixed eight-role typedguard protection; never qualifies Android app or framework QA."""
import hashlib
import json
import os
from pathlib import Path
import resource
import select
import signal
import stat
import time

BOOT_ID = '981ff371-cd72-4f81-9be3-a862111afdb1'
IDENTITY_SOURCE_SHA = '7c52723c372b9f486067456e720709ef401bcebe1a7aad158f6b8c099f67fcc8'
CURRENT_QUALIFICATION_SHA = '4bdfe7dd1e275bc4727f37c630dc2498b3dc31c528b03a4028e42c1cf8fc4fc6'
ACTIVATION = Path('/home/alex/work/pocket4-app-production-20261104-r10/deployment-preparation/activation-after-01.json')
ACTIVATION_SHA = '7e490c14586d891f6b121341f879f41c955414c9122e3a68053f04665c12e615'
OLD_INVALID_EPOCH_SHA = '48cb65c93ff81edbf160455af6506f5c703f0958363f15de4a80ece57c37e93f'
CG = Path('/sys/fs/cgroup/system.slice/droidloomd.service')
CELL = Path('/etc/droidloom/cell.json')
CELL_SHA = 'f64a9f9a63e76ac2bf765e8f98bb2f9a91a326b38f86b6e3c4ac512d60303bdc'
ENGINE_SHA = 'c8b9bae4466d4f66525fdef6bcec140b29612581efeb6ceb621f96e17277d26d'
PRESENTER_SHA = '47f34d5f68783a372283cb63a42034d5899e270524cca40122bf28fd5e903f24'
DEADLINE = None
EXPECTED = {'android_init': {'cgroup': '0::/system.slice/droidloomd.service\n',
                  'namespace_pids': [3268779, 1],
                  'namespaces': {'mnt': 'mnt:[4026533280]',
                                 'pid': 'pid:[4026533285]',
                                 'user': 'user:[4026531837]'},
                  'pid': 3268779,
                  'ppid': 3268775,
                  'root_identity': {'device': 106, 'inode': 1},
                  'start_ticks': 99615082,
                  'uids': [0, 0, 0, 0]},
 'composer': {'cgroup': '0::/system.slice/droidloomd.service/system/uid_1000/pid_652\n',
              'namespace_pids': [3270341, 652],
              'namespaces': {'mnt': 'mnt:[4026533280]',
                             'pid': 'pid:[4026533285]',
                             'user': 'user:[4026531837]'},
              'pid': 3270341,
              'ppid': 3268779,
              'root_identity': {'device': 106, 'inode': 1},
              'start_ticks': 99615244,
              'uids': [1000, 1000, 1000, 1000]},
 'daemon': {'cgroup': '0::/system.slice/droidloomd.service\n',
            'namespace_pids': [3588022],
            'namespaces': {'mnt': 'mnt:[4026531832]', 'pid': 'pid:[4026531836]', 'user': 'user:[4026531837]'},
            'pid': 3588022,
            'ppid': 1,
            'root_identity': {'device': 66306, 'inode': 2},
            'start_ticks': 80796995,
            'uids': [0, 0, 0, 0]},
 'launcher': {'cgroup': '0::/system.slice/droidloomd.service\n',
              'namespace_pids': [3268774],
              'namespaces': {'mnt': 'mnt:[4026533279]',
                             'pid': 'pid:[4026531836]',
                             'user': 'user:[4026531837]'},
              'pid': 3268774,
              'ppid': 3588022,
              'root_identity': {'device': 66306, 'inode': 2},
              'start_ticks': 99615080,
              'uids': [0, 0, 0, 0]},
 'presenter': {'cgroup': '0::/user.slice/user-1000.slice/user@1000.service/app.slice/droidloom.service\n',
               'namespace_pids': [3588024],
               'namespaces': {'mnt': 'mnt:[4026531832]',
                              'pid': 'pid:[4026531836]',
                              'user': 'user:[4026531837]'},
               'pid': 3588024,
               'ppid': 2472,
               'root_identity': {'device': 66306, 'inode': 2},
               'start_ticks': 80796995,
               'uids': [1000, 1000, 1000, 1000]},
 'surfaceflinger': {'cgroup': '0::/system.slice/droidloomd.service/system/uid_1000/pid_661\n',
                    'namespace_pids': [3270350, 661],
                    'namespaces': {'mnt': 'mnt:[4026533280]',
                                   'pid': 'pid:[4026533285]',
                                   'user': 'user:[4026531837]'},
                    'pid': 3270350,
                    'ppid': 3268779,
                    'root_identity': {'device': 106, 'inode': 1},
                    'start_ticks': 99615245,
                    'uids': [1000, 1000, 1000, 1000]},
 'system_server': {'cgroup': '0::/system.slice/droidloomd.service/system/uid_1000/pid_808\n',
                   'namespace_pids': [3270611, 808],
                   'namespaces': {'mnt': 'mnt:[4026533719]',
                                  'pid': 'pid:[4026533285]',
                                  'user': 'user:[4026531837]'},
                   'pid': 3270611,
                   'ppid': 3270325,
                   'root_identity': {'device': 106, 'inode': 1},
                   'start_ticks': 99615342,
                   'uids': [1000, 1000, 1000, 1000]},
 'zygote64': {'cgroup': '0::/system.slice/droidloomd.service/system/uid_0/pid_638\n',
              'namespace_pids': [3270325, 638],
              'namespaces': {'mnt': 'mnt:[4026533718]',
                             'pid': 'pid:[4026533285]',
                             'user': 'user:[4026531837]'},
              'pid': 3270325,
              'ppid': 3268779,
              'root_identity': {'device': 106, 'inode': 1},
              'start_ticks': 99615242,
              'uids': [0, 0, 0, 0]}}
LIMITS={"cpu.max":"200000 100000","memory.high":"5368709120","memory.max":"6442450944","memory.swap.max":"max","pids.max":"12288"}
STATUS_KEYS={'Uid','Gid','Groups','NSpid','CapInh','CapPrm','CapEff','CapBnd','CapAmb','Threads','State','PPid'}

def require(value, reason):
    if not value:
        raise RuntimeError(reason)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def read_regular(path):
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, 'unsafe fixed input')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            raw = stream.read(1024 * 1024 + 1)
        require(len(raw) <= 1024 * 1024, 'fixed input too large')
        return raw
    finally:
        os.close(fd)

def parse_counters(text):
    rows = {}
    for line in text.splitlines():
        key, value = line.split()
        require(key not in rows and value.isdecimal(), 'counter format changed')
        rows[key] = int(value)
    return rows

def need(value, reason):
    require(value, reason)


def check():
    need(DEADLINE is not None and time.monotonic() < DEADLINE, 'SNAPSHOT_DEADLINE')


def read(path,limit):
    check();fd=os.open(path,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        chunks=[];n=0
        while True:
            check();b=os.read(fd,min(8192,limit+1-n))
            if not b:break
            chunks.append(b);n+=len(b);need(n<=limit,'FIXED_READ_BOUND')
        return b''.join(chunks)
    finally:os.close(fd)

def statrow(pid):
    b=read('/proc/%d/stat'%pid,8192);at=b.rfind(b') ')
    need(at>0 and b[:at].startswith(str(pid).encode()+b' ('),'PROC_STAT_SCHEMA')
    f=b[at+2:].split();need(len(f)>=20,'PROC_STAT_FIELDS')
    return {'pid':pid,'start_ticks':int(f[19]),'state':f[0].decode('ascii'),'ppid':int(f[1])}

def process(pid,birth):
    row={'pid':pid,'expected_start_ticks':birth};held=None
    try:
        first=statrow(pid);row['before']=first
        if birth is not None:need(first['start_ticks']==birth,'ORIGINAL_PID_REUSED')
        held=os.pidfd_open(pid,0)
        poll=select.poll();poll.register(held,select.POLLIN)
        need(not poll.poll(0),'PROCESS_ALREADY_DEAD')
        status=read('/proc/%d/status'%pid,65536).decode('ascii','strict')
        row['status']={k:v.strip() for k,v in (line.split(':',1) for line in status.splitlines() if ':' in line) if k in STATUS_KEYS}
        row['cgroup']=read('/proc/%d/cgroup'%pid,8192).decode('ascii','strict')
        row['namespaces']={k:os.readlink('/proc/%d/ns/%s'%(pid,k)) for k in ('mnt','pid','user')}
        st=os.stat('/proc/%d/root'%pid);row['root_identity']={'device':st.st_dev,'inode':st.st_ino}
        last=statrow(pid);row['after']=last
        need(first['start_ticks']==last['start_ticks'] and not poll.poll(0),'PROCESS_CHANGED_DURING_READ')
        row['alive_identity_verified']=True
    except OSError as e:row['error']={'type':type(e).__name__,'errno':e.errno}
    except RuntimeError as e:row['error']={'type':type(e).__name__,'code':str(e)}
    finally:
        if held is not None:os.close(held)
    return row

def identity(row):
    need(row.get("alive_identity_verified") is True and "error" not in row,"FIXED_PROCESS_UNAVAILABLE")
    need(row["before"]["state"] not in ("Z","X") and row["after"]["state"] not in ("Z","X"),"FIXED_PROCESS_DEAD")
    need(row["before"]["ppid"]==row["after"]["ppid"] and
         row["before"]["start_ticks"]==row["after"]["start_ticks"],"FIXED_PROCESS_CHANGED")
    return {"pid":row["pid"],"start_ticks":row["before"]["start_ticks"],
            "ppid":row["before"]["ppid"],"uids":[int(x) for x in row["status"]["Uid"].split()],
            "namespace_pids":[int(x) for x in row["status"]["NSpid"].split()],
            "cgroup":row["cgroup"],"namespaces":row["namespaces"],"root_identity":row["root_identity"]}

def qualify_process(role, row):
    actual = identity(row)
    need(role in EXPECTED and actual == EXPECTED[role], 'FIXED_IDENTITY_DIFFERS_FROM_TYPED_BASELINE')
    return actual


def snapshot_processes():
    rows = {}
    for role, expected in EXPECTED.items():
        check()
        rows[role] = qualify_process(role, process(expected['pid'], expected['start_ticks']))
    need(set(rows) == set(EXPECTED) and len(rows) == 8, 'FIXED_EIGHT_ROLES_INCOMPLETE')
    return rows


RUNTIME_EPOCH_SHA = 'a7c7091a9e57eb6b373aa8a9225bb2f17b4ec0f1248679b56aaadc78eb0faca9'
FRAMEWORK_EPOCH_SHA = '7d927812392d30ab8cca43da87c0785e24695ca724da93b3b465122502b8045c'
CURRENT_GUARD_PIN = {'bytes': 3213,
 'path': '/home/alex/work/pocket4-cell-successor-repaired-r2-20261106-execute-01/current_baseline_guard.py',
 'sha256': 'd84df98d55352ef9ae66753ee15f3746d9d9a64c35fddf392a08f10ba4105cb3'}
CURRENT_GUARD_PINS = {'baseline': {'bytes': 44041,
              'path': '/home/alex/work/pocket4-cell-successor-repaired-r2-20261106-execute-01/baseline.private.json',
              'sha256': '7c52723c372b9f486067456e720709ef401bcebe1a7aad158f6b8c099f67fcc8'},
 'manifest_sha': 'b97002660594ad0ef6e7b453927b8c5b19cba49a5873bc133199d790019b1f9f',
 'qualification': {'bytes': 1587,
                   'path': '/home/alex/work/pocket4-cell-successor-repaired-r2-20261106-execute-01/qualification.private.json',
                   'sha256': '4bdfe7dd1e275bc4727f37c630dc2498b3dc31c528b03a4028e42c1cf8fc4fc6'},
 'root': '/home/alex/work/pocket4-cell-successor-repaired-r2-20261106-execute-01'}
APP_SCOPE_PIN = {'bytes': 57340,
 'path': '/home/alex/work/pocket4-successor-native-install-20261106-douyin-01/app-scope-after.private.json',
 'sha256': '489129d6e39a5aebc410ebcf74706279a99ff6751a15bd0a6b324ddd007e01a4'}
APP_SCOPE_PACKAGES = ['com.Hyatt.hyt',
 'com.MobileTicket',
 'com.amazon.mShop.android.shopping',
 'com.android.calendar',
 'com.android.camera2',
 'com.android.contacts',
 'com.android.deskclock',
 'com.android.dialer',
 'com.android.documentsui',
 'com.android.gallery3d',
 'com.android.messaging',
 'com.android.quicksearchbox',
 'com.android.settings',
 'com.android.threadnetwork.demoapp',
 'com.bestbuy.android',
 'com.ehi.national.mobile',
 'com.enflick.android.TextNow',
 'com.google.android.gms',
 'com.hertz.android.digital',
 'com.hilton.android.hhonors',
 'com.ihg.apps.android',
 'com.jingdong.app.mall',
 'com.lianjia.beike',
 'com.marriott.mrt',
 'com.pinger.textfree',
 'com.rytong.airchina',
 'com.rytong.ceair',
 'com.sankuai.meituan.takeoutnew',
 'com.sdu.didi.psnger',
 'com.ss.android.ugc.aweme',
 'com.szzc',
 'com.taobao.taobao',
 'com.tencent.mm',
 'com.ubercab',
 'com.united.mobile.android',
 'com.xunmeng.pinduoduo',
 'com.zhubajie.client',
 'com.zillow.android.streeteasy',
 'ctrip.android.view',
 'jp.co.ana.android.tabidachi',
 'local.pocket4.actions.v2',
 'local.pocket4.fixture',
 'org.chromium.webview_shell',
 'org.droidloom.qa.editorcontract',
 'org.fcitx.fcitx5.android',
 'tv.danmaku.bili']

"""Inserted into the existing fixed snapshot; not a standalone entry point."""

def expected_from_baseline(baseline):
    runtime = baseline['runtime']
    binding = runtime['held']['process_snapshot']['binding']
    extra = runtime['held']['extra']
    required = {'daemon', 'launcher', 'android_init', 'presenter', 'surfaceflinger', 'zygote64', 'system_server', 'composer'}
    need(set(binding['processes']) == set(extra) == required, 'TYPED_EIGHT_ROLES_REQUIRED')
    rows = {}
    for role, value in binding['processes'].items():
        item = extra[role]
        proc = item['held_proc']
        need(value['host_pid'] == proc['pid'] and value['start_ticks'] == int(proc['start']) and
             value['parent_host_pid'] == proc['ppid'] and value['uids'] == [int(v) for v in proc['uid']] and
             value['namespace_pids'] == [int(v) for v in proc['nspid']] and
             value['cgroup'] == proc['cgroup'].splitlines() and
             all(value['namespaces'][name] == item['namespaces'][name] for name in value['namespaces']),
             'TYPED_BASELINE_ROLE_RECORDS_DISAGREE')
        rows[role] = {'pid': value['host_pid'], 'start_ticks': value['start_ticks'],
                      'ppid': value['parent_host_pid'], 'uids': value['uids'],
                      'namespace_pids': value['namespace_pids'], 'cgroup': proc['cgroup'],
                      'namespaces': {name: item['namespaces'][name] for name in ('mnt', 'pid', 'user')},
                      'root_identity': item['root']}
    return rows


def qualify_baseline(baseline):
    runtime_raw = json.dumps(baseline['runtime'], sort_keys=True, separators=(',', ':'),
                             ensure_ascii=True, allow_nan=False).encode()
    need(baseline['schema'] == 'pocket4-successor-runtime-baseline-v1' and
         baseline['runtime_epoch_sha256'] == sha(runtime_raw) == RUNTIME_EPOCH_SHA and
         baseline['framework_epoch']['sha256'] == FRAMEWORK_EPOCH_SHA and
         baseline['runtime']['held']['process_snapshot']['binding']['boot_id'] == BOOT_ID and
         baseline['production_ready'] is False and baseline['UI_or_install_runtime_admitted'] is False,
         'TYPED_RUNTIME_BASELINE_CHANGED')
    need(expected_from_baseline(baseline) == EXPECTED, 'TYPED_BASELINE_PROTECTED_ROLES_CHANGED')
    need(baseline['runtime']['limits'] == LIMITS and baseline['runtime']['cell_config']['sha256'] == CELL_SHA,
         'TYPED_BASELINE_CONFIG_OR_LIMITS_CHANGED')


def qualify_scope_reference(pin, packages):
    need(type(pin) is dict and set(pin) == {'path', 'bytes', 'sha256'} and
         type(pin['path']) is str and pin['path'].startswith('/home/alex/work/') and
         all(part not in ('', '.', '..') for part in pin['path'][1:].split('/')) and
         type(pin['bytes']) is int and 0 < pin['bytes'] <= 4 * 1024 * 1024 and
         type(pin['sha256']) is str and len(pin['sha256']) == 64 and
         all(c in '0123456789abcdef' for c in pin['sha256']) and
         type(packages) is list and 0 < len(packages) <= 128 and
         all(type(name) is str and name for name in packages) and packages == sorted(set(packages)),
         'FINAL_APP_SCOPE_PIN_REQUIRED')
    return pin


def qualify_typed_guard(receipt):
    need(receipt.get('schema') == 'pocket4-successor-main-guard-v1' and
         receipt.get('baseline_sha256') == IDENTITY_SOURCE_SHA and
         receipt.get('runtime_epoch_sha256') == RUNTIME_EPOCH_SHA and
         receipt.get('Main_epoch_sha256') == FRAMEWORK_EPOCH_SHA and
         receipt.get('eight_roles_including_composer_match') is True and
         receipt.get('complete_paired_classpath_matches') is True and
         receipt.get('resource_limits_match') is True and
         receipt.get('runtime_only_app_scopes_checked_separately') is True and
         receipt.get('UI_or_install_runtime_admitted') is False and receipt.get('production_ready') is False,
         'TYPED_GUARD_RECEIPT_REJECTED')


def qualify_scope_receipt(receipt, pin, packages):
    qualify_scope_reference(pin, packages)
    need(receipt.get('schema') == 'pocket4-app-scope-guard-v1' and
         receipt.get('runtime_epoch_sha256') == RUNTIME_EPOCH_SHA and
         receipt.get('app_scope_sha256') == pin['sha256'] and receipt.get('packages') == packages and
         receipt.get('current_apk_paths_and_file_identities_match') is True and
         receipt.get('new_signature_verification_performed') is False and
         receipt.get('UI_or_install_runtime_admitted') is False,
         'CURRENT_APP_SCOPE_RECEIPT_REJECTED')


def load_current_guard():
    raw = read_regular(CURRENT_GUARD_PIN['path'])
    need(len(raw) == CURRENT_GUARD_PIN['bytes'] and sha(raw) == CURRENT_GUARD_PIN['sha256'], 'CURRENT_GUARD_SOURCE_PIN')
    scope = {'__name__': 'normal05_exact_current_typedguard', '__file__': CURRENT_GUARD_PIN['path']}
    exec(compile(raw, CURRENT_GUARD_PIN['path'], 'exec'), scope, scope)
    need(scope['PINS'] == CURRENT_GUARD_PINS, 'CURRENT_GUARD_AUTHORITY_PINS')
    return scope


def qualify_finish(primary_error, cleanup_errors, within_deadline):
    if primary_error is not None:
        raise primary_error
    need(not cleanup_errors, 'SNAPSHOT_FD_CLEANUP_FAILED')
    need(within_deadline, 'SNAPSHOT_DEADLINE')


def capture():
    global DEADLINE
    need(os.getuid() == 0 and os.geteuid() == 0, 'ROOT_SNAPSHOT_REQUIRED')
    qualify_scope_reference(APP_SCOPE_PIN, APP_SCOPE_PACKAGES)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    started = time.monotonic_ns()
    DEADLINE = time.monotonic() + 15
    signal.signal(signal.SIGALRM, signal.SIG_DFL)
    signal.alarm(15)  # Self-only watchdog. The existing typedguard may start fixed read-only service queries; its children remain owned by the root supervisor.
    cg_fd = None
    failure = None
    cleanup_errors = []
    result = None
    try:
        guard = load_current_guard()
        current_baseline = guard['current_baseline']()
        qualify_baseline(current_baseline)
        typed_guard_receipt = guard['current_guard'](current_baseline, action_attempted=False)
        qualify_typed_guard(typed_guard_receipt)
        need(read('/proc/sys/kernel/random/boot_id', 128).decode('ascii').strip() == BOOT_ID, 'BOOT_CHANGED')
        raw = read_regular(ACTIVATION)
        need(sha(raw) == ACTIVATION_SHA, 'HISTORICAL_ACTIVATION_CHANGED')
        activation = json.loads(raw)
        need(activation['main_deployed'] is True and activation['engine_sha256'] == ENGINE_SHA and
             activation['presenter_sha256'] == PRESENTER_SHA and
             activation['framework_epoch']['sha256'] == OLD_INVALID_EPOCH_SHA,
             'HISTORICAL_ACTIVATION_SHAPE_CHANGED')
        need(sha(read_regular(CELL)) == CELL_SHA, 'MAIN_CONFIG_CHANGED')
        before_processes = snapshot_processes()
        cg_fd = os.open(CG, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
        cg_info = os.fstat(cg_fd)
        def cg_id(info):
            return [info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid]
        need(stat.S_ISDIR(cg_info.st_mode) and cg_id(cg_info) == cg_id(CG.lstat()), 'MAIN_CGROUP_NAMING_CHANGED')
        def cg_read(name):
            check()
            need(name and '/' not in name and name not in ('.', '..'), 'CGROUP_FILENAME')
            fd = os.open(name, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=cg_fd)
            try:
                with os.fdopen(fd, 'rb', closefd=False) as stream:
                    value = stream.read(65537)
                need(len(value) <= 65536, 'CGROUP_FIELD_BOUND')
                return value.decode('ascii').strip()
            finally:
                os.close(fd)
        limits = {name: cg_read(name) for name in LIMITS}
        need(limits == LIMITS, 'MAIN_FIVE_LIMITS_CHANGED')
        events = parse_counters(cg_read('memory.events'))
        need({'oom', 'oom_kill', 'oom_group_kill'} <= events.keys(), 'MAIN_OOM_COUNTERS_INCOMPLETE')
        current = {name: int(cg_read(name)) for name in ('memory.current', 'memory.swap.current', 'pids.current')}
        need(all(value >= 0 for value in current.values()), 'MAIN_RESOURCE_COUNTER_INVALID')
        cpu = parse_counters(cg_read('cpu.stat'))
        pressure = cg_read('memory.pressure')
        need({name: cg_read(name) for name in LIMITS} == limits, 'MAIN_LIMITS_CHANGED_DURING_SNAPSHOT')
        need(cg_id(os.fstat(cg_fd)) == cg_id(cg_info) == cg_id(CG.lstat()), 'MAIN_CGROUP_CHANGED_DURING_SNAPSHOT')
        app_scope_receipt = guard['check_app_scope'](APP_SCOPE_PIN, APP_SCOPE_PACKAGES)
        qualify_scope_receipt(app_scope_receipt, APP_SCOPE_PIN, APP_SCOPE_PACKAGES)
        after_processes = snapshot_processes()
        need(before_processes == after_processes == EXPECTED, 'PROTECTED_PROCESSES_CHANGED_DURING_SNAPSHOT')
        need(read('/proc/sys/kernel/random/boot_id', 128).decode('ascii').strip() == BOOT_ID, 'BOOT_CHANGED')
        need(sha(read_regular(ACTIVATION)) == ACTIVATION_SHA and sha(read_regular(CELL)) == CELL_SHA,
             'SNAPSHOT_AUTHORITIES_CHANGED')
        result = {'schema': 2, 'ok': True,
                  'historical_activation_sha256': ACTIVATION_SHA,
                  'old_invalid_QA_epoch_sha256': OLD_INVALID_EPOCH_SHA,
                  'old_QA_epoch_invalid': True, 'new_QA_epoch_qualified': False,
                  'protected_boot_id': BOOT_ID,
                  'protected_identity_source_sha256': IDENTITY_SOURCE_SHA,
                  'current_qualification_sha256': CURRENT_QUALIFICATION_SHA,
                  'protected_processes': after_processes,
                  'runtime_epoch_sha256': RUNTIME_EPOCH_SHA, 'framework_epoch_sha256': FRAMEWORK_EPOCH_SHA,
                  'current_guard_source_sha256': CURRENT_GUARD_PIN['sha256'],
                  'app_scope_sha256': APP_SCOPE_PIN['sha256'], 'app_scope_packages': APP_SCOPE_PACKAGES,
                  'typed_guard_receipt': typed_guard_receipt, 'app_scope_guard_receipt': app_scope_receipt,
                  'cell_sha256': CELL_SHA, 'limits': limits,
                  'main_cgroup': str(CG),
                  'main_cgroup_identity': {'device': cg_info.st_dev, 'inode': cg_info.st_ino},
                  'memory_events': events, 'current_resources': current, 'cpu_stat': cpu,
                  'memory_pressure': pressure, 'started_monotonic_ns': started,
                  'Main_actions': 0, 'Android_actions': 0, 'subprocesses_started': None, 'readonly_guard_service_queries_possible': True,
                  'runtime_authorization_enabled': False,
                  'installed_engine_hash_observed': False,
                  'scope': 'Only the typedguard-bound eight process identities, current baseline/app scope, boot, historical activation pin, config, original Main limits and counters. No new QA epoch or full-interval noninterference qualification.'}
    except BaseException as error:
        failure = error
    finally:
        if cg_fd is not None:
            try:
                os.close(cg_fd)
            except BaseException as error:
                cleanup_errors.append({'phase': 'main-cgroup-close', 'type': type(error).__name__,
                                       'errno': getattr(error, 'errno', None)})
        # If the watchdog fired, no successful JSON can have been emitted.
        # Clear it only after local FD retirement; explicit time qualification remains.
        within_deadline = time.monotonic() < DEADLINE
        signal.alarm(0)
    qualify_finish(failure, cleanup_errors, within_deadline)
    result['finished_monotonic_ns'] = time.monotonic_ns()
    result['cleanup_errors'] = cleanup_errors
    return result


if __name__ == '__main__':
    try:
        print(json.dumps(capture(), separators=(',', ':')), flush=True)
    except Exception as error:
        safe = {'type': type(error).__name__, 'errno': getattr(error, 'errno', None)}
        if isinstance(error, RuntimeError) and all(c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ_0123456789' for c in str(error)):
            safe['code'] = str(error)
        print(json.dumps({'schema': 2, 'ok': False, 'error': safe,
                          'Main_actions': 0, 'Android_actions': 0,
                          'old_QA_epoch_invalid': True, 'new_QA_epoch_qualified': False,
                          'runtime_authorization_enabled': False}), flush=True)
        raise SystemExit(1)
