"""Typed current-baseline coordinator utilities. Importing performs no operations.
Fresh app workflows must use these new names and new recorder init options.
Historical activation receipts are lineage only; runtime admission is separate.
"""
import hashlib,json,os,signal,stat,subprocess,time,types
from pathlib import Path
HERE=Path(__file__).resolve().parent
BINDING={'schema': 'pocket4-successor-derived-recorder-binding-v1', 'package': 'com.lianjia.beike', 'component': 'com.lianjia.beike/com.lianjia.activity.MainActivity', 'uid': 10143, 'user': 0, 'runtime_guard': {'path': '/home/alex/work/pocket4-cell-successor-repaired-r2-20261106-execute-01/current_baseline_guard.py', 'bytes': 3213, 'sha256': 'd84df98d55352ef9ae66753ee15f3746d9d9a64c35fddf392a08f10ba4105cb3'}, 'baseline': {'path': '/home/alex/work/pocket4-cell-successor-repaired-r2-20261106-execute-01/baseline.private.json', 'sha256': '7c52723c372b9f486067456e720709ef401bcebe1a7aad158f6b8c099f67fcc8', 'bytes': 44041}, 'qualification': {'path': '/home/alex/work/pocket4-cell-successor-repaired-r2-20261106-execute-01/qualification.private.json', 'sha256': '4bdfe7dd1e275bc4727f37c630dc2498b3dc31c528b03a4028e42c1cf8fc4fc6', 'bytes': 1587}, 'runtime_epoch_sha256': 'a7c7091a9e57eb6b373aa8a9225bb2f17b4ec0f1248679b56aaadc78eb0faca9', 'framework_epoch': {'binding': {'boot_id': '981ff371-cd72-4f81-9be3-a862111afdb1', 'processes': {'init': {'cgroup': ['0::/system.slice/droidloomd.service'], 'cmdline': ['/init', 'second_stage'], 'executable': '/system/bin/init', 'host_pid': 3268779, 'namespace_pids': [3268779, 1], 'namespaces': {'mnt': 'mnt:[4026533280]', 'pid': 'pid:[4026533285]'}, 'parent_host_pid': 3268775, 'start_ticks': 99615082, 'uids': [0, 0, 0, 0]}, 'surfaceflinger': {'cgroup': ['0::/system.slice/droidloomd.service/system/uid_1000/pid_661'], 'cmdline': ['/system/bin/surfaceflinger'], 'executable': '/system/bin/surfaceflinger', 'host_pid': 3270350, 'namespace_pids': [3270350, 661], 'namespaces': {'mnt': 'mnt:[4026533280]', 'pid': 'pid:[4026533285]'}, 'parent_host_pid': 3268779, 'start_ticks': 99615245, 'uids': [1000, 1000, 1000, 1000]}, 'system_server': {'cgroup': ['0::/system.slice/droidloomd.service/system/uid_1000/pid_808'], 'cmdline': ['system_server'], 'executable': '/system/bin/app_process64', 'host_pid': 3270611, 'namespace_pids': [3270611, 808], 'namespaces': {'mnt': 'mnt:[4026533719]', 'pid': 'pid:[4026533285]'}, 'parent_host_pid': 3270325, 'start_ticks': 99615342, 'uids': [1000, 1000, 1000, 1000]}, 'zygote64': {'cgroup': ['0::/system.slice/droidloomd.service/system/uid_0/pid_638'], 'cmdline': ['zygote64'], 'executable': '/system/bin/app_process64', 'host_pid': 3270325, 'namespace_pids': [3270325, 638], 'namespaces': {'mnt': 'mnt:[4026533718]', 'pid': 'pid:[4026533285]'}, 'parent_host_pid': 3268779, 'start_ticks': 99615242, 'uids': [0, 0, 0, 0]}}}, 'collected_monotonic_ns': 996169557306983, 'schema': 'pocket4-framework-epoch-v1', 'sha256': '7d927812392d30ab8cca43da87c0785e24695ca724da93b3b465122502b8045c'}, 'app_scope': {'bytes': 2779, 'path': '/home/alex/work/pocket4-beike-successor-qa-input-20261106-b34f158f88bbebf112840fd88df25d03/beike-and-existing-actions.private.json', 'sha256': '2f3ed55a035e64401189cd2afbaded2414c7b0b9a3c641a82308a1c68b96a8eb'}, 'packages': {'com.lianjia.beike': 10143, 'local.pocket4.actions.v2': 10125}, 'app_directories': {'/data/user/0/com.lianjia.beike': {'device': 1811, 'inode': 152786, 'uid': 10143, 'gid': 10143}, '/data/user_de/0/com.lianjia.beike': {'device': 1811, 'inode': 152789, 'uid': 10143, 'gid': 10143}, '/data/user/0/local.pocket4.actions.v2': {'device': 1811, 'inode': 142156, 'uid': 10125, 'gid': 10125}, '/data/user_de/0/local.pocket4.actions.v2': {'device': 1811, 'inode': 142227, 'uid': 10125, 'gid': 10125}}, 'held_init_identity': {'cgroup': '0::/system.slice/droidloomd.service\n', 'exe': '/system/bin/init', 'ns': {'cgroup': 'cgroup:[4026533387]', 'ipc': 'ipc:[4026533284]', 'mnt': 'mnt:[4026533280]', 'net': 'net:[4026533041]', 'pid': 'pid:[4026533285]', 'uts': 'uts:[4026533281]'}, 'nspid': ['3268779', '1'], 'pid': 3268779, 'ppid': 3268775, 'start': '99615082', 'uid': ['0', '0', '0', '0']}, 'classpath_values': {'BOOTCLASSPATH': '/apex/com.android.art/javalib/core-oj.jar:/apex/com.android.art/javalib/core-libart.jar:/apex/com.android.art/javalib/okhttp.jar:/apex/com.android.art/javalib/bouncycastle.jar:/apex/com.android.art/javalib/apache-xml.jar:/system/framework/framework.jar:/system/framework/framework-graphics.jar:/system/framework/framework-location.jar:/system/framework/ext.jar:/system/framework/telephony-common.jar:/system/framework/voip-common.jar:/system/framework/ims-common.jar:/system/framework/framework-ondeviceintelligence-platform.jar:/apex/com.android.i18n/javalib/core-icu4j.jar:/apex/com.android.adservices/javalib/framework-adservices.jar:/apex/com.android.adservices/javalib/framework-sdksandbox.jar:/apex/com.android.appsearch/javalib/framework-appsearch.jar:/apex/com.android.bt/javalib/framework-bluetooth.jar:/apex/com.android.configinfrastructure/javalib/framework-configinfrastructure.jar:/apex/com.android.conscrypt/javalib/conscrypt.jar:/apex/com.android.conscrypt/javalib/framework-conscrypt-nsc.jar:/apex/com.android.crashrecovery/javalib/framework-crashrecovery.jar:/apex/com.android.devicelock/javalib/framework-devicelock.jar:/apex/com.android.healthfitness/javalib/framework-healthfitness.jar:/apex/com.android.ipsec/javalib/android.net.ipsec.ike.jar:/apex/com.android.media/javalib/updatable-media.jar:/apex/com.android.mediaprovider/javalib/framework-mediaprovider.jar:/apex/com.android.mediaprovider/javalib/framework-pdf.jar:/apex/com.android.mediaprovider/javalib/framework-pdf-v.jar:/apex/com.android.mediaprovider/javalib/framework-photopicker.jar:/apex/com.android.nfcservices/javalib/framework-nfc.jar:/apex/com.android.npumanager/javalib/framework-npumanager.jar:/apex/com.android.ondevicepersonalization/javalib/framework-ondevicepersonalization.jar:/apex/com.android.os.statsd/javalib/framework-statsd.jar:/apex/com.android.permission/javalib/framework-permission.jar:/apex/com.android.permission/javalib/framework-permission-s.jar:/apex/com.android.profiling/javalib/framework-anomaly-detector.jar:/apex/com.android.profiling/javalib/framework-profiling.jar:/apex/com.android.scheduling/javalib/framework-scheduling.jar:/apex/com.android.sdkext/javalib/framework-sdkextensions.jar:/apex/com.android.telephonycore/javalib/framework-telecom.jar:/apex/com.android.telephonycore/javalib/framework-telephony.jar:/apex/com.android.tethering/javalib/framework-connectivity.jar:/apex/com.android.tethering/javalib/framework-connectivity-b.jar:/apex/com.android.tethering/javalib/framework-connectivity-t.jar:/apex/com.android.tethering/javalib/framework-tethering.jar:/apex/com.android.uprobestats/javalib/framework-uprobestats.jar:/apex/com.android.uwb/javalib/framework-ranging.jar:/apex/com.android.uwb/javalib/framework-uwb.jar:/apex/com.android.virt/javalib/framework-virtualization.jar:/apex/com.android.webapp/javalib/framework-webapp.jar:/apex/com.android.wifi/javalib/framework-wifi.jar', 'DEX2OATBOOTCLASSPATH': '/apex/com.android.art/javalib/core-oj.jar:/apex/com.android.art/javalib/core-libart.jar:/apex/com.android.art/javalib/okhttp.jar:/apex/com.android.art/javalib/bouncycastle.jar:/apex/com.android.art/javalib/apache-xml.jar:/system/framework/framework.jar:/system/framework/framework-graphics.jar:/system/framework/framework-location.jar:/system/framework/ext.jar:/system/framework/telephony-common.jar:/system/framework/voip-common.jar:/system/framework/ims-common.jar:/system/framework/framework-ondeviceintelligence-platform.jar:/apex/com.android.i18n/javalib/core-icu4j.jar'}, 'status': {'host_pid': 3268774}, 'native_cli': {'path': '/usr/bin/droidloomctl', 'bytes': 1705648, 'sha256': 'f81e0223f6b256584d07a5e8fbc72f3f4c764ab53a88469b45b587c101e12c79'}, 'launcher_catalog_reference': {'path': '/home/alex/work/pocket4-beike-successor-qa-input-20261106-b34f158f88bbebf112840fd88df25d03/native-catalog.stdout.raw.json', 'sha256': '1352cb70367b09af255283dcbaecd8680c4d6bad662cf6432d01e2f2d6cabf54', 'bytes': 10114}, 'qa_input_reference': {'path': '/home/alex/work/pocket4-beike-successor-qa-input-20261106-b34f158f88bbebf112840fd88df25d03/qa-build-input.private.json', 'sha256': 'c393a18171684b84e4fc15588bcddfea1f14e96f1a5bb9bb2802377c598f2184', 'bytes': 6718}, 'launcher_resolver_reenumerated_by_generator': False, 'public_text': '北京', 'allowed_operations': ['state', 'inspect', 'click', 'set_text'], 'generation_nonce': 'b34f158f88bbebf112840fd88df25d03', 'old_Bili_unknown_reconciled': False, 'Bili_Accept_authorized_in_Main': False, 'Meituan_location_grant_authorized': False, 'security_bypass_authorized': False, 'UI_admitted': False, 'production_ready': False}
SOURCE_CONTRACT_SHA='0cbb8c79b494a529e7cb7fe0ce99eec444103ae7207a02a768dbc76d3bb3cbc3'
ENV={'PATH':'/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin','LANG':'C.UTF-8'}

