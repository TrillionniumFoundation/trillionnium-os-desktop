#!/usr/bin/env python3
"""Bounded normal CP3A vendor build with the original source locks and recovery.

The outer controller holds the original serial lock through build retirement,
normal source recovery, and verification. No host Android installation occurs.
"""
from pathlib import Path
import ctypes
import fcntl
import hashlib
import importlib.util
import json
import os
import shutil
import signal
import stat
import subprocess
import sys
import time
import traceback
from contextlib import contextmanager

ROOT = Path('/home/qq/work/p4-official-vendor-cp3a-20261118-162b-r1')
REPO = ROOT / 'producer-build-r19-9907'
WORK = Path('/home/qq/work/pocket4-native-source597-ai395-20261108-8b88-r1/work')
SOURCE = WORK / 'aosp-source'
DEPS = Path('/home/qq/work/p4-vendor-hostdeps-20261118-162b-r1')
CONTROL = ROOT / 'control/vendor-build-20261120-9907-r19/actual'
OUT = ROOT / 'out-build-r19-9907'
TMP = ROOT / 'tmp-build-r19-9907'
SELF = ROOT / 'control/vendor-build-20261120-9907-r19/source.py'
UNIT = 'p4-cp3a-vendor-20261120-9907-r19'
RECOVERY_UNIT = UNIT + '-recovery'
GIB = 1024 ** 3
TREE = 'fa0382574f4fc18f59b2b5dd67a30939167d8c3a'
INVENTORY = '5f131f2dbcccafb735b84594e5b1a5c29a77b2e4c9c7882d76b2e66c7a5ee473'
SYSTEM = ROOT / 'official-gsi/images/system.img'
NATIVE_ROOT = Path('/home/qq/work/p4-vendor-source-fix-20261118-162b-r1/teto-engine-source-r1')
NATIVE_MANIFEST = Path('/home/qq/work/p4-vendor-source-fix-20261118-162b-r1/input-freeze-r1/EXPECTED_INPUT.json')
LOCK = REPO / 'android/manifest/production-full-cmake-source-lock.json'
MR = Path('/home/qq/work/p4-broker-mac-provider-20261118-162b-r1')
PACKET = MR / 'cmake652-final-packet-r1'
RELEASE = Path('/home/qq/work/p4-integrated-continuation-20261118-162b-r1/unified-native-capex-asb-20261119-r2/release-tools-r1/bin')
SOURCE_TOOL = RELEASE / 'droidloom-source'
UPDATE_TOOL = RELEASE / 'droidloom-update'
OLD_LOCK = ROOT / 'producer-build-r6/android/manifest/production-full-source-lock.json'
RECOVERY_LOCK = PACKET / 'files/android/manifest/production-full-cmake-source-lock.json'
BOOKEND_PATH = ROOT / 'control/vendor-build-20261120-9907-r19/inputs/vendor_source_bookends_text_auto_9907.py'
CMAKE_PROJECT = SOURCE / 'prebuilts/cmake/linux-x86'
OLD_TREE = 'ed4664376e9c4b60de0f4359753862425ab41d75'
BOOKENDS = None
BASE_SOURCE = None
# Actual inc18 fixed-source freeze and original compiler retirement. This
# grants no disk/memory admission: both original fresh resource gates still run.
INC18_RETIREMENT = (
    '/home/qq/work/p4-runtime-continuation-20261118-162b-r1/increment-18/FINAL-FREEZE-RETIREMENT.json',
    3690, 'cf1ee0f86de62d58658b1b1fcf6bfa83bb3e799261710c34af31ef73a79ff253',
    'hepta-runtime-job-1a1f0474cc0-ffbe-763.service',
)
INC18_PRIOR_UNITS = [
    'hepta-runtime-job-1a1f04256da-ffbe-754.service',
    'hepta-runtime-job-1a1f0446d43-ffbe-75b.service',
    'hepta-runtime-job-1a1f04697e7-ffbe-761.service',
]
SERIAL = WORK.parent / 'native-full.serial.lock'
LOCK_PINS = [(SERIAL, 60857531), (WORK / 'package-build.lock', 60857480),
             (WORK / 'aosp-source-update.lock', 60857481)]
PINS = {
    Path('/home/qq/work/p4-vendor-source-fix-20261118-162b-r1/increment-production-local-signer-r1/SOURCE_FREEZE.json'): (4931, '8d03be88b1e9c23b8e1069340ccce0cd7458578d8ea9e6789b880102a602cca8'),
    Path('/home/qq/work/p4-vendor-source-fix-20261118-162b-r1/increment-production-local-signer-r1/DEPENDENCY-CLOSURE.json'): (7949, 'cb49fa404e3c7fad171407bed33216e16249125a96f5bb40379b205e733ef2d4'),
    Path('/home/qq/work/p4-vendor-source-fix-20261118-162b-r1/increment-production-local-signer-r1/VALIDATION.json'): (39049, '8590595280f893136ec5deb5d93bbe53dc3b65fec597d6e5734a225e4db362ee'),
    NATIVE_MANIFEST: (281101, '381f6852a217165edf649560c4bb292888c5b7cb5560a8b61abc40156f0e4667'),
    ROOT / 'packet-build-r6/verify.py': (28699, '5c630d2406135ba06ea08519055ea0b411e2beec1f0660a3f2b18432e66465ce'),
    ROOT / 'packet-build-r6/run_ci.py': (38239, '37f91a7989085b1b1114c010f0249159ae15993d631be3f9834d155fee6be1d1'),
    UPDATE_TOOL: (10007608, '7c34570d60681e7c725ccdb4f61e7c16dc2686ae497851d595349d382d6b6e27'),
    SOURCE_TOOL: (1939704, '59ceb228cdceb18597c2b10efbb896b38736a1ce67d3df208b5498509e907e43'),
    LOCK: (400661, '2e9877a58ebbc3625c7411d3573951afa409d9b13692468b825b4c25961ffffb'),
    OLD_LOCK: (400363, '30dcc1b5b090530b3fc06aeb3e489a961b0fc7c6368ed9d19eb0a1b2054e3eb4'),
    RECOVERY_LOCK: (400661, '2e9877a58ebbc3625c7411d3573951afa409d9b13692468b825b4c25961ffffb'),
    PACKET / 'SOURCE_FREEZE.json': (43944, '3f83c34869547c4d122574baa87d21e06094b783d3035eda5754e03fb32c047e'),
    PACKET / 'canonical-original-rows.json': (686369, 'b4487946940984c30cd5d7a3b2aaa821f183cedd13ef55bf6e56bd3ae392be44'),
    PACKET / 'canonical-tested-rows.json': (687144, '4495ec25cffb4cd06032fb5539b3b6811c904464c9035efefc50df52e055e34c'),
    BOOKEND_PATH: (29338, 'bab5c377bf642d4aaa7b50a416319cebad31537022e5179a77e6e8d63827fa88'),
    PACKET / 'evidence/vendor-cmake-provider-r1/OBSERVATION.json': (434968, '6f2029333aaba2b59563dccb4ee5d96c95cc714ea1d6c3ee7aca1be0a46813c0'),
    ROOT / 'control/vendor_build_r9.py': (37347, 'ef63b542be4506d09bea4b10db4d6461078ca0ad5b378aebb1abb8a6ae78d7d5'),
    DEPS / 'environment.json': (732, '47378c8e21bd23366d5c47e36dcef33705dace9d1e15ba3dbfeb12965b716dfd'),
    DEPS / 'dependency-validation.json': (16012, '1636b3a37b93208da2ae5952355c49d257c4c2a67c3de6e3be94ca25048846ce'),
    SYSTEM: (2294853632, 'dc781249bb4724b7a0777e5077321b84576db46f61abb4b9086b81077bfd0ab4'),
}
CANONICAL_SOURCE = Path('/home/qq/work/p4-integrated-continuation-20261118-162b-r1/unified-native-capex-asb-20261119-r2/producer')
CANONICAL_ROWS = Path('/home/qq/work/p4-integrated-continuation-20261118-162b-r1/unified-native-capex-asb-20261119-r2/SOURCE-ROWS-TESTED.json')
CANONICAL_FREEZE = Path('/home/qq/work/p4-integrated-continuation-20261118-162b-r1/unified-native-capex-asb-20261119-r2/SOURCE_FREEZE.json')
CANONICAL_FILES = 2336
CANONICAL_BYTES = 43854389
R11_RETIREMENT = Path('/home/qq/work/p4-broker-mac-provider-20261118-162b-r1/vendor-r11-latest-retirement-r2.json')
R11_RETIRED_UNITS = ['hepta-runtime-job-1a1f1f27008-ffbe-971.service', 'p4-beike-aurora-compile-20261119-r2.service', 'p4-kernel-native-exit-tu-20261119-r2.service', 'p4-kernel-output-entry-read-20261119-r1.service', 'p4-r11-lifecycle-partof-inner-r3.service', 'p4-r11-lifecycle-partof-parent-r3.service', 'p4-r11-lifecycle-r3-case-1-build.service', 'p4-r11-lifecycle-r3-case-1-recover.service', 'p4-r11-lifecycle-r3-case-2-build.service', 'p4-r11-lifecycle-r3-case-2-recover.service', 'p4-r11-lifecycle-r3-case-3-build.service', 'p4-r11-lifecycle-r3-case-3-recover.service', 'p4-r11-lifecycle-r3-case-4-build.service', 'p4-r11-lifecycle-r3-case-4-recover.service', 'p4-r11-lifecycle-unknown-build-r3.service', 'p4-r11-lifecycle-unknown-parent-r3.service', 'p4-r11-lifecycle-unknown-recover-r3.service', 'p4-real28-capex-compile-20261119-root-r1.service', 'p4-real28-capex-run-20261119-root-r1.service', 'p4-unified-current-packet-20261119-root-r1.service', 'p4-unified-current-packet-finalize-20261119-root-r2.service', 'p4-unified-native-capex-asb-release-20261119-root-r1.service', 'p4-unified-native-capex-asb-validate-20261119-root-r1.service', 'p4-unified-native-capex-asb-validate-20261119-root-r2.service', 'p4-unified-native-capex-asb-validate-20261119-root-r3.service', 'p4-unified-native-capex-asb-validate-20261119-root-r4.service', 'p4-unified-native-capex-asb-validate-20261119-root-r5.service', 'p4-unified-native-capex-asb-validate-20261119-root-r6.service', 'p4-vendor-r11-complete-preparation-20261119-r1.service', 'p4-vendor-r11-complete-preparation-20261119-r2.service', 'p4-vendor-r11-lifecycle-controls-20261119-r2.service', 'p4-vendor-r11-lifecycle-controls-20261119-r3.service']
PINS.update({CANONICAL_ROWS: (695778, 'fc2a18d512c621a582e5f6dd75aedff03137bdadc3c3b162a8553c125bcfa159'), CANONICAL_FREEZE: (14044, '3cfc7b0407cb9bfaebb595c880a4445fbc80d3adf6bb5dd5183e0a33c808f439'), R11_RETIREMENT: (13399, 'f025b3eb9c9c9070d95a5d141313391d9d1936ed1642a03dc595483018b6dee2')})
PLAN_ROOT = MR / 'vendor-r12-source-inputs-r1/actual'
PLAN651 = PLAN_ROOT / 'plan651.json'
PLAN652 = PLAN_ROOT / 'plan652.json'
PLAN_EVIDENCE = PLAN_ROOT / 'RESULT.json'
R11_TERMINAL_RETIREMENT = Path('/home/qq/work/p4-integrated-continuation-20261118-162b-r1/vendor-r11-final-retirement-r1/RESULT.json')
R12_RETIRED_UNITS = [
    'p4-cp3a-vendor-supervisor-20261119-162b-r11.service',
    'p4-cp3a-vendor-20261119-162b-r11.service',
    'p4-cp3a-vendor-20261119-162b-r11-recovery.service',
    'p4-vendor-r11-retirement-20261119-root-r1.service',
    'p4-vendor-r12-plans-20261119-r1.service',
]
PINS.update({
    PLAN651: (419480, 'b68746f9408d3d0618caf28e1db0c421a1f2ae2fe37dc85c7b5f0561bf7b5982'),
    PLAN652: (419810, 'e478b7103136e936522f77633f541ee1f6af2d200c7f7f4d4dee82f458fcb6cc'),
    PLAN_EVIDENCE: (10865, 'e3e7fac5857fdc5423f408ea685721db410bfa73478b7ae75de4b715b52eb0ca'),
    R11_TERMINAL_RETIREMENT: (7946, 'aee4308e3acfb86049d1fa41276b8936937f6ca99412d3b8d2f2665ba33db18e'),
})
R13_SOURCE_CONTROLS = ROOT / 'control/vendor_r13_5cd1_source_controls.json'
PINS[R13_SOURCE_CONTROLS] = (51448, '841ad38ca4dc7b90e7891cd43bef54f96f3b91a1d9ede7b7d59c99d317ac1090')

OBS = {'schema': 'p4-cp3a-normal-vendor-build-r19-v1', 'started_ns': time.time_ns(),
       'production_ready': False, 'runtime_qualified': False, 'installed': False,
       'source_tree': TREE, 'commands': [], 'errors': [], 'actual_updater_release_source_tree': 'fa0382574f4fc18f59b2b5dd67a30939167d8c3a', 'updater_release_and_full_canonical_source_tree_identical': True}
DEADLINE = None
CG = None
BASE_WORK = None
BASE_LIGHT = None
LIGHT_ROOTS = [
    Path('/home/qq/work/p4-remaining-app-inputs-20261118-162b-r1'),
    Path('/home/qq/work/p4-integrated-continuation-20261118-162b-r1'),
    Path('/home/qq/work/p4-runtime-continuation-20261118-162b-r1'),
    Path('/home/qq/work/p4-vendor-source-fix-20261118-162b-r1'),
    Path('/home/qq/work/p4-broker-mac-provider-20261118-162b-r1'),
    Path('/home/qq/work/p4-source-baseline-refresh-20261118-162b-r1'),
    Path('/home/qq/work/p4-kernel-6.18.64-cp3a-20261118-r1'),
]
LAST_DISK = 0.0
VERIFY = None
RUNNER = None
OBSERVATION_NAME = 'build-observation.json'


def need(value, message):
    if not value:
        raise RuntimeError(message)


def f9(s):
    return [s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_gid, s.st_nlink,
            s.st_size, s.st_mtime_ns, s.st_ctime_ns]


# Read-only host ABI input: exact root-owned inode, link count and content.
# Source inputs and new build outputs still require exactly one hard link.
HOST_READONLY_SHARED_INPUTS = {row['path']: row for row in [{"path":"/usr/lib/x86_64-linux-gnu/libstdc++.so.6.0.35","identity_strings":["66306","82182585","33188","0","0","2","2735712","1774168304000000000","1792407210846860418"],"bytes":2735712,"sha256":"5bb0d21308f123b6ad46c6f35b42cedfcb8d6d439a53aa3dae04d880aaffdde3"}]}

def digest(path):
    path = Path(path)
    need(path.resolve() == path, 'input alias: ' + str(path))
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = f9(os.fstat(fd))
        need(stat.S_ISREG(before[2]), 'ordinary input: ' + str(path))
        shared = HOST_READONLY_SHARED_INPUTS.get(str(path))
        if shared is None:
            need(before[5] == 1, 'ordinary single-link input: ' + str(path))
        else:
            need([str(v) for v in before] == shared['identity_strings']
                 and before[3] == before[4] == 0 and not before[2] & 0o022,
                 'exact read-only root host library identity: ' + str(path))
        h = hashlib.sha256()
        with os.fdopen(os.dup(fd), 'rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                h.update(block)
        need(before == f9(os.fstat(fd)) == f9(path.lstat()), 'changed input: ' + str(path))
        if shared is not None:
            need(before[6] == shared['bytes'] and h.hexdigest() == shared['sha256'],
                 'exact read-only host library content: ' + str(path))
        return {'path': str(path), 'identity': before, 'bytes': before[6], 'sha256': h.hexdigest()}
    finally:
        os.close(fd)


def save(name=None):
    name = name or OBSERVATION_NAME
    target = CONTROL / name
    temporary = target.with_suffix('.tmp')
    temporary.write_text(json.dumps(OBS, sort_keys=True, indent=2) + '\n')
    os.replace(temporary, target)


def import_pinned():
    global VERIFY, RUNNER, BOOKENDS
    for path in (ROOT / 'packet-build-r6/verify.py', ROOT / 'packet-build-r6/run_ci.py'):
        row = digest(path)
        need((row['bytes'], row['sha256']) == PINS[path], 'pinned helper changed')
    def get(name, path):
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    VERIFY = get('vendor_exact_source', ROOT / 'packet-build-r6/verify.py')
    RUNNER = get('vendor_owned_children', ROOT / 'packet-build-r6/run_ci.py')
    row = digest(BOOKEND_PATH)
    need((row['bytes'], row['sha256']) == PINS[BOOKEND_PATH], 'content bookend helper pin')
    BOOKENDS = get('original_source_content', BOOKEND_PATH)
    need(ctypes.CDLL(None, use_errno=True).prctl(36, 1, 0, 0, 0) == 0, 'subreaper admission')
    need(not RUNNER.owned_children(), 'pre-existing child')


def memory_available():
    for line in Path('/proc/meminfo').read_text().splitlines():
        if line.startswith('MemAvailable:'):
            return int(line.split()[1]) * 1024
    raise RuntimeError('MemAvailable absent')


def lock_records(path):
    s = path.lstat()
    key = f'{os.major(s.st_dev):02x}:{os.minor(s.st_dev):02x}:{s.st_ino}'
    return [line for line in Path('/proc/locks').read_text().splitlines() if key in line.split()]


def check_lock(path, inode):
    s = path.lstat()
    need(path.resolve() == path and f9(s)[:6] == [66306, inode, 33152, 1000, 1000, 1],
         'original lock identity differs: ' + str(path))
    return f9(s)


def allocated(roots):
    roots = [str(p) for p in roots if os.path.lexists(p)]
    if not roots:
        return 0
    result = subprocess.run(['/usr/bin/du', '--one-file-system', '--summarize', '--block-size=1',
                             '--', *roots], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            timeout=60, check=False)
    # File replacement during a build can make du report an actual transient
    # disappearance. Keep the prior measurement, and retry on the next guard.
    if result.returncode:
        missing_only = all('No such file or directory' in line for line in result.stderr.decode().splitlines())
        if missing_only:
            raise FileNotFoundError(result.stderr.decode()[:2000])
        raise RuntimeError('allocation accounting failed: ' + result.stderr.decode()[:2000])
    return sum(int(line.split(b'\t', 1)[0]) for line in result.stdout.splitlines())


def work_roots():
    return [p for p in WORK.iterdir() if p.name != 'aosp-source']


def resource_guard(force_disk=False):
    global LAST_DISK
    need(time.monotonic() < DEADLINE, 'original fixed build deadline')
    mem = memory_available()
    free = shutil.disk_usage(ROOT).free
    need(mem >= 8 * GIB, 'emergency host memory reserve')
    need(free >= 24 * GIB, 'host disk floor')
    row = {'observed_ns': time.time_ns(), 'memory_available': mem, 'disk_free': free}
    if force_disk or time.monotonic() - LAST_DISK >= 60:
        try:
            added = (allocated([OUT, TMP, CONTROL, REPO])
                     + max(0, allocated(work_roots()) - BASE_WORK)
                     + max(0, allocated([SOURCE]) - BASE_SOURCE))
            light_growth = max(0, allocated(LIGHT_ROOTS) - BASE_LIGHT)
            need(added <= 118 * GIB, 'vendor output and cache growth allocation')
            need(light_growth <= 2 * GIB, 'all light task roots combined growth allocation')
            need(added + light_growth <= 120 * GIB, 'original aggregate output and cache growth budget')
            row['own_output_and_cache_growth'] = added
            row['light_task_roots_growth'] = light_growth
            row['combined_growth'] = added + light_growth
            LAST_DISK = time.monotonic()
        except FileNotFoundError as error:
            row['allocation_snapshot_retry'] = str(error)
    OBS['latest_resources'] = row
    save()


def run(name, argv, env, timeout, guard=False):
    out_path, err_path = [CONTROL / (name + suffix) for suffix in ('.stdout', '.stderr')]
    row = {'name': name, 'argv': [str(v) for v in argv], 'started_ns': time.time_ns()}
    fd = None
    child = None
    error = None
    until = time.monotonic() + timeout
    with out_path.open('xb') as output, err_path.open('xb') as err:
        try:
            child = subprocess.Popen(argv, cwd=REPO if REPO.is_dir() else ROOT, env=env, stdin=subprocess.DEVNULL,
                                     stdout=output, stderr=err, start_new_session=True)
            fd = os.pidfd_open(child.pid)
            row.update(pid=child.pid, start_ticks=Path(f'/proc/{child.pid}/stat').read_text().rsplit(') ', 1)[1].split()[19])
            OBS['active_command'] = row
            save()
            progress = 0.0
            while child.poll() is None:
                need(time.monotonic() < until, 'command fixed deadline: ' + name)
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
                if guard:
                    resource_guard()
                if time.monotonic() >= progress:
                    print(json.dumps({'stage': name, 'elapsed_seconds': (time.time_ns() - row['started_ns']) // 10**9,
                                      'latest_resources': OBS.get('latest_resources')}), flush=True)
                    progress = time.monotonic() + 60
        except BaseException as failure:
            error = repr(failure)
        finally:
            if child is not None and child.returncode is None:
                for sig in (signal.SIGTERM, signal.SIGKILL):
                    try:
                        # Before parent wait/reap, this original child PID and
                        # its new session/process group cannot be recycled.
                        os.killpg(child.pid, sig)
                    except ProcessLookupError:
                        pass
                    try:
                        child.wait(timeout=10)
                        break
                    except subprocess.TimeoutExpired:
                        pass
            row['retired_descendants'] = RUNNER.reap_descendants()
            row['owned_descendants_remaining'] = len(RUNNER.owned_children())
            row['exit_code'] = None if child is None else child.returncode
            row['actual_child_reaped'] = child is not None and child.returncode is not None
            row['original_pidfd_held_until_reaped'] = fd is not None and row['actual_child_reaped']
            if fd is not None:
                os.close(fd)
    row.update(finished_ns=time.time_ns(), error=error, stdout=digest(out_path), stderr=digest(err_path))
    OBS['commands'].append(row)
    OBS.pop('active_command', None)
    save()
    need(error is None and row['exit_code'] == 0 and row['actual_child_reaped']
         and row['owned_descendants_remaining'] == 0, 'command or retirement failed: ' + name)
    return out_path


def environment():
    env = os.environ.copy()
    for key in ('OUT_DIR', 'OUT_DIR_COMMON_BASE', 'DIST_DIR', 'MAKEFLAGS', 'SOONG_ALLOW_MISSING_DEPENDENCIES',
                'ALLOW_MISSING_DEPENDENCIES', 'SELINUX_IGNORE_NEVERALLOWS', 'LD_PRELOAD',
                'RUSTC_WRAPPER', 'CC', 'CXX', 'CFLAGS', 'CXXFLAGS', 'LDFLAGS', 'PKG_CONFIG_SYSROOT_DIR'):
        env.pop(key, None)
    env.update(json.loads((DEPS / 'environment.json').read_text()))
    for key in list(env):
        if key.startswith('CCACHE_'):
            env.pop(key)
    env.update(TMPDIR=str(TMP), CCACHE_MAXSIZE='2G', DROIDLOOM_NATIVE_BRIDGE_SOURCE=str(NATIVE_ROOT), GIT_OPTIONAL_LOCKS='0')
    env['PATH'] = str(RELEASE) + ':' + env['PATH']
    return env



def native_snapshot():
    pin = digest(NATIVE_MANIFEST)
    need((pin['bytes'], pin['sha256']) == PINS[NATIVE_MANIFEST], 'native source manifest pin')
    manifest = json.loads(NATIVE_MANIFEST.read_text())
    wanted = {
        'commit': '9587399bccdbb7ec6f7de3edd3452609b974eb7c',
        'tree': 'cfe7f91f5afe6758e9dd94c7d4c09ae8e50eb150',
        'parent': '917021cf3ecd077eb1581146a79d2265011755b8',
        'origin': 'https://github.com/denialwm/teto.git',
        'upstream_commit': '917021cf3ecd077eb1581146a79d2265011755b8',
        'upstream_tree': '5e2d7e1577a7bb03917fee7b2ad66b72d09bff85',
        'member_count': 926, 'required_clean_worktree': True,
        'normal_parameter': 'DROIDLOOM_NATIVE_BRIDGE_SOURCE',
        'normal_path': str(NATIVE_ROOT),
        'production_function_sha256': '301378540ea1ba4bbe794540906dfb601583ecc4c484444c9129be4cee3b0a85',
    }
    need(all(manifest.get(k) == v for k, v in wanted.items()), 'exact original native source input')
    need(NATIVE_ROOT.resolve() == NATIVE_ROOT and (NATIVE_ROOT / '.git').is_dir()
         and not (NATIVE_ROOT / '.git').is_symlink(), 'real local native Git checkout required')
    def git(*args):
        result = subprocess.run(['/usr/bin/git', '-C', str(NATIVE_ROOT), *args],
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, env={**os.environ, 'GIT_OPTIONAL_LOCKS': '0'},
                                timeout=120, check=False)
        need(result.returncode == 0, 'native Git command failed: ' + repr(args) + result.stderr.decode(errors='replace')[:1000])
        return result.stdout
    identity = {
        'commit': git('rev-parse', 'HEAD').decode().strip(),
        'tree': git('rev-parse', 'HEAD^{tree}').decode().strip(),
        'parent': git('rev-parse', 'HEAD^').decode().strip(),
        'origin': git('config', '--get', 'remote.origin.url').decode().strip(),
        'upstream_tree': git('rev-parse', wanted['upstream_commit'] + '^{tree}').decode().strip(),
    }
    need(all(identity[k] == wanted[k] for k in identity), 'actual native Git provenance mismatch')
    git('merge-base', '--is-ancestor', wanted['upstream_commit'], wanted['commit'])
    need(git('status', '--porcelain=v1', '--untracked-files=all') == b'', 'native source worktree not clean')
    git('fsck', '--full', '--strict', '--no-reflogs')
    tree = {}
    for entry in git('ls-tree', '-rz', '--full-tree', 'HEAD').split(b'\0'):
        if not entry:
            continue
        header, rawpath = entry.split(b'\t', 1)
        mode, kind, blob = header.decode().split()
        need(kind == 'blob', 'native source non-blob entry')
        tree[rawpath.decode()] = (mode, blob)
    expected = manifest['files']
    need(len(expected) == 926 and set(tree) == set(expected), 'native committed membership')
    names = set()
    for directory, children, files in os.walk(NATIVE_ROOT, followlinks=False):
        if Path(directory) == NATIVE_ROOT:
            need('.git' in children, 'native Git metadata absent')
            children.remove('.git')
        for name in children:
            child = Path(directory) / name
            need(child.is_dir() and not child.is_symlink(), 'native directory alias')
        for name in files:
            names.add(str((Path(directory) / name).relative_to(NATIVE_ROOT)))
    need(names == set(expected), 'native working member inventory differs')
    frozen = []
    for relative, item in sorted(expected.items()):
        need(item['kind'] == 'file' and tree[relative] == (item['git_mode'], item['git_blob_sha1']),
             'native member kind or committed body differs')
        path = NATIVE_ROOT / relative
        actual = digest(path)
        need(actual['bytes'] == item['bytes'] and actual['sha256'] == item['sha256']
             and stat.S_IMODE(actual['identity'][2]) == item['mode'], 'native working source differs: ' + relative)
        frozen.append(actual)
    need(not RUNNER.owned_children(), 'native Git children not reaped')
    return {'manifest': pin, 'git': identity, 'member_count': len(frozen), 'files': frozen}


def check_inputs():
    frozen = []
    for path, pin in PINS.items():
        actual = digest(path)
        need((actual['bytes'], actual['sha256']) == pin, 'pinned build input: ' + str(path))
        frozen.append(actual)
    deps = json.loads((DEPS / 'dependency-validation.json').read_text())
    need(deps['host_dependency_validation_passed'] is True, 'dependency validation')
    for item in deps['tools'] + deps['linked_runtime_files']:
        path = Path(item.get('resolved', item['path']))
        actual = digest(path)
        need(actual['bytes'] == item['bytes'] and actual['sha256'] == item['sha256'], 'dependency changed: ' + str(path))
        frozen.append(actual)
    for path in sorted((ROOT / 'official-vendor-inputs').rglob('*')):
        need(not path.is_symlink(), 'vendor reference alias')
        if path.is_file():
            frozen.append(digest(path))
    native = native_snapshot()
    (CONTROL / 'native-source-before.json').write_text(json.dumps(native, indent=2) + '\n')
    frozen.extend(native['files'])
    OBS['native_source_git'] = native['git']
    OBS['native_source_member_count'] = native['member_count']
    capsule = VERIFY.verify_capsule(INVENTORY)
    need(VERIFY.tree_id(capsule['rows']) == OLD_TREE, 'unchanged original canonical source')
    rows = json.loads(CANONICAL_ROWS.read_text())
    source = VERIFY.source_snapshot(REPO, rows, TREE)
    return frozen, rows, source


def cgroup_admit(memory_gib, high_gib, cpus, pids):
    global CG
    raw = Path('/proc/self/cgroup').read_text().strip()
    need(raw.startswith('0::/'), 'cgroup v2 required')
    CG = Path('/sys/fs/cgroup') / raw[4:]
    limits = {n: (CG / n).read_text().strip() for n in
              ('memory.max', 'memory.high', 'memory.swap.max', 'pids.max', 'cpu.max')}
    need(limits['memory.max'] == str(int(memory_gib * GIB)) and limits['memory.high'] == str(int(high_gib * GIB))
         and limits['memory.swap.max'] == '0' and limits['pids.max'] == str(pids), 'exact resource limits')
    quota, period = map(int, limits['cpu.max'].split())
    need(quota == cpus * period and os.sched_getaffinity(0) == set(range(16)), 'CPU budget and reservation')
    return {'cgroup': str(CG), 'limits': limits, 'affinity': sorted(os.sched_getaffinity(0)),
            'pid': os.getpid(), 'start_ticks': Path('/proc/self/stat').read_text().rsplit(') ', 1)[1].split()[19]}


def verify_outer():
    record = json.loads((CONTROL / 'outer-admission.json').read_text())
    pid = record['pid']
    need(Path(f'/proc/{pid}/stat').read_text().rsplit(') ', 1)[1].split()[19] == record['start_ticks'], 'original outer controller')
    held = lock_records(SERIAL)
    need(len(held) == 1 and str(pid) in held[0].split(), 'original outer serial lock not held')
    return record


# R10 preserves the original R9 resource and three-lock contract. All original
# admissions and failures stay immutable. New canonical replay, full CMake fetch,
# normal source reconciliation and content bookends consume the same 118 GiB
# vendor / 2 GiB light / 120 GiB combined growth budget, never an extra reserve.
SERIALIZED_RETIREMENTS = [
    (Path('/home/qq/work/p4-runtime-continuation-20261118-162b-r1/increment-16/validation-r2-retirement.json'), 371, '5227627c14ec438e7342682eff3e43621aeebbe7fe47dd53fd95a2abcc164f4f', 'hepta-runtime-job-1a1efeed3cf-ffbe-683.service'),
    (Path('/home/qq/work/p4-runtime-continuation-20261118-162b-r1/increment-15/validation-r2-retirement.json'), 206, '9762d056176303cc6f8d7bb89dcffb267db333c6a3a02fa66c6360f968aeeb02', 'hepta-runtime-job-1a1efcb1c52-ffbe-5ef.service'),
    (Path('/home/qq/work/p4-source-baseline-refresh-20261118-162b-r1/RETIREMENT-r3.json'), 258, 'abe57dcef06cd90909b408cdebc4022bdefbc748fc40e40283d51e7d8e15221c', 'p4-source-baseline-refresh-20261118-r3.service'),
    (Path('/home/qq/work/p4-source-baseline-refresh-20261118-162b-r1/RETIREMENT-controls-r1.json'), 1988, '52b85111e9b279dc90d699ed705ab51ab94ba9e7ca663d31ec7a6868517bd023', 'p4-source-baseline-controls-20261118-r1.service'),
]

def verify_serialized_retirement():
    rows = []
    for path, size, sha, unit in SERIALIZED_RETIREMENTS:
        pin = digest(path)
        need((pin['bytes'], pin['sha256']) == (size, sha), 'heavy worker retirement pin: ' + str(path))
        receipt = json.loads(path.read_text())
        need(receipt['unit'] == unit, 'original retired worker unit')
        if 'all_original_compiler_children_reaped' in receipt:
            need(receipt['all_original_compiler_children_reaped'] is True, 'original compiler child retirement')
        else:
            need(receipt['cgroup_absent'] is True and receipt['fields']['ActiveState'] == 'inactive'
                 and receipt['fields']['MainPID'] == '0', 'original baseline retirement')
        result = status_run(['/usr/bin/systemctl', '--user', 'show', unit,
            '--property=LoadState,ActiveState,SubState,MainPID,ControlGroup'],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=15, check=False)
        fields = dict(line.split('=', 1) for line in result.stdout.decode().splitlines() if '=' in line)
        need(fields.get('LoadState') == 'not-found' and fields.get('ActiveState') == 'inactive'
             and fields.get('MainPID') == '0' and fields.get('ControlGroup') == '',
             'heavy worker no longer retired: ' + unit)
        cg = Path('/sys/fs/cgroup/user.slice/user-1000.slice/user@1000.service/app.slice') / unit
        need(not os.path.lexists(cg), 'retired heavy worker cgroup present')
        rows.append({'pin': pin, 'unit': unit, 'actual_fields': fields,
                     'systemctl_exit_code': result.returncode, 'cgroup_absent': True})
    extra = verify_cmake_and_latest_retirement()
    latest = verify_r11_latest_retirement()
    r12 = verify_r12_latest_retirement()
    predecessor = verify_r13_predecessor_retirement()
    previous_r14 = verify_r14_admission_failure()
    return {'actual_R14_prebuild_admission_failure': previous_r14, 'actual_R12_failure_retirement': predecessor, 'latest_r12_retirements': r12, 'latest_r11_retirements': latest, 'extra_exact_retirements': extra, 'schema': 'p4-serialized-heavy-build-resource-plan-v1', 'original_minimum_memory_gib': 42,
            'vendor_memory_max_gib': 24, 'simultaneous_other_heavy_compilers': 0,
            'bounded_light_scopes_max_gib': 3.25, 'host_reserve_gib': 12,
            'unallocated_margin_within_minimum_gib': 2.75, 'actual_retirements': rows,
            'observed_ns': time.time_ns()}


def check_pin(path):
    row = digest(path)
    need((row['bytes'], row['sha256']) == PINS[path], 'pinned new source input: ' + str(path))
    return row


def verify_cmake_and_latest_retirement():
    final = check_pin(PACKET / 'SOURCE_FREEZE.json')
    receipt = json.loads((PACKET / 'SOURCE_FREEZE.json').read_text())
    need(receipt['ordinary_source_tests_passed'] == 94
         and receipt['ordinary_updater_related_tests_passed'] == 38
         and receipt['ordinary_failed'] == receipt['ordinary_ignored'] == 0,
         'actual CMake source and updater controls')
    # A complete exact original receipt and fresh actual unit/cgroup retirement
    # are both mandatory; elapsed time or an unrelated new receipt is insufficient.
    need(isinstance(INC18_RETIREMENT, tuple) and len(INC18_RETIREMENT) == 4,
         'original inc18 compiler receipt has not yet been frozen')
    path, size, sha, final_unit = INC18_RETIREMENT
    pin = digest(Path(path))
    need((pin['bytes'], pin['sha256']) == (size, sha), 'actual inc18 retirement pin')
    completed = json.loads(Path(path).read_text())
    need(completed['schema'] == 'p4-inc18-final-freeze-retirement-v1'
         and completed['state'] == 'PASSED'
         and completed['source_actual_f9_sha_matches_complete_tested_bookend'] is True
         and completed['all_original_command_pidfds_retained_until_actual_reap'] is True
         and completed['six_commands_actual_reaped'] is True
         and completed['actual_ordinary_tests'] == 493 and completed['actual_ignored_tests'] == 25
         and completed['old_test_cases_removed'] == 0 and completed['additional_Rust_commands'] == 0,
         'actual complete original inc18 source/commands and retirement')
    expected_units = INC18_PRIOR_UNITS + [final_unit]
    need([x['unit'] for x in completed['units']] == expected_units,
         'all four exact original inc18 workers required')
    for item in completed['units']:
        need(item['properties'] == {'LoadState': 'not-found', 'ActiveState': 'inactive',
             'SubState': 'dead', 'MainPID': '0', 'ControlGroup': ''}
             and item['actual_cgroups'] == [], 'original inc18 retirement fact incomplete')
    need(digest(Path(path)) == pin, 'original inc18 retirement input changed')
    # The controller also requires every known compiler's real unit/cgroup to
    # remain gone at both fresh admissions.
    units = [x['unit'] for x in receipt['original_scope_retirement']]
    units += ['hepta-runtime-job-1a1f028e319-ffbe-722.service', final_unit,
              'p4-cp3a-vendor-20261118-162b-r9.service',
              'p4-cp3a-vendor-20261118-162b-r9-recovery.service']
    units += INC18_PRIOR_UNITS
    records = []
    for unit in units:
        result = status_run(['/usr/bin/systemctl', '--user', 'show', unit,
            '--property=LoadState,ActiveState,SubState,MainPID,ControlGroup'],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=15, check=False)
        fields = dict(x.split('=', 1) for x in result.stdout.decode().splitlines() if '=' in x)
        need(result.returncode == 0 and fields.get('LoadState') == 'not-found'
             and fields.get('ActiveState') == 'inactive' and fields.get('SubState') == 'dead'
             and fields.get('MainPID', '0') == '0' and not fields.get('ControlGroup'),
             'actual compiler or prior build retirement: ' + unit)
        cg = Path('/sys/fs/cgroup/user.slice/user-1000.slice/user@1000.service/app.slice') / unit
        need(not os.path.lexists(cg), 'retired compiler cgroup remains')
        records.append({'unit': unit, 'fields': fields, 'cgroup_absent': True})
    return {'source_control_receipt': final, 'inc18_receipt': pin, 'actual_units': records}


def prepare_canonical_producer():
    need(not os.path.lexists(REPO), 'fresh R11 canonical producer required')
    for path in (CANONICAL_ROWS, CANONICAL_FREEZE):
        check_pin(path)
    rows = json.loads(CANONICAL_ROWS.read_text())
    need(len(rows) == CANONICAL_FILES and sum(x['bytes'] for x in rows) == CANONICAL_BYTES
         and VERIFY.tree_id(rows) == TREE, 'full actual release source identity')
    before = VERIFY.source_snapshot(CANONICAL_SOURCE, rows, TREE)
    REPO.mkdir(mode=0o700)
    for row in rows:
        name = row['path']
        body = VERIFY.check(CANONICAL_SOURCE / name, row)
        need(VERIFY.object_id('blob', body) == row['git_blob'], 'exact canonical Git blob')
        path = REPO / name
        path.parent.mkdir(parents=True, exist_ok=True)
        need(path.parent.resolve() == path.parent, 'new canonical directory alias')
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        try:
            view = memoryview(body)
            while view:
                count = os.write(fd, view)
                need(count > 0, 'complete new canonical source')
                view = view[count:]
            os.fchmod(fd, int(row['mode'], 8) & 0o777)
            os.fsync(fd)
        finally:
            os.close(fd)
    need(VERIFY.source_snapshot(CANONICAL_SOURCE, rows, TREE) == before,
         'original complete tested source changed during replay')
    result = VERIFY.source_snapshot(REPO, rows, TREE)
    need(not os.path.lexists(REPO / '.work'), 'no prior Mesa cache admitted as source')
    (CONTROL / 'canonical-producer-replay.json').write_text(json.dumps(result, indent=2) + '\n')
    (CONTROL / 'canonical-source-original-bookends.json').write_text(json.dumps(before, indent=2) + '\n')
    OBS['canonical_producer_replay'] = digest(CONTROL / 'canonical-producer-replay.json')
    OBS['canonical_release_source_original_bookends'] = digest(CONTROL / 'canonical-source-original-bookends.json')
    resource_guard(True)


@contextmanager
def original_source_locks():
    held = []
    try:
        for path, inode in LOCK_PINS[1:]:
            before = check_lock(path, inode)
            fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                need(f9(os.fstat(fd)) == before, 'original source lock replaced')
            except BaseException:
                os.close(fd)
                raise
            held.append((fd, path, inode, before))
        yield
    finally:
        for fd, path, inode, before in reversed(held):
            need(f9(os.fstat(fd)) == before and check_lock(path, inode) == before,
                 'original source lock identity changed')
            os.close(fd)


def manifest_observation(name):
    path = SOURCE / '.droidloom-source-manifest.json'
    pin = digest(path)
    body = path.read_bytes()
    need(digest(path) == pin and hashlib.sha256(body).hexdigest() == pin['sha256'],
         'held normal materialized manifest changed')
    destination = CONTROL / (name + '.json')
    with destination.open('xb') as stream:
        stream.write(body)
    return BOOKENDS.strict_json(body), {'original': pin, 'copy': digest(destination)}


def content_bookend(name, projects):
    result = BOOKENDS.snapshot(SOURCE, projects, CONTROL / (name + '.ndjson'),
                               DEADLINE, resource_guard)
    path = CONTROL / (name + '.json')
    with path.open('x') as stream:
        json.dump(result, stream, sort_keys=True, indent=2)
        stream.write('\n')
    OBS.setdefault('content_bookends', {})[name] = digest(path)
    save()
    return result


def require_original_651(before, after):
    need(before['project_count'] == after['project_count'] == 651
         and before['content_sha256'] == after['content_sha256']
         and before['materialized_entries'] == after['materialized_entries']
         and before['materialized_bytes'] == after['materialized_bytes']
         and before['sparse_absent_entries'] == after['sparse_absent_entries'],
         'original 651 tuples, selected sparse bodies, modes or complete blob hashes changed')


def read_source_json(path, expected=None):
    path = Path(path)
    pin = digest(path)
    need(pin['bytes'] <= 16 * 1024 * 1024, 'bounded source control JSON')
    if expected is not None:
        need(pin == expected, 'original source control pin changed')
    body = path.read_bytes()
    need(hashlib.sha256(body).hexdigest() == pin['sha256'] and digest(path) == pin,
         'held source control JSON bookend')
    return BOOKENDS.strict_json(body), pin


def source_contracts():
    evidence, evidence_pin = read_source_json(PLAN_EVIDENCE)
    check_pin(PLAN_EVIDENCE)
    need(evidence['passed'] is True and evidence['all_original_children_reaped'] is True
         and evidence['inputs_before'] == evidence['inputs_after']
         and evidence['network_operations'] is False
         and evidence['materialize_or_reconcile'] is False,
         'actual normal read-only plan evidence')
    need(len(evidence['commands']) == 2, 'two original normal plan commands')
    result = {}
    for index, (count, profile, lock, path) in enumerate((
        (651, 'production-full', OLD_LOCK, PLAN651),
        (652, 'production-full-cmake', RECOVERY_LOCK, PLAN652),
    )):
        for item in (SOURCE_TOOL, lock, path):
            check_pin(item)
        command = evidence['commands'][index]
        need(command['name'] == 'plan' + str(count)
             and command['argv'] == [str(SOURCE_TOOL), '--profile', profile, 'plan', '--lock', str(lock)]
             and command['exit_code'] == 0 and command['actual_child_reaped'] is True
             and command['original_pidfd_held_until_reaped'] is True
             and command['waitid']['code'] == os.CLD_EXITED
             and command['waitid']['status'] == 0,
             'actual original normal plan command and PIDFD retirement')
        value, pin = read_source_json(path)
        output = command['stdout']
        need(output['path'] == str(path) and output['bytes'] == pin['bytes']
             and output['sha256'] == pin['sha256'] and output['f9'] == pin['identity'],
             'exact original normal plan output')
        for item in (SOURCE_TOOL, lock):
            observed = [p for p in evidence['inputs_before'] if p['path'] == str(item)]
            current = digest(item)
            need(len(observed) == 1 and observed[0]['bytes'] == current['bytes']
                 and observed[0]['sha256'] == current['sha256']
                 and observed[0]['f9'] == current['identity'], 'original plan producer and lock identity')
        plan = BOOKENDS.normalized_plan(value)
        need(len(plan['projects']) == count and len(plan['links']) == 8,
             'complete normal selected plan')
        result[count] = {'schema_version': 1, 'source_lock_sha256': PINS[lock][1], 'plan': plan}
    need(BOOKENDS.recovery_branch(result[651], result[651], result[652], False, False)
         == '651-before-reconcile-dispatch', 'full source contract extension')
    need(digest(PLAN_EVIDENCE) == evidence_pin, 'normal plan evidence unchanged')
    return result


SOURCE_STAGE_NAMES = {'source-reconcile-intent', 'source-reconcile-returned',
                      'source-transition-complete', 'source-vendor-intent'}


def write_source_stage(name, payload):
    need(name in SOURCE_STAGE_NAMES and type(payload) is dict, 'fixed source-stage record')
    owner = verify_outer()
    value = {'schema': 'p4-vendor-r18-source-stage-v1', 'stage': name,
             'generation': owner['generation'], 'worker_sha256': digest(SELF)['sha256'],
             'payload': payload}
    body = (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()
    need(len(body) <= 1024 * 1024, 'bounded source-stage record')
    directory = os.open(CONTROL, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    temporary_name = name + '.stage-new'
    final_name = name + '.json'
    fd = None
    try:
        identity = f9(os.fstat(directory))
        need(identity[:2] == f9(CONTROL.lstat())[:2], 'original control directory')
        fd = os.open(temporary_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                     | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=directory)
        view = memoryview(body)
        while view:
            done = os.write(fd, view)
            need(done > 0, 'complete source-stage write')
            view = view[done:]
        os.fsync(fd)
        libc = ctypes.CDLL(None, use_errno=True)
        rename = libc.renameat2
        rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        rename.restype = ctypes.c_int
        result = rename(directory, temporary_name.encode(), directory, final_name.encode(), 1)
        need(result == 0, 'atomic create-only source-stage publication errno=' + str(ctypes.get_errno()))
        os.fsync(directory)
        need(f9(os.fstat(directory))[:2] == identity[:2] == f9(CONTROL.lstat())[:2],
             'original control directory retained')
    finally:
        if fd is not None:
            os.close(fd)
        os.close(directory)
    pin = digest(CONTROL / final_name)
    OBS.setdefault('source_stages', {})[name] = pin
    save()
    return pin


def read_source_stage(name):
    need(name in SOURCE_STAGE_NAMES, 'fixed source-stage read')
    path = CONTROL / (name + '.json')
    if not os.path.lexists(path):
        return None
    value, pin = read_source_json(path)
    owner = verify_outer()
    need(type(value) is dict and set(value) == {'schema', 'stage', 'generation', 'worker_sha256', 'payload'}
         and value['schema'] == 'p4-vendor-r18-source-stage-v1' and value['stage'] == name
         and value['generation'] == owner['generation']
         and value['worker_sha256'] == digest(SELF)['sha256'] and type(value['payload']) is dict,
         'same original source-stage owner and worker')
    return value['payload'], pin


def read_content_bookend(name, projects, expected=None):
    value, pin = read_source_json(CONTROL / (name + '.json'), expected)
    need(value['schema'] == 'pocket4-original-materialized-source-content-bookend-v1'
         and value['all_actual_Git_blob_reads_verified'] is True and value['source_mutations'] is False
         and value['project_count'] == len(projects)
         and [p['project'] for p in value['projects']] == BOOKENDS.normalized_projects(projects),
         'complete original content-bookend plan')
    inventory = value['inventory']
    path = CONTROL / (name + '.ndjson')
    actual = digest(path)
    need(inventory['path'] == str(path) and inventory['bytes'] == actual['bytes']
         and inventory['sha256'] == actual['sha256'] and inventory['identity'] == actual['identity'],
         'complete original content inventory and identity')
    return value, pin


def verify_cmake_content(name, project):
    cmake = content_bookend(name, [project])
    need(cmake['project_count'] == 1 and cmake['sparse_absent_entries'] == 0
         and cmake['projects'][0]['tracked_entries'] == 3915,
         'complete original CMake checkout, not only the two executables')
    provider_path = PACKET / 'evidence/vendor-cmake-provider-r1/OBSERVATION.json'
    check_pin(provider_path)
    provider, provider_pin = read_source_json(provider_path)
    need(provider['commit'] == project['commit'] and provider['origin'] == project['url'],
         'external original provider provenance')
    expected_tree = BOOKENDS.tree_records(provider['tree'].replace('\n', '\0').encode())
    actual_tree = {}
    with (CONTROL / (name + '.ndjson')).open() as stream:
        for line in stream:
            item = BOOKENDS.strict_json(line)
            need(item['project'] == project['path'] and item['present'] is True
                 and item['path'] not in actual_tree, 'complete unique actual provider member')
            actual_tree[item['path']] = (item['git_mode'], item['git_blob'])
    need(actual_tree == expected_tree and len(expected_tree) == 3915,
         'all actual provider bodies must match the original independently verified tree')
    need(digest(provider_path) == provider_pin, 'original provider evidence unchanged')
    return cmake


def normal_reconcile_and_verify(env):
    contracts = source_contracts()
    with original_source_locks():
        run('verify-full651-before', [str(SOURCE_TOOL), '--profile', 'production-full',
            'verify-materialized', '--lock', str(OLD_LOCK), '--output', str(SOURCE)], env, 1200, True)
        old, old_pin = manifest_observation('manifest-651-before')
        need(BOOKENDS.normalized_manifest(old) == contracts[651], 'actual complete original 651 manifest')
        OBS['old651_manifest'] = old_pin
        before = content_bookend('original651-content-before', contracts[651]['plan']['projects'])
        need(not os.path.lexists(CMAKE_PROJECT), 'new full provider must start absent')
        intent_pin = write_source_stage('source-reconcile-intent', {
            'old_manifest': old_pin, 'before_content': OBS['content_bookends']['original651-content-before'],
            'expected_new_manifest_sha256': hashlib.sha256(BOOKENDS.encoded(contracts[652])).hexdigest(),
            'new_provider_absent_before_dispatch': True,
            'source_lock_before': PINS[OLD_LOCK][1], 'source_lock_after': PINS[RECOVERY_LOCK][1]})
        run('normal-reconcile-full652', [str(SOURCE_TOOL), '--profile', 'production-full-cmake',
            'reconcile', '--lock', str(LOCK), '--output', str(SOURCE)],
            env, max(1, DEADLINE - time.monotonic()), True)
        write_source_stage('source-reconcile-returned', {'intent': intent_pin, 'command': OBS['commands'][-1]})
        run('verify-full652-before', [str(SOURCE_TOOL), '--profile', 'production-full-cmake',
            'verify-materialized', '--lock', str(LOCK), '--output', str(SOURCE)], env, 1200, True)
        new, new_pin = manifest_observation('manifest-652-after-reconcile')
        need(BOOKENDS.normalized_manifest(new) == contracts[652],
             'only complete original CMake project and normal lock-hash extension allowed')
        after = content_bookend('original651-content-after-reconcile', contracts[652]['plan']['projects'][:651])
        require_original_651(before, after)
        addition = contracts[652]['plan']['projects'][651]
        verify_cmake_content('cmake-complete-content-before', addition)
        tool_pins = []
        versions = []
        for name in ('cmake', 'ctest'):
            path = CMAKE_PROJECT / 'bin' / name
            pin = digest(path)
            with path.open('rb') as stream:
                header = stream.read(20)
            need(header[:6] == b'\x7fELF\x02\x01' and header[18:20] == b'\x3e\x00'
                 and pin['identity'][2] & 0o111, 'original x86_64 executable CMake tool')
            output = run('original-cmake-provider-' + name + '-version',
                         [str(path), '--version'], env, 30, True)
            need(digest(path) == pin, 'original complete tool changed while executed')
            first = output.read_text().splitlines()[0]
            need(first.startswith(name + ' version '), 'original provider version output')
            versions.append(first.split(' version ', 1)[1])
            tool_pins.append(pin)
        need(versions[0] == versions[1], 'CMake and CTest versions differ')
        OBS['full652_reconcile'] = {'normal_cli_completed': True,
            'old_manifest': old_pin, 'new_manifest': new_pin,
            'original651_actual_bodies_preserved': True, 'new_provider': addition,
            'full_provider_tool_pins': tool_pins, 'actual_tool_version': versions[0],
            'materialization_only': True, 'vendor_build_credit': False}
        write_source_stage('source-transition-complete', {
            'intent': intent_pin, 'new_manifest': new_pin,
            'original651_after': OBS['content_bookends']['original651-content-after-reconcile'],
            'new_provider_content': OBS['content_bookends']['cmake-complete-content-before']})
        save()
    native_before = json.loads((CONTROL / 'native-source-before.json').read_text())
    need(native_snapshot() == native_before, 'reconciliation changed independent native926 input')


def verify_recovered_source(env):
    contracts = source_contracts()
    with original_source_locks():
        intent = read_source_stage('source-reconcile-intent')
        returned = read_source_stage('source-reconcile-returned')
        complete = read_source_stage('source-transition-complete')
        vendor = read_source_stage('source-vendor-intent')
        need(intent is not None or (returned is None and complete is None and vendor is None),
             'later source phases require original durable transition intent')
        before = None
        if intent is not None:
            payload, intent_pin = intent
            need(set(payload) == {'old_manifest', 'before_content', 'expected_new_manifest_sha256',
                 'new_provider_absent_before_dispatch', 'source_lock_before', 'source_lock_after'}
                 and payload['new_provider_absent_before_dispatch'] is True
                 and payload['source_lock_before'] == PINS[OLD_LOCK][1]
                 and payload['source_lock_after'] == PINS[RECOVERY_LOCK][1]
                 and payload['expected_new_manifest_sha256']
                     == hashlib.sha256(BOOKENDS.encoded(contracts[652])).hexdigest(),
                 'original source-transition intent contract')
            old, _ = read_source_json(CONTROL / 'manifest-651-before.json', payload['old_manifest']['copy'])
            need(BOOKENDS.normalized_manifest(old) == contracts[651], 'original whole 651 intent manifest')
            before, _ = read_content_bookend('original651-content-before', contracts[651]['plan']['projects'],
                                             payload['before_content'])
            if returned is not None:
                payload_returned, _ = returned
                command = payload_returned['command']
                need(set(payload_returned) == {'intent', 'command'} and payload_returned['intent'] == intent_pin
                     and command['name'] == 'normal-reconcile-full652'
                     and command['argv'] == [str(SOURCE_TOOL), '--profile', 'production-full-cmake',
                         'reconcile', '--lock', str(LOCK), '--output', str(SOURCE)]
                     and type(command['exit_code']) is int and command['exit_code'] == 0
                     and command['error'] is None and command['actual_child_reaped'] is True
                     and command['original_pidfd_held_until_reaped'] is True
                     and type(command['owned_descendants_remaining']) is int
                     and command['owned_descendants_remaining'] == 0,
                     'actual recorded reconcile return; absence never creates one')
            if complete is not None:
                payload_complete, _ = complete
                need(set(payload_complete) == {'intent', 'new_manifest', 'original651_after', 'new_provider_content'}
                     and payload_complete['intent'] == intent_pin, 'complete source stage belongs to original intent')
                prior_manifest, _ = read_source_json(CONTROL / 'manifest-652-after-reconcile.json',
                                                     payload_complete['new_manifest']['copy'])
                need(BOOKENDS.normalized_manifest(prior_manifest) == contracts[652], 'complete source-stage manifest')
                prior_after, _ = read_content_bookend('original651-content-after-reconcile',
                    contracts[651]['plan']['projects'], payload_complete['original651_after'])
                require_original_651(before, prior_after)
                read_content_bookend('cmake-complete-content-before', contracts[652]['plan']['projects'][651:],
                                     payload_complete['new_provider_content'])
            if vendor is not None:
                need(complete is not None and set(vendor[0]) == {'source_transition_complete'}
                     and vendor[0]['source_transition_complete'] == complete[1],
                     'vendor dispatch requires this original completed source transition')
        actual, observed = manifest_observation('manifest-recovery-state-before-verify')
        branch = BOOKENDS.recovery_branch(actual, contracts[651], contracts[652], intent is not None, vendor is not None)
        OBS['source_recovery_branch'] = {'branch': branch, 'observed_manifest': observed,
             'reconcile_dispatch_journal_present': intent is not None,
             'reconcile_return_journal_present': returned is not None,
             'source_complete_journal_present': complete is not None,
             'vendor_dispatch_journal_present': vendor is not None}
        save()
        if branch != '652-atomic-manifest-published':
            need(complete is None and vendor is None, '651 source cannot carry a completed 652 phase')
            run('verify-full651-after', [str(SOURCE_TOOL), '--profile', 'production-full',
                'verify-materialized', '--lock', str(OLD_LOCK), '--output', str(SOURCE)], env, 900, True)
            actual, pin = manifest_observation('manifest-651-after-recovery')
            need(BOOKENDS.normalized_manifest(actual) == contracts[651], 'normal full651 recovery verification')
            after = content_bookend('original651-content-after-recovery', contracts[651]['plan']['projects'])
            if before is None and os.path.lexists(CONTROL / 'original651-content-before.json'):
                before, _ = read_content_bookend('original651-content-before', contracts[651]['plan']['projects'])
            if before is not None:
                require_original_651(before, after)
            OBS['prior_whole651_content_bookend_available'] = before is not None
            OBS['original651_before_after_content_equal'] = True if before is not None else None
            OBS['current651_complete_git_bodies_verified'] = True
            OBS['final_normal_manifest'] = pin
            if branch == 'reconcile-dispatched-manifest-still-651':
                OBS['source_recovery_complete'] = False
                OBS['unresolved_reconcile_state'] = {'atomic_652_manifest_published': False,
                    'provider_path_present': os.path.lexists(CMAKE_PROJECT),
                    'new_normal_resume_admission_required': True}
                save()
                raise RuntimeError('reconcile was dispatched but full652 was not published; no rollback or recovery credit')
            need(not os.path.lexists(CMAKE_PROJECT), 'unexplained provider before this owner reconcile dispatch')
            OBS['full651_source_state_verified'] = True
            OBS['source_recovery_complete'] = True
            return
        need(before is not None, 'published 652 requires original complete 651 pre-mutation bookend')
        run('verify-full652-after', [str(SOURCE_TOOL), '--profile', 'production-full-cmake',
            'verify-materialized', '--lock', str(RECOVERY_LOCK), '--output', str(SOURCE)], env, 900, True)
        actual, pin = manifest_observation('manifest-652-after-recovery')
        need(BOOKENDS.normalized_manifest(actual) == contracts[652], 'normal complete full652 recovery verification')
        after = content_bookend('original651-content-after-recovery', contracts[651]['plan']['projects'])
        require_original_651(before, after)
        cmake = verify_cmake_content('cmake-complete-content-after-recovery', contracts[652]['plan']['projects'][651])
        prior_cmake = CONTROL / 'cmake-complete-content-before.json'
        compared = os.path.lexists(prior_cmake)
        if compared:
            old_cmake, _ = read_content_bookend('cmake-complete-content-before', contracts[652]['plan']['projects'][651:])
            need(cmake['content_sha256'] == old_cmake['content_sha256']
                 and cmake['materialized_entries'] == old_cmake['materialized_entries']
                 and cmake['materialized_bytes'] == old_cmake['materialized_bytes'],
                 'normal build/recovery changed original complete CMake bodies')
        OBS['full652_source_verified'] = True
        OBS['original651_before_after_content_equal'] = True
        OBS['complete_cmake_matches_independent_original_tree'] = True
        OBS['prior_cmake_bookend_comparison_performed'] = compared
        OBS['source_recovery_complete'] = True
        OBS['final_normal_manifest'] = pin


def verify_r12_latest_retirement():
    # The outer calls this before importing any source helper.
    pin = check_pin(R11_TERMINAL_RETIREMENT)
    receipt = json.loads(R11_TERMINAL_RETIREMENT.read_bytes())
    need(receipt['schema'] == 'p4-r11-failure-retirement-and-original651-verify-v1'
         and receipt['state'] == 'PASSED' and receipt['all_owned_children_reaped'] is True
         and receipt['normal_original651_verify_after_passed'] is True
         and receipt['original651_manifest_whole_bytes_unchanged'] is True
         and receipt['all_R11_inputs_and2336_sources_unchanged'] is True
         and receipt['reconcile_executed'] is False and receipt['CMake_added'] is False
         and receipt['vendor_compiler_executed'] is False
         and receipt['whole651_before_after_body_equality_claimed'] is False,
         'actual R11 retirement and original full651 verification')
    rows = []
    for unit in R12_RETIRED_UNITS:
        result = status_run(['/usr/bin/systemctl', '--user', 'show', unit,
            '--property=LoadState,ActiveState,SubState,MainPID,ControlGroup'],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15, check=False)
        fields = dict(line.split('=', 1) for line in result.stdout.decode().splitlines() if '=' in line)
        need(result.returncode == 0 and fields == {'LoadState':'not-found', 'ActiveState':'inactive',
             'SubState':'dead', 'MainPID':'0', 'ControlGroup':''}, 'original R11 owner remains active')
        cg = Path('/sys/fs/cgroup/user.slice/user-1000.slice/user@1000.service/app.slice') / unit
        need(not os.path.lexists(cg), 'original R11 cgroup remains')
        rows.append({'unit':unit, 'fields':fields, 'cgroup_absent':True})
    need(digest(R11_TERMINAL_RETIREMENT) == pin, 'original R11 terminal retirement changed')
    return {'receipt':pin, 'actual_units':rows}






def build():
    global DEADLINE, BASE_WORK, BASE_LIGHT, BASE_SOURCE
    import_pinned()
    verify_outer()
    OBS['serialized_heavy_admission'] = verify_serialized_retirement()
    need(not os.path.lexists(OUT) and not os.path.lexists(TMP), 'two fresh normal phase output roots required')
    need(not os.path.lexists(REPO), 'fresh canonical producer and absent cache required')
    OBS['admission'] = cgroup_admit(24, 22, 8, 8192)
    need(memory_available() >= 42 * GIB, 'original 42 GiB minimum with all other heavy compilers actually retired')
    need(shutil.disk_usage(ROOT).free >= 144 * GIB, 'original aggregate 120 GiB growth including light tasks plus 24 GiB reserve')
    for path, inode in LOCK_PINS:
        check_lock(path, inode)
    need(not (WORK / 'source-projection.json').exists(), 'pre-existing projection needs separate normal recovery first')
    DEADLINE = time.monotonic() + 28740
    OBS['admission'].update(fresh_ns=time.time_ns(), memory_available=memory_available(),
                            disk_free=shutil.disk_usage(ROOT).free, build_deadline_monotonic=DEADLINE,
                            growth_budget=120 * GIB, disk_floor=24 * GIB, emergency_memory_floor=8 * GIB)
    save()
    TMP.mkdir(mode=0o700)
    BASE_WORK = allocated(work_roots())
    BASE_LIGHT = allocated(LIGHT_ROOTS)
    BASE_SOURCE = allocated([SOURCE])
    (CONTROL / 'budget-baselines.json').write_text(json.dumps({'work': BASE_WORK, 'light': BASE_LIGHT, 'source': BASE_SOURCE}) + '\n')
    prepare_canonical_producer()
    OBS['initial_light_task_root_allocation'] = BASE_LIGHT
    OBS['disk_allocation_plan'] = {'vendor_growth_cap': 118 * GIB,
        'all_light_roots_growth_cap': 2 * GIB, 'combined_growth_cap': 120 * GIB,
        'disk_floor': 24 * GIB, 'original_fresh_disk_minimum': 144 * GIB,
        'light_roots': [str(path) for path in LIGHT_ROOTS]}
    save()
    frozen, rows, snapshot = check_inputs()
    (CONTROL / 'original-inputs.json').write_text(json.dumps(frozen, indent=2) + '\n')
    (CONTROL / 'original-producer-rows.json').write_text(json.dumps(rows, indent=2) + '\n')
    (CONTROL / 'original-producer-snapshot.json').write_text(json.dumps(snapshot, indent=2) + '\n')
    OBS['whole_producer_source_verified'] = True
    OBS['initial_non_source_work_allocation'] = BASE_WORK
    env = environment()
    OBS['environment'] = {k: env[k] for k in ('PATH', 'LD_LIBRARY_PATH', 'LLVM_CONFIG', 'PKG_CONFIG_PATH',
                                             'PYTHONPATH', 'PYTHONDONTWRITEBYTECODE', 'TMPDIR', 'CCACHE_MAXSIZE',\
                                             'DROIDLOOM_NATIVE_BRIDGE_SOURCE', 'GIT_OPTIONAL_LOCKS')}
    save()
    resource_guard(True)
    normal_reconcile_and_verify(env)
    complete = read_source_stage('source-transition-complete')
    need(complete is not None, 'vendor requires completed exact source transition')
    write_source_stage('source-vendor-intent', {'source_transition_complete': complete[1]})
    run('normal-official-gsi-vendor-build', [str(UPDATE_TOOL), '--source', str(REPO), '--jobs', '8',
        'official-gsi-vendor-build', '--work', str(WORK), '--out', str(OUT),
        '--system-image', str(SYSTEM), '--references', str(ROOT / 'official-vendor-inputs')],
        env, max(1, DEADLINE - time.monotonic()), True)
    result_path = OUT / 'droidloom-official-gsi-vendor-normal-result.json'
    OBS['normal_result'] = digest(result_path)
    result = json.loads(result_path.read_text())
    need(result['normal_user_commands_returned_success'] is True and result['source_projection_restored'] is True
         and result['official_system_bytes_preserved'] is True and result['production_ready'] is False
         and result['runtime_qualified'] is False, 'exact normal vendor result')
    OBS['normal_artifacts'] = []
    for key in ('normal_vendor_image', 'host_checkvintf', 'normal_vendor_result'):
        item = result[key]
        actual = digest(Path(item['path']))
        need(actual['sha256'] == item['sha256'] and actual['bytes'] == item['bytes'], 'normal output differs: ' + key)
        OBS['normal_artifacts'].append({'role': key, **actual})
    OBS['normal_build_returned_success'] = True
    OBS['cgroup_final'] = {n: (CG / n).read_text().strip() for n in
                           ('memory.peak', 'memory.events', 'memory.swap.current', 'cpu.stat', 'pids.peak')}
    events = dict(line.split() for line in OBS['cgroup_final']['memory.events'].splitlines())
    need(int(events['oom']) == int(events['oom_kill']) == 0 and OBS['cgroup_final']['memory.swap.current'] == '0',
         'OOM or swap occurred')
    resource_guard(True)
    OBS['finished_ns'] = time.time_ns()
    save()


def recover():
    global OBSERVATION_NAME, DEADLINE, BASE_WORK, BASE_LIGHT, BASE_SOURCE
    OBSERVATION_NAME = 'recovery-observation.json'
    import_pinned()
    verify_outer()
    OBS['admission'] = cgroup_admit(2, 1.5, 2, 512)
    DEADLINE = time.monotonic() + 1200
    baseline = json.loads((CONTROL / 'budget-baselines.json').read_text())
    BASE_WORK, BASE_LIGHT, BASE_SOURCE = baseline['work'], baseline['light'], baseline['source']
    for path, inode in LOCK_PINS:
        check_lock(path, inode)
    env = environment()
    env['TMPDIR'] = str(TMP if TMP.exists() else CONTROL)
    for path in (UPDATE_TOOL, SOURCE_TOOL, OLD_LOCK, RECOVERY_LOCK, BOOKEND_PATH, PLAN651, PLAN652, PLAN_EVIDENCE):
        got = digest(path)
        need((got['bytes'], got['sha256']) == PINS[path], 'recovery input changed')
    run('normal-source-recovery', [str(UPDATE_TOOL), 'recover-source', '--work', str(WORK)], env, 300)
    need(not (WORK / 'source-projection.json').exists(), 'normal recovery left source journal')
    verify_recovered_source(env)
    pins = CONTROL / 'original-inputs.json'
    if pins.exists():
        originals = json.loads(pins.read_text())
        need([digest(Path(item['path'])) for item in originals] == originals, 'original inputs changed')
        rows = json.loads((CONTROL / 'original-producer-rows.json').read_text())
        original = json.loads((CONTROL / 'original-producer-snapshot.json').read_text())
        # .work is a documented producer-owned download cache created by the
        # normal CLI. It is accounted separately, never claimed as source.
        actual_names = set()
        for directory, children, names in os.walk(REPO, followlinks=False):
            if Path(directory) == REPO and '.work' in children:
                children.remove('.work')
            need(all(not (Path(directory) / name).is_symlink() for name in children), 'producer directory alias')
            actual_names.update(str((Path(directory) / name).relative_to(REPO)) for name in names)
        need(actual_names == {r['path'] for r in rows}, 'producer source file membership changed')
        for row in rows:
            path = REPO / row['path']
            VERIFY.check(path, row)
            need(f9(path.lstat()) == original['files'][row['path']], 'producer source identity changed')
        native_before = json.loads((CONTROL / 'native-source-before.json').read_text())
        native_after = native_snapshot()
        need(native_after == native_before, 'original 926 native source members or Git provenance changed')
        (CONTROL / 'native-source-after.json').write_text(json.dumps(native_after, indent=2) + '\n')
        OBS['native_source_926_members_and_git_provenance_unchanged'] = True
        OBS['all_original_inputs_and_source_files_unchanged'] = True
    OBS['finished_ns'] = time.time_ns()
    save('recovery-observation.json')


def service(*args, **kwargs):
    raise RuntimeError('R12 phases require the separately pinned outer supervisor')


def outer():
    raise RuntimeError('R10-style outer is not available in R12')


def verify_r11_latest_retirement():
    pin = check_pin(R11_RETIREMENT)
    receipt = json.loads(R11_RETIREMENT.read_text())
    need(receipt['schema'] == 'pocket4-vendor-r11-latest-retirement-v1'
         and receipt['passed'] is True and receipt['all_original_children_reaped'] is True,
         'actual latest compiler and CAPEX retirement')
    units = receipt['units']
    need(units and len(units) == len(set(units)) and units == R11_RETIRED_UNITS,
         'exact latest retired scope set')
    observations = []
    for unit in units:
        need(unit.endswith('.service') or unit.endswith('.scope'), 'fixed original unit suffix')
        result = status_run(['/usr/bin/systemctl', '--user', 'show', unit,
            '--property=LoadState,ActiveState,SubState,MainPID,ControlGroup'],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=15, check=False)
        fields = dict(line.split('=', 1) for line in result.stdout.decode().splitlines() if '=' in line)
        need(result.returncode == 0 and fields == {'LoadState':'not-found','ActiveState':'inactive',
             'SubState':'dead','MainPID':'0','ControlGroup':''}, 'latest scope still active')
        cg = Path('/sys/fs/cgroup/user.slice/user-1000.slice/user@1000.service/app.slice') / unit
        need(not os.path.lexists(cg), 'latest original cgroup remains')
        observations.append({'unit':unit,'fields':fields,'cgroup_absent':True})
    need(digest(R11_RETIREMENT) == pin, 'latest retirement input changed')
    return {'receipt':pin,'actual_units':observations}


def status_run(argv, *, stdin, stdout, stderr, timeout, check):
    need(((argv[:3] == ['/usr/bin/systemctl','--user','show'] and len(argv) == 5)
          or argv in [
             ['/usr/bin/systemctl', 'show', 'p4-cp3a-vendor-supervisor-20261119-5cd1-r15.service', '--property=LoadState,ActiveState,SubState,MainPID,ControlGroup'],
             ['/usr/bin/systemctl', 'show', 'p4-cp3a-vendor-20261119-5cd1-r15.service', '--property=LoadState,ActiveState,SubState,MainPID,ControlGroup'],
             ['/usr/bin/systemctl', 'show', 'p4-cp3a-vendor-20261119-5cd1-r15-recovery.service', '--property=LoadState,ActiveState,SubState,MainPID,ControlGroup'],
             ['/usr/bin/systemctl', 'show', 'p4-cp3a-vendor-supervisor-20261119-5cd1-r16.service', '--property=LoadState,ActiveState,SubState,MainPID,ControlGroup'],
             ['/usr/bin/systemctl', 'show', 'p4-cp3a-vendor-20261119-5cd1-r16.service', '--property=LoadState,ActiveState,SubState,MainPID,ControlGroup'],
             ['/usr/bin/systemctl', 'show', 'p4-cp3a-vendor-20261119-5cd1-r16-recovery.service', '--property=LoadState,ActiveState,SubState,MainPID,ControlGroup'],
          ])
         and timeout == 15 and check is False and stdin == subprocess.DEVNULL
         and stdout == stderr == subprocess.PIPE, 'fixed status-only child contract')
    child = None
    pidfd = None
    row = {'argv':argv,'started_ns':time.time_ns(),'actual_child_reaped':False}
    OBS.setdefault('status_commands', []).append(row)
    failure = None
    try:
        child = subprocess.Popen(argv, stdin=stdin, stdout=stdout, stderr=stderr)
        row['pid'] = child.pid
        pidfd = os.pidfd_open(child.pid)
        deadline = time.monotonic() + timeout
        while True:
            info = os.waitid(os.P_PIDFD, pidfd, os.WEXITED | os.WNOHANG | os.WNOWAIT)
            if info is not None:
                break
            need(time.monotonic() < deadline, 'original status-child fixed deadline')
            time.sleep(0.02)
        result = child.wait(timeout=1)
        need(info.si_pid == child.pid and info.si_code in (os.CLD_EXITED,os.CLD_KILLED,os.CLD_DUMPED)
             and result == (info.si_status if info.si_code == os.CLD_EXITED else -info.si_status),
             'status waitid and real reap agree')
        out, err = child.stdout.read(65537), child.stderr.read(65537)
        need(len(out) <= 65536 and len(err) <= 65536, 'bounded status output')
        row.update(actual_child_reaped=True,original_pidfd_held_until_reaped=True,exit_code=result)
        return subprocess.CompletedProcess(argv,result,out,err)
    except BaseException as error:
        failure = repr(error)
        raise
    finally:
        if child is not None and child.returncode is None:
            if pidfd is not None:
                try:
                    signal.pidfd_send_signal(pidfd, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            else:
                # Original Popen child was never polled or waited; this sole
                # parent still owns the unreaped identity if pidfd_open failed.
                try:
                    os.kill(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            child.wait(timeout=5)
        row.update(actual_child_reaped=child is not None and child.returncode is not None,
                   original_pidfd_held_until_reaped=pidfd is not None and child is not None and child.returncode is not None,
                   error=failure,finished_ns=time.time_ns())
        if pidfd is not None:
            os.close(pidfd)


def verify_r13_predecessor_retirement():
    """Bind the actual R12 failure and normal verification; never invent recovery.

    This is an admission-only read. R12 failed before any source reconciliation
    or vendor compiler. Its normal verifier succeeded before and after the same
    sparse-cone observer error. The original failure stays immutable.
    """
    controls_pin = check_pin(R13_SOURCE_CONTROLS)
    controls = json.loads(R13_SOURCE_CONTROLS.read_bytes())
    need(controls['schema'] == 'pocket4-real-git-sparse-cone-controls-v1'
         and controls['passed'] is True and controls['tests_run'] == 13
         and len(controls['cases']) == 13
         and len({c['name'] for c in controls['cases']}) == 13
         and all(c['passed'] is True for c in controls['cases'])
         and controls['successor_helper_sha256'] == '4d192fa6738a954e0b2f4a480a8ba38a68ad47fefbd5eabbf3b8d00ca29cfad7'
         and controls['original_helper_sha256'] == '461fc7b33a907381a7a8647f9df2cf89e6b282b9b0030c753091cb1c46c2b7ae'
         and controls['temporary_fixtures_removed'] is True
         and controls['operational_source_mutations'] == controls['compilers_started'] == controls['VMs_started'] == 0
         and controls['runtime_qualified'] is False and controls['production_ready'] is False,
         'exact real-Git comparison controls and original source scope')
    need(digest(R13_SOURCE_CONTROLS) == controls_pin, 'original source controls changed during admission')
    previous = ROOT / 'control/build-r12'
    expected = {
        'outer-terminal.json': (51659, '7004ae364d219b9a835e70b16df552233e7e18d4b78e4d701b552e38942ad82b'),
        'build-observation.json': (53758, 'c732faef3943ee29743b585f6ab1f785f3cfe3c68ada838de4f573188e3bf16a'),
        'recovery-observation.json': (7534, '747de3669d663cab07fcc1a7fc271b164323a0f07cb93ac0813a483436679d7e'),
    }
    pins = {}
    values = {}
    for name, wanted in expected.items():
        path = previous / name
        pin = digest(path)
        need((pin['bytes'], pin['sha256']) == wanted, 'original R12 failure receipt changed: ' + name)
        body = path.read_bytes()
        need(hashlib.sha256(body).hexdigest() == pin['sha256'] and digest(path) == pin,
             'original R12 receipt read bookend: ' + name)
        pins[name] = pin
        values[name] = json.loads(body)
    terminal = values['outer-terminal.json']
    need(terminal['schema'] == 'pocket4-vendor-r12-supervisor-terminal-v1'
         and terminal['passed'] is False and terminal['build_attempted'] is True
         and terminal['all_owned_units_retired'] is True
         and terminal['all_created_children_reaped'] is True
         and terminal['normal_recovery_attempted'] is True
         and terminal['normal_recovery_verified'] is False
         and terminal['errors'] == [] and terminal['final_retirement_errors'] == []
         and terminal['serial_held_through_all_source_operations'] is True,
         'actual failed R12 lifecycle, without successful recovery credit')
    need([p['mode'] for p in terminal['phases']] == ['build', 'recover'],
         'exact two original R12 phases')
    for phase in terminal['phases']:
        client = phase['client']
        need(phase['success'] is False and phase['service_retired'] is True
             and phase['forced_service_retirement'] is False and phase['errors'] == []
             and phase['late_start_unresolved'] is False
             and client['exit_code'] == 1 and client['actual_reaped'] is True
             and client['original_pidfd_held_until_reaped'] is True
             and client['forced'] is False
             and client['waitid'] == {'pid': client['pid'], 'code': os.CLD_EXITED, 'status': 1},
             'actual original R12 failure and reaped original child')
    expected_commands = {
        'build-observation.json': ['verify-full651-before'],
        'recovery-observation.json': ['normal-source-recovery', 'verify-full651-after'],
    }
    command_pins = []
    for name, wanted in expected_commands.items():
        observation = values[name]
        need(observation['schema'] == 'p4-cp3a-normal-vendor-build-r12-v1'
             and observation['source_tree'] == TREE
             and observation['production_ready'] is False
             and observation['runtime_qualified'] is False and observation['installed'] is False,
             'original R12 evidence scope')
        need(len(observation['errors']) == 1
             and observation['errors'][0]['error'] == "RuntimeError('actual sparse cones differ from original plan')",
             'only the observed R12 sparse-cone comparison failure is admitted')
        need([c['name'] for c in observation['commands']] == wanted,
             'R12 did not dispatch reconciliation or vendor compilation')
        for command in observation['commands']:
            need(command['exit_code'] == 0 and command['error'] is None
                 and command['actual_child_reaped'] is True
                 and command['original_pidfd_held_until_reaped'] is True
                 and command['owned_descendants_remaining'] == 0,
                 'original normal source command and child retirement')
            for stream in ('stdout', 'stderr'):
                actual = digest(Path(command[stream]['path']))
                need(actual == command[stream], 'original R12 command output changed')
                command_pins.append(actual)
    before = values['build-observation.json']['old651_manifest']
    branch = values['recovery-observation.json']['source_recovery_branch']
    need(branch['branch'] == '651-before-reconcile-dispatch'
         and branch['reconcile_dispatch_journal_present'] is False
         and branch['reconcile_return_journal_present'] is False
         and branch['source_complete_journal_present'] is False
         and branch['vendor_dispatch_journal_present'] is False,
         'R12 source transition was never dispatched')
    after = branch['observed_manifest']
    need(before['original'] == after['original'],
         'original R12 historical before/after manifest is unchanged')
    repair_transition = verify_normal_same_plan_repair(before['original'])
    for copy in (before['copy'], after['copy']):
        need(digest(Path(copy['path'])) == copy
             and copy['sha256'] == before['original']['sha256'],
             'exact before/after original manifest copies')
    for stage in ('source-reconcile-intent', 'source-reconcile-returned',
                  'source-transition-complete', 'source-vendor-intent'):
        need(not os.path.lexists(previous / (stage + '.json'))
             and not os.path.lexists(previous / (stage + '.stage-new')),
             'no unexplained R12 source transition journal')
    units = [
        'p4-cp3a-vendor-supervisor-20261119-162b-r12.service',
        'p4-cp3a-vendor-20261119-162b-r12.service',
        'p4-cp3a-vendor-20261119-162b-r12-recovery.service',
        'p4-vendor-r12-frozen-preparation-20261119-r1.service',
    ]
    observed_units = []
    for unit in units:
        result = status_run(['/usr/bin/systemctl', '--user', 'show', unit,
            '--property=LoadState,ActiveState,SubState,MainPID,ControlGroup'],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=15, check=False)
        fields = dict(line.split('=', 1) for line in result.stdout.decode().splitlines() if '=' in line)
        need(result.returncode == 0 and fields == {'LoadState': 'not-found', 'ActiveState': 'inactive',
             'SubState': 'dead', 'MainPID': '0', 'ControlGroup': ''}, 'original R12 unit remains active')
        cgroup = Path('/sys/fs/cgroup/user.slice/user-1000.slice/user@1000.service/app.slice') / unit
        need(not os.path.lexists(cgroup), 'original R12 cgroup remains')
        observed_units.append({'unit': unit, 'fields': fields, 'cgroup_absent': True})
    for name, pin in pins.items():
        need(digest(previous / name) == pin, 'R12 predecessor receipt changed during admission')
    return {'successor_comparison_controls': controls_pin,
            'original_failed_receipts': pins, 'actual_normal_command_outputs': command_pins,
            'actual_units': observed_units, 'original_R12_before_after_manifest_unchanged': True,
            'actual_normal_same_plan_repair': repair_transition,
            'source_reconciliation_or_vendor_compiler_executed_by_R12': False,
            'R12_successful_recovery_claimed': False, 'whole651_body_equality_claimed': False}



REPAIR_ROOT = Path('/home/qq/work/p4-sameplan-source-repair-5cd1-20261119-r2')
REPAIR_RESULT_PIN = {'bytes': 6563547, 'f9': [66306, 49548252, 33152, 1000, 1000, 1, 6563547, 1795087946166954496, 1795087946166954496], 'path': '/home/qq/work/p4-sameplan-source-repair-5cd1-20261119-r2/actual/RESULT.json', 'sha256': '67d352ebf88622dc2233ce4f78b4c110a412a9ca4a2c29e9d099896c10c91521'}
REPAIR_RETIREMENT_PIN = {'bytes': 19028, 'f9': [66306, 72394495, 33200, 1000, 1000, 1, 19028, 1795088102371366141, 1795088102372366111], 'path': '/home/qq/work/p4-official-vendor-cp3a-20261118-162b-r1/control/vendor_r14_5cd1_repair_retirement.json', 'sha256': '53c8a8d5ef2c0f30fd514552e88cc1f8a39f51d3c9008bbe239fa5d715995c6f'}

def verify_normal_same_plan_repair(original_R12_manifest_pin):
    """Admit only the actual bounded normal repair, preserving all failures.

    This function is composed into a new generation only after the real R2
    terminal and independent retirement observation have been frozen. The old
    R12 and R13 files and their original observations are never edited.
    """
    global BOOKENDS
    need(REPAIR_RESULT_PIN is not None and REPAIR_RETIREMENT_PIN is not None,
         'actual successful repair and independent retirement are required')
    # The outer invokes this admission before worker.import_pinned(). Load only
    # the existing immutable read-only helper; do not change outer subreaping,
    # runner state or any compiler/source execution behavior.
    helper_pin = check_pin(BOOKEND_PATH)
    if BOOKENDS is None:
        import types
        helper_body = BOOKEND_PATH.read_bytes()
        need(hashlib.sha256(helper_body).hexdigest() == helper_pin['sha256']
             and digest(BOOKEND_PATH) == helper_pin, 'held pinned read-only helper')
        module = types.ModuleType('p4_r14_repair_readonly_bookends')
        module.__file__ = str(BOOKEND_PATH)
        exec(compile(helper_body, str(BOOKEND_PATH), 'exec'), module.__dict__)
        BOOKENDS = module

    def actual_pin(pin):
        need(type(pin) is dict and set(pin) == {'path', 'bytes', 'sha256', 'f9'},
             'exact repair file pin with real nine-field identity')
        path = Path(pin['path'])
        if pin['path'] == '/usr/lib/cargo/bin/coreutils/du':
            # This one independently observed uutils multicall tool is a
            # read-only root-owned hardlink. Keep worker.digest unchanged;
            # admit no other shared file or alternate path here.
            wanted = {'path': '/usr/lib/cargo/bin/coreutils/du', 'bytes': 11807104,
                      'sha256': 'f84e76ea4da1e0c4e92254bd0d7dccdabe2c8b3098e734f27997dae3ee5d8e02',
                      'f9': [66306, 82183780, 33261, 0, 0, 116, 11807104,
                             1788422510000000000, 1791032127435080941]}
            need(pin == wanted and path.resolve() == path, 'one exact original root system du identity')
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
            try:
                before = f9(os.fstat(fd))
                need(before == wanted['f9'] and stat.S_ISREG(before[2])
                     and before[3:6] == [0, 0, 116] and not before[2] & 0o022,
                     'exact non-writable shared root tool metadata')
                sha = hashlib.sha256()
                while True:
                    block = os.read(fd, 1024*1024)
                    if not block: break
                    sha.update(block)
                need(before == f9(os.fstat(fd)) == f9(path.lstat())
                     and sha.hexdigest() == wanted['sha256'], 'held complete shared system du body')
                observed = {'path': pin['path'], 'bytes': before[6], 'sha256': sha.hexdigest(), 'identity': before}
            finally:
                os.close(fd)
        else:
            observed = digest(path)
        need(observed == {'path': pin['path'], 'bytes': pin['bytes'], 'sha256': pin['sha256'],
                          'identity': pin['f9']}, 'actual repair evidence changed: ' + pin['path'])
        return observed

    def document(pin, limit=16*1024*1024):
        before = actual_pin(pin)
        need(pin['bytes'] <= limit, 'bounded actual repair document')
        raw = Path(pin['path']).read_bytes()
        need(hashlib.sha256(raw).hexdigest() == pin['sha256'] and actual_pin(pin) == before,
             'actual complete repair document bookend')
        return BOOKENDS.strict_json(raw)

    repair = document(REPAIR_RESULT_PIN)
    retired = document(REPAIR_RETIREMENT_PIN)
    need(repair['schema'] == 'pocket4-normal-same-plan-source-repair-v2'
         and repair['state'] == 'PASSED' and repair['source_tree'] == TREE
         and repair['source_reconcile_dispatched'] is True
         and repair['source_reconcile_returned_success'] is True
         and repair['all_original_children_reaped'] is True
         and repair['original_locks_held_through_child_retirement'] is True
         and repair['adopted_child_retirement'] == [] and repair['errors'] == []
         and repair['production_ready'] is False and repair['runtime_qualified'] is False
         and repair['Android_starts'] == repair['compilations'] == repair['installations']
             == repair['external_CURRENT_mutations'] == repair['owner_or_lease_changes'] == 0,
         'actual successful source-only repair with complete retirement')
    worker = actual_pin(repair['actual_worker_source'])
    need(worker['path'] == str(REPAIR_ROOT / 'repair_same_plan.py')
         and worker['bytes'] == 56374
         and worker['sha256'] == '7a86286830d5ba83db799bfa2911eaa3f919d12fdfac07a5e5fc8dc8acf2a6a3',
         'exact independently reviewed normal repair worker')
    need(retired['schema'] == 'pocket4-source-repair-r2-independent-retirement-v1'
         and retired['passed'] is True and retired['repair_result'] == REPAIR_RESULT_PIN
         and retired['unit'] == 'p4-sameplan-source-repair-5cd1-20261119-r2.service'
         and retired['invocation_id'] == 'fc510d65dbec4ff39fb98cca58274a4c'
         and retired['original_client_exit_code'] == 0 and retired['original_client_output_complete'] is True
         and retired['exact_unit_cgroup_absent'] is True,
         'independent actual original repair client and exact unit retirement')
    normal_names = ['normal-same-plan-reconcile', 'normal-verify-materialized']
    normal = [c for c in repair['commands'] if c['name'] in normal_names]
    need([c['name'] for c in normal] == normal_names, 'one normal reconcile and one normal verifier')
    for command, verb in zip(normal, ('reconcile', 'verify-materialized')):
        need(command['argv'] == [str(SOURCE_TOOL), '--profile', 'production-full', verb,
             '--lock', str(OLD_LOCK), '--output', str(SOURCE)], 'unchanged original normal source command')
        actual_pin(command['saved_stdout']); actual_pin(command['saved_stderr'])
    need(all(c['actual_child_reaped'] is True and c['original_pidfd_held_until_reaped'] is True
         and c['after_reap_echild'] is True and c['exit_code'] == 0 and not c.get('forced')
         and c['waitid'] == {'pid': c['pid'], 'code': os.CLD_EXITED, 'status': 0}
         for c in repair['commands']), 'every original repair child actually exited and was reaped')
    resources = repair['resources']
    need(resources['preflight_free_floor'] == 160*GIB and resources['runtime_free_floor'] == 144*GIB
         and resources['growth_cap'] == 16*GIB and resources['minimum_free_bavail'] >= 144*GIB
         and 0 <= resources['maximum_observed_growth'] <= 16*GIB,
         'original repair resource boundaries were actually preserved')
    before = repair['manifest_before']
    after = repair['manifest_after']
    need({'path': before['original']['path'], 'bytes': before['original']['bytes'],
          'sha256': before['original']['sha256'], 'identity': before['original']['f9']}
         == original_R12_manifest_pin, 'actual repair before is exactly the historical R12 original manifest')
    # Before is a historical inode; do not demand that its old inode survived
    # the normal CLI's documented atomic manifest replacement.
    before_manifest = document(before['copy'])
    after_manifest = document(after['copy'])
    live = r19_live_manifest_pin(after['original'])
    need(live['path'] == str(SOURCE / '.droidloom-source-manifest.json'), 'exact live source manifest')
    expected651 = source_contracts()[651]
    need(BOOKENDS.normalized_manifest(before_manifest) == expected651
         == BOOKENDS.normalized_manifest(after_manifest), 'same original complete651 plan before and after repair')
    need(before['copy']['sha256'] == before['original']['sha256']
         and after['copy']['sha256'] == after['original']['sha256'], 'actual before/after body copies')
    prior = repair['actual_R1_failure_retirement']
    actual_pin(prior['actual_failed_R1'])
    need(prior['actual_failed_R1']['bytes'] == 1096163
         and prior['actual_failed_R1']['sha256'] == 'e9fe709e0c33abbae48ba74646ac1448a9cf8af6f739cf5dbd6583072875ed2c'
         and prior['R1_source_repair_credit'] is False
         and prior['manifest_unchanged'] == before['original'], 'original failed R1 is preserved without repair credit')
    projects_before = document(repair['projects_before'])
    projects_after = document(repair['projects_after'])
    need(projects_before['project_count'] == projects_after['project_count'] == 651
         and projects_before['sparse_count'] == projects_after['sparse_count'] == 446
         and projects_after['missing_cones'] == {}, 'all651 metadata and446 complete canonical cone observations')
    expected = expected651['plan']['projects']
    need(len(projects_before['projects']) == len(projects_after['projects']) == len(expected), 'complete project rows')
    for old, new, project in zip(projects_before['projects'], projects_after['projects'], expected):
        need(old['project'] == new['project'] == project['path']
             and old['commit'] == new['commit'] == project['commit']
             and old['origin'] == new['origin'] == project['url']
             and old['tree_sha256'] == new['tree_sha256']
             and old['index_sha256'] == new['index_sha256']
             and old['tree_entries'] == new['tree_entries']
             and old['clean'] is True and new['clean'] is True,
             'every original HEAD/origin/index/tree/clean observation is preserved')
        need(set(new['actual_cones']) == set(BOOKENDS.canonical_sparse_cones(project['sparse_paths'])),
             'every repaired cone equals its canonical original plan')
    body_four = repair['restored_body_inventory']
    body_full = repair['restored_full_project_body_inventory']
    for pin, count, size in ((body_four, 25059, 12803167854), (body_full, 988, 1015464183)):
        need(pin['members_verified'] == count and pin['logical_bytes_verified'] == size
             and pin['every_actual_body_Git_blob_and_SHA256_verified'] is True,
             'actual complete new source member payload proof')
        actual_pin({k: pin[k] for k in ('path', 'bytes', 'sha256', 'f9')})
    need(body_full['symlink_bodies_verified'] == 486 and repair['restored_source_totals']['members_verified'] == 26047
         and repair['restored_source_totals']['logical_bytes_verified'] == 13818632037,
         'all26047 new regular/symlink bodies are accounted for')
    canonical_before = document(repair['canonical_producer_before'])
    canonical_after = document(repair['canonical_producer_after'])
    need(repair['complete_original_canonical_producer_unchanged'] is True
         and canonical_before == canonical_after and canonical_before['tree'] == TREE
         and len(canonical_before['files']) == 2336, 'full original frozen producer remained unchanged')
    for pin in repair['immutable_inputs_after']:
        actual_pin(pin)
    observed_units = []
    for unit in ('p4-sameplan-source-repair-5cd1-20261119-r1.service',
                 'p4-sameplan-source-repair-5cd1-20261119-r2.service',
                 'p4-cp3a-vendor-supervisor-20261119-5cd1-r13.service',
                 'p4-cp3a-vendor-20261119-5cd1-r13.service',
                 'p4-cp3a-vendor-20261119-5cd1-r13-recovery.service'):
        result = status_run(['/usr/bin/systemctl', '--user', 'show', unit,
            '--property=LoadState,ActiveState,SubState,MainPID,ControlGroup'],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=15, check=False)
        fields = dict(line.split('=', 1) for line in result.stdout.decode().splitlines() if '=' in line)
        need(result.returncode == 0 and not result.stderr and fields == {'LoadState': 'not-found',
             'ActiveState': 'inactive', 'SubState': 'dead', 'MainPID': '0', 'ControlGroup': ''},
             'actual original repair/unexecuted R13 unit must be retired')
        cgroup = Path('/sys/fs/cgroup/user.slice/user-1000.slice/user@1000.service/app.slice') / unit
        need(not os.path.lexists(cgroup), 'actual repair/unexecuted R13 cgroup remains')
        observed_units.append({'unit': unit, 'fields': fields, 'cgroup_absent': True})
    return {'actual_repair_result': actual_pin(REPAIR_RESULT_PIN),
            'actual_independent_retirement': actual_pin(REPAIR_RETIREMENT_PIN),
            'live_manifest_after_normal_atomic_replacement': live,
            'original_R12_manifest_before_repair': original_R12_manifest_pin,
            'same_original651_plan_verified': True, 'restored_members': 26047,
            'actual_units': observed_units, 'production_ready': False, 'runtime_qualified': False,
            'whole651_body_equality_claimed_by_repair': False}



PREVIOUS_R14_TERMINAL_PIN = {'bytes': 30119, 'f9': [66306, 72517683, 33152, 1000, 1000, 1, 30119, 1795089157009305899, 1795089157009305899], 'path': '/home/qq/work/p4-official-vendor-cp3a-20261118-162b-r1/control/build-r14-5cd1/outer-terminal.json', 'sha256': '441382427d4d725986c88f21bcb7324fc0a4bfeaf66e3b13a51a073dbb10b6bf'}
PREVIOUS_R14_RESOURCES_PIN = {'bytes': 319, 'f9': [66306, 72517682, 33152, 1000, 1000, 1, 319, 1795089157005306022, 1795089157005306022], 'path': '/home/qq/work/p4-official-vendor-cp3a-20261118-162b-r1/control/build-r14-5cd1/outer-resource-probe.json', 'sha256': '9af4c58d7e0217e8a768453b5db654f01d272fd2f77115dc2e7f9ea91cbc5347'}
PREVIOUS_R14_RETIREMENT_PIN = {'path': '/home/qq/work/p4-official-vendor-cp3a-20261118-162b-r1/control/vendor_r15_5cd1_previous_retirement.json', 'bytes': 8970, 'sha256': 'd7755ad8deb7f4aaa9e122300a2ac7c1d016ca0dc53678436482b7d52403f641', 'f9': [66306, 72394503, 33200, 1000, 1000, 1, 8970, 1795089394641721248, 1795089394641977048]}

def verify_r14_admission_failure():
    """Preserve R14's actual prebuild memory failure; grant no build credit."""
    need(BOOKENDS is not None, 'original repair proof must initialize the pinned JSON helper')

    def document(pin):
        expected = {'path': pin['path'], 'bytes': pin['bytes'],
                    'sha256': pin['sha256'], 'identity': pin['f9']}
        path = Path(pin['path'])
        need(pin['bytes'] <= 65536 and digest(path) == expected,
             'exact bounded previous admission evidence')
        raw = path.read_bytes()
        need(len(raw) == pin['bytes'] and hashlib.sha256(raw).hexdigest() == pin['sha256']
             and digest(path) == expected, 'previous admission evidence bookend')
        return BOOKENDS.strict_json(raw)

    terminal = document(PREVIOUS_R14_TERMINAL_PIN)
    resources = document(PREVIOUS_R14_RESOURCES_PIN)
    retired = document(PREVIOUS_R14_RETIREMENT_PIN)
    need(terminal['schema'] == 'pocket4-vendor-r14-supervisor-terminal-v1'
         and terminal['passed'] is False and terminal['build_attempted'] is False
         and terminal['phases'] == [] and terminal['children'] == []
         and terminal['normal_recovery_attempted'] is False
         and terminal['normal_recovery_verified'] is False
         and terminal['serial_held_through_all_source_operations'] is False
         and terminal['all_owned_units_retired'] is True
         and terminal['all_created_children_reaped'] is True
         and terminal['final_retirement_errors'] == []
         and terminal['serial_lock_acquired'] is True
         and terminal['production_ready'] is False and terminal['runtime_qualified'] is False
         and terminal['installed'] is False, 'actual R14 failure before every source/build phase')
    need(len(terminal['errors']) == 1 and terminal['errors'][0]['stage'] == 'outer'
         and terminal['errors'][0]['error'] == "RuntimeError('original fresh 42 GiB / 144 GiB admission')",
         'only the exact preserved original resource admission failure')
    children = terminal['original_worker_status_children']
    need(len(children) == 60 and all(x['actual_child_reaped'] is True
         and x['original_pidfd_held_until_reaped'] is True and x['exit_code'] == 0
         and x['error'] is None and x['argv'][:3] == ['/usr/bin/systemctl', '--user', 'show']
         for x in children), 'all original R14 metadata children actually retired')
    need(resources['memory_available'] == 42086125568
         and resources['memory_available'] < resources['required_memory'] == 42*GIB
         and resources['disk_free'] >= resources['required_disk'] == 144*GIB,
         'actual R14 memory failure is not converted into resource success')
    need(retired['schema'] == 'pocket4-r14-prebuild-admission-independent-retirement-v1'
         and retired['passed'] is True and retired['r14_build_passed'] is False
         and retired['original_outer_terminal'] == PREVIOUS_R14_TERMINAL_PIN
         and retired['original_outer_resource_probe'] == PREVIOUS_R14_RESOURCES_PIN
         and retired['original_client_session_id'] == 'dpty-76631c834f2996ba64f4695c884907304ba7ee1ff3b0637ea3fbcc10d49837af'
         and retired['original_invocation_id'] == 'c48fbb7ce80441779ef0b84b95c57ff2'
         and retired['original_client_exit_code'] == 1
         and retired['original_client_output_complete'] is True
         and retired['original_client_capture_error'] is None
         and retired['exact_three_units_cgroups_absent'] is True
         and retired['original_three_locks_free_unchanged_f9'] is True
         and retired['independent_observer_three_locks_released'] is True
         and retired['all_original_status_children_exit_zero_pidfd_and_reaped'] is True
         and retired['build_dispatched'] is False and retired['recovery_dispatched'] is False
         and retired['actual_resources'] == resources
         and retired['source_body_equality_claimed'] is False
         and retired['source_mutations'] == 0
         and retired['production_ready'] is False and retired['runtime_qualified'] is False,
         'independent original failed R14 client/unit/lock retirement')
    manifest = retired['actual_source_manifest_still_R2_after_pin']
    need(manifest['path'] == str(SOURCE / '.droidloom-source-manifest.json')
         and r19_manifest_transition_matches(manifest),
         'R14 no-dispatch retained the real normal R2 aftermanifest')
    units = ('p4-cp3a-vendor-supervisor-20261119-5cd1-r14.service',
             'p4-cp3a-vendor-20261119-5cd1-r14.service',
             'p4-cp3a-vendor-20261119-5cd1-r14-recovery.service')
    need([row['unit'] for row in retired['exact_units']] == list(units), 'exact previous R14 units')
    observed = []
    for unit in units:
        result = status_run(['/usr/bin/systemctl', '--user', 'show', unit,
            '--property=LoadState,ActiveState,SubState,MainPID,ControlGroup'],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=15, check=False)
        fields = dict(line.split('=', 1) for line in result.stdout.decode().splitlines() if '=' in line)
        need(result.returncode == 0 and not result.stderr and fields == {'LoadState': 'not-found',
             'ActiveState': 'inactive', 'SubState': 'dead', 'MainPID': '0', 'ControlGroup': ''},
             'actual prior R14 unit must remain retired')
        cgroup = Path('/sys/fs/cgroup/user.slice/user-1000.slice/user@1000.service/app.slice') / unit
        need(not os.path.lexists(cgroup), 'actual prior R14 cgroup remains')
        observed.append({'unit': unit, 'fields': fields, 'cgroup_absent': True})
    return {'previous_failed_terminal': PREVIOUS_R14_TERMINAL_PIN,
            'previous_failed_resources': PREVIOUS_R14_RESOURCES_PIN,
            'independent_retirement': PREVIOUS_R14_RETIREMENT_PIN,
            'prior_r14_build_credit': False, 'actual_units': observed,
            'production_ready': False, 'runtime_qualified': False}


R15_FAILURE_PINS = {'build': {'bytes': 73219,
           'f9': [66306,
                  72517831,
                  33152,
                  1000,
                  1000,
                  1,
                  73219,
                  1795091215607870184,
                  1795091215607870184],
           'path': '/home/qq/work/p4-official-vendor-cp3a-20261118-162b-r1/control/build-r15-5cd1/build-observation.json',
           'sha256': '1575578cd9c67e5879f3ea451b1936088b63ef3e097703d934518869d050e2e6'},
 'lock_contract': {'bytes': 10765,
                   'f9': [66306,
                          72394516,
                          33200,
                          1000,
                          1000,
                          1,
                          10765,
                          1795092249981156835,
                          1795092249983979724],
                   'path': '/home/qq/work/p4-official-vendor-cp3a-20261118-162b-r1/control/vendor_r16_5cd1_r15_lock_contract.json',
                   'sha256': '713e53940198fe4425a6a0aa77108e21fe9894faaaaf3a4443f00542abb87fbf'},
 'recovery': {'bytes': 8071,
              'f9': [66306,
                     72517900,
                     33152,
                     1000,
                     1000,
                     1,
                     8071,
                     1795091421482601892,
                     1795091421482601892],
              'path': '/home/qq/work/p4-official-vendor-cp3a-20261118-162b-r1/control/build-r15-5cd1/recovery-observation.json',
              'sha256': '23c3bde83627b13045d4ec093f2d82500bc08126d9e362eb39eed8bf87873f65'},
 'retirement': {'bytes': 19645,
                'f9': [66306,
                       72394515,
                       33200,
                       1000,
                       1000,
                       1,
                       19645,
                       1795092247237087635,
                       1795092247237087635],
                'path': '/home/qq/work/p4-official-vendor-cp3a-20261118-162b-r1/control/vendor_r16_5cd1_r15_retirement.json',
                'sha256': 'c306e580a837d739b506f0ed78fed3c2727bb95481e2df59a0b6254270c3a302'},
 'terminal': {'bytes': 106146,
              'f9': [66306,
                     72517960,
                     33152,
                     1000,
                     1000,
                     1,
                     106146,
                     1795091421690952109,
                     1795091421690952109],
              'path': '/home/qq/work/p4-official-vendor-cp3a-20261118-162b-r1/control/build-r15-5cd1/outer-terminal.json',
              'sha256': '71fbd19a2315d5dd9d5a0dd69ba94276086d49a36ed54d42971e8597d8685bed'}}

R15_UNCHANGED_MANIFEST_PIN = {'bytes': 441444,
 'f9': [66306, 61122520, 33152, 1000, 1000, 1, 441444, 1795087857519520381, 1795087857524520237],
 'path': '/home/qq/work/pocket4-native-source597-ai395-20261108-8b88-r1/work/aosp-source/.droidloom-source-manifest.json',
 'sha256': '704ec2a6ba4fec751490b0da492b161887479ef9579f18025374d56ced72f5a3'}

R15_LOCKS_BEFORE_NORMAL_RECOVERY = [{'f9': [66306, 60857531, 33152, 1000, 1000, 1, 0, 1794183129522871360, 1794183129522871360],
  'path': '/home/qq/work/pocket4-native-source597-ai395-20261108-8b88-r1/native-full.serial.lock'},
 {'f9': [66306, 60857480, 33152, 1000, 1000, 1, 8, 1795085579838887176, 1795085579838887176],
  'path': '/home/qq/work/pocket4-native-source597-ai395-20261108-8b88-r1/work/package-build.lock'},
 {'f9': [66306, 60857481, 33152, 1000, 1000, 1, 8, 1795085579838887176, 1795085579838887176],
  'path': '/home/qq/work/pocket4-native-source597-ai395-20261108-8b88-r1/work/aosp-source-update.lock'}]

R15_LOCKS_AFTER_NORMAL_RECOVERY = [{'f9': [66306, 60857531, 33152, 1000, 1000, 1, 0, 1794183129522871360, 1794183129522871360],
  'path': '/home/qq/work/pocket4-native-source597-ai395-20261108-8b88-r1/native-full.serial.lock'},
 {'f9': [66306, 60857480, 33152, 1000, 1000, 1, 8, 1795091215883526726, 1795091215883526726],
  'path': '/home/qq/work/pocket4-native-source597-ai395-20261108-8b88-r1/work/package-build.lock'},
 {'f9': [66306, 60857481, 33152, 1000, 1000, 1, 8, 1795091215883526726, 1795091215883526726],
  'path': '/home/qq/work/pocket4-native-source597-ai395-20261108-8b88-r1/work/aosp-source-update.lock'}]


def verify_r15_failed_body_bookend():
    """Consume the original R15 failure and retirement before a new source phase.

    This is an admission-only extension after the existing R12/R2/R14 guards.
    It grants no successful body-bookend, build or recovery credit. It must not
    be called after the successor has started normal source operations.
    """
    need(BOOKENDS is not None, 'the existing repair guard initializes the pinned JSON helper')
    need(set(R15_FAILURE_PINS) == {'terminal', 'build', 'recovery', 'retirement', 'lock_contract'},
         'exact bounded R15 predecessor document set')

    def actual_pin(pin):
        expected = {'path': pin['path'], 'bytes': pin['bytes'],
                    'sha256': pin['sha256'], 'identity': pin['f9']}
        need(digest(Path(pin['path'])) == expected, 'exact original R15 evidence identity and complete SHA')
        return expected

    def document(name):
        pin = R15_FAILURE_PINS[name]
        need(set(pin) == {'path', 'bytes', 'sha256', 'f9'}
             and type(pin['bytes']) is int and 0 < pin['bytes'] <= 131072,
             'one bounded frozen R15 evidence document')
        expected = actual_pin(pin)
        raw = Path(pin['path']).read_bytes()
        need(len(raw) == pin['bytes'] and hashlib.sha256(raw).hexdigest() == pin['sha256']
             and digest(Path(pin['path'])) == expected, 'R15 evidence complete read bookend')
        return BOOKENDS.strict_json(raw)

    terminal, build, recovery, retired, contract = [document(name) for name in
        ('terminal', 'build', 'recovery', 'retirement', 'lock_contract')]
    need(terminal['schema'] == 'pocket4-vendor-r15-supervisor-terminal-v1'
         and terminal['passed'] is False and terminal['build_attempted'] is True
         and terminal['normal_recovery_attempted'] is True
         and terminal['normal_recovery_verified'] is False
         and terminal['all_owned_units_retired'] is True
         and terminal['all_created_children_reaped'] is True
         and terminal['serial_lock_acquired'] is True
         and terminal['serial_held_through_all_source_operations'] is True
         and terminal['fixed_deadline_exceeded'] is False
         and terminal['errors'] == terminal['build_retirement_errors'] == terminal['final_retirement_errors'] == [],
         'actual R15 body failure with complete original custody and retirement')
    need(terminal['worker']['bytes'] == 103281
         and terminal['worker']['sha256'] == '3f22548ec796241659ec9288c358fc7c0b2074c984f2da0e839e0a18defd6492'
         and terminal['bundle']['bytes'] == 8138
         and terminal['bundle']['sha256'] == '557ca068e0293e992a51474943bf2780dbee61ccc5b1009e4405d0594eff2cda',
         'the original frozen R15 worker and bundle actually ran')
    actual_pin(terminal['worker']); actual_pin(terminal['bundle'])
    children = terminal['children']
    need(len(children) == 101 and len({child['pid'] for child in children}) == 101,
         'all 101 original R15 supervisor children are distinct')
    need({child['name'] for child in children} == {'outer-build', 'outer-recover'} |
         {'outer-command-%04d' % i for i in range(1, 100)}, 'exact original R15 supervisor child names')
    for child in children:
        expected_exit = 1 if child['name'] in ('outer-build', 'outer-recover') else 0
        need(child['actual_reaped'] is True and child['original_pidfd_held_until_reaped'] is True
             and child['forced'] is False and child['exit_code'] == expected_exit
             and child['waitid'] == {'pid': child['pid'], 'code': 1, 'status': expected_exit},
             'original R15 supervisor child terminal and reap without a forced retry')
    metadata_children = terminal['original_worker_status_children']
    need(len(metadata_children) == 63 and all(child['actual_child_reaped'] is True
         and child['original_pidfd_held_until_reaped'] is True and child['exit_code'] == 0
         and child['error'] is None and child['argv'][:3] == ['/usr/bin/systemctl', '--user', 'show']
         for child in metadata_children), 'all 63 original metadata status children actually retired')
    phases = terminal['phases']
    need([phase['mode'] for phase in phases] == ['build', 'recover'], 'exact original R15 two phases')
    invocations = {'build':'bf34d8b814154bd999dac81476394a1f',
                   'recover':'2b4cf56c3af34daab3dcc10ffc609342'}
    units = ('p4-cp3a-vendor-supervisor-20261119-5cd1-r15.service',
             'p4-cp3a-vendor-20261119-5cd1-r15.service',
             'p4-cp3a-vendor-20261119-5cd1-r15-recovery.service')
    for phase, unit in zip(phases, units[1:]):
        boundary = phase['client_retirement_boundary']
        need(phase['unit'] == unit and phase['invocation_id'] == invocations[phase['mode']]
             and phase['success'] is False and phase['service_retired'] is True
             and phase['forced_service_retirement'] is False and phase['late_start_unresolved'] is False
             and phase['errors'] == [] and phase['client']['exit_code'] == 1
             and phase['client'] in children and boundary['invocation_id'] == phase['invocation_id']
             and boundary['original_actor_observed_before_client_reap'] is True
             and boundary['original_client_actual_reaped'] is True
             and boundary['original_pidfd_held_until_reaped'] is True
             and boundary['client_exit_code'] == 1 and boundary['client_forced'] is False
             and boundary['phase_errors'] == [], 'both actual failed phase clients and cgroups retired')
        need(phase['final_properties']['LoadState'] == 'not-found'
             and phase['final_properties']['ActiveState'] == 'inactive'
             and phase['final_properties']['SubState'] == 'dead'
             and phase['final_properties']['MainPID'] == '0'
             and phase['final_properties']['ControlGroup'] == '', 'original failed phase unit final state')
    failure = "RuntimeError('actual source content differs from committed Git blob: stable/third_party/zstd/src/build/VS2008/fullbench/fullbench.vcproj')"
    # The original frozen worker retained its build schema string in recovery;
    # the exact file pins, phase and command lists identify the two real roles.
    need(build['schema'] == recovery['schema'] == 'p4-cp3a-normal-vendor-build-r15-v1',
         'both original R15 observation schema strings remain unmodified')
    for observation in (build, recovery):
        need(len(observation['errors']) == 1 and observation['errors'][0]['error'] == failure
             and observation['actual_updater_release_source_tree'] == 'fa0382574f4fc18f59b2b5dd67a30939167d8c3a'
             and observation['updater_release_and_full_canonical_source_tree_identical'] is True,
             'retain the exact original full body mismatch and frozen producer')
    need([command['name'] for command in build['commands']] == ['verify-full651-before']
         and [command['name'] for command in recovery['commands']] == ['normal-source-recovery', 'verify-full651-after'],
         'no original R15 reconcile or vendor command was dispatched')
    commands = build['commands'] + recovery['commands']
    expected_argv = [
        [str(SOURCE_TOOL), '--profile', 'production-full', 'verify-materialized', '--lock', str(OLD_LOCK), '--output', str(SOURCE)],
        [str(UPDATE_TOOL), 'recover-source', '--work', str(WORK)],
        [str(SOURCE_TOOL), '--profile', 'production-full', 'verify-materialized', '--lock', str(OLD_LOCK), '--output', str(SOURCE)]]
    actual_logs = []
    for command, argv, pid in zip(commands, expected_argv, (2646092, 2650863, 2650864)):
        need(command['argv'] == argv and command['pid'] == pid and command['exit_code'] == 0
             and command['actual_child_reaped'] is True and command['original_pidfd_held_until_reaped'] is True
             and command['owned_descendants_remaining'] == 0 and command['retired_descendants'] == []
             and command['error'] is None, 'exact three normal CLI successes do not replace body acceptance')
        for channel in ('stdout', 'stderr'):
            log = command[channel]
            pin = {key: log[key] for key in ('path', 'bytes', 'sha256')}
            pin['f9'] = log['identity']
            actual_pin(pin)
            actual_logs.append(pin)
    branch = recovery['source_recovery_branch']
    need(branch['branch'] == '651-before-reconcile-dispatch'
         and all(branch[key] is False for key in ('reconcile_dispatch_journal_present',
             'reconcile_return_journal_present', 'source_complete_journal_present', 'vendor_dispatch_journal_present')),
         'the original R15 failure preceded source reconcile and vendor dispatch')
    for observation in (terminal, build, recovery):
        need(all(observation[key] is False for key in ('installed', 'runtime_qualified', 'production_ready')),
             'original R15 failure grants no runtime or production credit')
    need(retired['schema'] == 'pocket4-r15-content-failure-independent-retirement-v1'
         and retired['passed'] is True and retired['retirement_only_pass'] is True
         and retired['r15_build_passed'] is False and retired['normal_recovery_verified'] is False
         and retired['all_blockers_closed'] is False and retired['source_body_equality_claimed'] is False
         and retired['source_reconcile_or_vendor_dispatched'] is False
         and retired['source_mutations'] == 0 and retired['whole_source_scanned'] is False
         and retired['production_ready'] is False
         and retired['actual_outer_children_reaped'] == 101 and retired['actual_metadata_children_reaped'] == 63
         and retired['actual_failed_phase_client_exit_codes'] == [1, 1]
         and retired['phase_invocation_ids'] == invocations
         and retired['invocation_id'] == 'eba051013701442182df74976f5a41d6'
         and retired['known_content_blocker_retained'] == 'external/cronet/stable/third_party/zstd/src/build/VS2008/fullbench/fullbench.vcproj',
         'independent R15 receipt is explicitly retirement-only with body failure retained')
    need(retired['proofs'] == {'outer-terminal.json':R15_FAILURE_PINS['terminal'],
         'build-observation.json':R15_FAILURE_PINS['build'], 'recovery-observation.json':R15_FAILURE_PINS['recovery']}
         and retired['original_normal_CLI_log_pins'] == actual_logs, 'independent receipt pins all original observations and CLI streams')
    client = retired['original_client']
    need(client['session_id'] == 'dpty-a6c5dfdcf4b2b8b2f68edded062920b8eb0bde305fd33ac355e5507fce9eaccb'
         and client['exit_code'] == retired['original_client_expected_exit_code'] == 1
         and client['output_complete'] is True and client['capture_error'] is None
         and client['full_archive_reconstructed'] is True and client['truncated'] is False
         and client['full_stdout']['bytes'] == 60229
         and client['full_stdout']['sha256'] == 'aed5c48e17d7225bd3f2aa8df236274fda65a95334342119723266eb53c56667',
         'complete original failed R15 client was independently observed')
    need(retired['collector']['exit_code'] == 0 and retired['collector']['output_complete'] is True
         and retired['all_three_original_locks_free_and_released'] is True
         and retired['original_lock_transitions_verified'] is True, 'actual independent retirement observer finished and released locks')
    manifest = retired['actual_final_source_manifest']
    need(manifest == R15_UNCHANGED_MANIFEST_PIN
         and build['old651_manifest']['original'] == {'path':manifest['path'], 'bytes':manifest['bytes'],
             'sha256':manifest['sha256'], 'identity':manifest['f9']}
         and branch['observed_manifest']['original'] == build['old651_manifest']['original'],
         'R15 retained the original normal R2 manifest identity without a transition exception')
    r19_live_manifest_pin(manifest)
    need(contract['schema'] == 'pocket4-frozen-normal-recovery-lock-write-contract-v1'
         and contract['state'] == 'VERIFIED_READ_ONLY_SOURCE_CONTRACT'
         and contract['canonical_release_source_tree'] == 'fa0382574f4fc18f59b2b5dd67a30939167d8c3a'
         and contract['original_normal_recovery_command'] == commands[1]
         and contract['frozen_remote_source_modified'] is False
         and contract['locks_modified_by_this_review'] is False
         and contract['normal_recovery_or_build_commands_executed_by_this_review'] == 0
         and contract['runtime_qualified'] is False and contract['production_ready'] is False,
         'frozen original normal recovery source contract supports only the recorded PID writes')
    need(retired['frozen_recovery_contract_receipt_sha256'] == R15_FAILURE_PINS['lock_contract']['sha256']
         and all(retired['frozen_source_lock_contract'][key] == R15_FAILURE_PINS['lock_contract'][key]
                 for key in ('bytes', 'sha256')), 'independent retirement consumes the exact frozen lock contract')
    for pin in retired['frozen_recovery_contract_inputs']:
        actual_pin(pin)
    source_contract = contract['contract']
    need(all(source_contract[key] is True for key in (
        'normal_recovery_acquires_package_lock_then_source_update_lock_before_optional_journal_check',
        'existing_lock_paths_opened_without_rename_or_unlink', 'exclusive_nonblocking_flock_precedes_content_update',
        'held_descriptor_is_inheritable', 'same_open_file_set_len_zero_then_own_PID_with_newline',
        'journal_absence_does_not_skip_lock_PID_writes')) and source_contract['open_truncate_flag'] is False,
        'the actual same-file PID update occurs after lock acquisition even without a journal')
    pid_body = b'2650863\n'
    need(source_contract['expected_successful_original_PID_body'] == {'text':pid_body.decode(),
         'hex':pid_body.hex(), 'bytes':8, 'sha256':hashlib.sha256(pid_body).hexdigest()}
         and retired['exact_normal_recovery_lock_body_hex'] == pid_body.hex()
         and retired['exact_normal_recovery_lock_body_sha256'] == hashlib.sha256(pid_body).hexdigest(),
         'only the actual successful original normal recovery PID may appear in the two locks')
    locks = retired['original_lock_transition_details']
    need(len(locks) == 3 and [row['path'] for row in locks] == [str(path) for path, inode in LOCK_PINS]
         and retired['original_locks_before_recovery'] == R15_LOCKS_BEFORE_NORMAL_RECOVERY
         and retired['original_locks'] == R15_LOCKS_AFTER_NORMAL_RECOVERY,
         'only the three exact original lock identities and recorded transition are admitted')
    for index, (row, before, after) in enumerate(zip(locks, R15_LOCKS_BEFORE_NORMAL_RECOVERY, R15_LOCKS_AFTER_NORMAL_RECOVERY)):
        need(row['before_f9'] == before['f9'] and row['actual_after_f9'] == after['f9']
             and before['path'] == after['path'] == row['path']
             and before['f9'][:7] == after['f9'][:7]
             and row['original_dev_inode_mode_uid_gid_nlink_size_unchanged'] is True
             and row['current_body_and_F9_unchanged_by_readonly_observer'] is True,
             'original lock device/inode/mode/owner/link count/size remain unchanged')
        if index == 0:
            body = b''
            need(before == after and row['serial_lock_complete_F9_unchanged'] is True
                 and row['legitimate_original_writer_pid'] is None and row['write_interval_ns'] is None,
                 'the original serial lock has no PID content or F9 transition')
        else:
            body = pid_body
            need(row['serial_lock_complete_F9_unchanged'] is False
                 and row['legitimate_original_writer_pid'] == commands[1]['pid'] == 2650863
                 and row['write_interval_ns'] == [commands[1]['started_ns'], commands[1]['finished_ns']]
                 and after['f9'][7:] == [1795091215883526726, 1795091215883526726]
                 and commands[1]['started_ns'] <= after['f9'][7] <= commands[1]['finished_ns'],
                 'the only two changed lock timestamps belong to the original normal recovery interval')
        need(row['bytes'] == len(body) and row['body_hex'] == body.hex()
             and row['sha256'] == hashlib.sha256(body).hexdigest(), 'exact recorded lock PID body')
        pin = {'path':row['path'], 'bytes':len(body), 'sha256':row['sha256'], 'f9':after['f9']}
        r18_live_lock_pin(pin)  # Original R15 history above; actual later R17 transition is separate.
    need([row['unit'] for row in retired['exact_units_and_cgroups_retired']] == list(units),
         'independent observer checked the exact three original R15 units')
    observed = []
    fixed_fields = {'LoadState':'not-found', 'ActiveState':'inactive', 'SubState':'dead',
                    'MainPID':'0', 'ControlGroup':''}
    for unit, original in zip(units, retired['exact_units_and_cgroups_retired']):
        need(len(original['status']) == 2 and len(original['absent_cgroups']) == 2,
             'both independent user/system observations and cgroup paths are required')
        for scope, original_status in zip(('user', 'system'), original['status']):
            argv = ['/usr/bin/systemctl'] + (['--user'] if scope == 'user' else []) + [
                'show', unit, '--property=LoadState,ActiveState,SubState,MainPID,ControlGroup']
            need(original_status['argv'] == argv and original_status['exit_code'] == 0
                 and original_status['actual_child_reaped'] is True
                 and original_status['original_pidfd_held_until_reaped'] is True
                 and not original_status['stderr']
                 and dict(line.split('=', 1) for line in original_status['stdout'].splitlines()) == fixed_fields,
                 'original independent unit observation is complete and retired')
            result = status_run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=15, check=False)
            fields = dict(line.split('=', 1) for line in result.stdout.decode().splitlines() if '=' in line)
            need(result.returncode == 0 and not result.stderr and fields == fixed_fields,
                 'the exact previous R15 unit must still be retired')
            cgroup = (Path('/sys/fs/cgroup/user.slice/user-1000.slice/user@1000.service/app.slice')
                      if scope == 'user' else Path('/sys/fs/cgroup/system.slice')) / unit
            need(str(cgroup) in original['absent_cgroups'], 'exact original user/system cgroup pathname')
            try:
                cgroup.lstat()
            except FileNotFoundError:
                pass
            else:
                need(False, 'the exact previous R15 cgroup must still be absent')
            observed.append({'unit':unit, 'scope':scope, 'fields':fields, 'cgroup_absent':True})
    need(len(observed) == 6, 'all six actual prior user/system unit and cgroup checks completed')
    return {'original_failed_documents':R15_FAILURE_PINS, 'normal_CLI_successes':3,
            'original_outer_children_reaped':101, 'original_metadata_children_reaped':63,
            'actual_previous_units':observed, 'manifest_identity_unchanged':True,
            'exact_original_two_lock_PID_transitions_verified':True,
            'prior_r15_build_credit':False, 'prior_r15_body_bookend_credit':False,
            'prior_r15_normal_recovery_verified':False, 'resource_admission_reused':False,
            'production_ready':False, 'runtime_qualified':False}


R16_CRLF_HELPER_PATH = ROOT / 'control/vendor_source_bookends_r17_5cd1.py'
R16_CRLF_HELPER_PIN = (23844, '9fce0eeac82906fe5aa556f1718425fdf0b3fa181699bce18ad8e04cffacae15')
R18_BOOKEND_PIN = (26545, '95511da9a71294064259935a6917c2c8fcbf2d96307d84e1b2085f060f61ebb8')
PINS[R16_CRLF_HELPER_PATH] = R16_CRLF_HELPER_PIN

R16_CRLF_EVIDENCE = {'controls': {'path': '/home/qq/work/p4-official-vendor-cp3a-20261118-162b-r1/control/vendor_r16_5cd1_crlf_controls.json', 'bytes': 185918, 'sha256': '6124a8954037a5ef56718d3cda8a19a3945ba5b151e81746161f800b96307b3d'}, 'review': {'path': '/home/qq/work/p4-official-vendor-cp3a-20261118-162b-r1/control/vendor_r16_5cd1_crlf_review.json', 'bytes': 4074, 'sha256': 'b9effa5f02faae6eb49068cbf6c5a5e8e44150d0e30a277ab1f5f7abd3ffd66d'}, 'execution': {'path': '/home/qq/work/p4-official-vendor-cp3a-20261118-162b-r1/control/vendor_r16_5cd1_crlf_execution.json', 'bytes': 1282, 'sha256': '6d6452c14cc144c422cea4a81b5177a0ed04cd602d755540f2529f8994d0cf97'}}
R16_CRLF_CASES = ['actual_CRLF_committed_rule_and_stable_digest', 'original_raw_LF_match_without_attributes', 'one_content_byte_corrupted', 'lone_CR_rejected', 'mixed_LF_rejected', 'NUL_rejected', 'missing_committed_attributes_rejected', 'wrong_committed_eol_rejected', 'text_auto_not_explicit_text_rejected', 'executable_CRLF_rejected', 'custom_filter_rejected_never_executed', 'ident_rejected', 'working_tree_encoding_rejected', 'local_info_override_rejected', 'uncommitted_worktree_attributes_cannot_grant_conversion', 'uncommitted_index_attributes_cannot_grant_conversion', 'external_attributes_file_cannot_grant_conversion', 'original_symlink_behavior', 'original_sparse_absence_behavior']


def verify_r16_crlf_evidence():
    """Bind the new real Git controls separately from the unchanged R13 history."""
    need(BOOKENDS is not None, 'the pinned source helper is initialized')
    need(PINS[R19_PREVIOUS_HELPER_PATH] == R18_BOOKEND_PIN, 'unchanged historical reviewed R18 helper')
    check_pin(R16_CRLF_HELPER_PATH)  # Retained original helper for the historical 19 controls.
    values, observed = {}, {}
    for name, expected in R16_CRLF_EVIDENCE.items():
        path = Path(expected['path'])
        need(path.parent == ROOT / 'control' and 0 < expected['bytes'] <= 262144,
             'bounded fixed CRLF evidence input')
        before = digest(path)
        need((before['bytes'], before['sha256']) == (expected['bytes'], expected['sha256']),
             'complete original CRLF evidence body: ' + name)
        body = path.read_bytes()
        need(len(body) == expected['bytes'] and hashlib.sha256(body).hexdigest() == expected['sha256']
             and digest(path) == before, 'CRLF evidence read identity bookend: ' + name)
        values[name] = BOOKENDS.strict_json(body)
        observed[name] = before
    controls, review, execution = [values[name] for name in ('controls', 'review', 'execution')]
    need(controls['schema'] == 'pocket4-committed-CRLF-bookend-real-Git-controls-v1'
         and controls['passed'] is True and controls['controls_expected'] == controls['controls_passed'] == 19
         and len(controls['controls']) == 19
         and [case['name'] for case in controls['controls']] == R16_CRLF_CASES
         and all(case['passed'] is True for case in controls['controls'])
         and (controls['helper']['bytes'], controls['helper']['sha256']) == R16_CRLF_HELPER_PIN
         and controls['helper_and_original_fixtures_unchanged'] is True
         and controls['only_owned_temporary_repositories_mutated'] is True
         and controls['temporary_repositories_removed'] is True
         and controls['old_13_sparse_controls_rerun'] is False
         and controls['remote_commands'] == controls['Android_actions'] == controls['actual_source_checkout_mutations'] == 0
         and all(controls[key] is False for key in ('build_qualified', 'runtime_qualified', 'production_ready')),
         'exact actual 19 local Git controls without source or runtime credit')
    need(len(controls['real_Git_fixture_setup_commands']) == 218
         and all(command['exit_code'] == 0 for command in controls['real_Git_fixture_setup_commands']),
         'all actual local fixture Git commands succeeded')
    queries = [command for case in controls['controls'] for command in case['helper_commands']]
    need(len(queries) == 15 and all(command['exit_code'] == 0 and command['actual_child_reaped'] is True
         and command['pidfd_inode'] > 0 and command['stderr_bytes'] == 0 for command in queries),
         'all actual immutable-commit attribute query children reaped')
    positive = controls['controls'][0]
    row = positive['returned_row']
    need(positive['second_actual_query_distinct_PID_same_stable_row'] is True
         and row['bytes'] == 11989
         and row['sha256'] == '98bb09f34b4c017c8cca9adfc11d24758ae5cd0dbbf1c9895a6e049e21b44e1e'
         and row['raw_git_blob'] == '82d5fba0fa6cbd597e68eea9bdaab8029df584d7'
         and row['git_blob'] == row['checkout_conversion']['normalized_git_blob'] ==
             '5e349dce95644ff02f7bf4177ef0c5cd29e0e2c5'
         and row['checkout_conversion']['CRLF_pairs'] == 549
         and row['checkout_conversion']['source_mutated'] is False
         and row['checkout_conversion']['custom_filters_executed'] is False,
         'actual original CRLF bytes match only after the committed conversion')
    need(all(case['expected_rejection'] is not None for case in controls['controls'][2:17])
         and all(case['raw_before_after_unchanged'] is True
                 and case['custom_filter_marker_absent_before_after'] is True
                 for case in controls['controls'][:17])
         and controls['controls'][17]['changed_target_rejected'] == 'symlink bytes differ from original Git blob'
         and controls['controls'][18]['inside_cone_required_absence_rejected'] == 'missing required source body: outside/missing.txt',
         'content, attributes, mode, symlink and required-presence failures remain rejected')
    need(review['schema'] == 'pocket4-committed-crlf-bookend-independent-source-review-v1'
         and review['passed'] is True and review['must_fix_findings'] == []
         and (review['candidate']['bytes'], review['candidate']['sha256']) == R16_CRLF_HELPER_PIN
         and review['predecessor']['sha256'] ==
             '4d192fa6738a954e0b2f4a480a8ba38a68ad47fefbd5eabbf3b8d00ca29cfad7'
         and len(review['unchanged_existing_functions']) == 15
         and review['full_651_after_fix_verified'] is False,
         'independent exact old-to-new helper review preserves the historical boundary')
    need(execution['schema'] == 'pocket4-crlf-required-controls-execution-v1'
         and execution['terminal']['exit_code'] == 0
         and execution['remote_commands'] == execution['Android_actions'] == 0
         and execution['source_or_runtime_qualification'] is False,
         'actual local control execution completed successfully')
    reported = BOOKENDS.strict_json(execution['terminal']['output'].encode())
    need(reported['passed'] is True and reported['controls'] == reported['controls_passed'] == 19
         and reported['helper_sha256'] == R16_CRLF_HELPER_PIN[1]
         and all(reported['result'][key] == R16_CRLF_EVIDENCE['controls'][key]
                 for key in ('bytes', 'sha256')), 'actual original control output binds the complete result')
    return {'evidence': observed, 'historical_R16_helper_controls_passed': 19,
            'historical_sparse_controls_helper_sha256':
                '4d192fa6738a954e0b2f4a480a8ba38a68ad47fefbd5eabbf3b8d00ca29cfad7',
            'whole651_body_success_claimed': False, 'runtime_qualified': False,
            'production_ready': False}


# Append after the existing R12/R2/R14 guard chain and the new R15 function.
# This wrapper is used only by the original outer/build admission call sites.
_verify_serialized_retirement_before_r16_r15_failure = verify_serialized_retirement


def verify_serialized_retirement():
    result = _verify_serialized_retirement_before_r16_r15_failure()
    result['previous_r15_failed_body_bookend'] = verify_r15_failed_body_bookend()
    result['committed_CRLF_helper_controls'] = verify_r16_crlf_evidence()
    return result


R16_STATUS_FAILURE_PINS = {'pty': {'bytes': 12432,
         'f9': [66306, 72394540, 33152, 1000, 1000, 1, 12432, 1795094201736072046, 1795094201737135629],
         'path': '/home/qq/work/p4-official-vendor-cp3a-20261118-162b-r1/control/vendor_r17_5cd1_r16_original_pty.stdout',
         'sha256': 'a3ce83f69501fcef2538fb95f5b0ea762c100e3111e886caf530bc52be23843e'},
 'retirement': {'bytes': 13209,
                'f9': [66306,
                       72394538,
                       33152,
                       1000,
                       1000,
                       1,
                       13209,
                       1795094193671783609,
                       1795094193671998423],
                'path': '/home/qq/work/p4-official-vendor-cp3a-20261118-162b-r1/control/vendor_r17_5cd1_r16_retirement.json',
                'sha256': 'ab4c59330dd15a8183369e068964983e698e99e32c0c8c79790b850d29324316'},
 'terminal': {'bytes': 32936,
              'f9': [66306,
                     72517965,
                     33152,
                     1000,
                     1000,
                     1,
                     32936,
                     1795093863371682915,
                     1795093863371682915],
              'path': '/home/qq/work/p4-official-vendor-cp3a-20261118-162b-r1/control/build-r16-5cd1/outer-terminal.json',
              'sha256': '7d70ecfc4b8da28ce66898e7302c84d60f0b1688827f875bb3170d25c935611c'},
 'worker': {'bytes': 135116,
            'f9': [66306, 72394520, 33152, 1000, 1000, 1, 135116, 1795093617845776456, 1795093617848226810],
            'path': '/home/qq/work/p4-official-vendor-cp3a-20261118-162b-r1/control/vendor_build_r16_5cd1.py',
            'sha256': '76bdb393dc7873f61301ada37387fd9f4781251a0da8f4fdbe508d24d38adbc1'}}

R16_STATUS_UNITS = ('p4-cp3a-vendor-supervisor-20261119-5cd1-r16.service',
 'p4-cp3a-vendor-20261119-5cd1-r16.service',
 'p4-cp3a-vendor-20261119-5cd1-r16-recovery.service')

R16_STATUS_PROPERTY_ARG = '--property=LoadState,ActiveState,SubState,MainPID,ControlGroup'

R16_ORIGINAL_CLIENT_SESSION = 'dpty-45e611016935edae3aa07ccd17aa2390f3c71eae488d88ce03f0ca5c8b08efad'

R16_ORIGINAL_INVOCATION = 'e474ddd0d5cb4a5686a9d97dcd00a7d1'

R16_ORIGINAL_STATUS_INITIAL_GUARD = ("need(argv[:3] == ['/usr/bin/systemctl','--user','show'] and len(argv) == 5\n"
 '         and timeout == 15 and check is False and stdin == subprocess.DEVNULL\n'
 "         and stdout == stderr == subprocess.PIPE, 'fixed status-only child contract')")

R16_UNCHANGED_MANIFEST = {'bytes': 441444,
 'f9': [66306, 61122520, 33152, 1000, 1000, 1, 441444, 1795087857519520381, 1795087857524520237],
 'path': '/home/qq/work/pocket4-native-source597-ai395-20261108-8b88-r1/work/aosp-source/.droidloom-source-manifest.json',
 'sha256': '704ec2a6ba4fec751490b0da492b161887479ef9579f18025374d56ced72f5a3'}

R16_UNCHANGED_LOCKS = [{'f9': [66306, 60857531, 33152, 1000, 1000, 1, 0, 1794183129522871360, 1794183129522871360],
  'path': '/home/qq/work/pocket4-native-source597-ai395-20261108-8b88-r1/native-full.serial.lock'},
 {'f9': [66306, 60857480, 33152, 1000, 1000, 1, 8, 1795091215883526726, 1795091215883526726],
  'path': '/home/qq/work/pocket4-native-source597-ai395-20261108-8b88-r1/work/package-build.lock'},
 {'f9': [66306, 60857481, 33152, 1000, 1000, 1, 8, 1795091215883526726, 1795091215883526726],
  'path': '/home/qq/work/pocket4-native-source597-ai395-20261108-8b88-r1/work/aosp-source-update.lock'}]

R16_ABSENT_ADMISSION_PATHS = ['/home/qq/work/p4-official-vendor-cp3a-20261118-162b-r1/control/build-r16-5cd1/outer-admission.json',
 '/home/qq/work/p4-official-vendor-cp3a-20261118-162b-r1/control/build-r16-5cd1/outer-resource-probe.json',
 '/home/qq/work/p4-official-vendor-cp3a-20261118-162b-r1/control/build-r16-5cd1/serialized-heavy-admission.json',
 '/home/qq/work/p4-official-vendor-cp3a-20261118-162b-r1/control/build-r16-5cd1/build-observation.json',
 '/home/qq/work/p4-official-vendor-cp3a-20261118-162b-r1/control/build-r16-5cd1/recovery-observation.json',
 '/home/qq/work/p4-official-vendor-cp3a-20261118-162b-r1/control/build-r16-5cd1/source-reconcile-intent.json',
 '/home/qq/work/p4-official-vendor-cp3a-20261118-162b-r1/control/build-r16-5cd1/source-reconcile-returned.json',
 '/home/qq/work/p4-official-vendor-cp3a-20261118-162b-r1/control/build-r16-5cd1/source-transition-complete.json',
 '/home/qq/work/p4-official-vendor-cp3a-20261118-162b-r1/control/build-r16-5cd1/source-vendor-intent.json']


def verify_r16_status_contract_failure():
    """Admit the exact retired R16 zero-phase failure; grant no build credit."""
    need(BOOKENDS is not None, 'the pinned JSON helper must already be initialized')

    def expected(pin):
        return {'path': pin['path'], 'bytes': pin['bytes'],
                'sha256': pin['sha256'], 'identity': pin['f9']}

    def body(pin):
        path = Path(pin['path'])
        need(pin['bytes'] <= 256 * 1024 and digest(path) == expected(pin),
             'exact bounded R16 historical input')
        raw = path.read_bytes()
        need(len(raw) == pin['bytes'] and hashlib.sha256(raw).hexdigest() == pin['sha256']
             and digest(path) == expected(pin), 'R16 complete historical input bookend')
        return raw

    raw = {name: body(pin) for name, pin in R16_STATUS_FAILURE_PINS.items()}
    terminal = BOOKENDS.strict_json(raw['terminal'])
    retired = BOOKENDS.strict_json(raw['retirement'])
    need(terminal['schema'] == 'pocket4-vendor-r16-supervisor-terminal-v1'
         and terminal['passed'] is False and terminal['build_attempted'] is False
         and terminal['normal_recovery_attempted'] is False
         and terminal['normal_recovery_verified'] is False
         and terminal['phases'] == terminal['children'] == []
         and terminal['serial_lock_acquired'] is True
         and terminal['serial_held_through_all_source_operations'] is False
         and terminal['all_created_children_reaped'] is True
         and terminal['all_owned_units_retired'] is True
         and terminal['final_retirement_errors'] == []
         and terminal['fixed_deadline_exceeded'] is False
         and all(terminal[key] is False for key in ('installed', 'runtime_qualified', 'production_ready')),
         'R16 really failed before every source, build and recovery phase')
    need(len(terminal['errors']) == 1 and terminal['errors'][0]['stage'] == 'outer'
         and terminal['errors'][0]['error'] == "RuntimeError('fixed status-only child contract')",
         'only the exact original status-contract failure is admitted')
    need(terminal['worker'] == R16_STATUS_FAILURE_PINS['worker'],
         'the actual failed outer bound this exact original worker')
    original_children = terminal['original_worker_status_children']
    need(len(original_children) == 64
         and all(row['actual_child_reaped'] is True and row['original_pidfd_held_until_reaped'] is True
                 and type(row['exit_code']) is int and row['exit_code'] == 0
                 and row['error'] is None and row['argv'][:3] == ['/usr/bin/systemctl', '--user', 'show']
                 for row in original_children)
         and original_children[-1]['argv'] == ['/usr/bin/systemctl', '--user', 'show',
              'p4-cp3a-vendor-supervisor-20261119-5cd1-r15.service', R16_STATUS_PROPERTY_ARG],
         'all 64 original user-status children exited and were reaped before the rejected system query')
    need(retired['schema'] == 'pocket4-r16-prephase-status-contract-independent-retirement-v1'
         and retired['passed'] is True
         and retired['passed_scope'] == 'actual failure evidence and exact unit/lock retirement only'
         and retired['proofs'] == {'outer-terminal.json': R16_STATUS_FAILURE_PINS['terminal']}
         and retired['original_worker'] == R16_STATUS_FAILURE_PINS['worker']
         and retired['actual_metadata_children_reaped'] == 64
         and retired['actual_outer_children_reaped'] == 0
         and retired['system_scope_query_rejected_before_row_or_child_creation'] is True
         and retired['original_status_function_initial_guard'] == R16_ORIGINAL_STATUS_INITIAL_GUARD
         and R16_ORIGINAL_STATUS_INITIAL_GUARD.encode() in raw['worker'],
         'the independent proof preserves the pre-spawn rejection and actual child retirement')
    need(all(retired[key] is False for key in ('r16_build_passed', 'normal_recovery_verified',
         'outer_resource_admission_completed', 'build_or_recovery_phase_dispatched',
         'source_reconcile_or_vendor_dispatched', 'source_body_equality_claimed', 'whole_source_scanned',
         'production_ready', 'runtime_qualified', 'installed'))
         and retired['source_mutations'] == 0,
         'no source equality, resource admission, recovery, build or production credit is granted')
    client = retired['original_client']
    need(client['host'] == 'ai395' and client['session_id'] == R16_ORIGINAL_CLIENT_SESSION
         and client['original_pid'] == 2759242 and client['original_owner_pid'] == 2759241
         and client['exit_code'] == 1 and client['output_complete'] is True
         and client['capture_error'] is None and client['available_end'] == 12432
         and client['whole_output']['bytes'] == R16_STATUS_FAILURE_PINS['pty']['bytes']
         and client['whole_output']['sha256'] == R16_STATUS_FAILURE_PINS['pty']['sha256']
         and retired['original_client_exit_code'] == 1
         and retired['original_client_output_complete'] is True
         and retired['outer_invocation_id'] == R16_ORIGINAL_INVOCATION,
         'the whole original failed client and exact invocation are joined to the pinned output')
    collector = retired['collector_original_client']
    need(collector['host'] == 'ai395'
         and collector['session_id'] == 'dpty-2159e9dee9db09dcc520b6e717c003e0063886772aa5060570be9730aff03c63'
         and collector['original_pid'] == 2771494 and collector['original_owner_pid'] == 2771486
         and collector['exit_code'] == 0 and collector['output_complete'] is True
         and collector['capture_error'] is None
         and collector['whole_output']['bytes'] == 7146
         and collector['whole_output']['sha256'] == 'aa54e06884b9ca6951757b5df9bc67fc69d120de6b9ec0d6e7addeb1cf0f1bfd',
         'the actual bounded independent collector completed successfully')
    output = raw['pty'].decode('utf-8', errors='strict')
    marker = 'Running as unit: p4-cp3a-vendor-supervisor-20261119-5cd1-r16.service; invocation ID: ' + R16_ORIGINAL_INVOCATION
    need(output.count(marker) == 1, 'exactly one original R16 supervisor invocation')
    objects = [BOOKENDS.strict_json(line.encode()) for line in output.splitlines() if line.startswith('{')]
    need(objects[0] == {'build_attempts': 0, 'outer_fresh_memory_requirement_unchanged': 42 * GIB,
         'pid': 2759242, 'required_disk': 144 * GIB, 'required_memory': 44 * GIB,
         'sample_seconds': 5, 'stable_seconds': 30, 'state': 'WAITING_FOR_SAMPLED_STABLE_RESOURCES',
         'wait_seconds': 1800}, 'the original bounded readiness contract was not weakened')
    samples = [row for row in objects if 'sample' in row]
    need([row['sample'] for row in samples] == list(range(1, 42))
         and all(samples[index]['monotonic_ns'] < samples[index+1]['monotonic_ns'] for index in range(40))
         and samples[-1] == retired['readiness_final_pre_exec_sample']
         and samples[-1]['final_pre_exec_sample'] is True
         and retired['readiness_stable_window_passed'] is True,
         'complete ordered actual readiness samples end in the same final pre-exec sample')
    stable = samples[33:40]
    need(len(stable) == 7 and stable[-1]['monotonic_ns'] - stable[0]['monotonic_ns'] >= 30_000_000_000
         and all(row['qualifies'] is True and row['original_three_locks_free'] is True
                 and row['memory_available'] >= 44 * GIB and row['free_bavail'] >= 144 * GIB
                 and row['stable_since_monotonic_ns'] == stable[0]['monotonic_ns'] for row in stable)
         and samples[-1]['qualifies'] is True
         and samples[-1]['memory_available'] >= 44 * GIB
         and samples[-1]['free_bavail'] >= 144 * GIB,
         'readiness really passed without substituting for the uncompleted outer resource gate')
    need(objects[-1] == {'passed': False, 'phases': [], 'errors': terminal['errors']},
         'the original complete PTY preserves the exact terminal failure')

    manifest = retired['actual_final_source_manifest']
    need(manifest == R16_UNCHANGED_MANIFEST
         and manifest['path'] == str(SOURCE / '.droidloom-source-manifest.json')
         and r19_manifest_transition_matches(manifest),
         'R16 did not change the original current manifest identity or content')
    need(retired['original_locks'] == R16_UNCHANGED_LOCKS
         and [row['path'] for row in R16_UNCHANGED_LOCKS] == [str(path) for path, inode in LOCK_PINS]
         and retired['all_three_original_locks_free_unchanged_f9_and_released'] is True,
         'the same three original lock identities were independently acquired and released')
    for index, lock in enumerate(R16_UNCHANGED_LOCKS):
        lock_body = b'' if index == 0 else b'2650863\n'
        pin = {'path': lock['path'], 'bytes': len(lock_body), 'f9': lock['f9'],
               'sha256': hashlib.sha256(lock_body).hexdigest()}
        need(retired['lock_body_hex'][index] == lock_body.hex()
             and retired['lock_body_sha256'][index] == pin['sha256'], 'unchanged historical R16 full lock F9 and PID body')
        r18_live_lock_pin(pin)
    need(retired['control_membership'] == ['outer-terminal.json']
         and retired['exact_absent_phase_and_admission_paths'] == R16_ABSENT_ADMISSION_PATHS,
         'the independent proof recorded no admission or phase artifacts')
    for name in R16_ABSENT_ADMISSION_PATHS:
        try:
            Path(name).lstat()
        except FileNotFoundError:
            pass
        else:
            need(False, 'an original R16 admission or phase artifact unexpectedly exists')

    original_units = retired['exact_units_and_cgroups_retired']
    need([row['unit'] for row in original_units] == list(R16_STATUS_UNITS),
         'only the three exact original R16 units are in scope')
    fixed_fields = {'LoadState': 'not-found', 'ActiveState': 'inactive', 'SubState': 'dead',
                    'MainPID': '0', 'ControlGroup': ''}
    observed = []
    for unit, original in zip(R16_STATUS_UNITS, original_units):
        cgroups = ['/sys/fs/cgroup/user.slice/user-1000.slice/user@1000.service/app.slice/' + unit,
                   '/sys/fs/cgroup/system.slice/' + unit]
        need(len(original['status']) == 2 and original['absent_cgroups'] == cgroups,
             'exact historical user/system observations and cgroup paths')
        for index, scope in enumerate(('user', 'system')):
            argv = ['/usr/bin/systemctl'] + (['--user'] if scope == 'user' else []) + [
                'show', unit, R16_STATUS_PROPERTY_ARG]
            history = original['status'][index]
            lines = history['stdout'].splitlines()
            need(history['argv'] == argv and history['exit_code'] == 0
                 and history['actual_child_reaped'] is True
                 and history['original_pidfd_held_until_reaped'] is True
                 and history['stderr'] == '' and len(lines) == 5
                 and dict(line.split('=', 1) for line in lines) == fixed_fields,
                 'the independent historical unit query was complete, retired and reaped')
            result = status_run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=15, check=False)
            lines = result.stdout.decode('utf-8', errors='strict').splitlines()
            need(result.returncode == 0 and not result.stderr and len(lines) == 5
                 and dict(line.split('=', 1) for line in lines) == fixed_fields,
                 'the exact prior R16 unit must still be fully retired')
            cgroup = Path(cgroups[index])
            try:
                cgroup.lstat()
            except FileNotFoundError:
                pass
            else:
                need(False, 'the exact prior R16 cgroup must still be absent')
            observed.append({'unit': unit, 'scope': scope, 'fields': fixed_fields,
                             'cgroup_path': str(cgroup), 'cgroup_absent': True})
    need(len(observed) == 6, 'all six exact live R16 retirement observations completed')
    for pin in R16_STATUS_FAILURE_PINS.values():
        need(digest(Path(pin['path'])) == expected(pin), 'final original failure evidence bookend')
    need(r19_manifest_transition_matches(manifest), 'final manifest with exact actual R4 transition')
    for index, lock in enumerate(R16_UNCHANGED_LOCKS):
        lock_body = b'' if index == 0 else b'2650863\n'
        pin = {'path': lock['path'], 'bytes': len(lock_body), 'f9': lock['f9'],
               'sha256': hashlib.sha256(lock_body).hexdigest()}
        r18_live_lock_pin(pin)  # Complete current R17 lock bookend; historical R16 pin stays unchanged.
    return {'original_failed_documents': R16_STATUS_FAILURE_PINS,
            'original_outer_invocation': R16_ORIGINAL_INVOCATION,
            'original_metadata_children_reaped': 64, 'original_outer_children_reaped': 0,
            'system_scope_query_rejected_before_child_creation': True,
            'actual_previous_units': observed, 'manifest_identity_unchanged': True, 'historical_R16_lock_identities_preserved': True,
            'current_lock_F9_advanced_only_by_R17_normal_recovery': True,
            'prior_r16_build_credit': False, 'prior_r16_recovery_credit': False,
            'prior_r16_source_body_credit': False, 'resource_admission_reused': False,
            'installed': False, 'runtime_qualified': False, 'production_ready': False}


R17_STATUS_EVIDENCE = {'controls': {'bytes': 30199, 'f9': [66306, 72394542, 33200, 1000, 1000, 1, 30199, 1795094717875580549, 1795094717877228529], 'path': '/home/qq/work/p4-official-vendor-cp3a-20261118-162b-r1/control/vendor_r17_5cd1_status_controls.json', 'sha256': '47d5b36545ae76acb0825f19c6e0abc96974a64d9282e0cff26ae656f8e5e0f8'}, 'retirement': {'bytes': 6214, 'f9': [66306, 72394557, 33200, 1000, 1000, 1, 6214, 1795094720486134727, 1795094720487134691], 'path': '/home/qq/work/p4-official-vendor-cp3a-20261118-162b-r1/control/vendor_r17_5cd1_status_controls_retirement.json', 'sha256': 'de8499d4d1e8b42ea300663a7cce838f113ea616b931d292345b64ff6add7e65'}}

def verify_r17_actual_status_controls():
    """Require the actual twelve predecessor queries and their retired unit."""
    values, observed = {}, {}
    for name, pin in R17_STATUS_EVIDENCE.items():
        path = Path(pin['path'])
        expected = {'path': pin['path'], 'bytes': pin['bytes'],
                    'sha256': pin['sha256'], 'identity': pin['f9']}
        need(path.parent == ROOT / 'control' and 0 < pin['bytes'] <= 131072
             and digest(path) == expected, 'exact bounded actual status evidence')
        raw = path.read_bytes()
        need(len(raw) == pin['bytes'] and hashlib.sha256(raw).hexdigest() == pin['sha256']
             and digest(path) == expected, 'actual status evidence whole-body bookend')
        values[name] = BOOKENDS.strict_json(raw)
        observed[name] = expected
    controls, retirement = values['controls'], values['retirement']
    need(controls['schema'] == 'pocket4-r17-actual-fixed-predecessor-status-controls-v1'
         and controls['state'] == 'PASSED' and controls['errors'] == []
         and controls['expected_query_count'] == 12 and len(controls['queries']) == 12
         and len(controls['status_commands']) == 12
         and controls['all_twelve_fixed_queries_passed'] is True
         and controls['all_created_query_children_reaped'] is True
         and controls['remaining_direct_children'] == ''
         and controls['input_pins_before'] == controls['input_pins_after']
         and controls['actual_function_extracted_from_candidate_AST'] is True
         and controls['operational_worker_imported_or_executed'] is False
         and controls['all_PIDFD_reap_algorithm_statements_unchanged'] is True
         and all(controls[key] == 0 for key in ('source_mutations', 'lock_operations', 'build_actions', 'VM_actions'))
         and controls['runtime_qualified'] is False and controls['production_ready'] is False,
         'the actual same-function twelve-query control completed without operational side effects')
    candidate = controls['input_pins_before']['candidate']
    need(candidate['bytes'] == 3622 and candidate['sha256'] ==
         '753b08b70df6f181656b18c38c048955184d807b653a3c28415d3a23e3808433'
         and controls['input_pins_before']['original_worker'] == R16_STATUS_FAILURE_PINS['worker'],
         'actual queries tested the exact new function against the actual failed predecessor')
    units = ('p4-cp3a-vendor-supervisor-20261119-5cd1-r15.service',
             'p4-cp3a-vendor-20261119-5cd1-r15.service',
             'p4-cp3a-vendor-20261119-5cd1-r15-recovery.service') + R16_STATUS_UNITS
    property_arg = '--property=LoadState,ActiveState,SubState,MainPID,ControlGroup'
    fields = {'LoadState': 'not-found', 'ActiveState': 'inactive',
              'SubState': 'dead', 'MainPID': '0', 'ControlGroup': ''}
    expected_queries = [(unit, scope) for unit in units for scope in ('user', 'system')]
    for query, command, (unit, scope) in zip(controls['queries'], controls['status_commands'], expected_queries):
        argv = ['/usr/bin/systemctl'] + (['--user'] if scope == 'user' else []) + ['show', unit, property_arg]
        need(query['unit'] == unit and query['scope'] == scope and query['argv'] == argv
             and query['exit_code'] == 0 and query['stderr'] == '' and query['fields'] == fields
             and query['post_reap_ECHILD'] is True and query['actual_status_child'] == command
             and command['argv'] == argv and command['exit_code'] == 0
             and command['actual_child_reaped'] is True and command['original_pidfd_held_until_reaped'] is True
             and command['error'] is None, 'all twelve exact original queries have complete child retirement')
    need(retirement['schema'] == 'pocket4-r17-status-scope-independent-retirement-v1'
         and retirement['passed'] is True and retirement['actual_query_count'] == 12
         and retirement['own_unit_and_two_cgroups_retired'] is True
         and retirement['all_twelve_PIDFD_held_until_actual_reap'] is True
         and retirement['all_twelve_post_reap_ECHILD'] is True
         and retirement['actual_input_bookends_unchanged'] is True
         and retirement['status_controls_repeated'] is False
         and retirement['invocation_id'] == controls['invocation_id']
         and all(retirement['actual_result'][key] == R17_STATUS_EVIDENCE['controls'][key]
                 for key in ('bytes', 'sha256'))
         and retirement['original_client']['exit_code'] == 0
         and retirement['original_client']['output_complete'] is True
         and retirement['original_client']['capture_error'] is None
         and retirement['original_client']['session_id'] ==
             'dpty-52cfc648078ee2ca766dc9f983db985b1d502a37e4d09904a03727b05cce12b1'
         and retirement['runtime_qualified'] is False and retirement['production_ready'] is False,
         'exact independently reviewed actual status result, original client and unit retirement')
    unit = 'p4-r17-status-scope-controls-5cd1-20261119-r1.service'
    need(controls['unit'] == unit and controls['invocation_id'] == '1d7c6df4891149f0ab7ca8e3a179d805',
         'the one actual bounded status control invocation')
    result = status_run(['/usr/bin/systemctl', '--user', 'show', unit, property_arg],
                        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        timeout=15, check=False)
    actual = dict(line.split('=', 1) for line in result.stdout.decode().splitlines())
    need(result.returncode == 0 and result.stderr == b'' and actual == fields,
         'the original status-only control unit must remain retired')
    for parent in ('/sys/fs/cgroup/user.slice/user-1000.slice/user@1000.service/app.slice',
                   '/sys/fs/cgroup/system.slice'):
        try:
            (Path(parent) / unit).lstat()
        except FileNotFoundError:
            pass
        else:
            need(False, 'the original status-only control cgroup remains')
    return {'evidence': observed, 'actual_prior_queries_passed': 12,
            'original_driver_unit_still_retired': True,
            'source_body_or_vendor_build_credit': False,
            'runtime_qualified': False, 'production_ready': False}


_verify_serialized_retirement_before_r17_r16_failure = verify_serialized_retirement

def verify_serialized_retirement():
    result = _verify_serialized_retirement_before_r17_r16_failure()
    result['previous_r16_failed_status_admission'] = verify_r16_status_contract_failure()
    result['actual_r17_status_scope_controls'] = verify_r17_actual_status_controls()
    return result

R18_ADMISSION_INPUTS = {'controls': {'path': '/home/qq/work/p4-official-vendor-cp3a-20261118-162b-r1/control/vendor_r18_2331_optional_info_controls.json', 'bytes': 537, 'sha256': '46fb758af85a8be8fba137f8bf6aa0f85819ab3f6bdf6238c8e603c097d6d60d'}, 'review': {'path': '/home/qq/work/p4-official-vendor-cp3a-20261118-162b-r1/control/vendor_r18_2331_optional_info_review.json', 'bytes': 2738, 'sha256': '08c71d12cc964d329910020e8df540d3df6d9f5bf03b341cb68c68a6af82cf92'}, 'retirement': {'path': '/home/qq/work/p4-official-vendor-cp3a-20261118-162b-r1/control/vendor_r18_2331_r17_retirement.json', 'bytes': 2257, 'sha256': 'b7b35a0a6f3d0a64ef5ff4bf091de9d90901dd0679c30271e213bc4d62a3a564'}, 'locks': {'path': '/home/qq/work/p4-official-vendor-cp3a-20261118-162b-r1/control/vendor_r18_2331_r17_locks.json', 'bytes': 3058, 'sha256': 'bd35a9d28e0bf0b0e6c5e60426025b1044b526a8ea72aec0b517df0357bd603c'}, 'admission': {'path': '/home/qq/work/p4-official-vendor-cp3a-20261118-162b-r1/control/build-r17-5cd1/outer-admission.json', 'bytes': 2264, 'sha256': '66e4e99e61285f6ef5cafbbf50ef73220dc28d003f47f3855110d39dae01a53b'}}
R17_PREDECESSOR_UNITS = ('p4-cp3a-vendor-supervisor-20261119-5cd1-r17.service', 'p4-cp3a-vendor-20261119-5cd1-r17.service', 'p4-cp3a-vendor-20261119-5cd1-r17-recovery.service')
PINS.update({Path(ref['path']):(ref['bytes'],ref['sha256']) for ref in R18_ADMISSION_INPUTS.values()})

# R18 adds only read-only admission evidence. The normal build/recovery and
# original serial/package/source lock acquisition algorithms remain unchanged.
R18_BOUND_LIVE_LOCKS = None


def r18_read_document(ref):
    path = Path(ref['path'])
    need(0 < ref['bytes'] <= 262144, 'bounded R18 admission document')
    observed = digest(path)
    need((observed['bytes'], observed['sha256']) == (ref['bytes'], ref['sha256']),
         'complete frozen R18 admission document')
    if 'f9' in ref:
        need(observed['identity'] == ref['f9'], 'exact original R17 document full F9')
    raw = path.read_bytes()
    need(len(raw) == ref['bytes'] and hashlib.sha256(raw).hexdigest() == ref['sha256']
         and digest(path) == observed, 'whole R18 admission document bookend')
    def pairs(items):
        value = {}
        for key, item in items:
            need(key not in value, 'duplicate R18 admission key')
            value[key] = item
        return value
    value = json.loads(raw, object_pairs_hook=pairs,
                       parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
    return value, observed


def validate_r18_helper_controls(controls, review):
    need(controls['schema'] == 'p4-r18-new-real-Git-optional-info-controls-v1'
         and controls['passed'] is True and controls['tests_run'] == 33
         and controls['failures'] == controls['errors'] == controls['original_source_mutations'] == 0
         and controls['new_controls_not_historical_replay'] is True
         and (controls['helper']['bytes'], controls['helper']['sha256']) == R18_BOOKEND_PIN
         and controls['production_ready'] is False, 'actual new R18 controls bind the current helper')
    need(review['schema'] == 'p4-r18-optional-info-bookend-AST-and-real-Git-review-v1'
         and review['passed'] is True and review['controls_passed'] == 33
         and review['new_controls_not_historical_19_replay'] is True
         and (review['predecessor']['bytes'], review['predecessor']['sha256']) == R16_CRLF_HELPER_PIN
         and (review['candidate']['bytes'], review['candidate']['sha256']) == R18_BOOKEND_PIN
         and review['new_functions'] == ['held_git_attribute_metadata']
         and review['changed_existing_functions'] == ['committed_crlf_equivalence']
         and len(review['unchanged_existing_functions']) == 18
         and review['all_original_CRLF_check_statements_AST_identical_inside_held_context'] is True
         and all(review[key] is False for key in ('runtime_qualified', 'vendor_build_passed', 'production_ready'))
         and review['source_mutations'] == 0
         and all(review['controls'][key] == R18_ADMISSION_INPUTS['controls'][key]
                 for key in ('bytes', 'sha256')), 'review preserves every historical CRLF check without runtime credit')


def validate_r17_optional_info_records(terminal, build, recovery, retired, admission, locks):
    fixed = {'LoadState': 'not-found', 'ActiveState': 'inactive', 'SubState': 'dead',
             'MainPID': '0', 'ControlGroup': '', 'InvocationID': ''}
    need(retired['schema'] == 'p4-r18-original-r17-terminal-retirement-observation-v1'
         and retired['boot'] == 'b1620269-aaef-43e7-bf47-bc6eb1c1a447'
         and retired['source_mutations'] == retired['native_starts'] == 0
         and set(retired['units']) == set(R17_PREDECESSOR_UNITS)
         and all(value == fixed for value in retired['units'].values()),
         'actual independent read-only R17 unit observation, not a successful build')
    need(terminal['schema'] == 'pocket4-vendor-r17-supervisor-terminal-v1'
         and terminal['passed'] is terminal['normal_recovery_verified'] is False
         and terminal['all_owned_units_retired'] is terminal['all_created_children_reaped'] is True
         and terminal['serial_held_through_all_source_operations'] is terminal['serial_lock_acquired'] is True
         and terminal['build_attempted'] is terminal['normal_recovery_attempted'] is True
         and terminal['errors'] == terminal['final_retirement_errors'] == []
         and all(terminal[key] is False for key in ('installed', 'runtime_qualified', 'production_ready'))
         and len(terminal['phases']) == 2
         and [phase['mode'] for phase in terminal['phases']] == ['build', 'recover'],
         'the two failed original R17 phases retired without build or recovery credit')
    for phase, unit in zip(terminal['phases'], R17_PREDECESSOR_UNITS[1:]):
        boundary = phase['client_retirement_boundary']
        need(phase['unit'] == unit and phase['service_retired'] is True
             and phase['success'] is phase['late_start_unresolved'] is False
             and phase['errors'] == [] and boundary['client_exit_code'] == 1
             and boundary['original_client_actual_reaped'] is boundary['original_pidfd_held_until_reaped'] is True,
             'same original failed R17 phase and held client retirement')
    need(all(row['actual_reaped'] is row['original_pidfd_held_until_reaped'] is True
             for row in terminal['children'])
         and all(row['actual_child_reaped'] is row['original_pidfd_held_until_reaped'] is True
                 for row in terminal['original_worker_status_children']), 'all original R17 children were reaped')
    expected_error = "FileNotFoundError(2, 'No such file or directory')"
    for document, names in ((build, ['verify-full651-before']),
                            (recovery, ['normal-source-recovery', 'verify-full651-after'])):
        need(document['schema'] == 'p4-cp3a-normal-vendor-build-r17-v1' and document['source_tree'] == TREE
             and all(document[key] is False for key in ('installed', 'runtime_qualified', 'production_ready'))
             and len(document['errors']) == 1 and document['errors'][0]['error'] == expected_error
             and str(SOURCE / 'external/lz4/.git/info') in document['errors'][0]['traceback']
             and 'vendor_source_bookends_r17_5cd1.py' in document['errors'][0]['traceback']
             and [row['name'] for row in document['commands']] == names,
             'only the actual R17 optional-info failure before reconciliation or vendor dispatch')
        for row in document['commands']:
            need(row['exit_code'] == 0 and row['error'] is None and row['actual_child_reaped'] is True
                 and row['original_pidfd_held_until_reaped'] is True and row['owned_descendants_remaining'] == 0,
                 'ordinary original source command completed and retired')
    branch = recovery['source_recovery_branch']
    need(branch['branch'] == '651-before-reconcile-dispatch'
         and all(branch[key] is False for key in ('reconcile_dispatch_journal_present',
                 'reconcile_return_journal_present', 'source_complete_journal_present', 'vendor_dispatch_journal_present'))
         and build['old651_manifest']['original'] == branch['observed_manifest']['original'],
         'the original R17 source manifest did not enter a source transition')
    command = recovery['commands'][0]
    need(command == locks['original_normal_recovery'] and command['pid'] == 2818006
         and command['argv'] == [str(UPDATE_TOOL), 'recover-source', '--work', str(WORK)]
         and [command['started_ns'], command['finished_ns']] == [1795096144335845980, 1795096144340141321]
         and locks['schema'] == 'p4-r18-original-R17-normal-recovery-lock-observation-v1'
         and locks['mutations'] == 0 and locks['observed_ns'] > terminal['finished_ns'],
         'actual R17 normal recovery is the sole admitted new lock PID writer')
    need(admission['generation'] == 'baa5f4d642a636c25e9aae857b42490c'
         and admission['pid'] == 2803024 and admission['serial_lock'] == R16_UNCHANGED_LOCKS[0]['f9']
         and admission['supervisor'] == str(ROOT / 'control/vendor_outer_r17_5cd1.py')
         and admission['observed_ns'] < command['started_ns']
         and len(admission['locks']) == len(locks['locks']) == len(LOCK_PINS) == 3,
         'actual original R17 outer held the unchanged original serial lock before normal recovery')
    transitions = {}
    for index, (prior, actual, historical) in enumerate(zip(admission['locks'], locks['locks'], R16_UNCHANGED_LOCKS)):
        need(prior['path'] == actual['path'] == historical['path'] == str(LOCK_PINS[index][0])
             and prior['identity'] == historical['f9'] and type(actual['f9']) is list
             and len(actual['f9']) == 9 and all(type(value) is int for value in actual['f9'])
             and actual['f9'][:7] == historical['f9'][:7], 'all original seven lock identity fields remain exact')
        body = b'' if index == 0 else b'2818006\n'
        need(actual['bytes'] == actual['f9'][6] == len(body) and actual['body_hex'] == body.hex()
             and actual['body_text'] == body.decode() and actual['sha256'] == hashlib.sha256(body).hexdigest(),
             'exact actual R17 normal recovery PID body')
        if index == 0:
            need(actual['f9'] == historical['f9'], 'serial full F9 has no transition')
        else:
            need(all(command['started_ns'] <= value <= command['finished_ns'] for value in actual['f9'][7:])
                 and actual['f9'][7] == actual['f9'][8]
                 and actual['f9'][7] > historical['f9'][7], 'both PID lock times belong only to the actual normal recovery interval')
        old_body = b'' if index == 0 else b'2650863\n'
        transitions[actual['path']] = {
            'historical': {'path':historical['path'], 'bytes':len(old_body), 'f9':historical['f9'],
                           'sha256':hashlib.sha256(old_body).hexdigest()},
            'current': {'path':actual['path'], 'bytes':actual['bytes'], 'identity':actual['f9'], 'sha256':actual['sha256']},
            'body_hex': actual['body_hex']}
    return transitions


def r18_live_lock_pin(historical):
    need(R18_BOUND_LIVE_LOCKS is not None and historical['path'] in R18_BOUND_LIVE_LOCKS,
         'actual R17 lock transition must be admitted before historical live comparisons')
    transition = R18_BOUND_LIVE_LOCKS[historical['path']]
    need(historical == transition['historical'], 'unchanged original R15/R16 lock history')
    expected = transition['current']
    # Keep the exact historical R17 pin; only the independently proven R18
    # ordinary recovery advances its two PID bodies before the R4 restoration.
    return r19_live_lock_pin(expected, transition['body_hex'])


def verify_r18_predecessor_and_helper():
    evidence = {name:r18_read_document(ref) for name, ref in R18_ADMISSION_INPUTS.items()}
    controls, review, retired, locks, admission = [evidence[name][0]
        for name in ('controls', 'review', 'retirement', 'locks', 'admission')]
    validate_r18_helper_controls(controls, review)
    files = retired['files']
    need(set(files) == {'outer-terminal.json', 'build-observation.json', 'recovery-observation.json'},
         'exact three original R17 failed-phase records')
    documents = {name:r18_read_document(ref)[0] for name, ref in files.items()}
    terminal, build, recovery = [documents[name] for name in
        ('outer-terminal.json', 'build-observation.json', 'recovery-observation.json')]
    transitions = validate_r17_optional_info_records(terminal, build, recovery, retired, admission, locks)
    for original in (terminal['worker'], terminal['bundle']):
        need(digest(Path(original['path'])) == {'path':original['path'], 'bytes':original['bytes'],
             'sha256':original['sha256'], 'identity':original['f9']}, 'retained original R17 source and bundle')
    for document in (build, recovery):
        for command in document['commands']:
            for stream in ('stdout', 'stderr'):
                need(digest(Path(command[stream]['path'])) == command[stream], 'original R17 normal CLI output retained')
    manifest = build['old651_manifest']['original']
    need(manifest['path'] == str(SOURCE / '.droidloom-source-manifest.json')
         and r19_manifest_transition_matches(manifest), 'original 651 manifest with exact actual R4 transition')
    for original in (build['old651_manifest']['copy'], recovery['source_recovery_branch']['observed_manifest']['copy']):
        need(digest(Path(original['path'])) == original and original['sha256'] == manifest['sha256'],
             'retained complete original R17 manifest copies')
    previous = ROOT / 'control/build-r17-5cd1'
    for name in ('source-reconcile-intent', 'source-reconcile-returned', 'source-transition-complete', 'source-vendor-intent'):
        need(not os.path.lexists(previous / (name + '.json'))
             and not os.path.lexists(previous / (name + '.stage-new')), 'original R17 never dispatched source reconciliation or vendor')
    fixed = {'LoadState':'not-found', 'ActiveState':'inactive', 'SubState':'dead',
             'MainPID':'0', 'ControlGroup':'', 'InvocationID':''}
    observed_units = []
    for unit in R17_PREDECESSOR_UNITS:
        result = status_run(['/usr/bin/systemctl', '--user', 'show', unit,
            '--property=LoadState,ActiveState,SubState,MainPID,ControlGroup,InvocationID'],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15, check=False)
        lines = result.stdout.decode('utf-8', errors='strict').splitlines()
        need(result.returncode == 0 and not result.stderr and len(lines) == 6
             and dict(line.split('=', 1) for line in lines) == fixed, 'exact original R17 user unit remains retired')
        for parent in ('/sys/fs/cgroup/user.slice/user-1000.slice/user@1000.service/app.slice', '/sys/fs/cgroup/system.slice'):
            need(not os.path.lexists(Path(parent) / unit), 'original R17 cgroup remains absent')
        observed_units.append({'unit':unit, 'scope':'user', 'fields':fixed, 'both_cgroup_paths_absent':True})
    for name, ref in files.items():
        need(digest(Path(ref['path'])) == {'path':ref['path'], 'bytes':ref['bytes'],
             'sha256':ref['sha256'], 'identity':ref['f9']}, 'original R17 failure document final bookend')
    for name, (_, pin) in evidence.items():
        need(digest(Path(pin['path'])) == pin, 'R18 admission evidence final bookend')
    return {'original_failed_documents':files, 'actual_previous_units':observed_units,
            'new_R18_helper_controls_passed':33, 'historical_R16_controls_relabelled_as_current':False,
            'R17_whole651_body_passed':False, 'R17_successful_recovery_claimed':False,
            'runtime_qualified':False, 'production_ready':False}, transitions


_verify_serialized_retirement_before_r18 = verify_serialized_retirement


def verify_serialized_retirement():
    global R18_BOUND_LIVE_LOCKS
    need(R18_BOUND_LIVE_LOCKS is None, 'single non-reentrant R18 admission observation')
    current, transitions = verify_r18_predecessor_and_helper()
    R18_BOUND_LIVE_LOCKS = transitions
    try:
        result = _verify_serialized_retirement_before_r18()
        for transition in transitions.values():
            r18_live_lock_pin(transition['historical'])
        result['previous_r17_optional_info_failure_and_current_lock_transition'] = current
        return result
    finally:
        R18_BOUND_LIVE_LOCKS = None


# New R19 evidence is separate from every historical R10-R18 pin.
R19_ADMISSION_PATH = ROOT / 'control/vendor-build-20261120-9907-r19/inputs/RESTORATION.json'
R19_ADMISSION_PIN = (7922, '2aaeeda6079bee7905607a1d27a8413438f6f532053257cac049778c57a8b139')
R19_BOUND_RESTORATION = None
R19_PREVIOUS_HELPER_PATH = ROOT / 'control/vendor_source_bookends_r18_2331.py'
PINS[R19_PREVIOUS_HELPER_PATH] = R18_BOOKEND_PIN
R19_RESTORE_CONTROL = ROOT / 'control/source-restore-20261120-9907-r4'
R19_RESTORE_UNIT = 'p4-source-restore-20261120-9907-r4.service'
R19_RESTORE_CONTROLLER_SHA = '4039f65ceae159b2149a8848939709cca6447ef3b66f6b8dc46c80ef5ac925df'
R19_RESTORE_CONTRACT_SHA = 'c35a3b714c0652ef9f0cc33b6475a458640e21191e08cf7dc68e2580ba9c9935'
R19_RESTORE_BUDGET = {'affinity': [18, 19], 'control_growth_bytes': 2147483648, 'disk_admission_bytes': 199715979264, 'disk_floor_bytes': 154618822656, 'memory_admission_bytes': 45097156608, 'memory_reserve_bytes': 8589934592, 'operation_seconds': 3600, 'reconcile_seconds': 900, 'source_growth_bytes': 42949672960, 'unit_seconds': 3900}
R19_HELPER_SHA = 'bab5c377bf642d4aaa7b50a416319cebad31537022e5179a77e6e8d63827fa88'
R19_LEGACY_HELPER_SHA = '89c48f7fe7147db9ea8cb2309a3a3ae08ce4203ab63546fbe06db6d0764efe56'
R19_RESTORE_SESSION = 'dpty-9024a53f799bfdf48c9f12dcb3ca0aa93bf71cdf7ccdcc9e18fe71119a72ef35'
R19_RESTORE_INVOCATION = '13a82b6acc5349a895b18f1237465b58'
R19_RESTORE_PID = 3600130
R19_RESTORE_CLIENT_OWNER = 3600128
R19_RESTORE_CLIENT_PID = 3600129
R19_CONTROLS_SHA = 'ed048c7f9aceb1d9f0a2597803bdf8437b772c5e313bffde1268d7bf45dcfdbf'

def r19_ref(ref):
    """Normalize a real recorded F9 spelling, without changing any value."""
    need(type(ref) is dict and set(ref) in (
        {'path', 'bytes', 'sha256', 'identity'}, {'path', 'bytes', 'sha256', 'f9'}),
        'one complete recorded file identity, never a synthesized historical pin')
    identity = ref.get('identity', ref.get('f9'))
    need(type(identity) is list and len(identity) == 9
         and all(type(value) is int for value in identity)
         and type(ref['bytes']) is int and ref['bytes'] == identity[6], 'recorded full F9 and length')
    return {'path': ref['path'], 'bytes': ref['bytes'], 'sha256': ref['sha256'], 'identity': identity}


def r19_actual_ref(ref):
    expected = r19_ref(ref)
    need(digest(Path(expected['path'])) == expected, 'exact current evidence body and F9: ' + expected['path'])
    return expected


def r19_read_json(ref):
    expected = r19_actual_ref(ref)
    need(0 < expected['bytes'] <= 32 * 1024 * 1024, 'bounded complete R19 proof document')
    body = Path(expected['path']).read_bytes()
    need(len(body) == expected['bytes'] and hashlib.sha256(body).hexdigest() == expected['sha256']
         and r19_actual_ref(ref) == expected, 'R19 whole document read bookend')
    def unique(items):
        result = {}
        for key, value in items:
            need(key not in result, 'duplicate R19 proof key')
            result[key] = value
        return result
    return json.loads(body, object_pairs_hook=unique,
                      parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))


def r19_live_manifest_pin(historical):
    need(R19_BOUND_RESTORATION is not None, 'actual complete restoration required before live manifest admission')
    transition = R19_BOUND_RESTORATION['manifest']
    need(r19_ref(historical) == transition['before'], 'exact historical R2/R14/R15/R16/R17/R18 manifest retained')
    return r19_actual_ref(transition['after'])


def r19_manifest_transition_matches(historical):
    r19_live_manifest_pin(historical)
    return True


def r19_live_lock_pin(previous_r17, body_hex):
    need(R19_BOUND_RESTORATION is not None, 'actual R18 normal recovery required before live lock admission')
    transition = R19_BOUND_RESTORATION['locks'][previous_r17['path']]
    need(r19_ref(previous_r17) == transition['before'] and body_hex == transition['before_body_hex'],
         'unchanged historical R17 lock transition is the exact R18 admission preimage')
    actual = r19_actual_ref(transition['after'])
    need(Path(actual['path']).read_bytes().hex() == transition['after_body_hex']
         and r19_actual_ref(transition['after']) == actual, 'actual unchanged R18 lock body through source restoration')
    return actual


def r19_validate_lock_transitions(admission, recovery, contract):
    command = recovery['commands'][0]
    need(command['name'] == 'normal-source-recovery' and command['pid'] == 3305208
         and command['argv'] == [str(UPDATE_TOOL), 'recover-source', '--work', str(WORK)]
         and admission['generation'] == 'c96d6730f79a9f0323fd94745f616185'
         and admission['pid'] == 3297738
         and admission['supervisor'] == str(ROOT / 'control/vendor_outer_r18_2331.py')
         and admission['observed_ns'] < command['started_ns'], 'actual R18 outer and normal recovery PID writer')
    previous, current = admission['locks'], contract['original_locks']
    need(len(previous) == len(current) == 3, 'exact three original locks')
    result = {}
    for index, (before, after) in enumerate(zip(previous, current)):
        old_body = b'' if index == 0 else b'2818006\n'
        body = b'' if index == 0 else b'3305208\n'
        need(before['path'] == after['path'] == str(LOCK_PINS[index][0])
             and before['identity'][:7] == after['identity'][:7]
             and after['bytes'] == len(body) and after['body_hex'] == body.hex()
             and after['sha256'] == hashlib.sha256(body).hexdigest(), 'original lock inode/owner/mode/size and exact actual PID body')
        if index == 0:
            need(before['identity'] == after['identity'] == admission['serial_lock'], 'unchanged entire serial-lock F9')
        else:
            need(all(command['started_ns'] <= value <= command['finished_ns'] for value in after['identity'][7:])
                 and all(new > old for old, new in zip(before['identity'][7:], after['identity'][7:])),
                 'only normal R18 recovery advances the two PID-lock timestamps')
        result[after['path']] = {
            'before': {'path': before['path'], 'bytes': len(old_body), 'sha256': hashlib.sha256(old_body).hexdigest(),
                       'identity': before['identity']},
            'before_body_hex': old_body.hex(),
            'after': {key: after[key] for key in ('path', 'bytes', 'sha256', 'identity')},
            'after_body_hex': body.hex()}
    return result


def r19_load_module(name, reference):
    import types
    actual = r19_actual_ref(reference)
    need(0 < actual['bytes'] <= 1024 * 1024, 'bounded exact reviewed Python input')
    source = Path(actual['path']).read_bytes()
    need(len(source) == actual['bytes'] and hashlib.sha256(source).hexdigest() == actual['sha256'],
         'complete held reviewed module body')
    value = types.ModuleType(name)
    value.__file__ = actual['path']
    exec(compile(source, value.__file__, 'exec'), value.__dict__)
    need(r19_actual_ref(reference) == actual, 'reviewed module identity after import')
    return value


def r19_restore_stage_names(contract):
    names = {'ADMISSION.json', 'PRE-DIAGNOSTIC.json', 'CENSUS-PREIMAGE-BINDING.json',
             'MANIFEST-PUBLICATION.json', 'STRICT-AFTER.json', 'COMPARISON.json',
             'POSTIMAGE-STABILITY.json'}
    if contract['candidate_projection']['summary']['candidates'] == 0:
        names.add('VERIFY-ONLY.json')
    else:
        names.update(('SOURCE-RESTORATION-INTENT.json', 'RECONCILE-INTENT.json', 'RECONCILE-RETURNED.json',
                      'CHECKOUT-ATTRIBUTES.json'))
        names.update('FULL-PROJECT-%02d-%s.json' % (number, suffix)
                     for number in range(1, len(contract['fresh_full_project_repairs']) + 1)
                     for suffix in ('INTENT', 'RETURNED'))
    return names


def r19_validate_completion(contract, terminal, stages, census):
    """Pure exact checks on the reviewed R4 execution and complete result."""
    need(contract['schema'] == 'pocket4-same651-source-restoration-contract-v4'
         and contract['frozen_complete_census_contract'] is True
         and contract['control'] == str(R19_RESTORE_CONTROL)
         and contract['unit'] == R19_RESTORE_UNIT
         and contract['representation_controls_must_be_frozen'] is True
         and contract['budget'] == R19_RESTORE_BUDGET, 'exact reviewed R4 generation and original complete budget')
    need(terminal['schema'] == 'pocket4-normal-same651-restoration-terminal-v4', 'actual R4 terminal schema')
    need(all(terminal[key] is True for key in ('source_restored', 'all_created_children_reaped',
                 'all_original_locks_held_through_child_retirement')),
         'complete actual source restoration and original child/lock custody')
    need(all(terminal[key] is False for key in ('fixed_operation_deadline_exceeded',
                 'original_lock_bodies_written', 'native_build_run', 'installed', 'runtime_qualified', 'production_ready'))
         and terminal['errors'] == terminal['retired_descendants'] == []
         and type(terminal['ordinary_reconcile_max_attempts']) is int
         and terminal['ordinary_reconcile_max_attempts'] == 1
         and terminal['finished_monotonic'] < terminal['operation_deadline_monotonic'],
         'actual finite source-only result retains every original limit')
    summary = contract['candidate_projection']['summary']
    need(summary['missing_H'] == summary['missing_H_outside_cone'] == 0,
         'this exact reviewed R4 generation has no missing-H mutation scope')
    need(terminal['result']['r3_restore']['r3_failed_before_any_source_mutation'] is True
         and terminal['result']['r3_restore']['all_original_r3_inputs_preserved'] is True
         and terminal['result']['r4_retirement']['all_original_and_later_known_clients_retired'] is True
         and terminal['result']['representation_controls'] == {
             'actual_target_git_controls_passed': 41, 'actual_representations_replayed': 440,
             'actual_batch_candidates': 2822, 'actual_batch_readonly_commands': 57,
             'source_qualified': False},
         'actual R4 preserves its failed R3 predecessor and exact target checkout controls')
    verify_only = summary['candidates'] == 0
    need(terminal['result']['verify_only'] is verify_only
         and terminal['reconcile_dispatched'] is (not verify_only), 'actual mutation versus verify-only branch')
    need(set(stages) == r19_restore_stage_names(contract), 'whole exact actual R4 stage roster')
    commands = terminal['commands']
    need(type(commands) is list and 1 <= len(commands) <= 4096, 'bounded actual controller command history')
    for command in commands:
        need(type(command['mutation']) is bool and type(command['exit_code']) is int
             and command['exit_code'] == 0 and command['error'] is None
             and command['actual_reaped'] is True and command['original_pidfd_held_until_reaped'] is True
             and command['forced'] is False, 'every actual source child exited normally and was reaped')
    mutations = [row for row in commands if row['mutation']]
    repairs = contract['fresh_full_project_repairs']
    expected_names = [] if verify_only else ['normal-full-project-%02d' % n for n in range(1, len(repairs) + 1)] + ['normal-same651-reconcile']
    expected_argv = [] if verify_only else [row['argv'] for row in repairs] + [contract['reconcile_argv']]
    need([row['name'] for row in mutations] == expected_names
         and [row['argv'] for row in mutations] == expected_argv,
         'all and only the actual fresh full-project repairs and single normal same651 reconcile')
    need(all(row['name'] in {'own-unit', 'actual-git-version', 'previous-unit', 'allocated'}
             for row in commands if not row['mutation']), 'only original bounded supporting read-only commands')
    admission = stages['ADMISSION.json']
    need(admission == terminal['result']['admission']
         and admission['source_locks'] == contract['original_locks']
         and admission['fixed_budget'] == contract['budget']
         and admission['fresh_full651_census'] == terminal['inputs']['fresh_census']
         and admission['candidate_catalog'] == terminal['result']['candidate_catalog'],
         'actual source admission consumes the unchanged locks, budget and new complete census')
    if not verify_only:
        need(stages['CHECKOUT-ATTRIBUTES.json'] == terminal['result']['checkout_attributes'],
             'actual checkout-rule stage is exactly the original terminal field')
        need(stages['RECONCILE-RETURNED.json'] == mutations[-1], 'exact single normal reconcile return')
        need(stages['SOURCE-RESTORATION-INTENT.json']['candidate_catalog'] == admission['candidate_catalog']
             and stages['SOURCE-RESTORATION-INTENT.json']['fresh_full_project_repairs'] == repairs,
             'source mutation intent is the fresh exact catalog and full-project roster')
        for number, (operation, returned) in enumerate(zip(repairs, mutations[:-1]), 1):
            intent = stages['FULL-PROJECT-%02d-INTENT.json' % number]
            need(all(intent[key] == operation[key] for key in ('project', 'missing_required_S', 'argv'))
                 and intent['all_three_original_locks_held'] is True
                 and intent['permitted_attempts'] == 1
                 and stages['FULL-PROJECT-%02d-RETURNED.json' % number] == returned,
                 'each actual whole full-project repair has its exact one-attempt intent and return')
    else:
        need(repairs == [] and stages['VERIFY-ONLY.json'] == {'new_census_missing_union': 0,
             'source_mutations': False, 'reconcile_dispatched': False, 'source_qualified': False},
             'zero missing bodies never authorize a source mutation')
    before, after, comparison = [stages[name] for name in ('PRE-DIAGNOSTIC.json', 'STRICT-AFTER.json', 'COMPARISON.json')]
    tracked = census['totals']['tracked_entries']
    need(before['schema'] == 'p4-restoration-unqualified-preimage-v3'
         and before['project_count'] == census['projects_examined'] == 651
         and before['tracked_entries'] == tracked
         and before['strict_source_qualified'] is False
         and before['all_present_source_bodies_read'] is True
         and before['source_mutations'] is before['production_ready'] is before['runtime_qualified'] is False
         and before['catalog_summary'] == summary
         and before['unresolved_restore_entries'] == summary['candidates'],
         'complete explicitly unqualified fresh preimage and exact new missing union')
    need(after['schema'] == 'pocket4-original-materialized-source-content-bookend-v1'
         and after['project_count'] == 651 and after['all_actual_Git_blob_reads_verified'] is True
         and after['source_mutations'] is False
         and [row['project'] for row in after['projects']] == [row['project'] for row in before['projects']],
         'complete same651 strict post-restoration original body bookend')
    need(comparison['schema'] == 'p4-exact-HS-source-restoration-comparison-v3'
         and comparison['source_entries_compared'] == tracked
         and comparison['exact_catalog_bodies_restored'] == summary['candidates']
         and comparison['restored_H'] == summary['missing_H']
         and comparison['restored_required_S'] == summary['missing_required_S']
         and comparison['known_restored_committed_bytes'] == summary['known_blob_bytes']
         and comparison['original_raw_rows_preserved'] is comparison['full_catalog_checked'] is True
         and comparison['before'] == before['inventory'] and comparison['after'] == after['inventory']
         and comparison['preserved_present'] == before['observed_present_entries']
         and after['materialized_entries'] == before['observed_present_entries'] + summary['candidates']
         and after['materialized_bytes'] == before['observed_present_bytes'] + comparison['restored_raw_bytes']
         and after['sparse_absent_entries'] == before['permitted_sparse_absences']
         and comparison['runtime_qualified'] is comparison['production_ready'] is False,
         'all committed entries compared, every fresh omission restored and every original raw body preserved')
    binding = stages['CENSUS-PREIMAGE-BINDING.json']
    need(binding['original_raw_bytes_and_F9_equal'] is binding['whole_inventory_identity_stable'] is True
         and binding['present_bodies_compared'] == census['totals']['present_tracked']
         and binding['raw_bytes_compared'] == census['totals']['present_raw_bytes']
         and binding['original_gitlinks_compared'] == census['totals']['gitlinks']
         and binding['source_entries_rechecked'] == tracked and binding['source_mutations'] is False,
         'all fresh census raw bodies, F9 and Gitlinks bind the complete new preimage')
    stable = stages['POSTIMAGE-STABILITY.json']
    need(stable['whole_inventory_identity_stable'] is True and stable['source_mutations'] is False
         and stable['source_entries_rechecked'] == tracked
         and stable['present_entries'] == after['materialized_entries'], 'complete strict after-inventory identity recheck')
    old = {key: contract['original_manifest'][key] for key in ('path', 'bytes', 'sha256', 'identity')}
    current = terminal['result']['manifest_after']
    publication = stages['MANIFEST-PUBLICATION.json']
    need(terminal['result']['manifest_before'] == old and publication['before'] == old
         and publication['after'] == current and publication['identical_whole_bytes'] is True
         and publication['reconcile_dispatched'] is (not verify_only)
         and all(old[key] == current[key] for key in ('path', 'bytes', 'sha256')),
         'actual normal publication preserves the exact complete original manifest bytes')
    if verify_only:
        need(current == old and publication['atomic_manifest_identity_changed'] is False,
             'verify-only keeps the complete original manifest identity')
    else:
        need(publication['atomic_manifest_identity_changed'] is True
             and old['identity'][0] == current['identity'][0]
             and old['identity'][2:7] == current['identity'][2:7]
             and old['identity'][1] != current['identity'][1]
             and all(mutations[-1]['started_ns'] <= value <= mutations[-1]['finished_ns']
                     for value in current['identity'][7:]),
             'only the actual normal atomic same-byte manifest publication advances its inode')
    return {'before': old, 'after': r19_ref(current)}


def r19_validate_post_observation(post, contract, terminal_ref, terminal, stages, manifest, census):
    need(post['schema'] == 'p4-source-restoration-r4-independent-post-observation-v1'
         and post['read_only'] is post['read_only_observer'] is True and post['observer_uid'] == 1000
         and post['source_restored'] is True and post['runtime_qualified'] is post['production_ready'] is False
         and post['observed_ns'] > terminal['finished_ns']
         and post['terminal'] == terminal_ref and post['contract'] == terminal['contract']
         and post['controller'] == terminal['inputs']['controller'],
         'actual independent completed R4 source-restoration observation')
    summary = contract['candidate_projection']['summary']
    verify_only = summary['candidates'] == 0
    expected_mutations = 0 if verify_only else len(contract['fresh_full_project_repairs']) + 1
    need(post['source_manifest'] == manifest['after']
         and post['mutation_command_count'] == expected_mutations
         and post['one_normal_reconcile_observed'] is (not verify_only) and post['verify_only'] is verify_only
         and post['full_project_repairs_observed'] == len(contract['fresh_full_project_repairs'])
         and post['exact_catalog_bodies_restored'] == summary['candidates']
         and post['restored_H'] == summary['missing_H']
         and post['restored_required_S'] == summary['missing_required_S']
         and post['source_entries_compared'] == census['totals']['tracked_entries'],
         'independent actual complete census, restoration scope and original body comparison')
    for key, filename in (('pre_diagnostic', 'PRE-DIAGNOSTIC.json'), ('strict_after', 'STRICT-AFTER.json'),
                          ('comparison', 'COMPARISON.json')):
        need(post['stages'][filename] == terminal['result'][key], 'same original actual result stage')
    need(post['inventories'] == [stages['PRE-DIAGNOSTIC.json']['inventory'], stages['STRICT-AFTER.json']['inventory']]
         and post['candidate_catalog'] == terminal['result']['candidate_catalog']['reference']
         and post['fresh_full651_census'] == terminal['inputs']['fresh_census']
         and post['census_preimage_binding'] == post['stages']['CENSUS-PREIMAGE-BINDING.json']
         and post['postimage_stability'] == post['stages']['POSTIMAGE-STABILITY.json']
         and post['checkout_attributes'] == post['stages']['CHECKOUT-ATTRIBUTES.json']
         and post['all_candidate_checkout_rules_verified_before_mutation'] is True,
         'all complete real inventories and current-census bindings independently read')
    comparison = stages['COMPARISON.json']
    need(post['original_identity_changes'] == comparison['original_identity_changes']
         and post['original_identity_change_sha256'] == comparison['original_identity_change_sha256'],
         'normal source inode changes reported exactly without claiming old F9 survived')
    current = post['independent_current_source_identity_observation']
    need(current['whole_inventory_identity_stable'] is True and current['source_mutations'] is False
         and current['source_entries_rechecked'] == census['totals']['tracked_entries']
         and current['present_entries'] == stages['STRICT-AFTER.json']['materialized_entries'],
         'independent after-retirement observation checked all current source identities and absences')
    need(len(post['source_locks']) == 3, 'three independently observed original locks')
    for actual, original in zip(post['source_locks'], contract['original_locks']):
        need(all(actual[key] == original[key] for key in ('path', 'bytes', 'sha256', 'identity', 'body_hex'))
             and actual['kernel_lock_rows'] == [], 'original source locks released with exact unchanged bodies and F9')
    expected_units = [contract['unit']] + contract['predecessor_units'] + contract['r4_predecessor_units']
    need(len(post['retired_units']) == len(expected_units), 'every actual source and predecessor unit observed retired')
    fixed = {'LoadState': 'not-found', 'ActiveState': 'inactive', 'SubState': 'dead',
             'MainPID': '0', 'ControlGroup': '', 'InvocationID': ''}
    for item, unit in zip(post['retired_units'], expected_units):
        paths = ['/sys/fs/cgroup/user.slice/user-1000.slice/user@1000.service/app.slice/' + unit,
                 '/sys/fs/cgroup/system.slice/' + unit]
        need(item['argv'] == ['/usr/bin/systemctl', '--user', 'show', unit,
             '--property=LoadState,ActiveState,SubState,MainPID,ControlGroup,InvocationID']
             and type(item['exit_code']) is int and item['exit_code'] == 0 and item['stderr'] == ''
             and item['properties'] == fixed and item['absent_cgroup_paths'] == paths
             and dict(line.split('=', 1) for line in item['stdout'].splitlines()) == fixed,
             'exact real retired unit and both original cgroup observations')
    need(post['absent_source_stages'] == contract['absent_source_stages']
         + [str(R19_RESTORE_CONTROL / 'actual/UNRESOLVED-RETIREMENT.json')], 'whole exact absent source-stage roster')


def r19_validate_checkout_attributes(stage, batch, summary):
    """Bind the real pre-mutation stage to the exact actual 57-query exercise."""
    need(stage['schema'] == 'p4-r4-actual-before-mutation-checkout-attributes-v1'
         and stage['all_candidates'] == summary['candidates'] == 2822
         and stage['committed_effective_equal_to_frozen'] is True
         and stage['whole_conversion_scope_unchanged'] is True
         and stage['original_global_budget_preserved'] is True
         and stage['candidate_content_transformations'] is stage['custom_filters_executed'] is False
         and stage['source_mutations'] is stage['source_qualified'] is False,
         'complete actual R4 checkout attributes preserve the exact missing-body budget')
    expected = batch['result']['projects']
    need([row['project'] for row in stage['projects']] == [row['project'] for row in expected]
         and len(expected) == len({row['project'] for row in expected}) == 19,
         'all and only the actual nineteen checkout-query projects in original order')
    count = 0
    for actual, frozen in zip(stage['projects'], expected):
        need(actual['candidate_count'] == frozen['candidate_count']
             and actual['attributes'] == frozen['attributes']
             and actual['source_mutations'] is False
             and len(actual['commands']) == len(frozen['commands']) == 3,
             'each whole actual candidate attribute result equals the frozen target exercise')
        count += actual['candidate_count']
        for command, original in zip(actual['commands'], frozen['commands']):
            need(command['exit_code'] == 0 and command['actual_child_reaped'] is True
                 and type(command['pid']) is int and command['pid'] > 1
                 and type(command['pidfd_inode']) is int and command['pidfd_inode'] > 0
                 and all(command[key] == original[key] for key in
                         ('args', 'stdout_bytes', 'stdout_sha256', 'stderr_bytes', 'stderr_sha256')),
                 'exact readonly Git argv, complete output and actual child retirement')
    need(count == stage['all_candidates'], 'the complete checkout-rule stage covers every candidate')


def r19_validate_client_capture(client, stdout_ref, boot):
    """Validate an original API result without substituting a later observation."""
    state = client['actual_status']
    need(client['host'] == 'ai395' and type(client['session_id']) is str
         and client['session_id'].startswith('dpty-')
         and state['state'] == 'exited' and state['boot'] == boot
         and type(state['exit_code']) is type(client['exit_code']) is int
         and state['exit_code'] == client['exit_code'] == 0
         and state['output_complete'] is client['output_complete'] is True
         and state['capture_error'] is client['capture_error'] is None
         and state['bytes_seen'] == state['bytes_stored'] == client['bytes_seen']
             == client['bytes_stored'] == stdout_ref['bytes']
         and all(type(state[key]) is int and state[key] > 1 for key in ('owner_pid', 'pid'))
         and state['owner_pid'] != state['pid']
         and stdout_ref['path'] == '/home/qq/.local/state/hepta-runtime-mac-worker/terminals/'
             + client['session_id'] + '/output.log',
         'actual original client exited successfully with complete exact durable output')
    r19_ref(stdout_ref)
    return {'unit': 'hepta-terminal-' + client['session_id'] + '.service',
            'pids': {state['owner_pid'], state['pid']}}


def r19_validate_external_clients(external, contract, terminal, post, evidence):
    original = external['original_client']
    observer = external['observer_client']
    boot = contract['retirement_gate']['boot_id']
    source = r19_validate_client_capture(original, external['original_client_stdout'], boot)
    observed = r19_validate_client_capture(observer, external['post_observation_stdout'], boot)
    need(original['session_id'] == evidence['actual_execution']['session_id'] == R19_RESTORE_SESSION
         and original['actual_status']['owner_pid'] == R19_RESTORE_CLIENT_OWNER
         and original['actual_status']['pid'] == R19_RESTORE_CLIENT_PID
         and evidence['actual_execution']['controller_pid'] == R19_RESTORE_PID
         and external['invocation_id'] == evidence['actual_execution']['invocation_id'] == R19_RESTORE_INVOCATION
         and post['observer_pid'] == observer['actual_status']['pid']
         and observed['unit'] != source['unit'],
         'exact observed R4 source invocation and actual independent observer child')
    retired = external['observer_retirement']
    need(retired['schema'] == 'p4-source-restoration-r4-observer-retirement-v1'
         and retired['read_only'] is True and retired['errors'] == []
         and terminal['finished_ns'] < post['observed_ns'] < retired['observed_ns']
         <= retired['finished_ns'] <= external['observed_ns'],
         'actual external retirement follows source success and the completed observer')
    targets = {row['unit']: row for row in retired['targets']}
    expected = {R19_RESTORE_UNIT: {R19_RESTORE_PID}, source['unit']: source['pids'],
                observed['unit']: observed['pids']}
    need(len(targets) == len(retired['targets']) == 3 and set(targets) == set(expected),
         'exact controller, original client and original observer retirement scope')
    fixed = {'LoadState': 'not-found', 'ActiveState': 'inactive', 'SubState': 'dead',
             'MainPID': '0', 'ControlGroup': '', 'InvocationID': ''}
    for unit, pids in expected.items():
        target = targets[unit]
        observation = target['unit_observation']
        need(len(target['pids']) == len(pids)
             and {row['pid'] for row in target['pids']} == pids
             and all(row['exists'] is False for row in target['pids'])
             and target['user_cgroup_exists'] is target['system_cgroup_exists'] is False
             and observation['argv'] == ['/usr/bin/systemctl', '--user', 'show', unit,
                 '--property=LoadState,ActiveState,SubState,MainPID,ControlGroup,InvocationID']
             and observation['exit_code'] == 0 and observation['stderr'] == ''
             and observation['properties'] == fixed
             and dict(line.split('=', 1) for line in observation['stdout'].splitlines()) == fixed,
             'actual original PIDs and both exact unit cgroups are retired')
    return expected


def verify_r19_source_restoration():
    global BOOKENDS
    need(R19_ADMISSION_PIN is not None,
         'source-only R19 candidate: actual successful R4 restoration and retirement not frozen')
    until = time.monotonic() + 150
    def guard():
        need(time.monotonic() < until, 'bounded complete R19 source-restoration evidence admission')
    admission_pin = digest(R19_ADMISSION_PATH)
    need((admission_pin['bytes'], admission_pin['sha256']) == R19_ADMISSION_PIN, 'whole fixed R19 restoration proof')
    evidence = r19_read_json(admission_pin)
    need(evidence['schema'] == 'p4-vendor-r19-restoration-admission-v4'
         and evidence['dispatch_inputs_frozen'] is True, 'actual final successor proof, never a pending slot')
    inputs = evidence['inputs']
    need(set(inputs) == {'r18_worker', 'r18_supervisor', 'r18_bundle', 'r18_terminal', 'r18_build',
         'r18_recovery', 'r18_admission', 'restore_controller', 'restore_contract', 'restore_terminal',
         'external_retirement', 'bookends_controls'}, 'exact finite R19 source-evidence set')
    for reference in inputs.values():
        guard(); r19_actual_ref(reference)
    fixed_sources = {
        'r18_worker': (ROOT / 'control/vendor_build_r18_2331.py', '358781b648b6019e86b5c6baa1f521197c8b5c86bc80db7f919e5fbe732b769b'),
        'r18_supervisor': (ROOT / 'control/vendor_outer_r18_2331.py', 'c3d703a9b4447e0b9a373ed127238b941b3e9abd6b50967d1afdc0a17ca2b2ab'),
        'r18_bundle': (ROOT / 'control/vendor_r18_2331_bundle.json', '376a4e846b10b134776c6fb4248300375ae84794055cacd2ed9f8549f014eab1'),
        'restore_controller': (R19_RESTORE_CONTROL / 'source.py', R19_RESTORE_CONTROLLER_SHA),
        'restore_contract': (R19_RESTORE_CONTROL / 'inputs/CONTRACT.json', R19_RESTORE_CONTRACT_SHA),
    }
    for name, (path, sha) in fixed_sources.items():
        need(inputs[name]['path'] == str(path) and inputs[name]['sha256'] == sha, 'exact retained reviewed source: ' + name)
    need(inputs['restore_terminal']['path'] == str(R19_RESTORE_CONTROL / 'actual/TERMINAL.json'),
         'exact actual R4 source terminal')
    values = {name: r19_read_json(reference) for name, reference in inputs.items()
              if name not in ('r18_worker', 'r18_supervisor', 'restore_controller')}
    contract, terminal = values['restore_contract'], values['restore_terminal']
    need(terminal['contract'] == r19_ref(inputs['restore_contract'])
         and terminal['inputs']['controller'] == r19_ref(inputs['restore_controller']), 'actual R4 controller and contract binding')
    for reference in terminal['inputs'].values():
        guard(); r19_actual_ref(reference)
    controller = r19_load_module('p4_r19_reviewed_R4_pure_predicates', inputs['restore_controller'])
    BOOKENDS = r19_load_module('p4_r19_exact_strict_bookends', terminal['inputs']['representation_bookends'])
    diagnostic = r19_load_module('p4_r19_exact_R4_diagnostic', terminal['inputs']['diagnostic_v3'])
    census_admission = r19_load_module('p4_r19_exact_R4_census', terminal['inputs']['census_admission'])
    census = r19_read_json(terminal['inputs']['fresh_census'])
    r2_contract = r19_read_json(terminal['inputs']['r2_contract'])
    controller.validate_terminal_proofs(values['r18_terminal'], values['r18_build'], values['r18_recovery'],
        r19_read_json(terminal['inputs']['retirement']), contract)
    controller.validate_restore_predecessor(r19_read_json(terminal['inputs']['prior_restore_terminal']),
        r19_read_json(terminal['inputs']['prior_restore_contract']), r2_contract, terminal['inputs'])
    controller.validate_r2_failure(r19_read_json(terminal['inputs']['r2_terminal']), r2_contract, contract, terminal['inputs'])
    controller.validate_retirement_gate(r19_read_json(terminal['inputs']['fresh_retirement']), contract, census)
    representation = r19_load_module('p4_r19_exact_R4_representation_admission',
                                      terminal['inputs']['representation_admission'])
    r3_failed = r19_read_json(terminal['inputs']['r3_terminal'])
    r3_contract = r19_read_json(terminal['inputs']['r3_contract'])
    r4_values = {name: r19_read_json(terminal['inputs'][name]) for name in (
        'r3_failure_retirement', 'r4_retirement', 'r3_clients', 'retirement_collector_client',
        'additional_validation_clients', 'representation_helper_controls',
        'representation_helper_execution', 'batch_attributes_controls', 'missing_checkout_attributes')}
    need(representation.validate_r3_failure(r3_failed, r3_contract, contract, terminal['inputs'])
         == terminal['result']['r3_restore'], 'independently revalidate the actual failed R3 history')
    need(representation.validate_clients_and_retirement(r3_failed,
         r4_values['r3_failure_retirement'], r4_values['r4_retirement'], r4_values['r3_clients'],
         r4_values['retirement_collector_client'], r4_values['additional_validation_clients'],
         contract, terminal['inputs']) == terminal['result']['r4_retirement'],
         'all actual later historical clients and checkout controls remain bound')
    import types
    checked = types.SimpleNamespace(values=r4_values, input_refs=terminal['inputs'], bookends=BOOKENDS,
        large_input_refs={key: terminal['inputs']['streamed_' + key] for key in contract['streamed_inputs']},
        catalog={'summary': contract['candidate_projection']['summary']},
        conversion_scope=r4_values['r4_retirement']['conversion_scope'])
    need(representation.validate_actual_controls(checked) == terminal['result']['representation_controls'],
         'exact actual target 41 controls, 440 representations and 57 candidate queries')
    representation.validate_missing_packet(checked, controller.read_ref)
    representation.assert_conversion_scope(checked)
    own = [row for row in terminal['commands'] if row['name'] == 'own-unit']
    need(len(own) == 1 and own[0]['argv'] == ['/usr/bin/systemctl', '--user', 'show', R19_RESTORE_UNIT,
         '--property=LoadState,ActiveState,SubState,MainPID,ControlGroup,InvocationID,Restart,KillMode'],
         'exact original R4 own-unit observation')
    properties = dict(line.split('=', 1) for line in controller.read_ref(own[0]['stdout'])[0].decode().splitlines())
    need(properties == {'LoadState': 'loaded', 'ActiveState': 'active', 'SubState': 'running',
         'MainPID': str(R19_RESTORE_PID),
         'ControlGroup': '/user.slice/user-1000.slice/user@1000.service/app.slice/' + R19_RESTORE_UNIT,
         'InvocationID': R19_RESTORE_INVOCATION, 'Restart': 'no', 'KillMode': 'control-group'},
         'actual source controller process and invocation match original start evidence')
    for name, key in (('r18_terminal', 'terminal'), ('r18_build', 'build'), ('r18_recovery', 'recovery')):
        need(r19_ref(inputs[name]) == terminal['inputs'][key], 'exact original R18 failure retained by R4')
    need(r19_ref(values['r18_terminal']['worker']) == r19_ref(inputs['r18_worker'])
         and r19_ref(values['r18_terminal']['bundle']) == r19_ref(inputs['r18_bundle']),
         'original R18 frozen worker and bundle remain unchanged')
    external = values['external_retirement']
    need(external['schema'] == 'p4-source-restoration-r4-external-retirement-v1'
         and external['unit'] == R19_RESTORE_UNIT and external['read_only'] is True
         and external['source_restored'] is True
         and external['production_ready'] is external['runtime_qualified'] is False
         and external['invocation_id'] == evidence['actual_execution']['invocation_id'],
         'actual independent complete R4 retirement and exact recorded invocation')
    post = external['post_observation']
    need(r19_read_json(external['post_observation_stdout']) == post, 'whole original independent observer stdout')
    external_targets = r19_validate_external_clients(external, contract, terminal, post, evidence)
    r19_actual_ref(external['original_client_stdout'])
    need(set(post['stages']) == r19_restore_stage_names(contract), 'every actual R4 source stage retained')
    stages = {}
    for name, reference in post['stages'].items():
        need(reference['path'] == str(R19_RESTORE_CONTROL / 'actual' / name), 'exact original source-stage path')
        stages[name] = r19_read_json(reference)
    manifest = r19_validate_completion(contract, terminal, stages, census)
    r19_validate_checkout_attributes(stages['CHECKOUT-ATTRIBUTES.json'],
                                    r4_values['batch_attributes_controls'], contract['candidate_projection']['summary'])
    transitions = r19_validate_lock_transitions(values['r18_admission'], values['r18_recovery'], contract)
    r19_validate_post_observation(post, contract, r19_ref(inputs['restore_terminal']), terminal, stages, manifest, census)
    for reference in post['inventories'] + [post['candidate_catalog']]:
        guard(); r19_actual_ref(reference)
    catalog = terminal['result']['candidate_catalog']
    need(catalog['summary'] == contract['candidate_projection']['summary']
         and all(catalog['reference'][key] == contract['candidate_projection'][key] for key in ('bytes', 'sha256')),
         'the real R4 candidate inventory is the independently frozen fresh projection')
    comparison = diagnostic.compare_restoration(BOOKENDS, stages['PRE-DIAGNOSTIC.json'],
        stages['STRICT-AFTER.json'], catalog, until, guard)
    need(comparison == stages['COMPARISON.json'], 'full immutable before/after inventories independently compare again')
    gitlinks = list(census_admission.records(BOOKENDS, diagnostic,
        terminal['inputs']['streamed_fresh_gitlinks'], until, guard))
    census_binding = census_admission.compare_census_pre(BOOKENDS, diagnostic, census,
        terminal['inputs']['streamed_fresh_present'], gitlinks, stages['PRE-DIAGNOSTIC.json'], until, guard)
    need(all(stages['CENSUS-PREIMAGE-BINDING.json'][key] == value for key, value in census_binding.items()),
         'complete raw census body, F9 and Gitlink binding independently compares again')
    for document in (terminal, r3_failed, values['r18_build'], values['r18_recovery']):
        for command in document['commands']:
            for channel in ('stdout', 'stderr'):
                guard(); r19_actual_ref(command[channel])
    for path in post['absent_source_stages']:
        need(not os.path.lexists(path), 'historical source generation has no unresolved stage')
    need(not os.path.lexists(CMAKE_PROJECT), 'same651 restoration creates no preexisting CMake provider')
    r19_actual_ref(manifest['after'])
    for transition in transitions.values():
        r19_actual_ref(transition['after'])
        need(Path(transition['after']['path']).read_bytes().hex() == transition['after_body_hex'],
             'actual unchanged R18 source-lock PID body through R4')
    controls = values['bookends_controls']
    need(inputs['bookends_controls']['sha256'] == R19_CONTROLS_SHA
         and controls['schema'] == 'pocket4-implicit-text-crlf-real-git-controls-v1'
         and controls['passed'] is True and controls['tests_run'] == 29
         and len(controls['cases']) == 29 and all(case['passed'] is True for case in controls['cases'])
         and controls['baseline_sha256'] == R18_BOOKEND_PIN[1]
         and controls['successor_sha256'] == R19_LEGACY_HELPER_SHA
         and controls['remote_commands'] == controls['operational_source_mutations'] == controls['Android_actions'] == 0
         and controls['source_restore_executed'] is False and controls['historical_19_controls_rerun'] is False
         and controls['temporary_repositories_removed'] is True,
         'previous 29 real CRLF controls remain distinct from new 41-control target evidence')
    need(PINS[BOOKEND_PATH] == (29338, R19_HELPER_SHA)
         and terminal['inputs']['representation_bookends']['sha256'] == R19_HELPER_SHA,
         'exact new strict text-auto helper for this generation')
    check_pin(BOOKEND_PATH); check_pin(R19_PREVIOUS_HELPER_PATH)
    fixed = {'LoadState': 'not-found', 'ActiveState': 'inactive', 'SubState': 'dead',
             'MainPID': '0', 'ControlGroup': '', 'InvocationID': ''}
    observed = []
    need(evidence['predecessor_units'] == [R19_RESTORE_UNIT] + contract['predecessor_units']
         + contract['r4_predecessor_units'],
         'whole exact R4 and original predecessor unit roster')
    for pid in set(contract['retirement_gate']['absent_pids'] + contract['r4_absent_pids']) | set().union(*external_targets.values()):
        need(not os.path.lexists('/proc/' + str(pid)), 'known source, cleanup or census process remains')
    actual_units = evidence['predecessor_units'] + [unit for unit in external_targets
                   if unit not in evidence['predecessor_units']]
    need(len(actual_units) == len(set(actual_units)) == 27,
         'all twenty-five source predecessors and two actual external client units')
    for unit in actual_units:
        guard()
        result = status_run(['/usr/bin/systemctl', '--user', 'show', unit,
            '--property=LoadState,ActiveState,SubState,MainPID,ControlGroup,InvocationID'],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15, check=False)
        lines = result.stdout.decode('utf-8', 'strict').splitlines()
        need(result.returncode == 0 and result.stderr == b'' and len(lines) == 6
             and dict(line.split('=', 1) for line in lines) == fixed, 'fresh exact actual predecessor unit retirement')
        for parent in ('/sys/fs/cgroup/user.slice/user-1000.slice/user@1000.service/app.slice', '/sys/fs/cgroup/system.slice'):
            need(not os.path.lexists(Path(parent) / unit), 'fresh actual predecessor cgroup absence')
        observed.append({'unit': unit, 'fields': fixed, 'both_cgroup_paths_absent': True})
    for reference in inputs.values():
        guard(); r19_actual_ref(reference)
    representation.assert_conversion_scope(checked)
    r19_actual_ref(admission_pin)
    return {'manifest': manifest, 'locks': transitions}, {
        'admission': admission_pin, 'restore_terminal': r19_ref(inputs['restore_terminal']),
        'external_retirement': r19_ref(inputs['external_retirement']), 'actual_units': observed,
        'complete_fresh_same651_restoration_consumed': True,
        'all_2822_actual_checkout_attributes_and_target_controls_consumed': True,
        'actual_original_and_observer_complete_capture_and_retirement_verified': True,
        'exact_catalog_bodies_restored': comparison['exact_catalog_bodies_restored'],
        'source_entries_compared': comparison['source_entries_compared'],
        'fresh_census_raw_and_gitlink_comparison_replayed': census_binding,
        'historical_failures_replaced': False, 'historical_source_inode_pins_rewritten': False,
        'runtime_qualified': False, 'production_ready': False}


_verify_serialized_retirement_before_r19 = verify_serialized_retirement


def verify_serialized_retirement():
    global R19_BOUND_RESTORATION
    need(R19_BOUND_RESTORATION is None, 'single non-reentrant R19 restoration admission')
    binding, receipt = verify_r19_source_restoration()
    R19_BOUND_RESTORATION = binding
    try:
        result = _verify_serialized_retirement_before_r19()
        r19_live_manifest_pin(binding['manifest']['before'])
        for transition in binding['locks'].values():
            r19_live_lock_pin(transition['before'], transition['before_body_hex'])
        result['actual_r18_failure_then_complete_same651_restoration'] = receipt
        return result
    finally:
        R19_BOUND_RESTORATION = None



def write_source_stage(name, payload):
    need(name in SOURCE_STAGE_NAMES and type(payload) is dict, 'fixed source-stage record')
    owner = verify_outer()
    value = {'schema': 'p4-vendor-r21-source-stage-v1', 'stage': name,
             'generation': owner['generation'], 'worker_sha256': digest(SELF)['sha256'],
             'payload': payload}
    body = (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()
    need(len(body) <= 1024 * 1024, 'bounded source-stage record')
    directory = os.open(CONTROL, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    temporary_name = name + '.stage-new'
    final_name = name + '.json'
    fd = None
    try:
        identity = f9(os.fstat(directory))
        need(identity[:2] == f9(CONTROL.lstat())[:2], 'original control directory')
        fd = os.open(temporary_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                     | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=directory)
        view = memoryview(body)
        while view:
            done = os.write(fd, view)
            need(done > 0, 'complete source-stage write')
            view = view[done:]
        os.fsync(fd)
        libc = ctypes.CDLL(None, use_errno=True)
        rename = libc.renameat2
        rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        rename.restype = ctypes.c_int
        result = rename(directory, temporary_name.encode(), directory, final_name.encode(), 1)
        need(result == 0, 'atomic create-only source-stage publication errno=' + str(ctypes.get_errno()))
        os.fsync(directory)
        need(f9(os.fstat(directory))[:2] == identity[:2] == f9(CONTROL.lstat())[:2],
             'original control directory retained')
    finally:
        if fd is not None:
            os.close(fd)
        os.close(directory)
    pin = digest(CONTROL / final_name)
    OBS.setdefault('source_stages', {})[name] = pin
    save()
    return pin

def read_source_stage(name):
    need(name in SOURCE_STAGE_NAMES, 'fixed source-stage read')
    path = CONTROL / (name + '.json')
    if not os.path.lexists(path):
        return None
    value, pin = read_source_json(path)
    owner = verify_outer()
    need(type(value) is dict and set(value) == {'schema', 'stage', 'generation', 'worker_sha256', 'payload'}
         and value['schema'] == 'p4-vendor-r21-source-stage-v1' and value['stage'] == name
         and value['generation'] == owner['generation']
         and value['worker_sha256'] == digest(SELF)['sha256'] and type(value['payload']) is dict,
         'same original source-stage owner and worker')
    return value['payload'], pin

# R20 successor: immutable R19 history, a fresh complete current runtime cohort,
# and exactly six original HealthFitness lint bodies. Appended to the unchanged
# R19 definitions. It never calls their old-651 live admission on the new baseline.
R20_CONTRACT_PATH = ROOT / 'control/vendor-build-20261120-9907-r21/inputs/CONTRACT.json'
R20_CONTRACT_PIN = (83652, 'f88235f91532045e2037a42ce2a44623dc549075e93e041fb955c945d4876d3d')  # frozen only after actual current CI/host custody/plan results
R20_HISTORICAL_PINS = dict(PINS)
R20 = None
ADMISSION20 = None
TRANSITION20 = None
PARTIAL20 = None
R20_ADMISSION_DEADLINE = None


def r20_ref(value, *, full=True):
    if full:
        return ADMISSION20.reference(value)
    need(type(value) is dict and type(value['bytes']) is int and value['bytes'] >= 0
         and type(value['sha256']) is str and len(value['sha256']) == 64
         and Path(value['path']).is_absolute(), 'fixed whole R20 input reference')
    return {k: value[k] for k in ('path', 'bytes', 'sha256')}


def r20_guard_admission():
    if R20_ADMISSION_DEADLINE is not None:
        need(time.monotonic() < R20_ADMISSION_DEADLINE, 'original bounded R20 evidence admission')


def r20_check(value, *, full=True):
    r20_guard_admission()
    expected = r20_ref(value, full=full)
    actual = digest(Path(expected['path']))
    need(all(actual[k] == v for k, v in expected.items()), 'exact R20 input differs: ' + expected['path'])
    r20_guard_admission()
    return actual


def r20_json(value, *, full=True):
    actual = r20_check(value, full=full)
    need(actual['bytes'] <= 16 * 1024 * 1024, 'bounded complete R20 JSON')
    body = Path(actual['path']).read_bytes()
    need(hashlib.sha256(body).hexdigest() == actual['sha256']
         and digest(Path(actual['path'])) == actual, 'R20 JSON full read bookends')
    return BOOKENDS.strict_json(body) if BOOKENDS is not None else json.loads(body)


def r20_module(name, reference):
    import types
    actual = r20_check(reference, full=False)
    need(actual['bytes'] <= 1024 * 1024, 'bounded R20 reviewed module')
    body = Path(actual['path']).read_bytes()
    need(hashlib.sha256(body).hexdigest() == actual['sha256']
         and digest(Path(actual['path'])) == actual, 'held reviewed module body')
    module = types.ModuleType(name); module.__file__ = actual['path']
    exec(compile(body, actual['path'], 'exec'), module.__dict__)
    return module


def r20_bootstrap():
    global R20, ADMISSION20, TRANSITION20, PARTIAL20
    global REPO, CONTROL, OUT, TMP, SELF, UNIT, RECOVERY_UNIT, TREE
    global CANONICAL_SOURCE, CANONICAL_ROWS, CANONICAL_FREEZE, CANONICAL_FILES, CANONICAL_BYTES
    global RELEASE, SOURCE_TOOL, UPDATE_TOOL, LOCK, RECOVERY_LOCK, BOOKEND_PATH
    need(type(R20_CONTRACT_PIN[0]) is int and R20_CONTRACT_PIN[0] > 0
         and type(R20_CONTRACT_PIN[1]) is str and len(R20_CONTRACT_PIN[1]) == 64,
         'R20 source-only template: actual current release and plans are not frozen')
    got = digest(R20_CONTRACT_PATH)
    need((got['bytes'], got['sha256']) == R20_CONTRACT_PIN, 'frozen R20 operational contract')
    R20 = r20_json(got, full=False)
    need(R20['schema'] == 'p4-vendor-r21-operational-input-contract-v1'
         and R20['operational_inputs_frozen'] is True
         and R20['runtime_qualified'] is False and R20['production_ready'] is False,
         'actual frozen current-generation input qualification only')
    ADMISSION20 = r20_module('p4_r20_admission', R20['support']['admission'])
    TRANSITION20 = r20_module('p4_r20_lint_transition', R20['support']['transition'])
    PARTIAL20 = r20_module('p4_r20_partial_diagnostic', R20['support']['partial'])
    current = R20['current_source']
    need({k: current[k] for k in ('tree', 'files', 'bytes')} == ADMISSION20.CURRENT,
         'exact complete reviewed current source cohort')
    REPO = ROOT / 'producer-build-r21-9907'
    CONTROL = ROOT / 'control/vendor-build-20261120-9907-r21/actual'
    OUT = ROOT / 'out-build-r21-9907'; TMP = ROOT / 'tmp-build-r21-9907'
    SELF = CONTROL.parent / 'source.py'
    UNIT = 'p4-cp3a-vendor-20261120-9907-r21'; RECOVERY_UNIT = UNIT + '-recovery'
    TREE = current['tree']; CANONICAL_FILES = current['files']; CANONICAL_BYTES = current['bytes']
    CANONICAL_SOURCE = Path(current['path']); CANONICAL_ROWS = Path(current['rows']['path'])
    CANONICAL_FREEZE = Path(current['freeze']['path'])
    release_refs = R20['current_binaries']
    need(tuple(sorted(release_refs)) == ADMISSION20.BINARIES, 'nineteen exact deployed normal binaries')
    RELEASE = Path(release_refs['droidloom-source']['path']).parent
    SOURCE_TOOL = RELEASE / 'droidloom-source'; UPDATE_TOOL = RELEASE / 'droidloom-update'
    LOCK = REPO / 'android/manifest/production-full-lint-source-lock.json'
    RECOVERY_LOCK = Path(R20['profiles']['new']['lock']['path'])
    BOOKEND_PATH = Path(R20['support']['bookends']['path'])
    need((R20['support']['bookends']['bytes'], R20['support']['bookends']['sha256'])
         == (29338, 'bab5c377bf642d4aaa7b50a416319cebad31537022e5179a77e6e8d63827fa88'),
         'unchanged strict original representation helper')
    # Every original PINS member is still retained at its original path. New
    # release/plan refs are added, never assigned to an old historical path.
    additions = [got, *R20['support'].values(), *release_refs.values(), current['rows'],
                 current['freeze'], R20['release_ci'], R20['plan_evidence'],
                 *[x[k] for x in R20['profiles'].values() for k in ('lock', 'plan')]]
    for item in additions:
        path = Path(item['path']); pin = (item['bytes'], item['sha256'])
        need(path not in PINS or PINS[path] == pin, 'cannot replace any historical input pin')
        PINS[path] = pin
    PINS[LOCK] = (400677, TRANSITION20.NEW_LOCK_SHA)
    OBS.update(schema='p4-cp3a-normal-vendor-build-r21-v1', source_tree=TREE,
               actual_updater_release_source_tree=TREE,
               updater_release_and_full_canonical_source_tree_identical=True,
               historical_R19_source_tree='fa0382574f4fc18f59b2b5dd67a30939167d8c3a')
    SOURCE_STAGE_NAMES.update(('source-resume-intent', 'source-resume-returned'))


def r20_validate_client(client, stdout, expected_exit_code=0):
    status = client['actual_status']; pin = r20_check(stdout)
    need(status['state'] == 'exited' and type(status['exit_code']) is int
         and status['exit_code'] == expected_exit_code
         and status['output_complete'] is True and status['capture_error'] is None
         and status['bytes_seen'] == status['bytes_stored'] == pin['bytes'],
         'actual complete preparation client and original capture')
    return pin


def r20_live_retired(unit, pids=(), scope='user'):
    need(type(unit) is str and 0 < len(unit) < 256 and '/' not in unit and '\x00' not in unit
         and unit.endswith(('.service', '.scope')) and scope in ('user', 'system'),
         'exact observed original unit and service scope')
    r20_guard_admission()
    if R20_ADMISSION_DEADLINE is not None:
        need(time.monotonic() + 15 < R20_ADMISSION_DEADLINE,
             'do not start a status child beyond the original evidence deadline')
    argv = ['/usr/bin/systemctl'] + (['--user'] if scope == 'user' else [])
    argv += ['show', unit, '--property=LoadState,ActiveState,SubState,MainPID,ControlGroup']
    result = status_run(argv,
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=15, check=False)
    # Capture the actual bounded bytes before decoding or judging retirement.
    OBS.setdefault('live_retirement_observations', []).append({
        'unit': unit, 'scope': scope, 'argv': argv, 'returncode': result.returncode,
        'stdout_hex': result.stdout.hex(), 'stderr_hex': result.stderr.hex(),
        'stdout_bytes': len(result.stdout), 'stderr_bytes': len(result.stderr)})
    fields = r21_retired_fields(unit, result.stdout, result.stderr, result.returncode)
    roots = [Path('/sys/fs/cgroup/user.slice/user-1000.slice/user@1000.service/app.slice'),
             Path('/sys/fs/cgroup/system.slice')]
    need(all(not os.path.lexists(p / unit) for p in roots), 'both known original cgroup paths absent')
    for pid in pids:
        need(type(pid) is int and pid > 1 and not os.path.lexists('/proc/' + str(pid)),
             'fixed previously retired actor PID is absent; no identity substitution')
    r20_guard_admission()
    return {'unit': unit, 'scope': scope, 'fields': fields, 'both_cgroup_paths_absent': True,
            'original_pids_absent': list(pids)}


# R21 only adds the actual R20 prebuild failure and type-correct retirement wire.
# All current source, release, recovery, lock and resource contracts remain R20's.
R21_SCOPES = (
    'p4-cmake652-validation-20261118-appagent-r1.scope',
    'p4-cmake652-validation-20261118-appagent-r2.scope',
    'p4-cmake652-finalize-20261118-appagent-r3.scope',
)
R21_PREDECESSOR_UNIT = 'p4-cp3a-vendor-supervisor-20261120-9907-r20.service'
R21_ORIGINAL_SESSION = 'dpty-2906d42bdba8abfc78eebb6aa3abf1cf3f2420fe7a4939ddab62b99b147555b5'
R21_OBSERVER_SESSION = 'dpty-433a4b7bf1b84328abf4925c89e8a1a57c6d8e447f480523fe82fa00f9f1448d'
R21_DIRECTORY_SESSION = 'dpty-6eb2228900859cc420b575cb9988e0cfa6620621ef7fdeb584726060a8856357'
R21_HISTORY = {
    'contract': (59441, '0d5b2a0e926d42ee3eabf5f960a70f5bf24acc0da2c2673cd72afe7344b84b10'),
    'worker': (264416, '7476bd460cf91cb30f40c45e5c1902afeae1191f32f56578bc963b460762cd1a'),
    'bundle': (3259, '417c25c35dd495cbfb20f3651848704b0e76ebd5014225da54a00193da37c942'),
    'outer': (35232, 'b5235de573194a674a1c0bf94cc19f834fcf7cf04c2396f9915162c9f18e8bfa'),
    'terminal': (20313, '0fdeee3c87b89274b48f8eecd9f84bfb18ed4a0d57dd941e376eec4a9875f425'),
}


def r21_retired_fields(unit, stdout, stderr, returncode):
    """Scopes do not have MainPID. Services still require the original five fields."""
    lines = stdout.decode('utf-8', 'strict').splitlines()
    pairs = [line.split('=', 1) for line in lines]
    need(all(len(v) == 2 for v in pairs) and len(pairs) == len(dict(pairs)), 'unique exact unit status')
    fields = dict(pairs)
    expected = {'LoadState': 'not-found', 'ActiveState': 'inactive',
                'SubState': 'dead', 'ControlGroup': ''}
    if unit.endswith('.service'):
        expected['MainPID'] = '0'
    else:
        need(unit.endswith('.scope'), 'only exact service or scope retirement wire')
    need(type(returncode) is int and returncode == 0 and stderr == b'' and fields == expected,
         'actual known prior unit remains retired: ' + unit)
    return fields


def r21_validate_prebuild_failure():
    """Recheck the frozen failed predecessor; it grants no build or recovery credit."""
    failure = R20['R20_prebuild_failure']
    refs = failure['files']
    need(set(refs) == set(R21_HISTORY), 'complete original R20 deployed and terminal references')
    for key, pin in R21_HISTORY.items():
        need((refs[key]['bytes'], refs[key]['sha256']) == pin, 'original R20 history pin: ' + key)
        r20_check(refs[key])
    old = r20_json(refs['contract'])
    bundle = r20_json(refs['bundle'])
    terminal = r20_json(refs['terminal'])
    need(old['schema'] == 'p4-vendor-r20-operational-input-contract-v1'
         and old['operational_inputs_frozen'] is True,
         'actual qualified R20 input contract remains historical')
    changed = {'schema', 'preparation_clients', 'live_retirement_targets'}
    need(set(R20) == set(old) | {'R20_prebuild_failure'}
         and all(R20[k] == v for k, v in old.items() if k not in changed),
         'R21 retains every current release, source, support, profile and budget input')
    need(bundle['schema'] == 'pocket4-vendor-r20-launch-bundle-v1'
         and bundle['dispatch_inputs_frozen'] is True
         and all(bundle['operational_contract'][k] == refs['contract'][k] for k in ('path', 'bytes', 'sha256'))
         and all(bundle['worker'][k] == refs['worker'][k] for k in ('path', 'bytes', 'sha256'))
         and ADMISSION20.reference(terminal['worker']) == ADMISSION20.reference(refs['worker'])
         and ADMISSION20.reference(terminal['bundle']) == ADMISSION20.reference(refs['bundle']),
         'actual failed original outer loaded the exact original bundle and worker')
    need(terminal['schema'] == 'pocket4-vendor-r20-supervisor-terminal-v1'
         and terminal['phases'] == [] and terminal['children'] == []
         and all(terminal[k] is False for k in ('build_attempted', 'normal_recovery_attempted',
             'normal_recovery_verified', 'passed', 'installed', 'runtime_qualified', 'production_ready',
             'fixed_deadline_exceeded', 'serial_held_through_all_source_operations'))
         and all(terminal[k] is True for k in ('serial_lock_acquired', 'all_owned_units_retired',
             'all_created_children_reaped'))
         and terminal['final_retirement_errors'] == []
         and len(terminal['errors']) == 1 and terminal['errors'][0]['stage'] == 'outer'
         and terminal['errors'][0]['error'] == repr(RuntimeError(
             'actual known prior unit remains retired: ' + R21_SCOPES[0])),
         'actual R20 failed only at prebuild scope retirement; no writer or recovery ran')
    children = terminal['original_worker_status_children']
    need(len(children) == 35 and len({r['pid'] for r in children}) == 35,
         'all thirty-five original status children retained')
    for row in children:
        ADMISSION20.command_reaped(row)
        need(type(row['pid']) is int and row['pid'] > 1
             and terminal['started_ns'] <= row['started_ns'] <= row['finished_ns'] <= terminal['finished_ns'],
             'actual original child identity and terminal time bounds')
    need(children[-1]['argv'] == ['/usr/bin/systemctl', '--user', 'show', R21_SCOPES[0],
        '--property=LoadState,ActiveState,SubState,MainPID,ControlGroup'], 'exact last failing scope query')
    original, observer = failure['original_client'], failure['observation_client']
    directory = failure['directory_client']
    for client, session, owner, pid, code in ((original, R21_ORIGINAL_SESSION, 3809990, 3809991, 1),
            (observer, R21_OBSERVER_SESSION, 3812404, 3812405, 0),
            (directory, R21_DIRECTORY_SESSION, 3828998, 3828999, 0)):
        need(client['host'] == 'ai395' and client['scope'] == 'user' and client['session_id'] == session
             and client['unit'] == 'hepta-terminal-' + session + '.service'
             and client['actual_status']['owner_pid'] == owner and client['actual_status']['pid'] == pid,
             'exact original API client identity')
        r20_validate_client(client, client['stdout'], code)
    launch = failure['observation_launch']
    need(launch['host'] == 'ai395' and launch['executable'] == '/usr/bin/python3'
         and launch['cwd'] == '/home/qq/work'
         and launch['idempotency_key'] == 'p4-r20-prebuild-failure-observe-20261120-9907-r1'
         and len(launch['args']) == 4 and launch['args'][:3] == ['-I', '-B', '-c']
         and len(launch['args'][3].encode()) == 10158
         and hashlib.sha256(launch['args'][3].encode()).hexdigest()
             == 'c296179f64c2ab1027c06c0f4e5f7b4a8102fdeb23c431d99226c43488dc0747',
         'actual one-shot ordinary read-only collector input retained verbatim')
    directory_launch = failure['directory_launch']
    need(directory_launch['host'] == 'ai395' and directory_launch['executable'] == '/usr/bin/python3'
         and directory_launch['cwd'] == '/home/qq/work'
         and directory_launch['idempotency_key'] == 'p4-r21-create-only-directory-20261120-9907-r1'
         and len(directory_launch['args']) == 4 and directory_launch['args'][:3] == ['-I', '-B', '-c']
         and len(directory_launch['args'][3].encode()) == 2923
         and hashlib.sha256(directory_launch['args'][3].encode()).hexdigest()
             == 'e8ad653f4949416ba3333868d8313a1a58f31785aae5e423d662d5ac5621b838'
         and (directory['stdout']['bytes'], directory['stdout']['sha256']) ==
             (899, '85d6721ace7db2acfc5f57c2c351ff9ef82dcd4a381eb04aa16220e6985050d5'),
         'only the actual fixed ordinary R21 directory preparation input and original output')
    prepared = r20_json(directory['stdout'])
    need(prepared['schema'] == 'p4-r21-create-only-support-directory-v1'
         and prepared['created'] is True and prepared['uid'] == 1000 and prepared['pid'] == 3828999
         and prepared['generation'] == str(R20_CONTRACT_PATH.parent.parent)
         and all(prepared[k] is False for k in ('source_changed', 'source_locks_acquired', 'worker_or_service_started'))
         and prepared['generation_f9'][2:5] == prepared['inputs_f9'][2:5] == [16832, 1000, 1000]
         and prepared['original_control_before'][:5] == prepared['original_control_after'][:5]
             == [66306, 72405101, 16832, 1000, 1000],
         'actual create-only generation and inputs, no source/lock/service actions')
    observation = r20_json(observer['stdout'])
    need(observation['schema'] == 'p4-r20-prebuild-failure-independent-observation-v1'
         and observation['host'] == 'ai395' and observation['observer_pid'] == observer['actual_status']['pid']
         and observation['read_only'] is True and observation['passed'] is True and observation['errors'] == []
         and all(observation[k] is False for k in ('source_locks_acquired', 'runtime_qualified', 'production_ready'))
         and all(type(observation[k]) is int and observation[k] == 0
                 for k in ('source_writes', 'builds_started', 'Android_starts'))
         and observation['known_source_lock_holders'] == []
         and ADMISSION20.reference(observation['terminal']) == ADMISSION20.reference(refs['terminal'])
         and ADMISSION20.reference(observation['original_client_stdout']) == ADMISSION20.reference(original['stdout'])
         and terminal['finished_ns'] < observation['started_ns'] <= observation['finished_ns'],
         'complete independent post-failure read-only observation, without runtime credit')
    for suffix in ('before', 'after'):
        need(observation['source_manifest_' + suffix] == ADMISSION20.MANIFEST
             and observation['source_locks_' + suffix] == ADMISSION20.LOCKS,
             'original old652 publication and all three lock bodies/F9 stayed unchanged')
    pids = sorted([3809990, 3809991, *[r['pid'] for r in children]])
    need(observation['known_pids'] == [{'pid': pid, 'exists': False} for pid in pids],
         'all original R20 client and child PIDs independently absent')
    units = [*R21_SCOPES, R21_PREDECESSOR_UNIT, original['unit']]
    need(len(observation['commands']) == len(observation['units']) == len(units),
         'complete five exact post-failure unit observations')
    collector_pids = []
    for index, (command, unit_row, unit) in enumerate(zip(observation['commands'], observation['units'], units)):
        ADMISSION20.command_reaped(command)
        need(command['argv'] == ['/usr/bin/systemctl', '--user', 'show', unit,
             '--property=LoadState,ActiveState,SubState,MainPID,ControlGroup']
             and type(command['pid']) is int and command['pid'] > 1
             and observation['started_ns'] <= command['started_ns'] <= command['finished_ns'] <= observation['finished_ns'],
             'actual collector query, fixed unit and bounded reaped child')
        collector_pids.append(command['pid'])
        stdout, stderr = bytes.fromhex(command['stdout_hex']), bytes.fromhex(command['stderr_hex'])
        need(stdout.decode('utf-8', 'strict') == command['stdout']
             and stderr.decode('utf-8', 'strict') == command['stderr'], 'complete original status wire')
        fields = r21_retired_fields(unit, stdout, stderr, command['exit_code'])
        need(command['properties'] == fields and unit_row['observed_fields'] == fields
             and unit_row['unit'] == unit and unit_row['scope'] == 'user'
             and unit_row['command_index'] == index and unit_row['retired_fields_match_unit_type'] is True
             and unit_row['cgroups'] == [{'path': root + '/' + unit, 'exists': False} for root in (
                 '/sys/fs/cgroup/user.slice/user-1000.slice/user@1000.service/app.slice',
                 '/sys/fs/cgroup/system.slice')], 'actual properties and both exact cgroups absent')
    need(len(set(collector_pids)) == 5, 'five distinct actual reaped collector children')
    need(R20['preparation_clients'] == [*old['preparation_clients'], observer, directory],
         'all seven original preparation clients plus the actual observer and directory client')
    extra_targets = [
        {'scope': 'user', 'unit': R21_PREDECESSOR_UNIT, 'pids': [r['pid'] for r in children],
         'provenance': ['R20 actual prebuild terminal and independent retirement']},
        {'scope': 'user', 'unit': original['unit'], 'pids': [3809990, 3809991],
         'provenance': ['R20 original API client, exited 1/full']},
        {'scope': 'user', 'unit': observer['unit'], 'pids': [3812404, 3812405, *collector_pids],
         'provenance': ['R20 independent observation original API client, exited 0/full']},
        {'scope': 'user', 'unit': directory['unit'], 'pids': [3828998, 3828999],
         'provenance': ['R21 create-only directory original API client, exited 0/full']},
    ]
    need(R20['live_retirement_targets'] == [*old['live_retirement_targets'], *extra_targets],
         'all 123 original live targets retained, plus four actual R20/observer/directory targets')
    return {'schema': 'p4-r21-actual-r20-prebuild-failure-admission-v1',
            'terminal': refs['terminal'], 'independent_observation': observer['stdout'],
            'create_only_directory_preparation': directory['stdout'],
            'original_client_exit_code': 1, 'build_attempted': False, 'normal_recovery_attempted': False,
            'original_source_and_locks_unchanged': True, 'runtime_qualified': False, 'production_ready': False}


def r20_current_baseline():
    need(digest(SOURCE / '.droidloom-source-manifest.json') == ADMISSION20.MANIFEST,
         'R19 actual old652 publication is the current initial manifest')
    for item, (path, inode) in zip(ADMISSION20.LOCKS, LOCK_PINS):
        need(str(path) == item['path'] and check_lock(path, inode) == item['identity']
             and digest(path) == ADMISSION20.reference(item)
             and path.read_bytes().hex() == item['body_hex'],
             'original lock inode and actual R19 recovery PID body unchanged')
    need(not os.path.lexists(WORK / 'source-projection.json'), 'no interrupted source projection')


def verify_serialized_retirement():
    global R20_ADMISSION_DEADLINE
    need(R20_ADMISSION_DEADLINE is None, 'single non-reentrant R20 admission')
    R20_ADMISSION_DEADLINE = time.monotonic() + 150
    try:
        r20_failure = r21_validate_prebuild_failure()
        refs = R20['R19']
        r20_check(refs['worker'])
        values = {k: r20_json(refs[k]) for k in ('bundle', 'outer', 'build', 'recovery', 'retirement')}
        previous = ADMISSION20.validate_predecessor(values, refs)
        legacy = r20_json(R20['historical_83'])
        need(len(legacy['paths']) == 83 and len({x['path'] for x in legacy['paths']}) == 83,
             'whole original historical 83-input roster')
        live_transition = {ADMISSION20.MANIFEST['path'], *[x['path'] for x in ADMISSION20.LOCKS]}
        checked = []
        for item in legacy['paths']:
            if item['path'] in live_transition:
                continue
            got = digest(Path(item['path']))
            need(item['expected_pins'] and all(
                 got['bytes'] == x['bytes'] and got['sha256'] == x['sha256']
                 and ('f9' not in x or got['identity'] == x['f9']) for x in item['expected_pins']),
                 'immutable original historical input remains exact: ' + item['path'])
            checked.append(got); r20_guard_admission()
        need(len(checked) == 79, 'only four explicitly bound live identities may transition')
        # R19's original whole immutable helper/producer/old plan pins also
        # stay required. The original 83 roster above is not substituted.
        for path, expected in R20_HISTORICAL_PINS.items():
            got = digest(path)
            need((got['bytes'], got['sha256']) == expected, 'original R19 fixed dependency retained')
            r20_guard_admission()
        for name, item in values['retirement']['clients'].items():
            r20_validate_client(item, item['stdout'], 1 if name == 'original' else 0)
        ci = r20_json(R20['release_ci'])
        release = ADMISSION20.validate_current_release(ci, R20['current_binaries'])
        for item in R20['current_binaries'].values():
            got = r20_check(item)
            with Path(got['path']).open('rb') as stream:
                header = stream.read(20)
            need(header[:6] == b'\x7fELF\x02\x01' and header[18:20] == b'\x3e\x00',
                 'actual current normal x86_64 ELF header')
            need(digest(Path(got['path'])) == got, 'ELF unchanged across actual header read')
        # Exact fresh host ABI inspection is a separate frozen input, never a
        # claim that CI has started Android or validated production behavior.
        host = r20_json(R20['host_direct_abi'])
        need(host['schema'] == 'p4-current19-static-direct-import-compatibility-v1'
             and host['host'] == 'ai395'
             and host['source'] == ADMISSION20.CURRENT and host['binary_count'] == 19
             and host['passed_direct_symbols_only'] is True
             and host['dynamic_transitive_loading_tested'] is False
             and host['runtime_qualified'] is False and host['production_ready'] is False
             and len(host['binaries']) == 19
             and len({x['binary'] for x in host['binaries']}) == 19
             and {x['binary']: x['sha256'] for x in host['binaries']}
                 == {n: x['sha256'] for n, x in R20['current_binaries'].items()}
             and all(x['missing_strong'] == [] for x in host['binaries']),
             'actual current direct host symbol check, with its limits retained')
        for item in ADMISSION20.validate_host_abi_custody(host, R20['host_abi_inputs']):
            r20_check(item)
        historical_units = {('user', x['argv'][3]) for x in values['outer']['original_worker_status_children']
                            if x['argv'][:3] == ['/usr/bin/systemctl', '--user', 'show']}
        historical_units |= {('system', x['argv'][2]) for x in values['outer']['original_worker_status_children']
                             if x['argv'][:2] == ['/usr/bin/systemctl', 'show']}
        historical_units |= {('user', x['unit']) for x in values['retirement']['units']}
        targets = R20['live_retirement_targets']
        need(len(targets) == len({(x['scope'], x['unit']) for x in targets})
             and historical_units <= {(x['scope'], x['unit']) for x in targets},
             'all actual prior known units and original user/system scopes retained')
        actual_units = [r20_live_retired(x['unit'], x.get('pids', []), x['scope']) for x in targets]
        for item in R20['preparation_clients']:
            r20_validate_client(item, item['stdout'])
        r20_current_baseline()
        return {'schema': 'p4-serialized-heavy-build-resource-plan-v1',
            'original_minimum_memory_gib': 42, 'vendor_memory_max_gib': 24,
            'simultaneous_other_heavy_compilers': 0, 'bounded_light_scopes_max_gib': 3.25,
            'host_reserve_gib': 12, 'unallocated_margin_within_minimum_gib': 2.75,
            'actual_R19_failed_build_and_complete_original_recovery': previous,
            'actual_R20_prebuild_failure_and_independent_retirement': r20_failure,
            'new_actual_current_release': release, 'historical_83_inputs_preserved': True,
            'historical_79_immutable_inputs_rechecked': checked, 'actual_units': actual_units,
            'new_lint_materialization_credit': False, 'resource_admission_reused': False,
            'production_ready': False, 'runtime_qualified': False, 'observed_ns': time.time_ns()}
    finally:
        R20_ADMISSION_DEADLINE = None


def source_contracts():
    evidence = r20_json(R20['plan_evidence'])
    need(evidence['schema'] == 'p4-r20-current-release-normal-plan-evidence-v1'
         and evidence['passed'] is True and evidence['all_original_children_reaped'] is True
         and evidence['inputs_before'] == evidence['inputs_after']
         and evidence['network_operations'] is False and evidence['materialize_or_reconcile'] is False
         and len(evidence['commands']) == 2, 'actual current normal read-only profile plans')
    result = {}
    for i, (key, profile, sha) in enumerate((('old', 'production-full-cmake', TRANSITION20.OLD_LOCK_SHA),
                                            ('new', 'production-full-lint', TRANSITION20.NEW_LOCK_SHA))):
        entry = R20['profiles'][key]
        lock, plan_ref = r20_check(entry['lock']), r20_check(entry['plan'])
        need(lock['sha256'] == sha and Path(lock['path']).is_relative_to(CANONICAL_SOURCE),
             'new-release canonical old and new profile lock inputs')
        command = evidence['commands'][i]
        ADMISSION20.command_reaped(command)
        need(command['name'] == 'plan-' + profile
             and command['argv'] == [str(SOURCE_TOOL), '--profile', profile, 'plan', '--lock', lock['path']]
             and ADMISSION20.reference(command['stdout']) == plan_ref,
             'actual exact current normal plan argv and complete output')
        r20_check(command['stderr'])
        for item in (R20['current_binaries']['droidloom-source'], entry['lock']):
            observed = [x for x in evidence['inputs_before'] if x['path'] == item['path']]
            need(len(observed) == 1 and ADMISSION20.reference(observed[0]) == r20_check(item),
                 'actual plan process used this current ELF and exact lock inode')
        plan = BOOKENDS.normalized_plan(r20_json(entry['plan']))
        result[key] = {'schema_version': 1, 'source_lock_sha256': sha, 'plan': plan}
    old, new = TRANSITION20.validate_profiles(BOOKENDS, result['old'], result['new'])
    need(BOOKENDS.normalized_manifest(r20_json(R20['old_manifest_copy'])) == old,
         'old actual normal plan exactly matches R19 original published 652 manifest')
    return {'old': old, 'new': new}


def r20_require_R19_bodies(summary, contracts):
    recovery = r20_json(R20['R19']['recovery'])
    old651 = r20_json(recovery['content_bookends']['original651-content-after-recovery'])
    cmake = r20_json(recovery['content_bookends']['cmake-complete-content-after-recovery'])
    keys = ('project', 'tree', 'tracked_entries', 'materialized_entries',
            'materialized_bytes', 'sparse_absent_entries', 'body_sha256')
    old_projects = old651['projects'] + cmake['projects']
    need(old651['project_count'] == 651 and cmake['project_count'] == 1
         and cmake['projects'][0]['tracked_entries'] == 3915
         and cmake['sparse_absent_entries'] == 0
         and summary['project_count'] == 652
         and [x['project'] for x in summary['projects']] == contracts['old']['plan']['projects']
         and [{k: p[k] for k in keys} for p in summary['projects']]
             == [{k: p[k] for k in keys} for p in old_projects],
         'all original R19 652 tuples, bodies, representation and CMake are unchanged')


def r20_compare(before, after, contracts, *, partial=False):
    if not partial:
        return TRANSITION20.compare_complete(BOOKENDS, contracts['old'], contracts['new'], before, after,
                                             DEADLINE, resource_guard)
    a = TRANSITION20.VerifiedInventory(BOOKENDS, before, contracts['old']['plan']['projects'],
                                      DEADLINE, resource_guard)
    b = TRANSITION20.VerifiedPartialInventory(BOOKENDS, after, contracts['old'], contracts['new'],
                                             DEADLINE, resource_guard)
    result = TRANSITION20.compare_rows(a, b, allow_partial=True,
                                      expected_count=TRANSITION20.TRACKED_MEMBERS)
    need(a.completed and b.completed, 'both full original and partial source streams completed')
    return result


def r20_candidate_rules(name):
    directory = CONTROL / (name + '-queries')
    result = PARTIAL20.candidate_checkout_rules(BOOKENDS, TRANSITION20,
        SOURCE / TRANSITION20.HEALTH, directory, DEADLINE, resource_guard, R20['git_conversion_admission'])
    need(result['all_five_attributes_unspecified'] is True, 'six original raw-only checkout rules')
    path = CONTROL / (name + '.json')
    with path.open('x') as stream:
        json.dump(result, stream, indent=2, sort_keys=True); stream.write('\n')
    return digest(path)


def normal_reconcile_and_verify(env):
    contracts = source_contracts()
    with original_source_locks():
        r20_current_baseline()
        run('verify-cmake652-before', [str(SOURCE_TOOL), '--profile', 'production-full-cmake',
            'verify-materialized', '--lock', R20['profiles']['old']['lock']['path'], '--output', str(SOURCE)],
            env, min(1200, max(1, DEADLINE - time.monotonic())), True)
        old, old_pin = manifest_observation('manifest-cmake652-before')
        need(BOOKENDS.normalized_manifest(old) == contracts['old']
             and old_pin['original'] == ADMISSION20.MANIFEST, 'whole original R19 manifest before mutation')
        before = content_bookend('original652-content-before', contracts['old']['plan']['projects'])
        r20_require_R19_bodies(before, contracts)
        # Fully validate every original row and prove the six original S-absent
        # entries without using a new partial state as the budget/baseline.
        a = TRANSITION20.VerifiedInventory(BOOKENDS, before, contracts['old']['plan']['projects'], DEADLINE, resource_guard)
        b = TRANSITION20.VerifiedInventory(BOOKENDS, before, contracts['old']['plan']['projects'], DEADLINE, resource_guard)
        initial = TRANSITION20.compare_rows(a, b, allow_partial=True, expected_count=TRANSITION20.TRACKED_MEMBERS)
        need(initial['lint_materialized'] == 0 and a.completed and b.completed, 'all six original lint inputs absent')
        rules = r20_candidate_rules('lint-checkout-rules-before')
        intent_pin = write_source_stage('source-reconcile-intent', {
            'old_manifest': old_pin, 'before_content': OBS['content_bookends']['original652-content-before'],
            'expected_new_manifest_sha256': hashlib.sha256(BOOKENDS.encoded(contracts['new'])).hexdigest(),
            'original_six_lint_members_absent': True, 'candidate_checkout_rules': rules,
            'source_lock_before': TRANSITION20.OLD_LOCK_SHA, 'source_lock_after': TRANSITION20.NEW_LOCK_SHA})
        run('normal-reconcile-lint652', [str(SOURCE_TOOL), '--profile', 'production-full-lint',
            'reconcile', '--lock', str(LOCK), '--output', str(SOURCE)],
            env, max(1, DEADLINE - time.monotonic()), True)
        write_source_stage('source-reconcile-returned', {'intent': intent_pin, 'command': OBS['commands'][-1]})
        run('verify-lint652-before', [str(SOURCE_TOOL), '--profile', 'production-full-lint',
            'verify-materialized', '--lock', str(LOCK), '--output', str(SOURCE)],
            env, min(1200, max(1, DEADLINE - time.monotonic())), True)
        new, new_pin = manifest_observation('manifest-lint652-after-reconcile')
        need(BOOKENDS.normalized_manifest(new) == contracts['new'], 'exact normal lint652 atomic publication')
        after = content_bookend('lint652-content-after-reconcile', contracts['new']['plan']['projects'])
        comparison = r20_compare(before, after, contracts)
        tool_pins, versions = [], []
        for name in ('cmake', 'ctest'):
            path = CMAKE_PROJECT / 'bin' / name; pin = digest(path)
            with path.open('rb') as stream:
                header = stream.read(20)
            need(header[:6] == b'\x7fELF\x02\x01' and header[18:20] == b'\x3e\x00'
                 and pin['identity'][2] & 0o111, 'original x86_64 executable CMake tool')
            output = run('original-cmake-provider-' + name + '-version', [str(path), '--version'], env, 30, True)
            need(digest(path) == pin, 'original tool unchanged during execution')
            first = output.read_text().splitlines()[0]
            need(first.startswith(name + ' version '), 'original provider actual version')
            versions.append(first.split(' version ', 1)[1]); tool_pins.append(pin)
        need(versions[0] == versions[1], 'original CMake/CTest versions agree')
        OBS['full_lint652_reconcile'] = {'normal_cli_completed': True, 'old_manifest': old_pin,
            'new_manifest': new_pin, 'comparison': comparison, 'original_complete_cmake_members': 3915,
            'full_provider_tool_pins': tool_pins, 'actual_tool_version': versions[0],
            'materialization_only': True, 'vendor_build_credit': False}
        write_source_stage('source-transition-complete', {'intent': intent_pin, 'new_manifest': new_pin,
            'full_lint652_after': OBS['content_bookends']['lint652-content-after-reconcile'], 'comparison': comparison})
        save()
    native_before = json.loads((CONTROL / 'native-source-before.json').read_text())
    need(native_snapshot() == native_before, 'normal lint reconciliation changed independent native926 input')


def r20_verify_reconcile_return(record, intent_pin, name):
    payload, pin = record; command = payload['command']
    need(set(payload) == {'intent', 'command'} and payload['intent'] == intent_pin
         and command['name'] == name and command['argv'] == [str(SOURCE_TOOL), '--profile', 'production-full-lint',
             'reconcile', '--lock', str(LOCK if name == 'normal-reconcile-lint652' else RECOVERY_LOCK),
             '--output', str(SOURCE)], 'same normal lint source command and original intent')
    ADMISSION20.command_reaped(command)
    r20_check(command['stdout']); r20_check(command['stderr'])


def r20_recovery_retirement():
    owner = verify_outer()
    record, _ = read_source_json(CONTROL / 'build-retirement-before-recovery.json')
    row = record['build_phase']
    need(record['schema'] == 'p4-r21-original-build-retirement-before-recovery-v1'
         and record['generation'] == owner['generation'] and record['serial_lock'] == owner['serial_lock']
         and record['worker_sha256'] == digest(SELF)['sha256']
         and row['mode'] == 'build' and row['unit'] == UNIT + '.service'
         and row['service_retired'] is True and row['client']['actual_reaped'] is True
         and row['client']['original_pidfd_held_until_reaped'] is True
         and row['late_start_unresolved'] is False
         and all(x['actual_reaped'] is True and x['original_pidfd_held_until_reaped'] is True
                 for x in record['original_outer_children']),
         'original outer retains actual complete build retirement before recovery')
    OBS['actual_build_retirement_before_recovery'] = r20_live_retired(UNIT + '.service')
    need(not RUNNER.owned_children(), 'no inherited unreaped build worker')
    resource_guard(True)


def verify_recovered_source(env):
    contracts = source_contracts()
    with original_source_locks():
        intent = read_source_stage('source-reconcile-intent')
        returned = read_source_stage('source-reconcile-returned')
        complete = read_source_stage('source-transition-complete')
        vendor = read_source_stage('source-vendor-intent')
        resume = read_source_stage('source-resume-intent')
        resume_returned = read_source_stage('source-resume-returned')
        need(intent is not None or all(x is None for x in (returned, complete, vendor, resume, resume_returned)),
             'no later source phase without this original durable transition intent')
        before = None
        if intent is not None:
            payload, intent_pin = intent
            need(set(payload) == {'old_manifest', 'before_content', 'expected_new_manifest_sha256',
                 'original_six_lint_members_absent', 'candidate_checkout_rules', 'source_lock_before', 'source_lock_after'}
                 and payload['original_six_lint_members_absent'] is True
                 and payload['source_lock_before'] == TRANSITION20.OLD_LOCK_SHA
                 and payload['source_lock_after'] == TRANSITION20.NEW_LOCK_SHA
                 and payload['expected_new_manifest_sha256'] == hashlib.sha256(BOOKENDS.encoded(contracts['new'])).hexdigest(),
                 'original six-body lint transition intent')
            old, _ = read_source_json(CONTROL / 'manifest-cmake652-before.json', payload['old_manifest']['copy'])
            need(BOOKENDS.normalized_manifest(old) == contracts['old']
                 and payload['old_manifest']['original'] == ADMISSION20.MANIFEST,
                 'original intent retains actual R19 complete manifest')
            before, _ = read_content_bookend('original652-content-before', contracts['old']['plan']['projects'],
                                             payload['before_content'])
            r20_require_R19_bodies(before, contracts)
            r20_check(payload['candidate_checkout_rules'])
            if returned is not None:
                r20_verify_reconcile_return(returned, intent_pin, 'normal-reconcile-lint652')
            if complete is not None:
                c, _ = complete
                need(set(c) == {'intent', 'new_manifest', 'full_lint652_after', 'comparison'}
                     and c['intent'] == intent_pin, 'original exact source completion belongs to intent')
                recorded, _ = read_source_json(CONTROL / 'manifest-lint652-after-reconcile.json', c['new_manifest']['copy'])
                need(BOOKENDS.normalized_manifest(recorded) == contracts['new'], 'original exact new publication')
                prior_after, _ = read_content_bookend('lint652-content-after-reconcile', contracts['new']['plan']['projects'],
                                                     c['full_lint652_after'])
                need(r20_compare(before, prior_after, contracts) == c['comparison'], 'actual original complete six-body comparison')
            if vendor is not None:
                need(complete is not None and set(vendor[0]) == {'source_transition_complete'}
                     and vendor[0]['source_transition_complete'] == complete[1], 'Vendor only after original exact complete source')
        actual, state_pin = manifest_observation('manifest-recovery-state-before-verify')
        branch = TRANSITION20.recovery_branch(BOOKENDS, actual, contracts['old'], contracts['new'],
                                              intent is not None, vendor is not None, resume is not None)
        need(resume_returned is None or resume is not None, 'no returned resume without durable intent')
        OBS['source_recovery_branch'] = {'branch': branch, 'observed_manifest': state_pin,
            'original_intent_present': intent is not None, 'original_return_present': returned is not None,
            'complete_present': complete is not None, 'vendor_present': vendor is not None,
            'resume_intent_present': resume is not None, 'original_deadline': DEADLINE}
        save()
        if branch == 'old652-before-reconcile-dispatch':
            run('verify-cmake652-after', [str(SOURCE_TOOL), '--profile', 'production-full-cmake',
                'verify-materialized', '--lock', R20['profiles']['old']['lock']['path'], '--output', str(SOURCE)],
                env, min(900, max(1, DEADLINE - time.monotonic())), True)
            after = content_bookend('cmake652-content-after-recovery', contracts['old']['plan']['projects'])
            r20_require_R19_bodies(after, contracts)
            final, final_pin = manifest_observation('manifest-cmake652-after-recovery')
            need(BOOKENDS.normalized_manifest(final) == contracts['old']
                 and final_pin['original'] == ADMISSION20.MANIFEST, 'original old652 unchanged before source dispatch')
            OBS.update(source_recovery_complete=True, original_cmake652_source_state_verified=True,
                       new_lint652_source_state_verified=False, final_normal_manifest=final_pin)
            return
        need(before is not None, 'all mutating or completed lint branches require original full before inventory')
        if branch == 'old652-dispatched-requires-partial-bookend-before-one-normal-resume':
            need(complete is None and vendor is None and returned is None and resume is None
                 and resume_returned is None, 'only a genuinely incomplete original normal reconcile may resume once')
            need(state_pin['original'] == payload['old_manifest']['original'] == ADMISSION20.MANIFEST,
                 'unpublished normal reconcile retains the original old manifest full F9 and bytes')
            r20_recovery_retirement()
            partial = PARTIAL20.partial_snapshot(BOOKENDS, TRANSITION20, SOURCE,
                contracts['old'], contracts['new'], CONTROL / 'partial-lint652-before-resume.ndjson',
                DEADLINE, resource_guard, R20['git_conversion_admission'], state_pin['original'])
            partial_path = CONTROL / 'partial-lint652-before-resume.json'
            with partial_path.open('x') as stream:
                json.dump(partial, stream, sort_keys=True, indent=2); stream.write('\n')
            comparison = r20_compare(before, partial, contracts, partial=True)
            rules = r20_candidate_rules('lint-checkout-rules-before-resume')
            need(digest(SOURCE / '.droidloom-source-manifest.json') == state_pin['original'],
                 'old manifest unchanged during partial recovery diagnostic')
            resource_guard(True)
            resume_pin = write_source_stage('source-resume-intent', {'original_intent': intent_pin,
                'original_before': payload['before_content'], 'partial_diagnostic': digest(partial_path),
                'partial_comparison': comparison, 'candidate_checkout_rules': rules,
                'fixed_recovery_deadline': DEADLINE, 'budget_baselines': digest(CONTROL / 'budget-baselines.json'),
                'normal_profile': 'production-full-lint', 'retry_number': 0})
            run('normal-resume-lint652-once', [str(SOURCE_TOOL), '--profile', 'production-full-lint',
                'reconcile', '--lock', str(RECOVERY_LOCK), '--output', str(SOURCE)],
                env, max(1, DEADLINE - time.monotonic()), True)
            write_source_stage('source-resume-returned', {'intent': resume_pin, 'command': OBS['commands'][-1]})
            actual, _ = manifest_observation('manifest-lint652-after-resume')
            need(BOOKENDS.normalized_manifest(actual) == contracts['new'], 'single normal resume published exact new manifest')
        elif resume is not None:
            # An existing resume record in a fresh recovery process is not a
            # license for another attempt or credit. This generation has only
            # one recovery phase; unexpected prior records fail closed.
            raise RuntimeError('pre-existing resume record requires a separately reviewed successor; no retry')
        run('verify-lint652-after', [str(SOURCE_TOOL), '--profile', 'production-full-lint',
            'verify-materialized', '--lock', str(RECOVERY_LOCK), '--output', str(SOURCE)],
            env, min(900, max(1, DEADLINE - time.monotonic())), True)
        final, final_pin = manifest_observation('manifest-lint652-after-recovery')
        need(BOOKENDS.normalized_manifest(final) == contracts['new'], 'complete normal lint652 recovery publication')
        after = content_bookend('lint652-content-after-recovery', contracts['new']['plan']['projects'])
        comparison = r20_compare(before, after, contracts)
        OBS.update(source_recovery_complete=True, new_lint652_source_state_verified=True,
                   original652_non_lint_tuples_preserved=True, complete_cmake_members_preserved=3915,
                   complete_original_lint_comparison=comparison, final_normal_manifest=final_pin)
        save()


r20_bootstrap()


def recover():
    global OBSERVATION_NAME, DEADLINE, BASE_WORK, BASE_LIGHT, BASE_SOURCE
    OBSERVATION_NAME = 'recovery-observation.json'
    import_pinned()
    verify_outer()
    OBS['admission'] = cgroup_admit(2, 1.5, 2, 512)
    DEADLINE = time.monotonic() + 1200
    baseline = json.loads((CONTROL / 'budget-baselines.json').read_text())
    BASE_WORK, BASE_LIGHT, BASE_SOURCE = baseline['work'], baseline['light'], baseline['source']
    r20_recovery_retirement()
    for path, inode in LOCK_PINS:
        check_lock(path, inode)
    env = environment()
    env['TMPDIR'] = str(TMP if TMP.exists() else CONTROL)
    for path in (UPDATE_TOOL, SOURCE_TOOL, OLD_LOCK, RECOVERY_LOCK, BOOKEND_PATH, PLAN651, PLAN652, PLAN_EVIDENCE):
        got = digest(path)
        need((got['bytes'], got['sha256']) == PINS[path], 'recovery input changed')
    run('normal-source-recovery', [str(UPDATE_TOOL), 'recover-source', '--work', str(WORK)], env, 300)
    need(not (WORK / 'source-projection.json').exists(), 'normal recovery left source journal')
    verify_recovered_source(env)
    pins = CONTROL / 'original-inputs.json'
    if pins.exists():
        originals = json.loads(pins.read_text())
        need([digest(Path(item['path'])) for item in originals] == originals, 'original inputs changed')
        rows = json.loads((CONTROL / 'original-producer-rows.json').read_text())
        original = json.loads((CONTROL / 'original-producer-snapshot.json').read_text())
        # .work is a documented producer-owned download cache created by the
        # normal CLI. It is accounted separately, never claimed as source.
        actual_names = set()
        for directory, children, names in os.walk(REPO, followlinks=False):
            if Path(directory) == REPO and '.work' in children:
                children.remove('.work')
            need(all(not (Path(directory) / name).is_symlink() for name in children), 'producer directory alias')
            actual_names.update(str((Path(directory) / name).relative_to(REPO)) for name in names)
        need(actual_names == {r['path'] for r in rows}, 'producer source file membership changed')
        for row in rows:
            path = REPO / row['path']
            VERIFY.check(path, row)
            need(f9(path.lstat()) == original['files'][row['path']], 'producer source identity changed')
        native_before = json.loads((CONTROL / 'native-source-before.json').read_text())
        native_after = native_snapshot()
        need(native_after == native_before, 'original 926 native source members or Git provenance changed')
        (CONTROL / 'native-source-after.json').write_text(json.dumps(native_after, indent=2) + '\n')
        OBS['native_source_926_members_and_git_provenance_unchanged'] = True
        OBS['all_original_inputs_and_source_files_unchanged'] = True
    OBS['finished_ns'] = time.time_ns()
    save('recovery-observation.json')


# This block is appended to the exact complete R21 source before its main guard.
# The historical bootstrap above remains unchanged and only reads its own pins.
R22_CONTRACT_PATH = ROOT / 'control/vendor-build-20261120-9907-r22/inputs/CONTRACT.json'
R22_CONTRACT_PIN = (82455, '746660a89df716c9ffc0dbd2a7e10257fec28f0792e504f5ec0304318595acc5')  # Freeze only after actual same-cohort CI, ELF/ABI and normal plans.
R22 = None
ADMISSION22 = None
TRANSITION22 = None
PARTIAL22 = None
R22_PRESERVED_PINS = dict(PINS)


def r22_bootstrap():
    global R22, ADMISSION22, TRANSITION22, PARTIAL22, BOOKENDS
    global REPO, CONTROL, OUT, TMP, SELF, UNIT, RECOVERY_UNIT, TREE
    global CANONICAL_SOURCE, CANONICAL_ROWS, CANONICAL_FREEZE, CANONICAL_FILES, CANONICAL_BYTES
    global RELEASE, SOURCE_TOOL, UPDATE_TOOL, LOCK, RECOVERY_LOCK, BOOKEND_PATH
    need(type(R22_CONTRACT_PIN) is tuple and len(R22_CONTRACT_PIN) == 2
         and type(R22_CONTRACT_PIN[0]) is int and R22_CONTRACT_PIN[0] > 0
         and type(R22_CONTRACT_PIN[1]) is str and len(R22_CONTRACT_PIN[1]) == 64,
         'R22 source-only template: actual complete CI, ELF custody, host ABI and normal plans not frozen')
    got = digest(R22_CONTRACT_PATH)
    need((got['bytes'], got['sha256']) == R22_CONTRACT_PIN, 'exact frozen R22 contract')
    R22 = r20_json(got, full=False)
    need(R22['schema'] == 'p4-vendor-r22-operational-input-contract-v1'
         and R22['operational_inputs_frozen'] is True
         and R22['runtime_qualified'] is False and R22['production_ready'] is False,
         'R22 current source input qualification only')
    need(R22['git_conversion_admission'] == R20['git_conversion_admission'],
         'all five original actual Git conversion inputs and scopes unchanged')
    ADMISSION22 = r20_module('p4_r22_admission', R22['support']['admission'])
    TRANSITION22 = r20_module('p4_r22_apex_test_transition', R22['support']['transition'])
    PARTIAL22 = r20_module('p4_r22_partial_apex_test_diagnostic', R22['support']['partial'])
    BOOKEND_PATH = Path(R22['support']['bookends']['path'])
    need((R22['support']['bookends']['bytes'], R22['support']['bookends']['sha256'])
         == (29338, 'bab5c377bf642d4aaa7b50a416319cebad31537022e5179a77e6e8d63827fa88'),
         'unchanged strict original complete representation helper')
    BOOKENDS = r20_module('p4_r22_original_bookends', R22['support']['bookends'])
    current = R22['current_source']
    need({k: current[k] for k in ('tree', 'files', 'bytes')} == ADMISSION22.CURRENT,
         'same full producer and nineteen actual release-binary cohort')
    need(R22['baseline'] == {'manifest': ADMISSION22.MANIFEST, 'locks': ADMISSION22.LOCKS},
         'actual original R21 final manifest and normal-recovery lock writer')
    REPO = ROOT / 'producer-build-r22-9907'
    CONTROL = ROOT / 'control/vendor-build-20261120-9907-r22/actual'
    OUT = ROOT / 'out-build-r22-9907'; TMP = ROOT / 'tmp-build-r22-9907'
    SELF = CONTROL.parent / 'source.py'
    UNIT = 'p4-cp3a-vendor-20261120-9907-r22'; RECOVERY_UNIT = UNIT + '-recovery'
    TREE = current['tree']; CANONICAL_FILES = current['files']; CANONICAL_BYTES = current['bytes']
    CANONICAL_SOURCE = Path(current['path']); CANONICAL_ROWS = Path(current['rows']['path'])
    CANONICAL_FREEZE = Path(current['freeze']['path'])
    release_refs = R22['current_binaries']
    need(tuple(sorted(release_refs)) == ADMISSION22.BINARIES, 'all original nineteen current binaries')
    RELEASE = Path(release_refs['droidloom-source']['path']).parent
    SOURCE_TOOL = RELEASE / 'droidloom-source'; UPDATE_TOOL = RELEASE / 'droidloom-update'
    LOCK = REPO / 'android/manifest/production-full-apex-tests-source-lock.json'
    RECOVERY_LOCK = Path(R22['profiles']['new']['lock']['path'])
    additions = [got, *R22['support'].values(), *release_refs.values(), current['rows'], current['freeze'],
        R22['release_ci'], R22['plan_evidence'], R22['host_direct_abi'],
        *R22['host_abi_inputs'], *R22['predecessor'].values(),
        *[row[k] for row in R22['profiles'].values() for k in ('lock', 'plan')],
        R22['controls']['transition'], R22['controls']['admission'], R22['controls']['real_git'],
        *R22['controls']['source_inputs']]
    for item in additions:
        path = Path(item['path']); pin = (item['bytes'], item['sha256'])
        need(path not in PINS or PINS[path] == pin, 'R22 cannot replace any historical input pin')
        PINS[path] = pin
    PINS[LOCK] = (400720, TRANSITION22.NEW_LOCK_SHA)
    need(all(PINS[path] == pin for path, pin in R22_PRESERVED_PINS.items()),
         'every pre-existing historical pin remains unchanged')
    OBS.update(schema='p4-cp3a-normal-vendor-build-r22-v1', source_tree=TREE,
        actual_updater_release_source_tree=TREE,
        updater_release_and_full_canonical_source_tree_identical=True,
        historical_R21_source_tree=R20['current_source']['tree'])


def r22_current_baseline():
    need(digest(SOURCE / '.droidloom-source-manifest.json') == ADMISSION22.MANIFEST,
         'actual R21 final full lint652 manifest remains the initial source baseline')
    for item, (path, inode) in zip(ADMISSION22.LOCKS, LOCK_PINS):
        need(str(path) == item['path'] and check_lock(path, inode) == item['identity']
             and digest(path) == ADMISSION22.reference(item)
             and path.read_bytes().hex() == item['body_hex'],
             'original lock inode and actual R21 normal recovery body unchanged')
    need(not os.path.lexists(WORK / 'source-projection.json'), 'no interrupted source projection')


def r22_validate_controls():
    controls = R22['controls']
    actual = ADMISSION22.validate_original_git_fixture(r20_json(controls['real_git']))
    admission = r20_json(controls['admission'])
    need(admission['schema'] == 'p4-r22-actual-predecessor-admission-controls-v1'
         and admission['passed'] is True and len(admission['negative_cases']) == 9
         and admission['complete_original_inputs_bookended'] is True
         and admission['actual_new_ci_consumed'] is False
         and all(admission[k] == 0 for k in ('children_started', 'source_mutations', 'Android_builds', 'Android_starts'))
         and admission['production_ready'] is admission['runtime_qualified'] is False
         and ADMISSION22.content_reference(admission['module'])
             == ADMISSION22.content_reference(R22['support']['admission']),
         'actual immutable R21 admission controls are input validation only')
    transition = r20_json(controls['transition'])
    need(transition['schema'] == 'p4-r22-source-transition-pure-controls-v1'
         and type(transition['exit_code']) is int and transition['exit_code'] == 0
         and transition['cases'] == 9 and transition['partial_materialization_masks'] == 16
         and transition['real_fixture_inventory_hash_checked'] is True
         and transition['actual_AOSP_materialization'] is transition['build_started'] is False
         and transition['production_ready'] is transition['runtime_qualified'] is False,
         'actual pure transition controls cannot qualify Android')
    for name, key in (('apex_test_transition.py', 'transition'), ('apex_test_partial.py', 'partial')):
        rows = [row for row in transition['files'] if row['path'] == name]
        need(len(rows) == 1 and all(rows[0][field] == R22['support'][key][field]
             for field in ('bytes', 'sha256')), 'same reviewed complete/partial transition source')
    for reference in controls['source_inputs']:
        r20_check(reference)
    return {'actual_original_Git_fixture': actual,
        'actual_R21_admission_negative_cases': len(admission['negative_cases']),
        'transition_control_receipt': controls['transition'],
        'actual_652_transition_credit': False, 'production_ready': False, 'runtime_qualified': False}


def verify_serialized_retirement():
    global R20_ADMISSION_DEADLINE
    need(R20_ADMISSION_DEADLINE is None, 'single non-reentrant R22 evidence admission')
    R20_ADMISSION_DEADLINE = time.monotonic() + 150
    try:
        # These two validators keep their original historical globals and F9 pins.
        # Their immutable predecessor reports are never treated as live source state.
        historical_failure = r21_validate_prebuild_failure()
        refs = R20['R19']
        r20_check(refs['worker'])
        historical_values = {k: r20_json(refs[k]) for k in ('bundle', 'outer', 'build', 'recovery', 'retirement')}
        historical_recovery = ADMISSION20.validate_predecessor(historical_values, refs)
        legacy = r20_json(R20['historical_83'])
        need(len(legacy['paths']) == 83 and len({x['path'] for x in legacy['paths']}) == 83,
             'whole unchanged original 83-input roster')
        live_transition = {ADMISSION20.MANIFEST['path'], *[x['path'] for x in ADMISSION20.LOCKS]}
        checked = []
        for item in legacy['paths']:
            if item['path'] in live_transition:
                continue
            got = digest(Path(item['path']))
            need(item['expected_pins'] and all(
                got['bytes'] == x['bytes'] and got['sha256'] == x['sha256']
                and ('f9' not in x or got['identity'] == x['f9']) for x in item['expected_pins']),
                'immutable original historical input: ' + item['path'])
            checked.append(got); r20_guard_admission()
        need(len(checked) == 79, 'only four explicitly bound current identities may transition')
        for path, expected in R20_HISTORICAL_PINS.items():
            got = digest(path)
            need((got['bytes'], got['sha256']) == expected, 'original R19 fixed dependency retained')
            r20_guard_admission()
        for name, item in historical_values['retirement']['clients'].items():
            r20_validate_client(item, item['stdout'], 1 if name == 'original' else 0)
        predecessor = R22['predecessor']
        for reference in predecessor.values():
            r20_check(reference)
        values = {k: r20_json(predecessor[k]) for k in ('contract', 'bundle', 'terminal', 'build', 'recovery')}
        need(values['contract'] == R20, 'exact old R21 operational contract retained')
        previous = ADMISSION22.validate_r21_predecessor(values, predecessor, R22['baseline'])
        for document in (values['build'], values['recovery']):
            for command in document['commands']:
                for channel in ('stdout', 'stderr'):
                    r20_check(command[channel])
        ci = r20_json(R22['release_ci'])
        release = ADMISSION22.validate_current_release(ci, R22['current_binaries'], R22['ci_provenance'])
        for item in R22['current_binaries'].values():
            got = r20_check(item)
            with Path(got['path']).open('rb') as stream:
                header = stream.read(20)
            need(header[:6] == b'\x7fELF\x02\x01' and header[18:20] == b'\x3e\x00',
                 'actual current normal x86_64 ELF header')
            need(digest(Path(got['path'])) == got, 'ELF unchanged across actual header read')
        host = r20_json(R22['host_direct_abi'])
        need(host['schema'] == 'p4-current19-static-direct-import-compatibility-v1'
             and host['host'] == 'ai395' and host['source'] == ADMISSION22.CURRENT
             and host['binary_count'] == 19 and host['passed_direct_symbols_only'] is True
             and host['dynamic_transitive_loading_tested'] is False
             and host['runtime_qualified'] is False and host['production_ready'] is False
             and len(host['binaries']) == 19 and len({x['binary'] for x in host['binaries']}) == 19
             and {x['binary']: x['sha256'] for x in host['binaries']}
                == {name: x['sha256'] for name, x in R22['current_binaries'].items()}
             and all(x['missing_strong'] == [] for x in host['binaries']),
             'actual current direct host symbol evidence, retaining its limits')
        for item in ADMISSION22.validate_host_abi_custody(host, R22['host_abi_inputs']):
            r20_check(item)
        controls = r22_validate_controls()
        targets = R22['live_retirement_targets']
        need(len(targets) == len({(x['scope'], x['unit']) for x in targets})
             and targets[:len(R20['live_retirement_targets'])] == R20['live_retirement_targets'],
             'all original known live retirement targets retained without substitution')
        required = {
            ('user', 'p4-cp3a-vendor-supervisor-20261120-9907-r21.service'),
            ('user', 'p4-cp3a-vendor-20261120-9907-r21.service'),
            ('user', 'p4-cp3a-vendor-20261120-9907-r21-recovery.service'),
            ('user', 'p4-r22-apex-providers-git-fixture-20261120-3b9d-r1.service'),
            ('user', 'p4-r22-apex-providers-git-fixture-20261120-3b9d-r2.service')}
        need(required <= {(x['scope'], x['unit']) for x in targets},
             'actual R21 and both isolated provider fixture units explicitly retired')
        actual_units = [r20_live_retired(x['unit'], x.get('pids', []), x['scope']) for x in targets]
        for item in R20['preparation_clients'] + R22['preparation_clients']:
            r20_validate_client(item, item['stdout'], item.get('expected_exit_code', 0))
        r22_current_baseline()
        return {'schema': 'p4-serialized-heavy-build-resource-plan-v1',
            'original_minimum_memory_gib': 42, 'vendor_memory_max_gib': 24,
            'simultaneous_other_heavy_compilers': 0, 'bounded_light_scopes_max_gib': 3.25,
            'host_reserve_gib': 12, 'unallocated_margin_within_minimum_gib': 2.75,
            'actual_R19_failed_build_and_complete_original_recovery': historical_recovery,
            'actual_R20_prebuild_failure_and_independent_retirement': historical_failure,
            'actual_R21_Soong_failure_and_complete_original_recovery': previous,
            'new_actual_current_release': release, 'historical_83_inputs_preserved': True,
            'historical_79_immutable_inputs_rechecked': checked, 'actual_units': actual_units,
            'new_four_provider_controls': controls, 'new_provider_materialization_credit': False,
            'resource_admission_reused': False, 'production_ready': False, 'runtime_qualified': False,
            'observed_ns': time.time_ns()}
    finally:
        R20_ADMISSION_DEADLINE = None


"""R22 source transition/recovery functions; ROOT must integrate and review.

This fragment has no import-time action. It requires ROOT's frozen R22,
TRANSITION22, PARTIAL22 and r22_current_baseline, plus the original strict
r20_check/r20_json, ADMISSION20 reference/reaped gates, three source locks,
owned runner, durable source stages and unchanged build/recover budgets.
Only r20_recovery_retirement keeps its legacy entry-point name because the
unchanged generic recover() calls it. No controller or Android action is run.
"""


def source_contracts():
    evidence = r20_json(R22['plan_evidence'])
    need(evidence['schema'] == 'p4-r22-current-release-normal-plan-evidence-v1'
         and evidence['passed'] is True and evidence['all_original_children_reaped'] is True
         and evidence['inputs_before'] == evidence['inputs_after']
         and evidence['network_operations'] is False and evidence['materialize_or_reconcile'] is False
         and len(evidence['commands']) == 2, 'actual current normal read-only profile plans')
    result = {}
    for i, (key, profile, sha) in enumerate((('old', 'production-full-lint', TRANSITION22.OLD_LOCK_SHA),
                                            ('new', 'production-full-apex-tests', TRANSITION22.NEW_LOCK_SHA))):
        entry = R22['profiles'][key]
        lock, plan_ref = r20_check(entry['lock']), r20_check(entry['plan'])
        need(lock['sha256'] == sha and Path(lock['path']).is_relative_to(CANONICAL_SOURCE),
             'new-release canonical old and new profile lock inputs')
        command = evidence['commands'][i]
        ADMISSION20.command_reaped(command)
        need(command['name'] == 'plan-' + profile
             and command['argv'] == [str(SOURCE_TOOL), '--profile', profile, 'plan', '--lock', lock['path']]
             and ADMISSION20.reference(command['stdout']) == plan_ref,
             'actual exact current normal plan argv and complete output')
        r20_check(command['stderr'])
        for item in (R22['current_binaries']['droidloom-source'], entry['lock']):
            observed = [x for x in evidence['inputs_before'] if x['path'] == item['path']]
            need(len(observed) == 1 and ADMISSION20.reference(observed[0]) == r20_check(item),
                 'actual plan process used this current ELF and exact lock inode')
        plan = BOOKENDS.normalized_plan(r20_json(entry['plan']))
        result[key] = {'schema_version': 1, 'source_lock_sha256': sha, 'plan': plan}
    old, new = TRANSITION22.validate_profiles(BOOKENDS, result['old'], result['new'])
    recovery = r20_json(R22['predecessor']['recovery'])
    need(recovery['schema'] == 'p4-cp3a-normal-vendor-build-r21-v1'
         and recovery['source_recovery_complete'] is True
         and recovery['new_lint652_source_state_verified'] is True
         and recovery['errors'] == []
         and recovery['final_normal_manifest']['original'] == R22['baseline']['manifest'],
         'actual complete R21 recovery retains this exact old manifest baseline')
    need(BOOKENDS.normalized_manifest(r20_json(recovery['final_normal_manifest']['copy'])) == old,
         'old actual normal plan exactly matches R21 final published lint652 manifest')
    return {'old': old, 'new': new}


def r22_require_R21_bodies(summary, contracts):
    recovery = r20_json(R22['predecessor']['recovery'])
    need(recovery['schema'] == 'p4-cp3a-normal-vendor-build-r21-v1'
         and recovery['source_recovery_complete'] is True
         and recovery['new_lint652_source_state_verified'] is True
         and recovery['all_original_inputs_and_source_files_unchanged'] is True
         and recovery['native_source_926_members_and_git_provenance_unchanged'] is True
         and recovery['complete_cmake_members_preserved'] == 3915
         and recovery['final_normal_manifest']['original'] == R22['baseline']['manifest']
         and recovery['errors'] == [], 'actual final R21 recovery required as the original source baseline')
    original = r20_json(recovery['content_bookends']['lint652-content-after-recovery'])
    keys = ('project', 'tree', 'tracked_entries', 'materialized_entries',
            'materialized_bytes', 'sparse_absent_entries', 'body_sha256')
    totals = ('content_sha256', 'materialized_entries', 'materialized_bytes', 'sparse_absent_entries')
    need(original['schema'] == summary['schema'] == 'pocket4-original-materialized-source-content-bookend-v1'
         and original['all_actual_Git_blob_reads_verified'] is True
         and summary['all_actual_Git_blob_reads_verified'] is True
         and original['source_mutations'] is summary['source_mutations'] is False
         and original['project_count'] == summary['project_count'] == 652
         and [x['project'] for x in original['projects']] == contracts['old']['plan']['projects']
         and [x['project'] for x in summary['projects']] == contracts['old']['plan']['projects']
         and sum(p['tracked_entries'] for p in original['projects']) == TRANSITION22.TRACKED_MEMBERS
         and sum(p['tracked_entries'] for p in summary['projects']) == TRANSITION22.TRACKED_MEMBERS
         and [{k: p[k] for k in keys} for p in summary['projects']]
             == [{k: p[k] for k in keys} for p in original['projects']]
         and {k: summary[k] for k in totals} == {k: original[k] for k in totals},
         'all actual R21 lint652 tuples, raw bodies, representation and complete CMake are unchanged')


def r22_compare(before, after, contracts, *, partial=False):
    if not partial:
        return TRANSITION22.compare_complete(BOOKENDS, contracts['old'], contracts['new'], before, after,
                                             DEADLINE, resource_guard)
    a = TRANSITION22.VerifiedInventory(BOOKENDS, before, contracts['old']['plan']['projects'],
                                      DEADLINE, resource_guard)
    b = TRANSITION22.VerifiedPartialInventory(BOOKENDS, after, contracts['old'], contracts['new'],
                                             DEADLINE, resource_guard)
    result = TRANSITION22.compare_rows(a, b, allow_partial=True,
                                      expected_count=TRANSITION22.TRACKED_MEMBERS)
    need(a.completed and b.completed, 'both full original and partial source streams completed')
    return result


def r22_candidate_rules(name):
    directory = CONTROL / (name + '-queries')
    result = PARTIAL22.candidate_checkout_rules(BOOKENDS, TRANSITION22,
        SOURCE, directory, DEADLINE, resource_guard, R22['git_conversion_admission'])
    need(result['schema'] == 'p4-r22-four-original-apex-provider-checkout-rules-v1'
         and result['candidate_count'] == 4 and set(result['providers']) == set(TRANSITION22.PROVIDERS)
         and result['all_five_attributes_unspecified'] is True
         and result['committed_effective_equal'] is True
         and result['custom_filters_executed'] is False and result['source_mutations'] is False,
         'four original raw-only APEX provider checkout rules from both actual projects')
    path = CONTROL / (name + '.json')
    with path.open('x') as stream:
        json.dump(result, stream, indent=2, sort_keys=True); stream.write('\n')
    return digest(path)


def normal_reconcile_and_verify(env):
    contracts = source_contracts()
    with original_source_locks():
        r22_current_baseline()
        run('verify-lint652-before', [str(SOURCE_TOOL), '--profile', 'production-full-lint',
            'verify-materialized', '--lock', R22['profiles']['old']['lock']['path'], '--output', str(SOURCE)],
            env, min(1200, max(1, DEADLINE - time.monotonic())), True)
        old, old_pin = manifest_observation('manifest-lint652-before')
        need(BOOKENDS.normalized_manifest(old) == contracts['old']
             and old_pin['original'] == R22['baseline']['manifest'], 'whole original R21 lint652 manifest before mutation')
        before = content_bookend('original-lint652-content-before', contracts['old']['plan']['projects'])
        r22_require_R21_bodies(before, contracts)
        # Fully validate every original row and prove the four original S-absent
        # entries without using a new partial state as the budget/baseline.
        a = TRANSITION22.VerifiedInventory(BOOKENDS, before, contracts['old']['plan']['projects'], DEADLINE, resource_guard)
        b = TRANSITION22.VerifiedInventory(BOOKENDS, before, contracts['old']['plan']['projects'], DEADLINE, resource_guard)
        initial = TRANSITION22.compare_rows(a, b, allow_partial=True, expected_count=TRANSITION22.TRACKED_MEMBERS)
        need(initial['provider_materialized'] == 0 and initial['provider_remaining_absent'] == 4
             and initial['provider_raw_bytes_materialized'] == 0 and a.completed and b.completed,
             'all four original APEX provider inputs absent')
        rules = r22_candidate_rules('apex-tests-checkout-rules-before')
        intent_pin = write_source_stage('source-reconcile-intent', {
            'old_manifest': old_pin, 'before_content': OBS['content_bookends']['original-lint652-content-before'],
            'expected_new_manifest_sha256': hashlib.sha256(BOOKENDS.encoded(contracts['new'])).hexdigest(),
            'original_four_apex_provider_members_absent': True, 'candidate_checkout_rules': rules,
            'source_lock_before': TRANSITION22.OLD_LOCK_SHA, 'source_lock_after': TRANSITION22.NEW_LOCK_SHA})
        run('normal-reconcile-apex-tests652', [str(SOURCE_TOOL), '--profile', 'production-full-apex-tests',
            'reconcile', '--lock', str(LOCK), '--output', str(SOURCE)],
            env, max(1, DEADLINE - time.monotonic()), True)
        write_source_stage('source-reconcile-returned', {'intent': intent_pin, 'command': OBS['commands'][-1]})
        run('verify-apex-tests652-before', [str(SOURCE_TOOL), '--profile', 'production-full-apex-tests',
            'verify-materialized', '--lock', str(LOCK), '--output', str(SOURCE)],
            env, min(1200, max(1, DEADLINE - time.monotonic())), True)
        new, new_pin = manifest_observation('manifest-apex-tests652-after-reconcile')
        need(BOOKENDS.normalized_manifest(new) == contracts['new'], 'exact normal APEX provider atomic publication')
        after = content_bookend('apex-tests652-content-after-reconcile', contracts['new']['plan']['projects'])
        comparison = r22_compare(before, after, contracts)
        tool_pins, versions = [], []
        for name in ('cmake', 'ctest'):
            path = CMAKE_PROJECT / 'bin' / name; pin = digest(path)
            with path.open('rb') as stream:
                header = stream.read(20)
            need(header[:6] == b'\x7fELF\x02\x01' and header[18:20] == b'\x3e\x00'
                 and pin['identity'][2] & 0o111, 'original x86_64 executable CMake tool')
            output = run('original-cmake-provider-' + name + '-version', [str(path), '--version'], env, 30, True)
            need(digest(path) == pin, 'original tool unchanged during execution')
            first = output.read_text().splitlines()[0]
            need(first.startswith(name + ' version '), 'original provider actual version')
            versions.append(first.split(' version ', 1)[1]); tool_pins.append(pin)
        need(versions[0] == versions[1], 'original CMake/CTest versions agree')
        OBS['full_apex_tests652_reconcile'] = {'normal_cli_completed': True, 'old_manifest': old_pin,
            'new_manifest': new_pin, 'comparison': comparison, 'original_complete_cmake_members': 3915,
            'full_provider_tool_pins': tool_pins, 'actual_tool_version': versions[0],
            'materialization_only': True, 'vendor_build_credit': False}
        write_source_stage('source-transition-complete', {'intent': intent_pin, 'new_manifest': new_pin,
            'full_apex_tests652_after': OBS['content_bookends']['apex-tests652-content-after-reconcile'], 'comparison': comparison})
        save()
    native_before = json.loads((CONTROL / 'native-source-before.json').read_text())
    need(native_snapshot() == native_before, 'normal APEX provider reconciliation changed independent native926 input')


def r22_verify_reconcile_return(record, intent_pin, name):
    payload, pin = record; command = payload['command']
    need(set(payload) == {'intent', 'command'} and payload['intent'] == intent_pin
         and command['name'] == name and command['argv'] == [str(SOURCE_TOOL), '--profile', 'production-full-apex-tests',
             'reconcile', '--lock', str(LOCK if name == 'normal-reconcile-apex-tests652' else RECOVERY_LOCK),
             '--output', str(SOURCE)], 'same normal APEX provider source command and original intent')
    ADMISSION20.command_reaped(command)
    r20_check(command['stdout']); r20_check(command['stderr'])


def r20_recovery_retirement():
    owner = verify_outer()
    record, _ = read_source_json(CONTROL / 'build-retirement-before-recovery.json')
    row = record['build_phase']
    need(record['schema'] == 'p4-r22-original-build-retirement-before-recovery-v1'
         and record['generation'] == owner['generation'] and record['serial_lock'] == owner['serial_lock']
         and record['worker_sha256'] == digest(SELF)['sha256']
         and row['mode'] == 'build' and row['unit'] == UNIT + '.service'
         and row['service_retired'] is True and row['client']['actual_reaped'] is True
         and row['client']['original_pidfd_held_until_reaped'] is True
         and row['late_start_unresolved'] is False
         and all(x['actual_reaped'] is True and x['original_pidfd_held_until_reaped'] is True
                 for x in record['original_outer_children']),
         'original outer retains actual complete build retirement before recovery')
    OBS['actual_build_retirement_before_recovery'] = r20_live_retired(UNIT + '.service')
    need(not RUNNER.owned_children(), 'no inherited unreaped build worker')
    resource_guard(True)


def verify_recovered_source(env):
    contracts = source_contracts()
    with original_source_locks():
        intent = read_source_stage('source-reconcile-intent')
        returned = read_source_stage('source-reconcile-returned')
        complete = read_source_stage('source-transition-complete')
        vendor = read_source_stage('source-vendor-intent')
        resume = read_source_stage('source-resume-intent')
        resume_returned = read_source_stage('source-resume-returned')
        need(intent is not None or all(x is None for x in (returned, complete, vendor, resume, resume_returned)),
             'no later source phase without this original durable transition intent')
        before = None
        if intent is not None:
            payload, intent_pin = intent
            need(set(payload) == {'old_manifest', 'before_content', 'expected_new_manifest_sha256',
                 'original_four_apex_provider_members_absent', 'candidate_checkout_rules', 'source_lock_before', 'source_lock_after'}
                 and payload['original_four_apex_provider_members_absent'] is True
                 and payload['source_lock_before'] == TRANSITION22.OLD_LOCK_SHA
                 and payload['source_lock_after'] == TRANSITION22.NEW_LOCK_SHA
                 and payload['expected_new_manifest_sha256'] == hashlib.sha256(BOOKENDS.encoded(contracts['new'])).hexdigest(),
                 'original four-body APEX provider transition intent')
            old, _ = read_source_json(CONTROL / 'manifest-lint652-before.json', payload['old_manifest']['copy'])
            need(BOOKENDS.normalized_manifest(old) == contracts['old']
                 and payload['old_manifest']['original'] == R22['baseline']['manifest'],
                 'original intent retains actual R21 complete lint manifest')
            before, _ = read_content_bookend('original-lint652-content-before', contracts['old']['plan']['projects'],
                                             payload['before_content'])
            r22_require_R21_bodies(before, contracts)
            r20_check(payload['candidate_checkout_rules'])
            if returned is not None:
                r22_verify_reconcile_return(returned, intent_pin, 'normal-reconcile-apex-tests652')
            if complete is not None:
                c, _ = complete
                need(set(c) == {'intent', 'new_manifest', 'full_apex_tests652_after', 'comparison'}
                     and c['intent'] == intent_pin, 'original exact source completion belongs to intent')
                recorded, _ = read_source_json(CONTROL / 'manifest-apex-tests652-after-reconcile.json', c['new_manifest']['copy'])
                need(BOOKENDS.normalized_manifest(recorded) == contracts['new'], 'original exact new publication')
                prior_after, _ = read_content_bookend('apex-tests652-content-after-reconcile', contracts['new']['plan']['projects'],
                                                     c['full_apex_tests652_after'])
                need(r22_compare(before, prior_after, contracts) == c['comparison'], 'actual original complete four-body provider comparison')
            if vendor is not None:
                need(complete is not None and set(vendor[0]) == {'source_transition_complete'}
                     and vendor[0]['source_transition_complete'] == complete[1], 'Vendor only after original exact complete source')
        actual, state_pin = manifest_observation('manifest-recovery-state-before-verify')
        branch = TRANSITION22.recovery_branch(BOOKENDS, actual, contracts['old'], contracts['new'],
                                              intent is not None, vendor is not None, resume is not None)
        need(resume_returned is None or resume is not None, 'no returned resume without durable intent')
        OBS['source_recovery_branch'] = {'branch': branch, 'observed_manifest': state_pin,
            'original_intent_present': intent is not None, 'original_return_present': returned is not None,
            'complete_present': complete is not None, 'vendor_present': vendor is not None,
            'resume_intent_present': resume is not None, 'original_deadline': DEADLINE}
        save()
        if branch == 'old652-before-reconcile-dispatch':
            run('verify-lint652-after', [str(SOURCE_TOOL), '--profile', 'production-full-lint',
                'verify-materialized', '--lock', R22['profiles']['old']['lock']['path'], '--output', str(SOURCE)],
                env, min(900, max(1, DEADLINE - time.monotonic())), True)
            after = content_bookend('lint652-content-after-recovery', contracts['old']['plan']['projects'])
            r22_require_R21_bodies(after, contracts)
            final, final_pin = manifest_observation('manifest-lint652-after-recovery')
            need(BOOKENDS.normalized_manifest(final) == contracts['old']
                 and final_pin['original'] == R22['baseline']['manifest'], 'original old652 unchanged before source dispatch')
            OBS.update(source_recovery_complete=True, original_lint652_source_state_verified=True,
                       new_apex_tests652_source_state_verified=False, final_normal_manifest=final_pin)
            return
        need(before is not None, 'all mutating or completed APEX provider branches require original full before inventory')
        if branch == 'old652-dispatched-requires-partial-bookend-before-one-normal-resume':
            need(complete is None and vendor is None and returned is None and resume is None
                 and resume_returned is None, 'only a genuinely incomplete original normal reconcile may resume once')
            need(state_pin['original'] == payload['old_manifest']['original'] == R22['baseline']['manifest'],
                 'unpublished normal reconcile retains the original old manifest full F9 and bytes')
            r20_recovery_retirement()
            partial = PARTIAL22.partial_snapshot(BOOKENDS, TRANSITION22, SOURCE,
                contracts['old'], contracts['new'], CONTROL / 'partial-apex-tests652-before-resume.ndjson',
                DEADLINE, resource_guard, R22['git_conversion_admission'], state_pin['original'])
            partial_path = CONTROL / 'partial-apex-tests652-before-resume.json'
            with partial_path.open('x') as stream:
                json.dump(partial, stream, sort_keys=True, indent=2); stream.write('\n')
            comparison = r22_compare(before, partial, contracts, partial=True)
            rules = r22_candidate_rules('apex-tests-checkout-rules-before-resume')
            need(digest(SOURCE / '.droidloom-source-manifest.json') == state_pin['original'],
                 'old manifest unchanged during partial recovery diagnostic')
            resource_guard(True)
            resume_pin = write_source_stage('source-resume-intent', {'original_intent': intent_pin,
                'original_before': payload['before_content'], 'partial_diagnostic': digest(partial_path),
                'partial_comparison': comparison, 'candidate_checkout_rules': rules,
                'fixed_recovery_deadline': DEADLINE, 'budget_baselines': digest(CONTROL / 'budget-baselines.json'),
                'normal_profile': 'production-full-apex-tests', 'retry_number': 0})
            run('normal-resume-apex-tests652-once', [str(SOURCE_TOOL), '--profile', 'production-full-apex-tests',
                'reconcile', '--lock', str(RECOVERY_LOCK), '--output', str(SOURCE)],
                env, max(1, DEADLINE - time.monotonic()), True)
            write_source_stage('source-resume-returned', {'intent': resume_pin, 'command': OBS['commands'][-1]})
            actual, _ = manifest_observation('manifest-apex-tests652-after-resume')
            need(BOOKENDS.normalized_manifest(actual) == contracts['new'], 'single normal resume published exact new manifest')
        elif resume is not None:
            # An existing resume record in a fresh recovery process is not a
            # license for another attempt or credit. This generation has only
            # one recovery phase; unexpected prior records fail closed.
            raise RuntimeError('pre-existing resume record requires a separately reviewed successor; no retry')
        run('verify-apex-tests652-after', [str(SOURCE_TOOL), '--profile', 'production-full-apex-tests',
            'verify-materialized', '--lock', str(RECOVERY_LOCK), '--output', str(SOURCE)],
            env, min(900, max(1, DEADLINE - time.monotonic())), True)
        final, final_pin = manifest_observation('manifest-apex-tests652-after-recovery')
        need(BOOKENDS.normalized_manifest(final) == contracts['new'], 'complete normal APEX provider recovery publication')
        after = content_bookend('apex-tests652-content-after-recovery', contracts['new']['plan']['projects'])
        comparison = r22_compare(before, after, contracts)
        OBS.update(source_recovery_complete=True, new_apex_tests652_source_state_verified=True,
                   original652_non_apex_provider_tuples_preserved=True, complete_cmake_members_preserved=3915,
                   complete_original_apex_provider_comparison=comparison, final_normal_manifest=final_pin)
        save()


r22_bootstrap()

# Appended to the exact frozen R22 prefix before its unchanged main guard.
# R22's original operational contract and source-transition functions remain
# historical inputs. Only this generation's paths and prebuild admission change.
R23_CONTRACT_PATH = ROOT / 'control/vendor-build-20261120-9907-r23/inputs/CONTRACT.json'
R23_CONTRACT_PIN = (86703, '0957c9d15970b80301eb30d498c2b9baf3a9b84e7dccd0ec42c5f7442a35e875')
R23 = None
PREBUILD22 = None
R23_R22_PINS = dict(PINS)
R23_UNMATERIALIZED_LOCK = ROOT / 'producer-build-r22-9907/android/manifest/production-full-apex-tests-source-lock.json'
R23_UNMATERIALIZED_ROOTS = ('producer-build-r22-9907', 'out-build-r22-9907', 'tmp-build-r22-9907')


def r23_raw(reference):
    """Read the actual full historical body under its original complete F9."""
    r20_guard_admission()
    expected = ADMISSION22.reference(reference)
    path = Path(expected['path'])
    need(path.resolve() == path and expected['bytes'] <= 1024 * 1024,
         'canonical bounded R23 historical raw input')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = f9(os.fstat(fd))
        need(before == expected['identity'] and stat.S_ISREG(before[2]) and before[5] == 1,
             'same complete original raw input identity')
        with os.fdopen(os.dup(fd), 'rb') as stream:
            body = stream.read(expected['bytes'] + 1)
        need(len(body) == expected['bytes']
             and hashlib.sha256(body).hexdigest() == expected['sha256']
             and before == f9(os.fstat(fd)) == f9(path.lstat()),
             'whole raw input content and held/path identity bookends')
        r20_guard_admission()
        return {'reference': expected, 'raw': body}
    finally:
        os.close(fd)


def r23_current_baseline():
    r22_current_baseline()
    manifest = digest(SOURCE / '.droidloom-source-manifest.json')
    locks = []
    for original, (path, inode) in zip(ADMISSION22.LOCKS, LOCK_PINS):
        check_lock(path, inode)
        actual = r23_raw(original)
        row = dict(actual['reference'])
        row['body_hex'] = actual['raw'].hex()
        locks.append(row)
    return {'manifest': manifest, 'locks': locks}


def r23_failure_inputs():
    inputs = {name: r23_raw(reference) for name, reference in R23['r22_inputs'].items()}
    inputs['preparation_outputs'] = {
        client['session_id']: r23_raw(client['stdout']) for client in R22['preparation_clients']}
    return PREBUILD22.validate_r22_prebuild(inputs, r23_current_baseline())


def r23_absent_predecessor_roots():
    """Observe only the never-created R22 roots, through their held parent."""
    need(ROOT.resolve() == ROOT, 'original vendor root has no aliases')
    fd = os.open(ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = f9(os.fstat(fd))
        need(stat.S_ISDIR(before[2]) and before[:5] == R23['root_authority']
             and before[3] == before[4] == 1000 and not before[2] & 0o022,
             'same original owner-controlled vendor parent directory')
        for name in R23_UNMATERIALIZED_ROOTS:
            try:
                os.stat(name, dir_fd=fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise RuntimeError('R22 root was materialized or substituted: ' + name)
        need(before == f9(os.fstat(fd)) == f9(ROOT.lstat()),
             'held original parent unchanged across all three no-follow absence checks')
        return {'parent': str(ROOT), 'parent_identity': before,
            'absent_direct_children': list(R23_UNMATERIALIZED_ROOTS),
            'unmaterialized_planned_lock': str(R23_UNMATERIALIZED_LOCK),
            'actual_historical_input_removed': False}
    finally:
        os.close(fd)


def r23_validate_controls():
    result = r20_json(R23['prebuild_controls'])
    need(result['schema'] == 'p4-r23-actual-r22-prebuild-admission-controls-v1'
         and result['passed'] is True and result['actual_positive_cases'] == 1
         and result['actual_failure_preserved'] is True and len(result['negative_cases']) == 27
         and result['host_inputs_read_from_actual_files'] is True
         and result['host_metadata_observation_only'] is True
         and result['fresh_live_unit_retirement_tested'] is False
         and result['source_locks_acquired'] is False
         and result['successor_resource_admission_tested'] is False
         and all(result[key] == 0 for key in ('children_started', 'source_mutations', 'Android_builds', 'Android_starts'))
         and result['runtime_qualified'] is result['production_ready'] is False,
         'actual pure prebuild controls preserve their source-only limits')
    need((result['module']['bytes'], result['module']['sha256'])
         == (R23['prebuild_helper']['bytes'], R23['prebuild_helper']['sha256']),
         'same full pure helper source as the actual control run')
    for reference in R23['source_inputs']:
        r20_check(reference)
    return {'control_receipt': R23['prebuild_controls'], 'actual_positive_cases': 1,
            'negative_cases': 27, 'runtime_qualified': False, 'production_ready': False}


def r23_bootstrap():
    global R23, PREBUILD22, REPO, CONTROL, OUT, TMP, SELF, UNIT, RECOVERY_UNIT, LOCK
    need(type(R23_CONTRACT_PIN) is tuple and len(R23_CONTRACT_PIN) == 2
         and type(R23_CONTRACT_PIN[0]) is int and R23_CONTRACT_PIN[0] > 0
         and type(R23_CONTRACT_PIN[1]) is str and len(R23_CONTRACT_PIN[1]) == 64,
         'R23 successor is not frozen from the actual R22 failure')
    contract_ref = digest(R23_CONTRACT_PATH)
    need((contract_ref['bytes'], contract_ref['sha256']) == R23_CONTRACT_PIN,
         'exact frozen R23 continuation contract')
    R23 = r20_json(contract_ref)
    need(R23['schema'] == 'p4-vendor-r23-prebuild-continuation-contract-v1'
         and R23['operational_inputs_frozen'] is True
         and R23['current_source'] == R22['current_source']
         and R23['baseline'] == R22['baseline']
         and R23['current_binaries'] == R22['current_binaries']
         and R23['runtime_qualified'] is R23['production_ready'] is False,
         'same actually qualified source, release and unchanged source baseline')
    need(set(R23['r22_inputs']) == {'worker', 'outer', 'contract', 'bundle', 'terminal', 'resource', 'serialized'}
         and r20_json(R23['r22_inputs']['contract']) == R22,
         'the exact complete R22 historical operational contract is retained')
    r20_check(R23['prebuild_helper'])
    PREBUILD22 = r20_module('p4_r23_actual_r22_prebuild', R23['prebuild_helper'])
    failure = r23_failure_inputs()
    need(failure['actual_R22_prebuild_failure_consumed'] is True
         and failure['original_status_children_reaped'] == 132
         and failure['R22_uncreated_producer_lock_adopted'] is False,
         'complete actual no-build/no-recovery R22 refusal before path transition')
    absence = r23_absent_predecessor_roots()
    need(LOCK == R23_UNMATERIALIZED_LOCK
         and R23_R22_PINS[LOCK] == (400720, TRANSITION22.NEW_LOCK_SHA)
         and R23['unmaterialized_R22_plan'] == {
             'lock_path': str(LOCK), 'lock_bytes': 400720, 'lock_sha256': TRANSITION22.NEW_LOCK_SHA,
             'absent_roots': list(R23_UNMATERIALIZED_ROOTS)},
         'only the original never-created planned producer lock is reclassified')
    # This exact planned path has no file, inode, body or build phase. Retain
    # the declaration and its full absence evidence, but never fabricate it as
    # an existing historical input. Every actual R22 input remains in PINS.
    del PINS[R23_UNMATERIALIZED_LOCK]
    REPO = ROOT / 'producer-build-r23-9907'
    CONTROL = ROOT / 'control/vendor-build-20261120-9907-r23/actual'
    OUT = ROOT / 'out-build-r23-9907'; TMP = ROOT / 'tmp-build-r23-9907'
    SELF = CONTROL.parent / 'source.py'
    UNIT = 'p4-cp3a-vendor-20261120-9907-r23'; RECOVERY_UNIT = UNIT + '-recovery'
    LOCK = REPO / 'android/manifest/production-full-apex-tests-source-lock.json'
    additions = [contract_ref, R23['prebuild_helper'], R23['prebuild_controls'],
        *R23['r22_inputs'].values(), *R23['source_inputs'],
        *[client['stdout'] for client in R23['preparation_clients']]]
    for reference in additions:
        actual = r20_check(reference)
        path = Path(actual['path']); pin = (actual['bytes'], actual['sha256'])
        need(path not in PINS or PINS[path] == pin, 'no historical actual R22 pin replacement')
        PINS[path] = pin
    need(LOCK not in PINS, 'fresh R23 planned producer lock')
    PINS[LOCK] = (400720, TRANSITION22.NEW_LOCK_SHA)
    need(all(PINS[path] == pin for path, pin in R23_R22_PINS.items()
             if path != R23_UNMATERIALIZED_LOCK)
         and set(R23_R22_PINS) - set(PINS) == {R23_UNMATERIALIZED_LOCK},
         'every actual historical pin retained; only proved unmaterialized declaration changes')
    OBS.update(schema='p4-cp3a-normal-vendor-build-r23-v1',
        actual_R22_prebuild_failure=failure, actual_unmaterialized_R22_plan=absence,
        actual_R22_source_and_release_reused_without_runtime_credit=True,
        R22_failure_record_replaced=False)


def r23_successor_extra_admission():
    # Called inside the original R22 function's try/finally. No new deadline
    # is created: every old and new check uses that one absolute 150s bound.
    need(R20_ADMISSION_DEADLINE is not None, 'original admission owns the deadline')
    original_deadline = R20_ADMISSION_DEADLINE
    r20_guard_admission()
    failure = r23_failure_inputs()
    absence = r23_absent_predecessor_roots()
    controls = r23_validate_controls()
    targets = R23['additional_live_retirement_targets']
    need(targets == [
        {'scope': 'user', 'unit': 'p4-cp3a-vendor-supervisor-20261120-9907-r22.service', 'pids': []},
        {'scope': 'user', 'unit': 'p4-cp3a-vendor-20261120-9907-r22.service', 'pids': []},
        {'scope': 'user', 'unit': 'p4-cp3a-vendor-20261120-9907-r22-recovery.service', 'pids': []}],
        'three exact R22 units must receive fresh original live retirement checks')
    observed = [r20_live_retired(row['unit'], row['pids'], row['scope']) for row in targets]
    clients = R23['preparation_clients']
    need(len(clients) >= 3 and len({row['session_id'] for row in clients}) == len(clients),
         'complete original R22 final freeze, supervisor and subsequent preparation clients')
    fixed = {
        'r22-freeze-r2': ('dpty-f70ee7be8e5157c61d3f7d090147804e1da433c8e29decdc44d543452b8ac077', 0),
        'r22-original-supervisor': ('dpty-a2dd1fc97b891e1fc369ec9b2c8fec978a93d6a288e4d21cd5c1209cbdfe0b1c', 1),
        'r22-prebuild-input-capture': ('dpty-807b1e5927cac379fbeb56ad26e3c8fb8d54b64633bb0ab39edee88ca111a91a', 0)}
    need(len({row['name'] for row in clients}) == len(clients)
         and fixed.items() <= {row['name']: (row['session_id'], row['expected_exit_code']) for row in clients}.items(),
         'all actual successful and failed predecessor clients retain exact outcomes')
    for client in clients:
        r20_validate_client(client, client['stdout'], client['expected_exit_code'])
    r23_current_baseline()
    need(R20_ADMISSION_DEADLINE == original_deadline, 'no extension or replacement of the admission deadline')
    r20_guard_admission()
    return {'actual_R22_prebuild_failure_and_original_status_retirement': failure,
        'actual_unmaterialized_R22_plan': absence, 'current_prebuild_controls': controls,
        'additional_R22_live_retirement_observations': observed,
        'all_actual_R22_input_pins_preserved': True, 'resource_admission_reused': False,
        'same_total_admission_budget_seconds': 150, 'observed_ns': time.time_ns()}


# r20_recovery_retirement is copied below with only its current-generation
# schema literal changed to R23. No historical R22 receipt is relabeled.


def verify_serialized_retirement():
    global R20_ADMISSION_DEADLINE
    need(R20_ADMISSION_DEADLINE is None, 'single non-reentrant R22 evidence admission')
    R20_ADMISSION_DEADLINE = time.monotonic() + 150
    try:
        # These two validators keep their original historical globals and F9 pins.
        # Their immutable predecessor reports are never treated as live source state.
        historical_failure = r21_validate_prebuild_failure()
        refs = R20['R19']
        r20_check(refs['worker'])
        historical_values = {k: r20_json(refs[k]) for k in ('bundle', 'outer', 'build', 'recovery', 'retirement')}
        historical_recovery = ADMISSION20.validate_predecessor(historical_values, refs)
        legacy = r20_json(R20['historical_83'])
        need(len(legacy['paths']) == 83 and len({x['path'] for x in legacy['paths']}) == 83,
             'whole unchanged original 83-input roster')
        live_transition = {ADMISSION20.MANIFEST['path'], *[x['path'] for x in ADMISSION20.LOCKS]}
        checked = []
        for item in legacy['paths']:
            if item['path'] in live_transition:
                continue
            got = digest(Path(item['path']))
            need(item['expected_pins'] and all(
                got['bytes'] == x['bytes'] and got['sha256'] == x['sha256']
                and ('f9' not in x or got['identity'] == x['f9']) for x in item['expected_pins']),
                'immutable original historical input: ' + item['path'])
            checked.append(got); r20_guard_admission()
        need(len(checked) == 79, 'only four explicitly bound current identities may transition')
        for path, expected in R20_HISTORICAL_PINS.items():
            got = digest(path)
            need((got['bytes'], got['sha256']) == expected, 'original R19 fixed dependency retained')
            r20_guard_admission()
        for name, item in historical_values['retirement']['clients'].items():
            r20_validate_client(item, item['stdout'], 1 if name == 'original' else 0)
        predecessor = R22['predecessor']
        for reference in predecessor.values():
            r20_check(reference)
        values = {k: r20_json(predecessor[k]) for k in ('contract', 'bundle', 'terminal', 'build', 'recovery')}
        need(values['contract'] == R20, 'exact old R21 operational contract retained')
        previous = ADMISSION22.validate_r21_predecessor(values, predecessor, R22['baseline'])
        for document in (values['build'], values['recovery']):
            for command in document['commands']:
                for channel in ('stdout', 'stderr'):
                    r20_check(command[channel])
        ci = r20_json(R22['release_ci'])
        release = ADMISSION22.validate_current_release(ci, R22['current_binaries'], R22['ci_provenance'])
        for item in R22['current_binaries'].values():
            got = r20_check(item)
            with Path(got['path']).open('rb') as stream:
                header = stream.read(20)
            need(header[:6] == b'\x7fELF\x02\x01' and header[18:20] == b'\x3e\x00',
                 'actual current normal x86_64 ELF header')
            need(digest(Path(got['path'])) == got, 'ELF unchanged across actual header read')
        host = r20_json(R22['host_direct_abi'])
        need(host['schema'] == 'p4-current19-static-direct-import-compatibility-v1'
             and host['host'] == 'ai395' and host['source'] == ADMISSION22.CURRENT
             and host['binary_count'] == 19 and host['passed_direct_symbols_only'] is True
             and host['dynamic_transitive_loading_tested'] is False
             and host['runtime_qualified'] is False and host['production_ready'] is False
             and len(host['binaries']) == 19 and len({x['binary'] for x in host['binaries']}) == 19
             and {x['binary']: x['sha256'] for x in host['binaries']}
                == {name: x['sha256'] for name, x in R22['current_binaries'].items()}
             and all(x['missing_strong'] == [] for x in host['binaries']),
             'actual current direct host symbol evidence, retaining its limits')
        for item in ADMISSION22.validate_host_abi_custody(host, R22['host_abi_inputs']):
            r20_check(item)
        controls = r22_validate_controls()
        targets = R22['live_retirement_targets']
        need(len(targets) == len({(x['scope'], x['unit']) for x in targets})
             and targets[:len(R20['live_retirement_targets'])] == R20['live_retirement_targets'],
             'all original known live retirement targets retained without substitution')
        required = {
            ('user', 'p4-cp3a-vendor-supervisor-20261120-9907-r21.service'),
            ('user', 'p4-cp3a-vendor-20261120-9907-r21.service'),
            ('user', 'p4-cp3a-vendor-20261120-9907-r21-recovery.service'),
            ('user', 'p4-r22-apex-providers-git-fixture-20261120-3b9d-r1.service'),
            ('user', 'p4-r22-apex-providers-git-fixture-20261120-3b9d-r2.service')}
        need(required <= {(x['scope'], x['unit']) for x in targets},
             'actual R21 and both isolated provider fixture units explicitly retired')
        actual_units = [r20_live_retired(x['unit'], x.get('pids', []), x['scope']) for x in targets]
        for item in R20['preparation_clients'] + R22['preparation_clients']:
            r20_validate_client(item, item['stdout'], item.get('expected_exit_code', 0))
        r22_current_baseline()
        successor = r23_successor_extra_admission()
        return {'actual_R22_continuation': successor, 'schema': 'p4-serialized-heavy-build-resource-plan-v1',
            'original_minimum_memory_gib': 42, 'vendor_memory_max_gib': 24,
            'simultaneous_other_heavy_compilers': 0, 'bounded_light_scopes_max_gib': 3.25,
            'host_reserve_gib': 12, 'unallocated_margin_within_minimum_gib': 2.75,
            'actual_R19_failed_build_and_complete_original_recovery': historical_recovery,
            'actual_R20_prebuild_failure_and_independent_retirement': historical_failure,
            'actual_R21_Soong_failure_and_complete_original_recovery': previous,
            'new_actual_current_release': release, 'historical_83_inputs_preserved': True,
            'historical_79_immutable_inputs_rechecked': checked, 'actual_units': actual_units,
            'new_four_provider_controls': controls, 'new_provider_materialization_credit': False,
            'resource_admission_reused': False, 'production_ready': False, 'runtime_qualified': False,
            'observed_ns': time.time_ns()}
    finally:
        R20_ADMISSION_DEADLINE = None


def r20_recovery_retirement():
    owner = verify_outer()
    record, _ = read_source_json(CONTROL / 'build-retirement-before-recovery.json')
    row = record['build_phase']
    need(record['schema'] == 'p4-r23-original-build-retirement-before-recovery-v1'
         and record['generation'] == owner['generation'] and record['serial_lock'] == owner['serial_lock']
         and record['worker_sha256'] == digest(SELF)['sha256']
         and row['mode'] == 'build' and row['unit'] == UNIT + '.service'
         and row['service_retired'] is True and row['client']['actual_reaped'] is True
         and row['client']['original_pidfd_held_until_reaped'] is True
         and row['late_start_unresolved'] is False
         and all(x['actual_reaped'] is True and x['original_pidfd_held_until_reaped'] is True
                 for x in record['original_outer_children']),
         'original outer retains actual complete build retirement before recovery')
    OBS['actual_build_retirement_before_recovery'] = r20_live_retired(UNIT + '.service')
    need(not RUNNER.owned_children(), 'no inherited unreaped build worker')
    resource_guard(True)


r23_bootstrap()

if __name__ == '__main__':
    code = 1
    mode = sys.argv[1] if len(sys.argv) == 2 else ''
    try:
        need(mode in ('build', 'recover'), 'one fixed controller mode required')
        if mode == 'outer':
            code = outer()
        else:
            build() if mode == 'build' else recover()
            code = 0
    except BaseException as error:
        OBS['errors'].append({'error': repr(error), 'traceback': traceback.format_exc()})
        OBS['finished_ns'] = time.time_ns()
        if CONTROL.is_dir():
            save({'outer': 'outer-error.json', 'recover': 'recovery-observation.json'}.get(mode, 'build-observation.json'))
        print(json.dumps({'stage': mode + '-failed', 'error': repr(error)}), flush=True)
    sys.exit(code)