def require(ok, message):
    if not ok:
        raise RuntimeError(message)

def digest(data):
    return hashlib.sha256(data).hexdigest()

def read(path, maximum=1024 * 1024, expected=None):
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        first = os.fstat(fd)
        require(stat.S_ISREG(first.st_mode) and first.st_nlink == 1 and first.st_size <= maximum,
                'bounded single-link regular file required: ' + str(path))
        data = bytearray()
        while len(data) <= maximum:
            block = os.read(fd, min(65536, maximum + 1 - len(data)))
            if not block:
                break
            data.extend(block)
        last = os.fstat(fd)
        fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
        require(all(getattr(first, k) == getattr(last, k) for k in fields) and len(data) == first.st_size,
                'input changed or exceeded bound')
        if expected is not None:
            require(digest(data) == expected, 'input hash changed: ' + str(path))
        return bytes(data)
    finally:
        os.close(fd)

def write_new(path, value, mode=0o600):
    data = value if isinstance(value, bytes) else (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW, mode)
    try:
        with os.fdopen(fd, 'wb', closefd=False) as stream:
            stream.write(data)
            stream.flush()
            os.fsync(fd)
    finally:
        os.close(fd)
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    return {'path': str(path), 'bytes': len(data), 'sha256': digest(data)}

def module(raw, filename, name):
    value = types.ModuleType(name)
    value.__file__ = str(filename)
    exec(compile(raw, str(filename), 'exec'), value.__dict__)
    return value

def run_cli(name, argv, timeout, evidence, guard):
    guard()
    write_new(evidence / (name + '.intent.json'), {'argv': argv, 'timeout_seconds': timeout,
        'separate_process': True, 'automatic_retry': False})
    observed = {'name': name, 'argv': argv, 'spawned': False, 'joined': False, 'timed_out': False,
                'returncode': None, 'secondary_errors': [], 'Main_before': True}
    process = pidfd = None
    primary = None
    streams = []
    try:
        for suffix in ('.stdout', '.stderr'):
            streams.append(open(evidence / (name + suffix), 'xb'))
        process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=streams[0], stderr=streams[1],
                                   env=ENV, close_fds=True)
        observed.update(spawned=True, owned_child_pid=process.pid)
        pidfd = os.pidfd_open(process.pid, 0)
        try:
            observed['returncode'] = process.wait(timeout=timeout)
            observed['joined'] = True
        except BaseException as error:
            observed['timed_out'] = isinstance(error, subprocess.TimeoutExpired)
            raise
    except BaseException as error:
        primary = error
        observed['primary_error'] = {'type': type(error).__name__, 'message': str(error)}
    finally:
        if process is not None and not observed['joined']:
            try:
                if process.poll() is None:
                    if pidfd is not None:
                        signal.pidfd_send_signal(pidfd, signal.SIGKILL)
                    else:
                        # Exact Popen child, no intervening wait/reaper; no ambient PID selection.
                        process.kill()
                observed['returncode'] = process.wait(timeout=6)
                observed['joined'] = True
            except BaseException as error:
                observed['secondary_errors'].append({'stage': 'owned-child-retirement', 'error': repr(error)})
        if pidfd is not None:
            try:
                os.close(pidfd)
            except BaseException as error:
                observed['secondary_errors'].append({'stage': 'owned-pidfd-close', 'error': repr(error)})
        for stream in streams:
            try:
                stream.flush()
                os.fsync(stream.fileno())
            except BaseException as error:
                observed['secondary_errors'].append({'stage': 'output-sync', 'error': repr(error)})
            try:
                stream.close()
            except BaseException as error:
                observed['secondary_errors'].append({'stage': 'output-close', 'error': repr(error)})
        try:
            observed['Main_after'] = guard()
        except BaseException as error:
            observed['secondary_errors'].append({'stage': 'Main-after', 'error': repr(error)})
        for suffix in ('.stdout', '.stderr'):
            try:
                data = read(evidence / (name + suffix))
                observed[suffix[1:]] = {'bytes': len(data), 'sha256': digest(data)}
            except BaseException as error:
                observed['secondary_errors'].append({'stage': 'output-read', 'error': repr(error)})
        try:
            write_new(evidence / (name + '.result.json'), observed)
        except BaseException as error:
            observed['secondary_errors'].append({'stage': 'phase-result-write', 'error': repr(error)})
            if primary is None:
                primary = error
            else:
                primary.add_note('phase result write: ' + repr(error))
    if primary is not None:
        raise primary
    require(observed['joined'] and observed['returncode'] == 0 and not observed['secondary_errors'],
            name + ' did not complete exactly once with a preserved Main fence')
    return json.loads(read(evidence / (name + '.stdout')))

def guard_module():
    source=module(read(HERE/'source_contract.py',expected=SOURCE_CONTRACT_SHA),HERE/'source_contract.py','successor_coordinator_source')
    return source.load_guard()
def current_baseline():
    return guard_module().current_baseline()
def main_guard(baseline=None,epoch=None):
    return guard_module().current_guard(baseline,action_attempted=False)
